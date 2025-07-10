"""
Tests for device mapping functionality.
"""

import unittest
from unittest.mock import patch, mock_open
import json

from libtuya.intelligence.device_mappings import (
    DeviceCategory, DeviceMappingManager, device_mapping_manager
)


class TestDeviceMappingManager(unittest.TestCase):
    """Test device mapping management functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_mappings = {
            "description": "Test device mappings",
            "categories": {
                "lights": {
                    "dj": {
                        "name": "Light",
                        "capabilities": ["switch_led", "bright_value", "colour_data"]
                    },
                    "dc": {
                        "name": "String Lights",
                        "capabilities": ["switch_led", "bright_value", "temp_value"],
                        "notes": "Temperature control"
                    }
                },
                "switches": {
                    "kg": {
                        "name": "Switch",
                        "capabilities": ["switch_1", "switch_2"]
                    }
                }
            }
        }
        
        self.mock_json_data = json.dumps(self.test_mappings)
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_load_data(self, mock_exists, mock_file):
        """Test loading device mapping data from JSON file."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = DeviceMappingManager()
        
        # Verify data was loaded correctly
        category = manager.get_category("dj")
        self.assertIsNotNone(category)
        self.assertEqual(category.name, "Light")
        self.assertEqual(category.platform, "lights")
        self.assertIn("switch_led", category.capabilities)
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_get_category(self, mock_exists, mock_file):
        """Test getting device category information."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = DeviceMappingManager()
        
        # Test valid category
        category = manager.get_category("dj")
        self.assertIsNotNone(category)
        self.assertEqual(category.category_id, "dj")
        self.assertEqual(category.name, "Light")
        self.assertEqual(category.platform, "lights")
        
        # Test invalid category
        category = manager.get_category("invalid")
        self.assertIsNone(category)
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_get_capabilities(self, mock_exists, mock_file):
        """Test getting capabilities for a device category."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = DeviceMappingManager()
        
        # Test valid category
        capabilities = manager.get_capabilities("dj")
        self.assertIn("switch_led", capabilities)
        self.assertIn("bright_value", capabilities)
        self.assertIn("colour_data", capabilities)
        
        # Test invalid category
        capabilities = manager.get_capabilities("invalid")
        self.assertEqual(len(capabilities), 0)
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_get_categories_by_platform(self, mock_exists, mock_file):
        """Test getting categories by platform."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = DeviceMappingManager()
        
        # Test valid platform
        light_categories = manager.get_categories_by_platform("lights")
        self.assertIn("dj", light_categories)
        self.assertIn("dc", light_categories)
        
        # Test invalid platform
        invalid_categories = manager.get_categories_by_platform("invalid")
        self.assertEqual(len(invalid_categories), 0)
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_get_categories_with_capability(self, mock_exists, mock_file):
        """Test getting categories that support a specific capability."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = DeviceMappingManager()
        
        # Test common capability
        categories = manager.get_categories_with_capability("switch_led")
        self.assertIn("dj", categories)
        self.assertIn("dc", categories)
        
        # Test specific capability
        categories = manager.get_categories_with_capability("colour_data")
        self.assertIn("dj", categories)
        self.assertNotIn("dc", categories)
        
        # Test non-existent capability
        categories = manager.get_categories_with_capability("nonexistent")
        self.assertEqual(len(categories), 0)
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_has_capability(self, mock_exists, mock_file):
        """Test checking if a category has a specific capability."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = DeviceMappingManager()
        
        # Test valid capability
        self.assertTrue(manager.has_capability("dj", "switch_led"))
        self.assertTrue(manager.has_capability("dj", "colour_data"))
        
        # Test invalid capability
        self.assertFalse(manager.has_capability("dj", "nonexistent"))
        self.assertFalse(manager.has_capability("kg", "colour_data"))
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_search_categories(self, mock_exists, mock_file):
        """Test searching categories by name or ID."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = DeviceMappingManager()
        
        # Test search by ID
        results = manager.search_categories("dj")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].category_id, "dj")
        
        # Test search by name
        results = manager.search_categories("Light")
        self.assertGreater(len(results), 0)
        
        # Test case-insensitive search
        results = manager.search_categories("light")
        self.assertGreater(len(results), 0)
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_get_category_suggestions(self, mock_exists, mock_file):
        """Test getting category suggestions based on capabilities."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = DeviceMappingManager()
        
        # Test with light capabilities
        suggestions = manager.get_category_suggestions(["switch_led", "bright_value"])
        self.assertIn("dj", suggestions)
        self.assertIn("dc", suggestions)
        
        # Test with specific capability
        suggestions = manager.get_category_suggestions(["colour_data"])
        self.assertIn("dj", suggestions)
        self.assertNotIn("dc", suggestions)
        
        # Test with no capabilities
        suggestions = manager.get_category_suggestions([])
        self.assertEqual(len(suggestions), 0)
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_validate_category_mapping(self, mock_exists, mock_file):
        """Test validating category mappings."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = DeviceMappingManager()
        
        # Test valid mapping
        result = manager.validate_category_mapping("dj", ["switch_led", "bright_value"])
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["missing_capabilities"]), 0)
        
        # Test missing capabilities
        result = manager.validate_category_mapping("dj", ["switch_led", "nonexistent"])
        self.assertFalse(result["valid"])
        self.assertIn("nonexistent", result["missing_capabilities"])
        
        # Test invalid category
        result = manager.validate_category_mapping("invalid", ["switch_led"])
        self.assertFalse(result["valid"])
        self.assertIn("not found", result["error"])
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_get_category_stats(self, mock_exists, mock_file):
        """Test getting category statistics."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = DeviceMappingManager()
        
        stats = manager.get_category_stats()
        
        # Verify stats structure
        self.assertIn("total_categories", stats)
        self.assertIn("total_platforms", stats)
        self.assertIn("total_capabilities", stats)
        self.assertIn("categories_per_platform", stats)
        self.assertIn("capability_usage", stats)
        
        # Verify stats values
        self.assertEqual(stats["total_categories"], 3)
        self.assertEqual(stats["total_platforms"], 2)


class TestDeviceCategory(unittest.TestCase):
    """Test DeviceCategory data class."""
    
    def test_device_category_creation(self):
        """Test creating DeviceCategory objects."""
        category = DeviceCategory(
            category_id="dj",
            name="Light",
            capabilities=["switch_led", "bright_value"],
            notes="Test light",
            platform="lights"
        )
        
        self.assertEqual(category.category_id, "dj")
        self.assertEqual(category.name, "Light")
        self.assertEqual(len(category.capabilities), 2)
        self.assertEqual(category.notes, "Test light")
        self.assertEqual(category.platform, "lights")
    
    def test_device_category_defaults(self):
        """Test DeviceCategory with default values."""
        category = DeviceCategory(
            category_id="test",
            name="Test Device",
            capabilities=["test_capability"]
        )
        
        self.assertIsNone(category.notes)
        self.assertEqual(category.platform, "unknown")


if __name__ == "__main__":
    unittest.main()