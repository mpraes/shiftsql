"""
Dynamic Contract Factory for converting SQLAlchemy metadata to Pydantic models.
Implements runtime model generation with validation and data cleaning capabilities.
"""

from typing import Dict, Any, Optional, Type, List
from pydantic import BaseModel, create_model, validator
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, Text
from sqlalchemy.types import TypeEngine
import re
from datetime import datetime

# Try to import SQLAlchemy types, provide fallbacks if not available
try:
    from sqlalchemy.types import (
        VARCHAR, CHAR, TEXT, INTEGER, BIGINT, SMALLINT,
        FLOAT, NUMERIC, DECIMAL, BOOLEAN, DATE, TIME, TIMESTAMP,
        CLOB, BLOB, BINARY, VARBINARY
    )
except ImportError:
    # Fallback definitions
    VARCHAR = String
    CHAR = String
    TEXT = Text
    INTEGER = Integer
    BIGINT = Integer
    SMALLINT = Integer
    FLOAT = Float
    NUMERIC = Float
    DECIMAL = Float
    BOOLEAN = Boolean
    DATE = DateTime
    TIME = DateTime
    TIMESTAMP = DateTime
    CLOB = Text
    BLOB = Text
    BINARY = Text
    VARBINARY = Text


def get_pydantic_type(sa_type: TypeEngine) -> Any:
    """
    Map SQLAlchemy types to Python/Pydantic types.
    
    Args:
        sa_type: SQLAlchemy type object
        
    Returns:
        Corresponding Python type for Pydantic
    """
    type_map = {
        Integer: int,
        String: str,
        Text: str,
        VARCHAR: str,
        CHAR: str,
        DateTime: datetime,
        Boolean: bool,
        Float: float,
        NUMERIC: float,
        DECIMAL: float,
    }
    
    # Check for exact matches
    for sa_class, py_type in type_map.items():
        if isinstance(sa_type, sa_class):
            return py_type
    
    # Handle parameterized types (like VARCHAR(255))
    sa_type_str = str(sa_type).lower()
    if 'varchar' in sa_type_str or 'char' in sa_type_str or 'text' in sa_type_str:
        return str
    elif 'int' in sa_type_str:
        return int
    elif 'float' in sa_type_str or 'numeric' in sa_type_str or 'decimal' in sa_type_str:
        return float
    elif 'bool' in sa_type_str:
        return bool
    elif 'date' in sa_type_str or 'time' in sa_type_str:
        return datetime
    
    # Default to string for unknown types
    return str


def clean_string_value(value: Any) -> str:
    """
    Clean string values by stripping whitespace and handling common issues.
    
    Args:
        value: Input value to clean
        
    Returns:
        Cleaned string value
    """
    if value is None:
        return None
    if isinstance(value, str):
        # Strip whitespace
        cleaned = value.strip()
        # Replace multiple spaces with single space
        cleaned = re.sub(r'\s+', ' ', cleaned)
        return cleaned
    return str(value).strip()


def clean_numeric_value(value: Any) -> float:
    """
    Clean numeric values by converting to float and handling edge cases.
    
    Args:
        value: Input value to clean
        
    Returns:
        Cleaned numeric value
    """
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def clean_datetime_value(value: Any) -> datetime:
    """
    Clean datetime values by attempting to parse common formats.
    
    Args:
        value: Input value to clean
        
    Returns:
        Cleaned datetime value or default
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        # Try to parse common datetime string formats
        if isinstance(value, str):
            # Remove timezone info for simplicity (can be enhanced)
            value = re.sub(r'\s*[+-]\d{2}:?\d{2}', '', value)
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        pass
    # Return current time as fallback (or could raise)
    return datetime.now()


class ContractFactory:
    """Factory for creating dynamic Pydantic models from SQLAlchemy table metadata."""
    
    def __init__(self, type_overrides: Optional[Dict[str, Any]] = None):
        """
        Initialize the contract factory.
        
        Args:
            type_overrides: Optional dictionary mapping column names to custom types
        """
        self.type_overrides = type_overrides or {}
        self._model_cache: Dict[str, Type[BaseModel]] = {}
    
    def create_model_from_table(self, table_name: str, columns: List[Dict[str, Any]]) -> Type[BaseModel]:
        """
        Create a Pydantic model from table column definitions.
        
        Args:
            table_name: Name of the table (used for model name)
            columns: List of column dictionaries with name, type, nullable info
            
        Returns:
            Dynamically created Pydantic model class
        """
        # Check cache first
        cache_key = f"{table_name}_{hash(tuple(sorted([(c['name'], str(c.get('type', ''))) for c in columns])))}"
        if cache_key in self._model_cache:
            return self._model_cache[cache_key]
        
        # Prepare field definitions
        field_definitions = {}
        validators = {}
        
        for column in columns:
            col_name = column["name"]
            col_type = column.get("type")
            nullable = column.get("nullable", True)
            
            # Determine Python type
            if col_name in self.type_overrides:
                python_type = self.type_overrides[col_name]
            elif col_type:
                python_type = get_pydantic_type(col_type)
            else:
                python_type = str  # Default fallback
            
            # Handle nullable fields
            if nullable:
                python_type = Optional[python_type]
            
            field_definitions[col_name] = (python_type, ...)
            
            # Add cleaners based on type
            if python_type == str or (hasattr(python_type, '__origin__') and python_type.__origin__ == Optional and python_type.__args__[0] == str):
                validators[f"clean_{col_name}"] = validator(col_name, pre=True, allow_reuse=True)(clean_string_value)
            elif python_type == float or (hasattr(python_type, '__origin__') and python_type.__origin__ == Optional and python_type.__args__[0] == float):
                validators[f"clean_{col_name}"] = validator(col_name, pre=True, allow_reuse=True)(clean_numeric_value)
            elif python_type == datetime or (hasattr(python_type, '__origin__') and python_type.__origin__ == Optional and python_type.__args__[0] == datetime):
                validators[f"clean_{col_name}"] = validator(col_name, pre=True, allow_reuse=True)(clean_datetime_value)
        
        # Create model class
        model_name = f"{table_name.title().replace('_', '')}Contract"
        model_class = create_model(
            model_name,
            __base__=BaseModel,
            **field_definitions,
            __validators__=validators
        )
        
        # Cache the model
        self._model_cache[cache_key] = model_class
        
        return model_class
    
    def validate_data(self, model_class: Type[BaseModel], data: Dict[str, Any]) -> BaseModel:
        """
        Validate data against a Pydantic model instance.
        
        Args:
            model_class: Pydantic model class
            data: Dictionary of data to validate
            
        Returns:
            Validated model instance
            
        Raises:
            ValidationError: If data doesn't conform to model
        """
        return model_class(**data)
    
    def clear_cache(self):
        """Clear the model cache."""
        self._model_cache.clear()