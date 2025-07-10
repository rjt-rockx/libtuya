"""
Tests for the main DeviceIntelligence interface.
"""

import unittest
from unittest.mock import patch, mock_open, MagicMock
import json

from libtuya.intelligence import (
    DeviceIntelligence, DeviceAnalysis, CapabilityInfo
)
from libtuya.intelligence.quirks import QuirkType, DeviceQuirk


class TestDeviceIntelligence(unittest.TestCase):
    """Test the main DeviceIntelligence interface."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create mock data for all components
        self.mock_dpcodes = {
            "description": "Test DPCode definitions",
            "total_count": 5,
            "dpcodes": {
                "BRIGHT_VALUE": "bright_value",
                "SWITCH_LED": "switch_led",
                "COLOUR_DATA": "colour_data",
                "TEMP_VALUE": "temp_value",
                "WORK_MODE": "work_mode"
            }
        }
        
        self.mock_mappings = {
            "description": "Test device mappings",
            "categories": {
                "lights": {
                    "dj": {
                        "name": "Light",
                        "capabilities": ["switch_led", "bright_value", "colour_data", "temp_value"]
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
        
        self.mock_scaling = {
            "description": "Test scaling rules",
            "color_scaling": {
                "DEFAULT_COLOR_TYPE_DATA": {
                    "h_type": {"min": 1, "max": 360, "scale": 0, "step": 1},
                    "s_type": {"min": 1, "max": 255, "scale": 0, "step": 1},
                    "v_type": {"min": 1, "max": 255, "scale": 0, "step": 1}
                }
            }
        }
        
        self.mock_quirks = {
            "description": "Test quirks data",
            "category_duplicates": {
                "mappings": {
                    "cz": "kg"
                }
            },
            "multi_entity_devices": {
                "examples": {}
            },
            "dpcode_fallbacks": {
                "examples": {}
            },
            "undocumented_categories": {
                "categories": {
                    "mbd": "VECINO RGBW light"
                }
            }
        }
    
    def mock_file_reads(self, mock_file):
        """Configure mock file reads for all data files."""
        def side_effect(filename, *args, **kwargs):
            mock_file_obj = MagicMock()
            
            if "dpcodes.json" in str(filename):
                mock_file_obj.read.return_value = json.dumps(self.mock_dpcodes)
            elif "device_mappings.json" in str(filename):
                mock_file_obj.read.return_value = json.dumps(self.mock_mappings)
            elif "scaling_rules.json" in str(filename):
                mock_file_obj.read.return_value = json.dumps(self.mock_scaling)
            elif "quirks.json" in str(filename):
                mock_file_obj.read.return_value = json.dumps(self.mock_quirks)
            
            return mock_file_obj
        
        return side_effect
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_device_intelligence_initialization(self, mock_exists, mock_file):
        """Test DeviceIntelligence initialization."""
        mock_file.side_effect = self.mock_file_reads(mock_file)
        
        intelligence = DeviceIntelligence()
        
        # Verify all managers are initialized
        self.assertIsNotNone(intelligence.dpcode_manager)
        self.assertIsNotNone(intelligence.mapping_manager)
        self.assertIsNotNone(intelligence.scaling_manager)
        self.assertIsNotNone(intelligence.quirks_manager)
        
        # Verify caches are initialized
        self.assertEqual(len(intelligence._device_cache), 0)
        self.assertEqual(len(intelligence._capability_cache), 0)
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_analyze_device(self, mock_exists, mock_file):
        """Test device analysis functionality."""
        mock_file.side_effect = self.mock_file_reads(mock_file)
        
        intelligence = DeviceIntelligence()
        
        # Test analyzing a light device
        analysis = intelligence.analyze_device("dj")
        
        self.assertIsInstance(analysis, DeviceAnalysis)
        self.assertEqual(analysis.category_id, "dj")
        self.assertEqual(analysis.canonical_category, "dj")
        self.assertEqual(analysis.category_name, "Light")
        self.assertEqual(analysis.platform, "lights")
        self.assertIn("switch_led", analysis.capabilities)
        self.assertIn("bright_value", analysis.capabilities)
        self.assertIn("colour_data", analysis.capabilities)
        self.assertFalse(analysis.has_quirks)
        self.assertFalse(analysis.is_multi_entity)
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_analyze_device_with_quirks(self, mock_exists, mock_file):
        """Test analyzing device with quirks."""
        mock_file.side_effect = self.mock_file_reads(mock_file)
        
        intelligence = DeviceIntelligence()
        
        # Test analyzing a duplicate category
        analysis = intelligence.analyze_device("cz")
        
        self.assertEqual(analysis.category_id, "cz")
        self.assertEqual(analysis.canonical_category, "kg")
        self.assertTrue(analysis.has_quirks)
        self.assertGreater(len(analysis.recommendations), 0)
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_analyze_device_caching(self, mock_exists, mock_file):
        """Test device analysis caching."""
        mock_file.side_effect = self.mock_file_reads(mock_file)
        
        intelligence = DeviceIntelligence()
        
        # First analysis
        analysis1 = intelligence.analyze_device("dj")
        self.assertEqual(len(intelligence._device_cache), 1)
        
        # Second analysis should use cache
        analysis2 = intelligence.analyze_device("dj")
        self.assertEqual(len(intelligence._device_cache), 1)
        self.assertEqual(analysis1, analysis2)
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_get_capabilities(self, mock_exists, mock_file):
        """Test getting capabilities for a device category."""
        mock_file.side_effect = self.mock_file_reads(mock_file)
        
        intelligence = DeviceIntelligence()
        
        # Test light capabilities
        capabilities = intelligence.get_capabilities("dj")
        self.assertIn("switch_led", capabilities)
        self.assertIn("bright_value", capabilities)
        self.assertIn("colour_data", capabilities)
        self.assertIn("temp_value", capabilities)
        
        # Test switch capabilities
        capabilities = intelligence.get_capabilities("kg")
        self.assertIn("switch_1", capabilities)
        self.assertIn("switch_2", capabilities)
        
        # Test unknown category
        capabilities = intelligence.get_capabilities("unknown")
        self.assertEqual(len(capabilities), 0)
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_get_dpcodes_for_category(self, mock_exists, mock_file):
        """Test getting DPCodes for a device category."""
        mock_file.side_effect = self.mock_file_reads(mock_file)
        
        intelligence = DeviceIntelligence()
        
        # Test light DPCodes
        dpcodes = intelligence.get_dpcodes_for_category("dj")
        self.assertIn("switch_led", dpcodes)
        self.assertIn("bright_value", dpcodes)
        self.assertIn("colour_data", dpcodes)
        self.assertIn("temp_value", dpcodes)
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_get_capability_info(self, mock_exists, mock_file):
        """Test getting capability information."""
        mock_file.side_effect = self.mock_file_reads(mock_file)
        
        intelligence = DeviceIntelligence()
        
        # Test brightness capability
        info = intelligence.get_capability_info("bright_value")
        self.assertIsInstance(info, CapabilityInfo)
        self.assertEqual(info.dpcode, "bright_value")
        self.assertEqual(info.dpcode_name, "BRIGHT_VALUE")
        self.assertEqual(info.data_type, "integer")
        
        # Test switch capability
        info = intelligence.get_capability_info("switch_led")
        self.assertIsInstance(info, CapabilityInfo)
        self.assertEqual(info.dpcode, "switch_led")
        self.assertEqual(info.data_type, "boolean")
        
        # Test unknown capability
        info = intelligence.get_capability_info("unknown_dpcode")
        self.assertIsNone(info)
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_get_capability_info_caching(self, mock_exists, mock_file):
        """Test capability info caching."""
        mock_file.side_effect = self.mock_file_reads(mock_file)
        
        intelligence = DeviceIntelligence()
        
        # First call
        info1 = intelligence.get_capability_info("bright_value")
        self.assertEqual(len(intelligence._capability_cache), 1)
        
        # Second call should use cache
        info2 = intelligence.get_capability_info("bright_value")
        self.assertEqual(len(intelligence._capability_cache), 1)
        self.assertEqual(info1, info2)
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_scale_value(self, mock_exists, mock_file):
        """Test value scaling functionality."""
        mock_file.side_effect = self.mock_file_reads(mock_file)
        
        intelligence = DeviceIntelligence()
        
        # Test scaling a brightness value
        scaled = intelligence.scale_value("bright_value", 500, "dj")
        self.assertIsInstance(scaled, (int, float))
        
        # Test scaling with target range
        scaled = intelligence.scale_value("bright_value", 500, "dj", (0, 255))
        self.assertIsInstance(scaled, (int, float))
        
        # Test scaling unknown DPCode
        scaled = intelligence.scale_value("unknown_dpcode", 500, "dj")
        self.assertEqual(scaled, 500)  # Should return original value
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_convert_color_data(self, mock_exists, mock_file):
        """Test color data conversion."""
        mock_file.side_effect = self.mock_file_reads(mock_file)
        
        intelligence = DeviceIntelligence()
        
        # Test HSV conversion
        hsv = intelligence.convert_color_data(255, 0, 0, "hsv")
        self.assertEqual(len(hsv), 3)
        self.assertEqual(hsv[0], 0)  # Red hue
        self.assertEqual(hsv[1], 100)  # Full saturation
        self.assertEqual(hsv[2], 100)  # Full value
        
        # Test hex conversion
        hex_color = intelligence.convert_color_data(255, 0, 0, "hex")
        self.assertEqual(hex_color, "#ff0000")
        
        # Test RGB conversion
        rgb = intelligence.convert_color_data(255, 0, 0, "rgb")
        self.assertEqual(rgb, (255, 0, 0))
        
        # Test invalid format
        with self.assertRaises(ValueError):
            intelligence.convert_color_data(255, 0, 0, "invalid")
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_suggest_device_category(self, mock_exists, mock_file):
        """Test device category suggestion."""
        mock_file.side_effect = self.mock_file_reads(mock_file)
        
        intelligence = DeviceIntelligence()
        
        # Test with light DPCodes
        suggestions = intelligence.suggest_device_category(["switch_led", "bright_value", "colour_data"])
        self.assertIsInstance(suggestions, list)
        
        # Test with empty DPCodes
        suggestions = intelligence.suggest_device_category([])
        self.assertEqual(len(suggestions), 0)
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_validate_device_setup(self, mock_exists, mock_file):
        """Test device setup validation."""
        mock_file.side_effect = self.mock_file_reads(mock_file)
        
        intelligence = DeviceIntelligence()
        
        # Test valid setup
        result = intelligence.validate_device_setup("dj", ["switch_led", "bright_value", "colour_data"])
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["missing_dpcodes"]), 1)  # temp_value is missing
        
        # Test invalid setup
        result = intelligence.validate_device_setup("dj", ["unknown_dpcode"])
        self.assertFalse(result["valid"])
        self.assertGreater(len(result["missing_dpcodes"]), 0)
        
        # Verify result structure
        self.assertIn("category_analysis", result)
        self.assertIn("expected_dpcodes", result)
        self.assertIn("available_dpcodes", result)
        self.assertIn("recommendations", result)
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_get_system_stats(self, mock_exists, mock_file):
        """Test getting system statistics."""
        mock_file.side_effect = self.mock_file_reads(mock_file)
        
        intelligence = DeviceIntelligence()
        
        # Trigger some caching
        intelligence.analyze_device("dj")
        intelligence.get_capability_info("bright_value")
        
        stats = intelligence.get_system_stats()
        
        # Verify stats structure
        self.assertIn("dpcodes", stats)
        self.assertIn("device_categories", stats)
        self.assertIn("quirks", stats)
        self.assertIn("cache_stats", stats)
        
        # Verify cache stats
        self.assertEqual(stats["cache_stats"]["analyzed_devices"], 1)
        self.assertEqual(stats["cache_stats"]["cached_capabilities"], 1)
        
        # Verify DPCode stats
        self.assertEqual(stats["dpcodes"]["total_count"], 5)


class TestDeviceAnalysis(unittest.TestCase):
    """Test DeviceAnalysis data class."""
    
    def test_device_analysis_creation(self):
        """Test creating DeviceAnalysis objects."""
        analysis = DeviceAnalysis(
            category_id="dj",
            canonical_category="dj",
            category_name="Light",
            platform="lights",
            capabilities=["switch_led", "bright_value"],
            supported_dpcodes=["switch_led", "bright_value"],
            quirks=[],
            has_quirks=False,
            is_multi_entity=False,
            entity_mappings=[],
            scaling_info={},
            recommendations=[]
        )
        
        self.assertEqual(analysis.category_id, "dj")
        self.assertEqual(analysis.canonical_category, "dj")
        self.assertEqual(analysis.category_name, "Light")
        self.assertEqual(analysis.platform, "lights")
        self.assertEqual(len(analysis.capabilities), 2)
        self.assertEqual(len(analysis.supported_dpcodes), 2)
        self.assertFalse(analysis.has_quirks)
        self.assertFalse(analysis.is_multi_entity)


class TestCapabilityInfo(unittest.TestCase):
    """Test CapabilityInfo data class."""
    
    def test_capability_info_creation(self):
        """Test creating CapabilityInfo objects."""
        info = CapabilityInfo(
            dpcode="bright_value",
            dpcode_name="BRIGHT_VALUE",
            fallback_dpcodes=["bright_value_v2"],
            data_type="integer",
            scaling_info=None,
            description="Brightness control"
        )
        
        self.assertEqual(info.dpcode, "bright_value")
        self.assertEqual(info.dpcode_name, "BRIGHT_VALUE")
        self.assertEqual(len(info.fallback_dpcodes), 1)
        self.assertEqual(info.data_type, "integer")
        self.assertIsNone(info.scaling_info)
        self.assertEqual(info.description, "Brightness control")


if __name__ == "__main__":
    unittest.main()