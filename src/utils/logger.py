"""
Structured Logging Utility for ShiftSQL Migration Framework.
Implements JSONL logging per table with error tracking and summary generation.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import threading


class JSONLLogger:
    """JSON Lines logger that creates one file per table for structured logging."""
    
    def __init__(self, logs_dir: Path, project_name: str = "default"):
        """
        Initialize the JSONL logger.
        
        Args:
            logs_dir: Directory where log files will be stored
            project_name: Name of the project/migration job
        """
        self.logs_dir = logs_dir
        self.project_name = project_name
        self.project_logs_dir = logs_dir / project_name
        self._lock = threading.Lock()
        
        # Ensure project logs directory exists
        self.project_logs_dir.mkdir(parents=True, exist_ok=True)
        
        # Track errors for summary
        self.errors: List[Dict[str, Any]] = []
        
        # Setup standard logger as well
        self.setup_standard_logger()
    
    def setup_standard_logger(self):
        """Setup standard Python logger for general application logging."""
        log_file = self.project_logs_dir / "migration.log"
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        self.std_logger = logging.getLogger(__name__)
    
    def _get_table_log_path(self, table_name: str) -> Path:
        """
        Get the log file path for a specific table.
        
        Args:
            table_name: Name of the table
            
        Returns:
            Path to the JSONL log file for the table
        """
        # Sanitize table name for filesystem usage
        safe_table_name = "".join(c for c in table_name if c.isalnum() or c in ('_', '-')).rstrip()
        if not safe_table_name:
            safe_table_name = "unknown_table"
        return self.project_logs_dir / f"{safe_table_name}.jsonl"
    
    def log_structured(self, table_name: str, level: str, chunk_id: Optional[int] = None, 
                      payload_sample: Optional[Any] = None, additional_data: Optional[Dict[str, Any]] = None):
        """
        Log a structured JSONL entry for a table.
        
        Args:
            table_name: Name of the table
            level: Log level (INFO, WARNING, ERROR, etc.)
            chunk_id: ID of the chunk being processed (if applicable)
            payload_sample: Sample of data payload (especially useful for errors)
            additional_data: Any additional data to include in the log entry
        """
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level.upper(),
            "table_name": table_name,
            "chunk_id": chunk_id
        }
        
        if payload_sample is not None:
            # Convert payload to string sample if it's not already a string
            if isinstance(payload_sample, (dict, list)):
                log_entry["payload_sample"] = json.dumps(payload_sample, default=str)[:500]  # Limit size
            else:
                log_entry["payload_sample"] = str(payload_sample)[:500]
        
        if additional_data:
            log_entry.update(additional_data)
        
        # Write to table-specific JSONL file
        log_path = self._get_table_log_path(table_name)
        with self._lock:
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry) + '\n')
        
        # Also log to standard logger for immediate visibility
        msg = f"[{table_name}]"
        if chunk_id is not None:
            msg += f"[Chunk:{chunk_id}]"
        msg += f" {level}: "
        if payload_sample is not None:
            msg += f"Payload: {str(payload_sample)[:100]}"
        if additional_data:
            msg += f" Data: {additional_data}"
            
        if level.upper() == "ERROR":
            self.std_logger.error(msg)
            # Track error for summary
            self.errors.append({
                "timestamp": log_entry["timestamp"],
                "table_name": table_name,
                "chunk_id": chunk_id,
                "level": level,
                "message": msg,
                "payload_sample": log_entry.get("payload_sample"),
                "additional_data": additional_data
            })
        elif level.upper() == "WARNING":
            self.std_logger.warning(msg)
        else:
            self.std_logger.info(msg)
    
    def info(self, table_name: str, chunk_id: Optional[int] = None, 
             payload_sample: Optional[Any] = None, additional_data: Optional[Dict[str, Any]] = None):
        """Log an INFO level entry."""
        self.log_structured(table_name, "INFO", chunk_id, payload_sample, additional_data)
    
    def warning(self, table_name: str, chunk_id: Optional[int] = None, 
                payload_sample: Optional[Any] = None, additional_data: Optional[Dict[str, Any]] = None):
        """Log a WARNING level entry."""
        self.log_structured(table_name, "WARNING", chunk_id, payload_sample, additional_data)
    
    def error(self, table_name: str, chunk_id: Optional[int] = None, 
              payload_sample: Optional[Any] = None, additional_data: Optional[Dict[str, Any]] = None):
        """Log an ERROR level entry."""
        self.log_structured(table_name, "ERROR", chunk_id, payload_sample, additional_data)
    
    def debug(self, table_name: str, chunk_id: Optional[int] = None, 
              payload_sample: Optional[Any] = None, additional_data: Optional[Dict[str, Any]] = None):
        """Log a DEBUG level entry."""
        self.log_structured(table_name, "DEBUG", chunk_id, payload_sample, additional_data)
    
    def get_error_summary(self) -> Dict[str, Any]:
        """
        Generate an error summary from all tracked errors.
        
        Returns:
            Dictionary containing error statistics and details
        """
        if not self.errors:
            return {
                "total_errors": 0,
                "errors_by_table": {},
                "errors_by_level": {},
                "recent_errors": [],
                "summary_generated_at": datetime.utcnow().isoformat() + "Z"
            }
        
        # Group errors by table
        errors_by_table = {}
        for error in self.errors:
            table_name = error["table_name"]
            if table_name not in errors_by_table:
                errors_by_table[table_name] = []
            errors_by_table[table_name].append(error)
        
        # Group errors by level
        errors_by_level = {}
        for error in self.errors:
            level = error["level"]
            if level not in errors_by_level:
                errors_by_level[level] = 0
            errors_by_level[level] += 1
        
        # Get recent errors (last 10)
        recent_errors = sorted(self.errors, key=lambda x: x["timestamp"], reverse=True)[:10]
        
        return {
            "total_errors": len(self.errors),
            "errors_by_table": {
                table: len(errors) for table, errors in errors_by_table.items()
            },
            "errors_by_level": errors_by_level,
            "recent_errors": recent_errors,
            "summary_generated_at": datetime.utcnow().isoformat() + "Z"
        }
    
    def save_error_summary(self, output_path: Optional[Path] = None) -> Path:
        """
        Save error summary to a JSON file.
        
        Args:
            output_path: Optional path to save the summary (defaults to logs_dir/error_summary.json)
            
        Returns:
            Path where the summary was saved
        """
        if output_path is None:
            output_path = self.project_logs_dir / "error_summary.json"
        
        summary = self.get_error_summary()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, default=str)
        
        self.std_logger.info(f"Error summary saved to {output_path}")
        return output_path
    
    def cleanup_old_logs(self, days_to_keep: int = 30):
        """
        Clean up log files older than specified days.
        
        Args:
            days_to_keep: Number of days of logs to keep
        """
        cutoff_time = datetime.now().timestamp() - (days_to_keep * 24 * 3600)
        
        for log_file in self.project_logs_dir.glob("*.jsonl"):
            if log_file.stat().st_mtime < cutoff_time:
                try:
                    log_file.unlink()
                    self.std_logger.info(f"Removed old log file: {log_file}")
                except OSError as e:
                    self.std_logger.error(f"Error removing log file {log_file}: {e}")


# Global logger instance (will be initialized in main)
_logger_instance: Optional[JSONLLogger] = None


def init_logger(logs_dir: Path, project_name: str = "default") -> JSONLLogger:
    """
    Initialize the global logger instance.
    
    Args:
        logs_dir: Directory where log files will be stored
        project_name: Name of the project/migration job
        
    Returns:
        Initialized JSONLLogger instance
    """
    global _logger_instance
    _logger_instance = JSONLLogger(logs_dir, project_name)
    return _logger_instance


def get_logger() -> JSONLLogger:
    """
    Get the global logger instance.
    
    Returns:
        JSONLLogger instance
        
    Raises:
        RuntimeError: If logger hasn't been initialized
    """
    if _logger_instance is None:
        raise RuntimeError("Logger not initialized. Call init_logger() first.")
    return _logger_instance


# Convenience functions for direct usage
def log_info(table_name: str, chunk_id: Optional[int] = None, 
             payload_sample: Optional[Any] = None, additional_data: Optional[Dict[str, Any]] = None):
    """Convenience function for INFO logging."""
    get_logger().info(table_name, chunk_id, payload_sample, additional_data)


def log_warning(table_name: str, chunk_id: Optional[int] = None, 
                payload_sample: Optional[Any] = None, additional_data: Optional[Dict[str, Any]] = None):
    """Convenience function for WARNING logging."""
    get_logger().warning(table_name, chunk_id, payload_sample, additional_data)


def log_error(table_name: str, chunk_id: Optional[int] = None, 
              payload_sample: Optional[Any] = None, additional_data: Optional[Dict[str, Any]] = None):
    """Convenience function for ERROR logging."""
    get_logger().error(table_name, chunk_id, payload_sample, additional_data)


def log_debug(table_name: str, chunk_id: Optional[int] = None, 
              payload_sample: Optional[Any] = None, additional_data: Optional[Dict[str, Any]] = None):
    """Convenience function for DEBUG logging."""
    get_logger().debug(table_name, chunk_id, payload_sample, additional_data)


def get_error_summary() -> Dict[str, Any]:
    """Convenience function to get error summary."""
    return get_logger().get_error_summary()


def save_error_summary(output_path: Optional[Path] = None) -> Path:
    """Convenience function to save error summary."""
    return get_logger().save_error_summary(output_path)


if __name__ == "__main__":
    # Example usage
    import tempfile
    
    with tempfile.TemporaryDirectory() as temp_dir:
        logs_dir = Path(temp_dir) / "logs"
        logger = init_logger(logs_dir, "test_project")
        
        # Log some entries
        logger.info("users", chunk_id=1, payload_sample={"id": 1, "name": "John Doe"})
        logger.warning("users", chunk_id=2, payload_sample={"id": 2, "name": ""}, 
                      additional_data={"warning": "Empty name field"})
        logger.error("orders", chunk_id=5, payload_sample={"id": 5, "amount": "invalid"},
                    additional_data={"error": "Failed to parse amount as decimal"})
        
        # Get error summary
        summary = logger.get_error_summary()
        print("Error Summary:")
        print(json.dumps(summary, indent=2))
        
        # Save error summary
        summary_path = logger.save_error_summary()
        print(f"\nError summary saved to: {summary_path}")