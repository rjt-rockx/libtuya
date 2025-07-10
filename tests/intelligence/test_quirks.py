"""
Tests for device quirks and edge cases functionality.
"""

import unittest
from unittest.mock import patch, mock_open
import json

from libtuya.intelligence.quirks import (
    DeviceQuirk, EntityMapping, DPCodeFallback, QuirkType,
    DeviceQuirksManager, quirks_manager
)


class TestDeviceQuirksManager(unittest.TestCase):
    """Test device quirks management functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_quirks = {
            "description": "Test quirks data",
            "category_duplicates": {
                "mappings": {
                    "cz": "kg",
                    "pc": "kg"
                }
            },
            "multi_entity_devices": {
                "examples": {
                    "tgkg": {
                        "name": "Dimmer Switch",
                        "entities": [
                            {"key": "switch_led_1", "brightness": "bright_value_1"},
                            {"key": "switch_led_2", "brightness": "bright_value_2"}
                        ]
                    }
                }
            },
            "dpcode_fallbacks": {
                "examples": {
                    "brightness_fallback": "(BRIGHT_VALUE_V2, BRIGHT_VALUE)",
                    "color_temp_fallback": "(TEMP_VALUE_V2, TEMP_VALUE)"
                }
            },
            "undocumented_categories": {
                "categories": {
                    "mbd": "VECINO RGBW light - found in diagnostics",
                    "qjdcz": "Unknown product with light/switch capabilities"
                }
            }
        }
        
        self.mock_json_data = json.dumps(self.test_quirks)
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_load_data(self, mock_exists, mock_file):
        """Test loading quirks data from JSON file."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = DeviceQuirksManager()
        
        # Verify category duplicates were loaded
        self.assertEqual(manager.get_canonical_category("cz"), "kg")
        self.assertEqual(manager.get_canonical_category("pc"), "kg")
        
        # Verify multi-entity devices were loaded
        self.assertTrue(manager.is_multi_entity_device("tgkg"))
        
        # Verify undocumented categories were loaded
        self.assertTrue(manager.is_undocumented_category("mbd"))
        self.assertTrue(manager.is_undocumented_category("qjdcz"))
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_get_canonical_category(self, mock_exists, mock_file):
        """Test getting canonical category ID."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = DeviceQuirksManager()
        
        # Test duplicate categories
        self.assertEqual(manager.get_canonical_category("cz"), "kg")
        self.assertEqual(manager.get_canonical_category("pc"), "kg")
        
        # Test non-duplicate categories
        self.assertEqual(manager.get_canonical_category("dj"), "dj")
        self.assertEqual(manager.get_canonical_category("kg"), "kg")
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_is_duplicate_category(self, mock_exists, mock_file):
        """Test checking if category is a duplicate."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = DeviceQuirksManager()
        
        # Test duplicate categories
        self.assertTrue(manager.is_duplicate_category("cz"))
        self.assertTrue(manager.is_duplicate_category("pc"))
        
        # Test non-duplicate categories
        self.assertFalse(manager.is_duplicate_category("kg"))
        self.assertFalse(manager.is_duplicate_category("dj"))
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_get_multi_entity_mappings(self, mock_exists, mock_file):
        """Test getting multi-entity device mappings."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = DeviceQuirksManager()
        
        # Test multi-entity device
        mappings = manager.get_multi_entity_mappings("tgkg")
        self.assertEqual(len(mappings), 2)
        self.assertEqual(mappings[0].key, "switch_led_1")
        self.assertEqual(mappings[0].brightness_dpcode, "bright_value_1")
        self.assertEqual(mappings[1].key, "switch_led_2")
        self.assertEqual(mappings[1].brightness_dpcode, "bright_value_2")
        
        # Test non-multi-entity device
        mappings = manager.get_multi_entity_mappings("dj")
        self.assertEqual(len(mappings), 0)
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_is_multi_entity_device(self, mock_exists, mock_file):
        """Test checking if device is multi-entity."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = DeviceQuirksManager()
        
        # Test multi-entity device
        self.assertTrue(manager.is_multi_entity_device("tgkg"))
        
        # Test non-multi-entity device
        self.assertFalse(manager.is_multi_entity_device("dj"))
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_get_dpcode_fallbacks(self, mock_exists, mock_file):
        """Test getting DPCode fallback sequences."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = DeviceQuirksManager()
        
        # Test brightness fallback
        fallback = manager.get_dpcode_fallbacks("brightness_fallback")
        self.assertIsNotNone(fallback)
        self.assertEqual(fallback.primary_dpcode, "BRIGHT_VALUE_V2")
        self.assertIn("BRIGHT_VALUE", fallback.fallback_dpcodes)
        
        # Test color temp fallback
        fallback = manager.get_dpcode_fallbacks("color_temp_fallback")
        self.assertIsNotNone(fallback)
        self.assertEqual(fallback.primary_dpcode, "TEMP_VALUE_V2")
        self.assertIn("TEMP_VALUE", fallback.fallback_dpcodes)
        
        # Test non-existent fallback
        fallback = manager.get_dpcode_fallbacks("nonexistent")
        self.assertIsNone(fallback)
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_get_fallback_dpcodes(self, mock_exists, mock_file):
        """Test getting fallback DPCodes for primary DPCode."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = DeviceQuirksManager()
        
        # Test existing fallback
        fallbacks = manager.get_fallback_dpcodes("BRIGHT_VALUE_V2")
        self.assertIn("BRIGHT_VALUE", fallbacks)
        
        # Test non-existent fallback
        fallbacks = manager.get_fallback_dpcodes("nonexistent")
        self.assertEqual(len(fallbacks), 0)
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_is_undocumented_category(self, mock_exists, mock_file):
        """Test checking if category is undocumented."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = DeviceQuirksManager()
        
        # Test undocumented categories
        self.assertTrue(manager.is_undocumented_category("mbd"))
        self.assertTrue(manager.is_undocumented_category("qjdcz"))
        
        # Test documented categories
        self.assertFalse(manager.is_undocumented_category("dj"))
        self.assertFalse(manager.is_undocumented_category("kg"))
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_get_undocumented_description(self, mock_exists, mock_file):
        """Test getting description for undocumented category."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = DeviceQuirksManager()
        
        # Test undocumented categories
        description = manager.get_undocumented_description("mbd")
        self.assertEqual(description, "VECINO RGBW light - found in diagnostics")
        
        description = manager.get_undocumented_description("qjdcz")
        self.assertEqual(description, "Unknown product with light/switch capabilities")
        
        # Test documented category
        description = manager.get_undocumented_description("dj")
        self.assertIsNone(description)
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_get_quirks_for_category(self, mock_exists, mock_file):
        """Test getting quirks for a specific category."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = DeviceQuirksManager()
        
        # Test category with quirks
        quirks = manager.get_quirks_for_category("cz")
        self.assertGreater(len(quirks), 0)
        self.assertEqual(quirks[0].quirk_type, QuirkType.CATEGORY_DUPLICATE)
        
        # Test multi-entity category
        quirks = manager.get_quirks_for_category("tgkg")
        self.assertGreater(len(quirks), 0)
        self.assertEqual(quirks[0].quirk_type, QuirkType.MULTI_ENTITY)
        
        # Test undocumented category
        quirks = manager.get_quirks_for_category("mbd")
        self.assertGreater(len(quirks), 0)
        self.assertEqual(quirks[0].quirk_type, QuirkType.UNDOCUMENTED_CATEGORY)
        
        # Test category without quirks
        quirks = manager.get_quirks_for_category("dj")
        self.assertEqual(len(quirks), 0)
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_has_quirks(self, mock_exists, mock_file):
        """Test checking if category has quirks."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = DeviceQuirksManager()
        
        # Test categories with quirks
        self.assertTrue(manager.has_quirks("cz"))
        self.assertTrue(manager.has_quirks("tgkg"))
        self.assertTrue(manager.has_quirks("mbd"))
        
        # Test category without quirks
        self.assertFalse(manager.has_quirks("dj"))
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_apply_category_quirks(self, mock_exists, mock_file):
        """Test applying category-level quirks."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = DeviceQuirksManager()
        
        # Test duplicate category resolution
        result = manager.apply_category_quirks("cz")
        self.assertEqual(result, "kg")
        
        result = manager.apply_category_quirks("pc")
        self.assertEqual(result, "kg")
        
        # Test non-duplicate category
        result = manager.apply_category_quirks("dj")
        self.assertEqual(result, "dj")
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_get_dpcode_with_fallbacks(self, mock_exists, mock_file):
        """Test getting DPCode with fallbacks."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = DeviceQuirksManager()
        
        # Test with fallbacks
        dpcodes = manager.get_dpcode_with_fallbacks("dj", "brightness_fallback")
        self.assertIn("BRIGHT_VALUE_V2", dpcodes)
        self.assertIn("BRIGHT_VALUE", dpcodes)
        
        # Test without fallbacks
        dpcodes = manager.get_dpcode_with_fallbacks("dj", "nonexistent")
        self.assertEqual(len(dpcodes), 0)
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_get_quirk_summary(self, mock_exists, mock_file):
        """Test getting quirk summary statistics."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = DeviceQuirksManager()
        
        summary = manager.get_quirk_summary()
        
        # Verify summary structure
        self.assertIn("total_quirks", summary)
        self.assertIn("quirk_counts", summary)
        self.assertIn("category_duplicates", summary)
        self.assertIn("multi_entity_devices", summary)
        self.assertIn("dpcode_fallbacks", summary)
        self.assertIn("undocumented_categories", summary)
        
        # Verify some values
        self.assertGreater(summary["total_quirks"], 0)
        self.assertEqual(summary["category_duplicates"], 2)
        self.assertEqual(summary["multi_entity_devices"], 1)
        self.assertEqual(summary["undocumented_categories"], 2)
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_validate_category_against_quirks(self, mock_exists, mock_file):
        """Test validating category against quirks."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = DeviceQuirksManager()
        
        # Test duplicate category
        result = manager.validate_category_against_quirks("cz", {})
        self.assertEqual(result["category_id"], "cz")
        self.assertEqual(result["canonical_category"], "kg")
        self.assertTrue(result["has_quirks"])
        self.assertIn("duplicate", result["warnings"][0])
        
        # Test multi-entity category
        result = manager.validate_category_against_quirks("tgkg", {})
        self.assertTrue(result["has_quirks"])
        self.assertIn("entities", result["warnings"][0])
        
        # Test undocumented category
        result = manager.validate_category_against_quirks("mbd", {})
        self.assertTrue(result["has_quirks"])
        self.assertIn("undocumented", result["warnings"][0])
        
        # Test normal category
        result = manager.validate_category_against_quirks("dj", {})
        self.assertFalse(result["has_quirks"])
        self.assertEqual(len(result["warnings"]), 0)


