"""
Tests for value scaling and conversion functionality.
"""

import unittest
from unittest.mock import patch, mock_open
import json

from libtuya.intelligence.scaling import (
    IntegerTypeData, EnumTypeData, ColorTypeData, ValueScalingManager,
    scaling_manager, remap_value
)


class TestIntegerTypeData(unittest.TestCase):
    """Test IntegerTypeData functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.brightness_data = IntegerTypeData(
            dpcode="bright_value",
            min_value=10,
            max_value=1000,
            scale=0,
            step=1,
            unit="brightness"
        )
        
        self.temperature_data = IntegerTypeData(
            dpcode="temp_value",
            min_value=1000,
            max_value=10000,
            scale=0,
            step=1,
            unit="K"
        )
    
    def test_scale_value(self):
        """Test scaling device values."""
        # Test with scale=0 (no scaling)
        self.assertEqual(self.brightness_data.scale_value(500), 500)
        
        # Test with scale=1 (divide by 10)
        scaled_data = IntegerTypeData("test", 0, 100, scale=1)
        self.assertEqual(scaled_data.scale_value(100), 10.0)
        
        # Test with scale=2 (divide by 100)
        scaled_data = IntegerTypeData("test", 0, 100, scale=2)
        self.assertEqual(scaled_data.scale_value(500), 5.0)
    
    def test_scale_value_back(self):
        """Test scaling values back to device range."""
        # Test with scale=0 (no scaling)
        self.assertEqual(self.brightness_data.scale_value_back(500), 500)
        
        # Test with scale=1 (multiply by 10)
        scaled_data = IntegerTypeData("test", 0, 100, scale=1)
        self.assertEqual(scaled_data.scale_value_back(10), 100)
        
        # Test with scale=2 (multiply by 100)
        scaled_data = IntegerTypeData("test", 0, 100, scale=2)
        self.assertEqual(scaled_data.scale_value_back(5), 500)
    
    def test_remap_value_to(self):
        """Test remapping values to target range."""
        # Test brightness remapping to 0-255 range
        remapped = self.brightness_data.remap_value_to(505, 0, 255)
        self.assertAlmostEqual(remapped, 127.5, places=1)
        
        # Test temperature remapping
        remapped = self.temperature_data.remap_value_to(5500, 0, 100)
        self.assertEqual(remapped, 50.0)
    
    def test_remap_value_from(self):
        """Test remapping values from target range."""
        # Test brightness remapping from 0-255 range
        remapped = self.brightness_data.remap_value_from(127.5, 0, 255)
        self.assertAlmostEqual(remapped, 505, places=1)
        
        # Test temperature remapping
        remapped = self.temperature_data.remap_value_from(50, 0, 100)
        self.assertEqual(remapped, 5500.0)


class TestEnumTypeData(unittest.TestCase):
    """Test EnumTypeData functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.work_mode_data = EnumTypeData(
            dpcode="work_mode",
            range_values=["white", "colour", "scene", "music"]
        )
    
    def test_is_valid_value(self):
        """Test enum value validation."""
        # Test valid values
        self.assertTrue(self.work_mode_data.is_valid_value("white"))
        self.assertTrue(self.work_mode_data.is_valid_value("colour"))
        self.assertTrue(self.work_mode_data.is_valid_value("scene"))
        self.assertTrue(self.work_mode_data.is_valid_value("music"))
        
        # Test invalid values
        self.assertFalse(self.work_mode_data.is_valid_value("invalid"))
        self.assertFalse(self.work_mode_data.is_valid_value(""))
        self.assertFalse(self.work_mode_data.is_valid_value("WHITE"))  # case sensitive
    
    def test_get_valid_values(self):
        """Test getting all valid enum values."""
        valid_values = self.work_mode_data.get_valid_values()
        
        self.assertEqual(len(valid_values), 4)
        self.assertIn("white", valid_values)
        self.assertIn("colour", valid_values)
        self.assertIn("scene", valid_values)
        self.assertIn("music", valid_values)
        
        # Test that returned list is a copy
        valid_values.append("new_value")
        self.assertEqual(len(self.work_mode_data.range_values), 4)


