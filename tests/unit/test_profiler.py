"""
Unit tests for the Profiler class.
"""
import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add src to path so we can import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from core.profiler import Profiler


class TestProfiler(unittest.TestCase):
    """Test cases for the Profiler class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.connection_string = "postgresql://user:pass@localhost:5432/testdb"
    
    @patch('core.profiler.create_engine')
    def test_profiler_initialization(self, mock_create_engine):
        """Test that Profiler initializes correctly."""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine
        
        profiler = Profiler(self.connection_string)
        
        self.assertEqual(profiler.connection_string, self.connection_string)
        mock_create_engine.assert_called_once_with(self.connection_string)
    
    @patch('core.profiler.create_engine')
    def test_connect_success(self, mock_create_engine):
        """Test successful database connection."""
        mock_engine = Mock()
        mock_connection = Mock()
        mock_metadata = Mock()
        
        mock_create_engine.return_value = mock_engine
        mock_engine.connect.return_value = mock_connection
        
        profiler = Profiler(self.connection_string)
        result = profiler.connect()
        
        self.assertTrue(result)
        self.assertEqual(profiler.engine, mock_engine)
        self.assertEqual(profiler.connection, mock_connection)
        mock_metadata.reflect.assert_called_once_with(bind=mock_engine)
    
    @patch('core.profiler.create_engine')
    def test_connect_failure(self, mock_create_engine):
        """Test failed database connection."""
        from sqlalchemy.exc import SQLAlchemyError
        
        mock_create_engine.side_effect = SQLAlchemyError("Connection failed")
        
        profiler = Profiler(self.connection_string)
        result = profiler.connect()
        
        self.assertFalse(result)
    
    @patch('core.profiler.create_engine')
    def test_get_table_names(self, mock_create_engine):
        """Test getting table names."""
        mock_engine = Mock()
        mock_metadata = Mock()
        mock_metadata.tables = {
            'users': Mock(),
            'orders': Mock(),
            'products': Mock()
        }
        
        mock_create_engine.return_value = mock_engine
        
        profiler = Profiler(self.connection_string)
        profiler.engine = mock_engine
        profiler.metadata = mock_metadata
        
        table_names = profiler.get_table_names()
        
        self.assertEqual(set(table_names), {'users', 'orders', 'products'})
    
    @patch('core.profiler.create_engine')
    def test_get_table_info(self, mock_create_engine):
        """Test getting table information."""
        mock_engine = Mock()
        mock_connection = Mock()
        mock_metadata = Mock()
        mock_table = Mock()
        
        # Setup mock table with columns
        mock_col1 = Mock()
        mock_col1.name = 'id'
        mock_col1.type = Mock()
        mock_col1.type.__str__ = Mock(return_value='INTEGER')
        mock_col1.nullable = False
        mock_col1.primary_key = True
        mock_col1.foreign_keys = []
        
        mock_col2 = Mock()
        mock_col2.name = 'name'
        mock_col2.type = Mock()
        mock_col2.type.__str__ = Mock(return_value='VARCHAR(255)')
        mock_col2.nullable = True
        mock_col2.primary_key = False
        mock_col2.foreign_keys = []
        
        mock_table.columns = [mock_col1, mock_col2]
        mock_table.primary_key.columns = [mock_col1]
        mock_table.foreign_keys = []
        
        mock_metadata.tables = {'test_table': mock_table}
        
        mock_create_engine.return_value = mock_engine
        mock_engine.connect.return_value = mock_connection
        mock_engine.execute.return_value.scalar.return_value = 100
        
        profiler = Profiler(self.connection_string)
        profiler.engine = mock_engine
        profiler.metadata = mock_metadata
        
        table_info = profiler.get_table_info('test_table')
        
        self.assertEqual(table_info['name'], 'test_table')
        self.assertEqual(table_info['row_count'], 100)
        self.assertEqual(len(table_info['columns']), 2)
        self.assertEqual(table_info['primary_keys'], ['id'])
        self.assertEqual(table_info['foreign_keys'], [])
    
    @patch('core.profiler.create_engine')
    def test_identify_dangerous_types(self, mock_create_engine):
        """Test identification of dangerous types."""
        mock_engine = Mock()
        
        mock_create_engine.return_value = mock_engine
        
        profiler = Profiler(self.connection_string)
        profiler.engine = mock_engine
        
        table_info = {
            'columns': [
                {'name': 'id', 'type': 'INTEGER'},
                {'name': 'data', 'type': 'CLOB'},
                {'name': 'description', 'type': 'TEXT'},
                {'name': 'name', 'type': 'VARCHAR(100)'}
            ]
        }
        
        dangerous_types = profiler.identify_dangerous_types(table_info)
        
        self.assertEqual(set(dangerous_types), {'data', 'description'})


if __name__ == '__main__':
    unittest.main()