class TestDeviceQuirk(unittest.TestCase):
    """Test DeviceQuirk data class."""
    
    def test_device_quirk_creation(self):
        """Test creating DeviceQuirk objects."""
        quirk = DeviceQuirk(
            category_id="cz",
            quirk_type=QuirkType.CATEGORY_DUPLICATE,
            description="Category duplicate",
            data={"original_category": "kg"},
            workaround="Use kg instead"
        )
        
        self.assertEqual(quirk.category_id, "cz")
        self.assertEqual(quirk.quirk_type, QuirkType.CATEGORY_DUPLICATE)
        self.assertEqual(quirk.description, "Category duplicate")
        self.assertEqual(quirk.data["original_category"], "kg")
        self.assertEqual(quirk.workaround, "Use kg instead")
    
    def test_applies_to_category(self):
        """Test checking if quirk applies to category."""
        quirk = DeviceQuirk(
            category_id="cz",
            quirk_type=QuirkType.CATEGORY_DUPLICATE,
            description="Test quirk",
            data={"applies_to": ["cz", "pc"]}
        )
        
        # Test direct category match
        self.assertTrue(quirk.applies_to_category("cz"))
        
        # Test applies_to list match
        self.assertTrue(quirk.applies_to_category("pc"))
        
        # Test no match
        self.assertFalse(quirk.applies_to_category("dj"))


