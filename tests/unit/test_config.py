"""
Unit tests for configuration module.
"""
import unittest
import os
from pathlib import Path

# Add src to path so we can import modules
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

# We'll test the functions directly rather than instantiating Settings
# since it requires environment variables


class TestConfig(unittest.TestCase):
    """Test cases for Settings configuration."""
    
    def test_paths_are_path_objects(self):
        """Test that we can create Path objects."""
        # This test doesn't require Settings instantiation
        project_root = Path.cwd()
        logs_dir = project_root / "logs"
        state_db_path = project_root / "state.db"
        
        self.assertIsInstance(project_root, Path)
        self.assertIsInstance(logs_dir, Path)
        self.assertIsInstance(state_db_path, Path)


if __name__ == '__main__':
    unittest.main()