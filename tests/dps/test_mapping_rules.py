"""
Tests for DPS mapping rules

This module tests the bulletproof DPS mapping heuristics for all device categories.
"""

import pytest
from libtuya.dps.mapping_rules import DPSMappingRules, DPSConfidence, DPSMapping


class TestDPSMappingRules:
    """Test DPS mapping rules functionality"""
    
    def test_get_mappings_for_category_lights(self):
        """Test DPS mappings for light categories"""
        # Test standard light
        mappings = DPSMappingRules.get_mappings_for_category("dj")
        assert 1 in mappings
        assert mappings[1] == ("switch_led", DPSConfidence.HIGH, "Standard light switch")
        assert 3 in mappings
        assert mappings[3] == ("bright_value", DPSConfidence.HIGH, "Brightness control")
        assert 5 in mappings
        assert mappings[5] == ("colour_data", DPSConfidence.HIGH, "RGB color data")
        
        # Test string lights
        mappings = DPSMappingRules.get_mappings_for_category("dc")
        assert 1 in mappings
        assert mappings[1] == ("switch_led", DPSConfidence.HIGH, "String light switch")
        
        # Test ceiling light
        mappings = DPSMappingRules.get_mappings_for_category("xdd")
        assert 6 in mappings
        assert mappings[6] == ("switch_night_light", DPSConfidence.MEDIUM, "Night light switch")
    
    def test_get_mappings_for_category_switches(self):
        """Test DPS mappings for switch categories"""
        # Test standard switch
        mappings = DPSMappingRules.get_mappings_for_category("kg")
        assert 1 in mappings
        assert mappings[1] == ("switch", DPSConfidence.HIGH, "Standard switch")
        assert 2 in mappings
        assert mappings[2] == ("switch_1", DPSConfidence.HIGH, "Switch channel 1")
        assert 10 in mappings
        assert mappings[10] == ("child_lock", DPSConfidence.MEDIUM, "Child lock")
        
        # Test power socket
        mappings = DPSMappingRules.get_mappings_for_category("pc")
        assert 8 in mappings
        assert mappings[8] == ("switch_usb1", DPSConfidence.MEDIUM, "USB port 1")
    
    def test_get_mappings_for_category_climate(self):
        """Test DPS mappings for climate categories"""
        # Test air conditioner
        mappings = DPSMappingRules.get_mappings_for_category("kt")
        assert 1 in mappings
        assert mappings[1] == ("switch", DPSConfidence.HIGH, "AC power")
        assert 2 in mappings
        assert mappings[2] == ("temp_set", DPSConfidence.HIGH, "AC temperature set")
        assert 5 in mappings
        assert mappings[5] == ("fan_speed", DPSConfidence.HIGH, "AC fan speed")
        
        # Test thermostat
        mappings = DPSMappingRules.get_mappings_for_category("wk")
        assert 5 in mappings
        assert mappings[5] == ("child_lock", DPSConfidence.MEDIUM, "Thermostat child lock")
    
    def test_get_mappings_for_category_fans(self):
        """Test DPS mappings for fan categories"""
        mappings = DPSMappingRules.get_mappings_for_category("fs")
        assert 1 in mappings
        assert mappings[1] == ("switch", DPSConfidence.HIGH, "Fan power switch")
        assert 2 in mappings
        assert mappings[2] == ("fan_speed", DPSConfidence.HIGH, "Fan speed")
        assert 3 in mappings
        assert mappings[3] == ("fan_direction", DPSConfidence.HIGH, "Fan direction")
        assert 4 in mappings
        assert mappings[4] == ("light", DPSConfidence.HIGH, "Fan light")
    
    def test_duplicate_mappings(self):
        """Test duplicate category mappings"""
        # Test that duplicate categories map to the same base category
        cz_mappings = DPSMappingRules.get_mappings_for_category("cz")
        kg_mappings = DPSMappingRules.get_mappings_for_category("kg")
        assert cz_mappings == kg_mappings
        
        pc_mappings = DPSMappingRules.get_mappings_for_category("pc")
        assert pc_mappings == kg_mappings  # pc also maps to kg
    
    def test_get_universal_mappings(self):
        """Test universal DPS mappings"""
        universal = DPSMappingRules.get_universal_mappings()
        assert 1 in universal
        assert universal[1] == ("switch", DPSConfidence.HIGH, "DPS 1 is switch in 99% of devices")
        assert 20 in universal
        assert universal[20] == ("switch", DPSConfidence.MEDIUM, "DPS 20 is alternate switch pattern")
    
    def test_get_fallback_mappings(self):
        """Test fallback DPS mappings"""
        fallback = DPSMappingRules.get_fallback_mappings()
        assert 1 in fallback
        assert fallback[1] == ("switch", DPSConfidence.HIGH, "DPS 1 universal switch")
        assert 3 in fallback
        assert fallback[3] == ("brightness", DPSConfidence.MEDIUM, "DPS 3 common brightness")
        assert 5 in fallback
        assert fallback[5] == ("color", DPSConfidence.MEDIUM, "DPS 5 common color")
    
    def test_predict_dps_for_capability(self):
        """Test DPS prediction for capabilities"""
        # Test switch capability with category
        predictions = DPSMappingRules.predict_dps_for_capability("switch_led", "dj")
        assert len(predictions) > 0
        assert predictions[0][0] == 1  # DPS 1
        assert predictions[0][1] == DPSConfidence.HIGH
        
        # Test brightness capability
        predictions = DPSMappingRules.predict_dps_for_capability("bright_value", "dj")
        assert len(predictions) > 0
        assert predictions[0][0] == 3  # DPS 3
        assert predictions[0][1] == DPSConfidence.HIGH
        
        # Test color capability
        predictions = DPSMappingRules.predict_dps_for_capability("colour_data", "dj")
        assert len(predictions) > 0
        assert predictions[0][0] == 5  # DPS 5
        assert predictions[0][1] == DPSConfidence.HIGH
        
        # Test without category (fallback)
        predictions = DPSMappingRules.predict_dps_for_capability("switch")
        assert len(predictions) > 0
        assert 1 in [p[0] for p in predictions]  # Should include DPS 1
    
    def test_get_capability_for_dps(self):
        """Test capability prediction for DPS indices"""
        # Test with category
        result = DPSMappingRules.get_capability_for_dps(1, "dj")
        assert result is not None
        assert result[0] == "switch_led"
        assert result[1] == DPSConfidence.HIGH
        
        result = DPSMappingRules.get_capability_for_dps(3, "dj")
        assert result is not None
        assert result[0] == "bright_value"
        assert result[1] == DPSConfidence.HIGH
        
        # Test without category (universal)
        result = DPSMappingRules.get_capability_for_dps(1)
        assert result is not None
        assert result[0] == "switch"
        assert result[1] == DPSConfidence.HIGH
        
        # Test fallback
        result = DPSMappingRules.get_capability_for_dps(999)
        assert result is None
    
    def test_get_common_dps_ranges(self):
        """Test common DPS ranges"""
        ranges = DPSMappingRules.get_common_dps_ranges()
        assert len(ranges) == 3
        assert ranges[0] == range(1, 12)
        assert ranges[1] == range(20, 32)
        assert ranges[2] == range(100, 112)
    
    def test_helper_methods(self):
        """Test helper methods for DPS classification"""
        # Test switch detection
        assert DPSMappingRules.is_switch_dps(1) == True
        assert DPSMappingRules.is_switch_dps(20) == True
        assert DPSMappingRules.is_switch_dps(2) == True
        assert DPSMappingRules.is_switch_dps(100) == False
        
        # Test brightness detection
        assert DPSMappingRules.is_brightness_dps(3) == True
        assert DPSMappingRules.is_brightness_dps(22) == True
        assert DPSMappingRules.is_brightness_dps(7) == True
        assert DPSMappingRules.is_brightness_dps(1) == False
        
        # Test color detection
        assert DPSMappingRules.is_color_dps(5) == True
        assert DPSMappingRules.is_color_dps(24) == True
        assert DPSMappingRules.is_color_dps(1) == False
    
    def test_get_supported_categories(self):
        """Test supported categories list"""
        categories = DPSMappingRules.get_supported_categories()
        assert "dj" in categories  # Standard light
        assert "kg" in categories  # Standard switch
        assert "kt" in categories  # Air conditioner
        assert "fs" in categories  # Fan
        assert "cz" in categories  # Duplicate mapping
        assert "pc" in categories  # Another duplicate
        assert len(categories) > 30  # Should have many categories
    
    def test_unknown_category(self):
        """Test behavior with unknown category"""
        mappings = DPSMappingRules.get_mappings_for_category("unknown_category")
        assert mappings == {}
        
        # Should still get fallback predictions
        predictions = DPSMappingRules.predict_dps_for_capability("switch", "unknown_category")
        assert len(predictions) > 0
        assert predictions[0][0] == 1  # Should still predict DPS 1 for switch
    
    def test_confidence_levels(self):
        """Test confidence level values"""
        assert DPSConfidence.HIGH.value == 0.9
        assert DPSConfidence.MEDIUM.value == 0.6
        assert DPSConfidence.LOW.value == 0.3
        assert DPSConfidence.UNKNOWN.value == 0.0
        
        # Test ordering
        assert DPSConfidence.HIGH.value > DPSConfidence.MEDIUM.value
        assert DPSConfidence.MEDIUM.value > DPSConfidence.LOW.value
        assert DPSConfidence.LOW.value > DPSConfidence.UNKNOWN.value
    
    def test_complex_devices(self):
        """Test mapping rules for complex devices"""
        # Test dimmer switch with multiple channels
        mappings = DPSMappingRules.get_mappings_for_category("tgkg")
        assert 1 in mappings
        assert mappings[1] == ("switch_led_1", DPSConfidence.HIGH, "Dimmer switch channel 1")
        assert 5 in mappings
        assert mappings[5] == ("switch_led_2", DPSConfidence.HIGH, "Dimmer switch channel 2")
        assert 9 in mappings
        assert mappings[9] == ("switch_led_3", DPSConfidence.HIGH, "Dimmer switch channel 3")
        
        # Test camera with many capabilities
        mappings = DPSMappingRules.get_mappings_for_category("sp")
        assert 1 in mappings
        assert mappings[1] == ("switch", DPSConfidence.HIGH, "Camera power")
        assert 2 in mappings
        assert mappings[2] == ("floodlight_switch", DPSConfidence.HIGH, "Camera floodlight")
        assert len(mappings) >= 10  # Should have many mappings
    
    def test_edge_cases(self):
        """Test edge cases and error conditions"""
        # Test empty strings
        mappings = DPSMappingRules.get_mappings_for_category("")
        assert mappings == {}
        
        # Test None values
        mappings = DPSMappingRules.get_mappings_for_category(None)
        assert mappings == {}
        
        # Test predictions with empty capability
        predictions = DPSMappingRules.predict_dps_for_capability("", "dj")
        assert len(predictions) == 0
        
        # Test capability for DPS with invalid category
        result = DPSMappingRules.get_capability_for_dps(1, "")
        assert result is not None  # Should fall back to universal
        assert result[0] == "switch"