class TestColorTypeData(unittest.TestCase):
    """Test ColorTypeData functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.color_data = ColorTypeData(
            h_min=1,
            h_max=360,
            s_min=1,
            s_max=255,
            v_min=1,
            v_max=255,
            h_scale=0,
            s_scale=0,
            v_scale=0
        )
    
    def test_color_type_data_creation(self):
        """Test creating ColorTypeData objects."""
        self.assertEqual(self.color_data.h_min, 1)
        self.assertEqual(self.color_data.h_max, 360)
        self.assertEqual(self.color_data.s_min, 1)
        self.assertEqual(self.color_data.s_max, 255)
        self.assertEqual(self.color_data.v_min, 1)
        self.assertEqual(self.color_data.v_max, 255)


class TestRemapValue(unittest.TestCase):
    """Test remap_value function."""
    
    def test_basic_remapping(self):
        """Test basic value remapping."""
        # Test 0-255 to 0-100 range
        self.assertEqual(remap_value(0, 0, 255, 0, 100), 0)
        self.assertEqual(remap_value(255, 0, 255, 0, 100), 100)
        self.assertEqual(remap_value(127.5, 0, 255, 0, 100), 50)
        
        # Test 10-1000 to 0-255 range
        self.assertEqual(remap_value(10, 10, 1000, 0, 255), 0)
        self.assertEqual(remap_value(1000, 10, 1000, 0, 255), 255)
        self.assertEqual(remap_value(505, 10, 1000, 0, 255), 127.5)
    
    def test_reverse_remapping(self):
        """Test reverse value remapping."""
        # Test with reverse=True
        result = remap_value(100, 0, 255, 0, 100, reverse=True)
        # Value should be reversed: 255 - 100 + 0 = 155
        # Then mapped: 155/255 * 100 = ~60.78
        self.assertAlmostEqual(result, 60.78, places=1)
    
    def test_same_range_remapping(self):
        """Test remapping within same range."""
        # Test with same source and target ranges
        self.assertEqual(remap_value(100, 0, 255, 0, 255), 100)
        self.assertEqual(remap_value(50, 0, 100, 0, 100), 50)


class TestValueScalingManager(unittest.TestCase):
    """Test ValueScalingManager functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_scaling_data = {
            "description": "Test scaling rules",
            "color_scaling": {
                "DEFAULT_COLOR_TYPE_DATA": {
                    "h_type": {"min": 1, "max": 360, "scale": 0, "step": 1},
                    "s_type": {"min": 1, "max": 255, "scale": 0, "step": 1},
                    "v_type": {"min": 1, "max": 255, "scale": 0, "step": 1}
                },
                "DEFAULT_COLOR_TYPE_DATA_V2": {
                    "h_type": {"min": 1, "max": 360, "scale": 0, "step": 1},
                    "s_type": {"min": 1, "max": 1000, "scale": 0, "step": 1},
                    "v_type": {"min": 1, "max": 1000, "scale": 0, "step": 1}
                }
            }
        }
        
        self.mock_json_data = json.dumps(self.test_scaling_data)
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_load_data(self, mock_exists, mock_file):
        """Test loading scaling data from JSON file."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = ValueScalingManager()
        
        # Verify color types were loaded
        self.assertIn("default", manager._color_types)
        self.assertIn("default_v2", manager._color_types)
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_create_integer_type(self, mock_exists, mock_file):
        """Test creating IntegerTypeData instances."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = ValueScalingManager()
        
        integer_type = manager.create_integer_type("bright_value", 10, 1000, 0, 1, "brightness")
        
        self.assertEqual(integer_type.dpcode, "bright_value")
        self.assertEqual(integer_type.min_value, 10)
        self.assertEqual(integer_type.max_value, 1000)
        self.assertEqual(integer_type.scale, 0)
        self.assertEqual(integer_type.step, 1)
        self.assertEqual(integer_type.unit, "brightness")
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_create_enum_type(self, mock_exists, mock_file):
        """Test creating EnumTypeData instances."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = ValueScalingManager()
        
        enum_type = manager.create_enum_type("work_mode", ["white", "colour", "scene"])
        
        self.assertEqual(enum_type.dpcode, "work_mode")
        self.assertEqual(len(enum_type.range_values), 3)
        self.assertIn("white", enum_type.range_values)
        self.assertIn("colour", enum_type.range_values)
        self.assertIn("scene", enum_type.range_values)
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_scale_brightness(self, mock_exists, mock_file):
        """Test brightness scaling."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = ValueScalingManager()
        
        # Test default scaling (10-1000 to 0-255)
        scaled = manager.scale_brightness(505)
        self.assertEqual(scaled, 128)  # Rounded value
        
        # Test custom scaling
        scaled = manager.scale_brightness(50, 0, 100, 0, 255)
        self.assertEqual(scaled, 128)  # 50/100 * 255 = 127.5, rounded to 128
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_scale_color_temp(self, mock_exists, mock_file):
        """Test color temperature scaling."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = ValueScalingManager()
        
        # Test with mireds conversion
        scaled = manager.scale_color_temp(5000, use_mireds=True)
        self.assertEqual(scaled, 200)  # 1000000 / 5000 = 200
        
        # Test without mireds conversion
        scaled = manager.scale_color_temp(5000, use_mireds=False)
        self.assertEqual(scaled, 5000)  # Remapped to same range
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_hsv_rgb_conversion(self, mock_exists, mock_file):
        """Test HSV to RGB conversion."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = ValueScalingManager()
        
        # Test pure red
        r, g, b = manager.convert_hsv_to_rgb(0, 100, 100)
        self.assertEqual(r, 255)
        self.assertEqual(g, 0)
        self.assertEqual(b, 0)
        
        # Test pure green
        r, g, b = manager.convert_hsv_to_rgb(120, 100, 100)
        self.assertEqual(r, 0)
        self.assertEqual(g, 255)
        self.assertEqual(b, 0)
        
        # Test pure blue
        r, g, b = manager.convert_hsv_to_rgb(240, 100, 100)
        self.assertEqual(r, 0)
        self.assertEqual(g, 0)
        self.assertEqual(b, 255)
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_rgb_hsv_conversion(self, mock_exists, mock_file):
        """Test RGB to HSV conversion."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = ValueScalingManager()
        
        # Test pure red
        h, s, v = manager.convert_rgb_to_hsv(255, 0, 0)
        self.assertEqual(h, 0)
        self.assertEqual(s, 100)
        self.assertEqual(v, 100)
        
        # Test pure green
        h, s, v = manager.convert_rgb_to_hsv(0, 255, 0)
        self.assertEqual(h, 120)
        self.assertEqual(s, 100)
        self.assertEqual(v, 100)
        
        # Test pure blue
        h, s, v = manager.convert_rgb_to_hsv(0, 0, 255)
        self.assertEqual(h, 240)
        self.assertEqual(s, 100)
        self.assertEqual(v, 100)
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_validate_color_value(self, mock_exists, mock_file):
        """Test color value validation."""
        mock_file.return_value.read.return_value = self.mock_json_data
        
        manager = ValueScalingManager()
        
        # Test valid hex colors
        self.assertTrue(manager.validate_color_value("#FF0000"))
        self.assertTrue(manager.validate_color_value("#00FF00"))
        self.assertTrue(manager.validate_color_value("#0000FF"))
        
        # Test valid HSV colors
        self.assertTrue(manager.validate_color_value("hsv(0, 100, 100)"))
        self.assertTrue(manager.validate_color_value("hsv(120, 50, 75)"))
        
        # Test invalid colors
        self.assertFalse(manager.validate_color_value("invalid"))
        self.assertFalse(manager.validate_color_value("#GGGGGG"))
        self.assertFalse(manager.validate_color_value("hsv(400, 100, 100)"))  # H > 360


if __name__ == "__main__":
    unittest.main()