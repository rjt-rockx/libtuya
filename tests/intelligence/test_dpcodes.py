"""
Tests for DPCode management functionality.
"""

import unittest
from unittest.mock import patch, mock_open
import json

from libtuya.intelligence.dpcodes import DPCode, DPCodeManager, dpcode_manager


class TestDPCodeManager(unittest.TestCase):
    """Test DPCode management functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_dpcodes = {
            "description": "Test DPCode definitions",
            "total_count": 3,
            "dpcodes": {
                "BRIGHT_VALUE": "bright_value",
                "SWITCH_LED": "switch_led",
                "COLOUR_DATA": "colour_data"
            }
        }
        
        # Mock the file reading
        self.mock_json_data = json.dumps(self.test_dpcodes)
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_load_data(self, mock_exists, mock_file):
        """Test loading DPCode data from JSON file."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = DPCodeManager()
        
        # Verify data was loaded correctly
        self.assertEqual(manager.get_total_count(), 3)
        self.assertEqual(manager.get_code_by_name("BRIGHT_VALUE"), "bright_value")
        self.assertEqual(manager.get_name_by_code("switch_led"), "SWITCH_LED")
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_get_code_by_name(self, mock_exists, mock_file):
        """Test getting DPCode by constant name."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = DPCodeManager()
        
        # Test valid names
        self.assertEqual(manager.get_code_by_name("BRIGHT_VALUE"), "bright_value")
        self.assertEqual(manager.get_code_by_name("SWITCH_LED"), "switch_led")
        
        # Test invalid name
        self.assertIsNone(manager.get_code_by_name("INVALID_CODE"))
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_get_name_by_code(self, mock_exists, mock_file):
        """Test getting constant name by DPCode."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = DPCodeManager()
        
        # Test valid codes
        self.assertEqual(manager.get_name_by_code("bright_value"), "BRIGHT_VALUE")
        self.assertEqual(manager.get_name_by_code("switch_led"), "SWITCH_LED")
        
        # Test invalid code
        self.assertIsNone(manager.get_name_by_code("invalid_code"))
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_search_codes(self, mock_exists, mock_file):
        """Test searching DPCodes by pattern."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = DPCodeManager()
        
        # Test search patterns
        results = manager.search_codes("bright")
        self.assertIn("bright_value", results)
        
        results = manager.search_codes("switch")
        self.assertIn("switch_led", results)
        
        results = manager.search_codes("nonexistent")
        self.assertEqual(len(results), 0)
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_search_names(self, mock_exists, mock_file):
        """Test searching constant names by pattern."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = DPCodeManager()
        
        # Test search patterns
        results = manager.search_names("BRIGHT")
        self.assertIn("BRIGHT_VALUE", results)
        
        results = manager.search_names("SWITCH")
        self.assertIn("SWITCH_LED", results)
        
        results = manager.search_names("NONEXISTENT")
        self.assertEqual(len(results), 0)
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_validation_methods(self, mock_exists, mock_file):
        """Test DPCode validation methods."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = DPCodeManager()
        
        # Test valid code validation
        self.assertTrue(manager.is_valid_code("bright_value"))
        self.assertTrue(manager.is_valid_code("switch_led"))
        self.assertFalse(manager.is_valid_code("invalid_code"))
        
        # Test valid name validation
        self.assertTrue(manager.is_valid_name("BRIGHT_VALUE"))
        self.assertTrue(manager.is_valid_name("SWITCH_LED"))
        self.assertFalse(manager.is_valid_name("INVALID_NAME"))
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_get_all_methods(self, mock_exists, mock_file):
        """Test methods that return all codes/names."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = DPCodeManager()
        
        # Test get all codes
        all_codes = manager.get_all_codes()
        self.assertEqual(len(all_codes), 3)
        self.assertIn("bright_value", all_codes)
        self.assertIn("switch_led", all_codes)
        self.assertIn("colour_data", all_codes)
        
        # Test get all names
        all_names = manager.get_all_names()
        self.assertEqual(len(all_names), 3)
        self.assertIn("BRIGHT_VALUE", all_names)
        self.assertIn("SWITCH_LED", all_names)
        self.assertIn("COLOUR_DATA", all_names)
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_get_category_codes(self, mock_exists, mock_file):
        """Test getting DPCodes for specific categories."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = DPCodeManager()
        
        # Test light category
        light_codes = manager.get_category_codes("dj")
        self.assertGreater(len(light_codes), 0)
        
        # Test switch category
        switch_codes = manager.get_category_codes("kg")
        self.assertGreater(len(switch_codes), 0)
        
        # Test unknown category
        unknown_codes = manager.get_category_codes("unknown")
        self.assertEqual(len(unknown_codes), 0)


class TestDPCodeEnum(unittest.TestCase):
    """Test DPCode enumeration functionality."""
    
    def test_dpcode_enum_access(self):
        """Test accessing DPCode enum values."""
        # Test that enum values exist and are accessible
        self.assertIsInstance(DPCode.BRIGHT_VALUE, str)
        self.assertIsInstance(DPCode.SWITCH_LED, str)
        
        # Test that enum values have correct string values
        self.assertEqual(DPCode.BRIGHT_VALUE, "bright_value")
        self.assertEqual(DPCode.SWITCH_LED, "switch_led")
    
    def test_dpcode_enum_membership(self):
        """Test DPCode enum membership checks."""
        # Test valid membership
        self.assertTrue(hasattr(DPCode, "BRIGHT_VALUE"))
        self.assertTrue(hasattr(DPCode, "SWITCH_LED"))
        
        # Test invalid membership
        self.assertFalse(hasattr(DPCode, "INVALID_DPCODE"))


if __name__ == "__main__":
    unittest.main()