"""
JIT Configuration using Pydantic Settings.
Loads environment variables from .env and provides configuration for the migration framework.
"""

from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Database connection settings
    source_db_type: str = Field(..., env="SOURCE_DB_TYPE")
    source_db_host: str = Field(..., env="SOURCE_DB_HOST")
    source_db_port: int = Field(..., env="SOURCE_DB_PORT")
    source_db_name: str = Field(..., env="SOURCE_DB_NAME")
    source_db_user: str = Field(..., env="SOURCE_DB_USER")
    source_db_password: str = Field(..., env="SOURCE_DB_PASSWORD")
    
    target_db_type: str = Field(..., env="TARGET_DB_TYPE")
    target_db_host: str = Field(..., env="TARGET_DB_HOST")
    target_db_port: int = Field(..., env="TARGET_DB_PORT")
    target_db_name: str = Field(..., env="TARGET_DB_NAME")
    target_db_user: str = Field(..., env="TARGET_DB_USER")
    target_db_password: str = Field(..., env="TARGET_DB_PASSWORD")
    
    # Migration settings
    batch_size: int = Field(default=5000, env="BATCH_SIZE")
    parallel_workers: int = Field(default=4, env="PARALLEL_WORKERS")
    
    # Paths
    project_root: Path = Field(default=Path.cwd())
    logs_dir: Path = Field(default=Path.cwd() / "logs")
    state_db_path: Path = Field(default=Path.cwd() / "state.db")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
    
    def get_source_connection_string(self) -> str:
        """Build SQLAlchemy connection string for source database."""
        return f"{self.source_db_type}://{self.source_db_user}:{self.source_db_password}@{self.source_db_host}:{self.source_db_port}/{self.source_db_name}"
    
    def get_target_connection_string(self) -> str:
        """Build SQLAlchemy connection string for target database."""
        return f"{self.target_db_type}://{self.target_db_user}:{self.target_db_password}@{self.target_db_host}:{self.target_db_port}/{self.target_db_name}"


# Global settings instance
settings = Settings()