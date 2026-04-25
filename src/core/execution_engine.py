"""
Execution Engine for chunked data transfer with parallel workers and checkpointing.
Implements resilient data migration with progress tracking and recovery capabilities.
"""

import sqlite3
import threading
import time
from typing import Dict, List, Any, Optional, Callable, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import SQLAlchemyError
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class CheckpointManager:
    """Manages checkpoints for migration resumability using SQLite."""
    
    def __init__(self, db_path: Path):
        """
        Initialize checkpoint manager.
        
        Args:
            db_path: Path to SQLite database for storing checkpoints
        """
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize the checkpoint database with required tables."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS table_checkpoints (
                    table_name TEXT PRIMARY KEY,
                    last_processed_id INTEGER,
                    total_rows INTEGER,
                    migrated_rows INTEGER,
                    status TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS migration_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    table_name TEXT,
                    chunk_id INTEGER,
                    status TEXT,
                    rows_processed INTEGER,
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
    
    @contextmanager
    def _get_connection(self):
        """Context manager for SQLite connections."""
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()
    
    def get_checkpoint(self, table_name: str) -> Optional[Dict[str, Any]]:
        """
        Get checkpoint for a table.
        
        Args:
            table_name: Name of the table
            
        Returns:
            Dictionary with checkpoint data or None if not found
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT last_processed_id, total_rows, migrated_rows, status FROM table_checkpoints WHERE table_name = ?",
                (table_name,)
            )
            row = cursor.fetchone()
            if row:
                return {
                    "last_processed_id": row[0],
                    "total_rows": row[1],
                    "migrated_rows": row[2],
                    "status": row[3]
                }
            return None
    
    def save_checkpoint(self, table_name: str, last_processed_id: int, 
                       total_rows: int = 0, migrated_rows: int = 0, status: str = "PENDING"):
        """
        Save or update checkpoint for a table.
        
        Args:
            table_name: Name of the table
            last_processed_id: Last processed row ID
            total_rows: Total rows in table
            migrated_rows: Number of rows migrated
            status: Current status (PENDING, SYNCING, VALIDATING, SUCCESS, FAILED)
        """
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO table_checkpoints 
                (table_name, last_processed_id, total_rows, migrated_rows, status, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (table_name, last_processed_id, total_rows, migrated_rows, status))
            conn.commit()
    
    def log_chunk(self, table_name: str, chunk_id: int, status: str, 
                 rows_processed: int = 0, error_message: str = None):
        """
        Log chunk processing details.
        
        Args:
            table_name: Name of the table
            chunk_id: Chunk identifier
            status: Status of chunk processing
            rows_processed: Number of rows processed in chunk
            error_message: Error message if any
        """
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO migration_logs 
                (table_name, chunk_id, status, rows_processed, error_message)
                VALUES (?, ?, ?, ?, ?)
            """, (table_name, chunk_id, status, rows_processed, error_message))
            conn.commit()


class ChunkedReader:
    """Handles chunked reading of database tables using server-side cursors."""
    
    def __init__(self, connection_string: str, batch_size: int = 5000):
        """
        Initialize chunked reader.
        
        Args:
            connection_string: SQLAlchemy connection string
            batch_size: Number of rows per chunk
        """
        self.connection_string = connection_string
        self.batch_size = batch_size
        self.engine = create_engine(connection_string)
    
    def get_table_row_count(self, table_name: str, id_column: str = "id") -> int:
        """
        Get approximate row count for a table.
        
        Args:
            table_name: Name of the table
            id_column: Column to use for counting (preferably indexed)
            
        Returns:
            Approximate row count
        """
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                return result.scalar() or 0
        except SQLAlchemyError as e:
            logger.warning(f"Could not get row count for {table_name}: {e}")
            return 0
    
    def get_max_id(self, table_name: str, id_column: str = "id") -> int:
        """
        Get maximum ID value for a table (for chunking).
        
        Args:
            table_name: Name of the table
            id_column: Column to use for ID-based chunking
            
        Returns:
            Maximum ID value
        """
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(f"SELECT MAX({id_column}) FROM {table_name}"))
                max_id = result.scalar()
                return max_id if max_id is not None else 0
        except SQLAlchemyError as e:
            logger.warning(f"Could not get max ID for {table_name}: {e}")
            return 0
    
    def read_chunk(self, table_name: str, start_id: int, end_id: int, 
                   id_column: str = "id") -> List[Dict[str, Any]]:
        """
        Read a chunk of data from a table based on ID range.
        
        Args:
            table_name: Name of the table
            start_id: Starting ID (inclusive)
            end_id: Ending ID (exclusive)
            id_column: Column to use for chunking
            
        Returns:
            List of dictionaries representing rows
        """
        try:
            with self.engine.connect() as conn:
                query = text(f"""
                    SELECT * FROM {table_name} 
                    WHERE {id_column} >= :start_id AND {id_column} < :end_id
                    ORDER BY {id_column}
                """)
                result = conn.execute(query, {"start_id": start_id, "end_id": end_id})
                
                # Convert to list of dictionaries
                columns = result.keys()
                rows = []
                for row in result:
                    rows.append(dict(zip(columns, row)))
                
                return rows
        except SQLAlchemyError as e:
            logger.error(f"Error reading chunk {start_id}-{end_id} from {table_name}: {e}")
            return []