class TestEntityMapping(unittest.TestCase):
    """Test EntityMapping data class."""
    
    def test_entity_mapping_creation(self):
        """Test creating EntityMapping objects."""
        mapping = EntityMapping(
            key="switch_led_1",
            brightness_dpcode="bright_value_1",
            entity_type="light",
            additional_dpcodes=["colour_data_1", "temp_value_1"]
        )
        
        self.assertEqual(mapping.key, "switch_led_1")
        self.assertEqual(mapping.brightness_dpcode, "bright_value_1")
        self.assertEqual(mapping.entity_type, "light")
        self.assertEqual(len(mapping.additional_dpcodes), 2)
    
    def test_entity_mapping_defaults(self):
        """Test EntityMapping with default values."""
        mapping = EntityMapping(key="switch_led_1")
        
        self.assertEqual(mapping.key, "switch_led_1")
        self.assertIsNone(mapping.brightness_dpcode)
        self.assertEqual(mapping.entity_type, "light")
        self.assertIsNone(mapping.additional_dpcodes)


class TestDPCodeFallback(unittest.TestCase):
    """Test DPCodeFallback data class."""
    
    def test_dpcode_fallback_creation(self):
        """Test creating DPCodeFallback objects."""
        fallback = DPCodeFallback(
            primary_dpcode="BRIGHT_VALUE_V2",
            fallback_dpcodes=["BRIGHT_VALUE"],
            description="Brightness fallback"
        )
        
        self.assertEqual(fallback.primary_dpcode, "BRIGHT_VALUE_V2")
        self.assertEqual(len(fallback.fallback_dpcodes), 1)
        self.assertEqual(fallback.fallback_dpcodes[0], "BRIGHT_VALUE")
        self.assertEqual(fallback.description, "Brightness fallback")


if __name__ == "__main__":
    unittest.main()