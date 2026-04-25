"""
Profiling Engine for database metadata discovery.
Connects to source database and reflects schemas to generate profiling reports.
"""

from typing import Dict, List, Any, Optional
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, text
from sqlalchemy.exc import SQLAlchemyError
import json
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class Profiler:
    """Database profiler for schema discovery and metadata extraction."""
    
    def __init__(self, connection_string: str):
        """
        Initialize the profiler with a database connection string.
        
        Args:
            connection_string: SQLAlchemy compatible connection string
        """
        self.connection_string = connection_string
        self.engine = None
        self.metadata = MetaData()
        self.connection = None
        
    def connect(self) -> bool:
        """
        Establish connection to the database.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            self.engine = create_engine(self.connection_string)
            self.connection = self.engine.connect()
            self.metadata.reflect(bind=self.engine)
            logger.info(f"Successfully connected to database: {self.connection_string}")
            return True
        except SQLAlchemyError as e:
            logger.error(f"Failed to connect to database: {e}")
            return False
    
    def disconnect(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
        if self.engine:
            self.engine.dispose()
        logger.info("Database connection closed")
    
    def get_table_names(self) -> List[str]:
        """
        Get list of all table names in the database.
        
        Returns:
            List[str]: List of table names
        """
        if not self.metadata.tables:
            return []
        return list(self.metadata.tables.keys())
    
    def get_table_info(self, table_name: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific table.
        
        Args:
            table_name: Name of the table to inspect
            
        Returns:
            Dict containing table information
        """
        if table_name not in self.metadata.tables:
            return {}
        
        table = self.metadata.tables[table_name]
        
        # Get column information
        columns = []
        for column in table.columns:
            col_info = {
                "name": column.name,
                "type": str(column.type),
                "nullable": column.nullable,
                "primary_key": column.primary_key,
                "foreign_keys": [fk.target_fullname for fk in column.foreign_keys]
            }
            columns.append(col_info)
        
        # Get row count (approximate for large tables)
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                row_count = result.scalar()
        except Exception:
            row_count = -1  # Indicates error or unable to get count
        
        # Get primary keys
        primary_keys = [col.name for col in table.primary_key.columns]
        
        # Get foreign keys
        foreign_keys = []
        for fk in table.foreign_keys:
            foreign_keys.append({
                "column": fk.parent.name,
                "references": f"{fk.column.table.name}.{fk.column.name}"
            })
        
        return {
            "name": table_name,
            "row_count": row_count,
            "columns": columns,
            "primary_keys": primary_keys,
            "foreign_keys": foreign_keys
        }
    
    def identify_dangerous_types(self, table_info: Dict[str, Any]) -> List[str]:
        """
        Identify potentially problematic data types (LOBs, BLOBs, etc.).
        
        Args:
            table_info: Table information dictionary
            
        Returns:
            List of column names with dangerous types
        """
        dangerous_types = []
        dangerous_type_keywords = ['LOB', 'BLOB', 'CLOB', 'TEXT', 'NTEXT', 'IMAGE', 'XML', 'JSON']
        
        for column in table_info.get("columns", []):
            col_type = column["type"].upper()
            if any(keyword in col_type for keyword in dangerous_type_keywords):
                dangerous_types.append(column["name"])
        
        return dangerous_types
    
    def generate_profile_report(self, output_path: Optional[Path] = None) -> Dict[str, Any]:
        """
        Generate a comprehensive profile report of the database.
        
        Args:
            output_path: Optional path to save the report as JSON
            
        Returns:
            Dict containing the complete profile report
        """
        if not self.engine:
            raise RuntimeError("Not connected to database. Call connect() first.")
        
        report = {
            "database_connection": self.connection_string.split('@')[-1] if '@' in self.connection_string else self.connection_string,
            "tables": [],
            "summary": {
                "total_tables": 0,
                "total_rows": 0,
                "tables_with_lobs": 0
            }
        }
        
        table_names = self.get_table_names()
        report["summary"]["total_tables"] = len(table_names)
        
        for table_name in table_names:
            table_info = self.get_table_info(table_name)
            dangerous_types = self.identify_dangerous_types(table_info)
            
            table_report = {
                "name": table_info["name"],
                "row_count": table_info["row_count"],
                "column_count": len(table_info["columns"]),
                "primary_keys": table_info["primary_keys"],
                "foreign_keys": table_info["foreign_keys"],
                "dangerous_types": dangerous_types,
                "columns": table_info["columns"]
            }
            
            report["tables"].append(table_report)
            
            # Update summary statistics
            if table_info["row_count"] > 0:
                report["summary"]["total_rows"] += table_info["row_count"]
            if dangerous_types:
                report["summary"]["tables_with_lobs"] += 1
        
        # Save report if output path provided
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            logger.info(f"Profile report saved to {output_path}")
        
        return report