class DataWriter:
    """Handles writing data to target database using bulk operations."""
    
    def __init__(self, connection_string: str):
        """
        Initialize data writer.
        
        Args:
            connection_string: SQLAlchemy connection string for target database
        """
        self.connection_string = connection_string
        self.engine = create_engine(connection_string)
    
    def write_chunk(self, table_name: str, data: List[Dict[str, Any]]) -> bool:
        """
        Write a chunk of data to the target table.
        
        Args:
            table_name: Name of the target table
            data: List of dictionaries representing rows to insert
            
        Returns:
            True if successful, False otherwise
        """
        if not data:
            return True
            
        try:
            with self.engine.connect() as conn:
                # Insert data using bulk insert
                if data:
                    # Get column names from first row
                    columns = list(data[0].keys())
                    
                    # Build INSERT statement
                    placeholders = ", ".join([":" + col for col in columns])
                    query = text(f"""
                        INSERT INTO {table_name} ({', '.join(columns)})
                        VALUES ({placeholders})
                    """)
                    
                    # Execute bulk insert
                    conn.execute(query, data)
                    conn.commit()
                    
                return True
        except SQLAlchemyError as e:
            logger.error(f"Error writing chunk to {table_name}: {e}")
            return False


class ExecutionEngine:
    """Main execution engine orchestrating chunked reading, parallel processing, and checkpointing."""
    
    def __init__(self, source_connection_string: str, target_connection_string: str,
                 batch_size: int = 5000, parallel_workers: int = 4,
                 checkpoint_db_path: Path = Path("state.db")):
        """
        Initialize execution engine.
        
        Args:
            source_connection_string: Source database connection string
            target_connection_string: Target database connection string
            batch_size: Number of rows per chunk
            parallel_workers: Number of parallel workers
            checkpoint_db_path: Path to SQLite checkpoint database
        """
        self.source_connection_string = source_connection_string
        self.target_connection_string = target_connection_string
        self.batch_size = batch_size
        self.parallel_workers = parallel_workers
        
        self.checkpoint_manager = CheckpointManager(checkpoint_db_path)
        self.chunked_reader = ChunkedReader(source_connection_string, batch_size)
        self.data_writer = DataWriter(target_connection_string)
        
        # Thread lock for shared resources
        self._lock = threading.Lock()
    
    def migrate_table(self, table_name: str, id_column: str = "id",
                     progress_callback: Optional[Callable] = None) -> bool:
        """
        Migrate a single table using chunked reading and parallel workers.
        
        Args:
            table_name: Name of the table to migrate
            id_column: Column to use for chunking (should be indexed)
            progress_callback: Optional callback function for progress updates
            
        Returns:
            True if migration successful, False otherwise
        """
        logger.info(f"Starting migration of table: {table_name}")
        
        # Update status to SYNCING
        self.checkpoint_manager.save_checkpoint(table_name, 0, 0, 0, "SYNCING")
        
        try:
            # Get table statistics
            total_rows = self.chunked_reader.get_table_row_count(table_name, id_column)
            max_id = self.chunked_reader.get_max_id(table_name, id_column)
            
            logger.info(f"Table {table_name}: {total_rows} rows, max ID: {max_id}")
            
            # Update checkpoint with total rows
            self.checkpoint_manager.save_checkpoint(
                table_name, 0, total_rows, 0, "SYNCING"
            )
            
            # Get existing checkpoint if any
            checkpoint = self.checkpoint_manager.get_checkpoint(table_name)
            start_id = checkpoint["last_processed_id"] if checkpoint else 0
            
            if start_id >= max_id:
                logger.info(f"Table {table_name} already migrated (up to ID {start_id})")
                self.checkpoint_manager.save_checkpoint(
                    table_name, start_id, total_rows, total_rows, "SUCCESS"
                )
                return True
            
            # Calculate chunks
            chunk_size = self.batch_size
            chunks = []
            current_id = start_id
            
            while current_id < max_id:
                end_id = min(current_id + chunk_size, max_id + 1)  # +1 to make end exclusive
                chunks.append((current_id, end_id))
                current_id = end_id
            
            logger.info(f"Table {table_name}: split into {len(chunks)} chunks")
            
            # Process chunks with parallel workers
            migrated_rows = start_id  # Start from where we left off
            failed_chunks = 0
            
            with ThreadPoolExecutor(max_workers=self.parallel_workers) as executor:
                # Submit all chunk processing tasks
                future_to_chunk = {
                    executor.submit(
                        self._process_chunk, 
                        table_name, 
                        chunk_id, 
                        start_id, 
                        end_id, 
                        id_column
                    ): (chunk_id, start_id, end_id)
                    for chunk_id, (start_id, end_id) in enumerate(chunks)
                }
                
                # Process completed tasks
                for future in as_completed(future_to_chunk):
                    chunk_id, start_id, end_id = future_to_chunk[future]
                    try:
                        success, rows_processed = future.result()
                        if success:
                            with self._lock:
                                migrated_rows += rows_processed
                                # Update checkpoint after each successful chunk
                                self.checkpoint_manager.save_checkpoint(
                                    table_name, 
                                    end_id,  # Last processed ID
                                    total_rows,
                                    migrated_rows,
                                    "SYNCING"
                                )
                                self.checkpoint_manager.log_chunk(
                                    table_name, chunk_id, "SUCCESS", rows_processed
                                )
                                
                                # Call progress callback if provided
                                if progress_callback:
                                    progress_callback(table_name, chunk_id, len(chunks), 
                                                    migrated_rows, total_rows, True)
                        else:
                            failed_chunks += 1
                            self.checkpoint_manager.log_chunk(
                                table_name, chunk_id, "FAILED", 0, 
                                "Chunk processing failed"
                            )
                            if progress_callback:
                                progress_callback(table_name, chunk_id, len(chunks), 
                                                migrated_rows, total_rows, False)
                    except Exception as e:
                        failed_chunks += 1
                        logger.error(f"Exception processing chunk {chunk_id} for {table_name}: {e}")
                        self.checkpoint_manager.log_chunk(
                            table_name, chunk_id, "FAILED", 0, str(e)
                        )
                        if progress_callback:
                            progress_callback(table_name, chunk_id, len(chunks), 
                                            migrated_rows, total_rows, False)
            
            # Check if migration was successful
            if failed_chunks == 0:
                logger.info(f"Table {table_name} migration completed successfully")
                self.checkpoint_manager.save_checkpoint(
                    table_name, max_id, total_rows, total_rows, "SUCCESS"
                )
                if progress_callback:
                    progress_callback(table_name, -1, len(chunks), total_rows, total_rows, True)
                return True
            else:
                logger.error(f"Table {table_name} migration failed: {failed_chunks} chunks failed")
                self.checkpoint_manager.save_checkpoint(
                    table_name, migrated_rows, total_rows, migrated_rows, "FAILED"
                )
                if progress_callback:
                    progress_callback(table_name, -1, len(chunks), migrated_rows, total_rows, False)
                return False
                
        except Exception as e:
            logger.error(f"Error migrating table {table_name}: {e}")
            self.checkpoint_manager.save_checkpoint(
                table_name, 0, 0, 0, "FAILED"
            )
            if progress_callback:
                progress_callback(table_name, -1, 0, 0, 0, False)
            return False
    
    def _process_chunk(self, table_name: str, chunk_id: int, start_id: int, 
                      end_id: int, id_column: str) -> Tuple[bool, int]:
        """
        Process a single chunk of data.
        
        Args:
            table_name: Name of the table
            chunk_id: Chunk identifier
            start_id: Starting ID (inclusive)
            end_id: Ending ID (exclusive)
            id_column: Column used for chunking
            
        Returns:
            Tuple of (success_flag, rows_processed)
        """
        try:
            # Read chunk from source
            data = self.chunked_reader.read_chunk(table_name, start_id, end_id, id_column)
            
            if not data:
                logger.warning(f"No data returned for chunk {chunk_id} ({start_id}-{end_id}) of {table_name}")
                return True, 0  # Success but no data
            
            # Write chunk to target
            success = self.data_writer.write_chunk(table_name, data)
            
            if success:
                logger.debug(f"Chunk {chunk_id} ({start_id}-{end_id}) processed successfully: {len(data)} rows")
                return True, len(data)
            else:
                logger.error(f"Failed to write chunk {chunk_id} ({start_id}-{end_id}) for {table_name}")
                return False, 0
                
        except Exception as e:
            logger.error(f"Error processing chunk {chunk_id} ({start_id}-{end_id}) for {table_name}: {e}")
            return False, 0
    
    def migrate_tables(self, table_list: List[str], id_column: str = "id",
                      progress_callback: Optional[Callable] = None) -> Dict[str, bool]:
        """
        Migrate multiple tables.
        
        Args:
            table_list: List of table names to migrate
            id_column: Column to use for chunking
            progress_callback: Optional callback function for progress updates
            
        Returns:
            Dictionary mapping table names to migration success status
        """
        results = {}
        
        for table_name in table_list:
            logger.info(f"Migrating table: {table_name}")
            success = self.migrate_table(table_name, id_column, progress_callback)
            results[table_name] = success
            
            if not success:
                logger.error(f"Failed to migrate table: {table_name}")
            else:
                logger.info(f"Successfully migrated table: {table_name}")
        
        return results
    
    def get_migration_status(self, table_list: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Get migration status for multiple tables.
        
        Args:
            table_list: List of table names to check
            
        Returns:
            Dictionary mapping table names to their status information
        """
        statuses = {}
        for table_name in table_list:
            checkpoint = self.checkpoint_manager.get_checkpoint(table_name)
            if checkpoint:
                statuses[table_name] = checkpoint
            else:
                statuses[table_name] = {
                    "last_processed_id": 0,
                    "total_rows": 0,
                    "migrated_rows": 0,
                    "status": "NOT_STARTED"
                }
        return statuses


# Example usage and testing functions
def example_progress_callback(table_name: str, chunk_id: int, total_chunks: int,
                            migrated_rows: int, total_rows: int, success: bool):
    """Example progress callback function."""
    if chunk_id >= 0:
        status = "✓" if success else "✗"
        print(f"{status} {table_name} - Chunk {chunk_id}/{total_chunks-1}: "
              f"{migrated_rows}/{total_rows} rows migrated")
    else:
        status = "✓" if success else "✗"
        print(f"{status} {table_name} - Migration {'completed' if success else 'failed'}: "
              f"{migrated_rows}/{total_rows} rows")


if __name__ == "__main__":
    # Example usage (for testing purposes)
    logging.basicConfig(level=logging.INFO)
    
    # This would normally come from configuration
    source_conn = "sqlite:///source.db"
    target_conn = "sqlite:///target.db"
    
    engine = ExecutionEngine(
        source_connection_string=source_conn,
        target_connection_string=target_conn,
        batch_size=1000,
        parallel_workers=2
    )
    
    # Example table list
    tables = ["users", "orders", "products"]
    
    # Run migration
    results = engine.migrate_tables(tables, "id", example_progress_callback)
    
    print("\nMigration Results:")
    for table, success in results.items():
        print(f"  {table}: {'SUCCESS' if success else 'FAILED'}")