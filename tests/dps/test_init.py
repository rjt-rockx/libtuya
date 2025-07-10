"""
Tests for DPS module initialization and convenience functions

This module tests the main DPS module interface and convenience functions.
"""

import pytest
from libtuya.dps import (
    DPSMapper, DeviceInfo, DPSMappingInfo, DPSDiscoveryEngine, 
    DPSMappingRules, DPSConfidence, create_device_info, 
    validate_device_category, get_supported_categories, create_mapper,
    DEVICE_CATEGORIES, COMMON_CAPABILITIES, CONFIDENCE_LEVELS,
    DEFAULT_DPS_RANGES, COMMON_DPS_PATTERNS, ERROR_CODES
)


class TestModuleInterface:
    """Test module interface and exports"""
    
    def test_main_classes_exported(self):
        """Test that main classes are exported"""
        # Test main interface classes
        assert DPSMapper is not None
        assert DeviceInfo is not None
        assert DPSMappingInfo is not None
        
        # Test discovery engine classes
        assert DPSDiscoveryEngine is not None
        
        # Test mapping rules classes
        assert DPSMappingRules is not None
        assert DPSConfidence is not None
    
    def test_convenience_functions_exported(self):
        """Test that convenience functions are exported"""
        assert create_device_info is not None
        assert validate_device_category is not None
        assert get_supported_categories is not None
        assert create_mapper is not None
    
    def test_constants_exported(self):
        """Test that constants are exported"""
        assert isinstance(DEVICE_CATEGORIES, dict)
        assert isinstance(COMMON_CAPABILITIES, dict)
        assert isinstance(CONFIDENCE_LEVELS, dict)
        assert isinstance(DEFAULT_DPS_RANGES, list)
        assert isinstance(COMMON_DPS_PATTERNS, dict)
        assert isinstance(ERROR_CODES, dict)


class TestConvenienceFunctions:
    """Test convenience functions"""
    
    def test_create_device_info(self):
        """Test create_device_info function"""
        # Test basic creation
        device_info = create_device_info("test_device", "dj")
        assert device_info.device_id == "test_device"
        assert device_info.category == "dj"
        assert device_info.name is None
        
        # Test with additional parameters
        device_info = create_device_info(
            "test_device", 
            "dj", 
            name="Test Light",
            model="TL001",
            local_key="1234567890abcdef"
        )
        assert device_info.device_id == "test_device"
        assert device_info.category == "dj"
        assert device_info.name == "Test Light"
        assert device_info.model == "TL001"
        assert device_info.local_key == "1234567890abcdef"
        
        # Test with invalid parameters
        with pytest.raises(ValueError):
            create_device_info("", "dj")
        
        with pytest.raises(ValueError):
            create_device_info("test_device", "")
    
    def test_validate_device_category(self):
        """Test validate_device_category function"""
        # Test valid categories
        assert validate_device_category("dj") == True
        assert validate_device_category("kg") == True
        assert validate_device_category("kt") == True
        assert validate_device_category("fs") == True
        
        # Test invalid categories
        assert validate_device_category("invalid") == False
        assert validate_device_category("") == False
        assert validate_device_category("unknown") == False
    
    def test_get_supported_categories(self):
        """Test get_supported_categories function"""
        categories = get_supported_categories()
        assert isinstance(categories, list)
        assert len(categories) > 0
        assert "dj" in categories
        assert "kg" in categories
        assert "kt" in categories
        assert "fs" in categories
    
    def test_create_mapper(self):
        """Test create_mapper function"""
        # Test default creation
        mapper = create_mapper()
        assert isinstance(mapper, DPSMapper)
        assert mapper.enable_cache == True
        
        # Test with custom parameters
        mapper = create_mapper(
            enable_cache=False,
            discovery_timeout=60.0
        )
        assert isinstance(mapper, DPSMapper)
        assert mapper.enable_cache == False
        assert mapper.discovery_engine.discovery_timeout == 60.0


class TestConstants:
    """Test module constants"""
    
    def test_device_categories(self):
        """Test DEVICE_CATEGORIES constant"""
        assert isinstance(DEVICE_CATEGORIES, dict)
        assert len(DEVICE_CATEGORIES) > 0
        
        # Test some known categories
        assert DEVICE_CATEGORIES["dj"] == "Light"
        assert DEVICE_CATEGORIES["kg"] == "Switch"
        assert DEVICE_CATEGORIES["kt"] == "Air Conditioner"
        assert DEVICE_CATEGORIES["fs"] == "Fan"
        
        # Test all values are strings
        for category, name in DEVICE_CATEGORIES.items():
            assert isinstance(category, str)
            assert isinstance(name, str)
            assert len(category) > 0
            assert len(name) > 0
    
    def test_common_capabilities(self):
        """Test COMMON_CAPABILITIES constant"""
        assert isinstance(COMMON_CAPABILITIES, dict)
        assert len(COMMON_CAPABILITIES) > 0
        
        # Test some known capabilities
        assert "switch" in COMMON_CAPABILITIES
        assert "switch_led" in COMMON_CAPABILITIES
        assert "bright_value" in COMMON_CAPABILITIES
        assert "colour_data" in COMMON_CAPABILITIES
        
        # Test all values are strings
        for capability, description in COMMON_CAPABILITIES.items():
            assert isinstance(capability, str)
            assert isinstance(description, str)
            assert len(capability) > 0
            assert len(description) > 0
    
    def test_confidence_levels(self):
        """Test CONFIDENCE_LEVELS constant"""
        assert isinstance(CONFIDENCE_LEVELS, dict)
        assert len(CONFIDENCE_LEVELS) == 4
        
        # Test confidence values
        assert CONFIDENCE_LEVELS["HIGH"] == 0.9
        assert CONFIDENCE_LEVELS["MEDIUM"] == 0.6
        assert CONFIDENCE_LEVELS["LOW"] == 0.3
        assert CONFIDENCE_LEVELS["UNKNOWN"] == 0.0
        
        # Test all values are numeric
        for level, value in CONFIDENCE_LEVELS.items():
            assert isinstance(level, str)
            assert isinstance(value, (int, float))
            assert 0.0 <= value <= 1.0
    
    def test_default_dps_ranges(self):
        """Test DEFAULT_DPS_RANGES constant"""
        assert isinstance(DEFAULT_DPS_RANGES, list)
        assert len(DEFAULT_DPS_RANGES) == 3
        
        # Test specific ranges
        assert DEFAULT_DPS_RANGES[0] == range(1, 12)
        assert DEFAULT_DPS_RANGES[1] == range(20, 32)
        assert DEFAULT_DPS_RANGES[2] == range(100, 112)
        
        # Test all elements are ranges
        for r in DEFAULT_DPS_RANGES:
            assert isinstance(r, range)
            assert len(r) > 0
    
    def test_common_dps_patterns(self):
        """Test COMMON_DPS_PATTERNS constant"""
        assert isinstance(COMMON_DPS_PATTERNS, dict)
        assert len(COMMON_DPS_PATTERNS) > 0
        
        # Test some known patterns
        assert COMMON_DPS_PATTERNS[1] == "switch"
        assert COMMON_DPS_PATTERNS[3] == "brightness"
        assert COMMON_DPS_PATTERNS[5] == "color"
        assert COMMON_DPS_PATTERNS[20] == "switch"
        
        # Test all keys are integers and values are strings
        for dps, capability in COMMON_DPS_PATTERNS.items():
            assert isinstance(dps, int)
            assert isinstance(capability, str)
            assert dps > 0
            assert len(capability) > 0
    
    def test_error_codes(self):
        """Test ERROR_CODES constant"""
        assert isinstance(ERROR_CODES, dict)
        assert len(ERROR_CODES) > 0
        
        # Test some known error codes
        assert "DISCOVERY_TIMEOUT" in ERROR_CODES
        assert "DEVICE_UNREACHABLE" in ERROR_CODES
        assert "NO_DPS_FOUND" in ERROR_CODES
        assert "INVALID_CATEGORY" in ERROR_CODES
        
        # Test all values are strings
        for code, message in ERROR_CODES.items():
            assert isinstance(code, str)
            assert isinstance(message, str)
            assert len(code) > 0
            assert len(message) > 0


class TestModuleDefaults:
    """Test module default values"""
    
    def test_module_metadata(self):
        """Test module metadata"""
        import libtuya.dps
        
        assert hasattr(libtuya.dps, '__version__')
        assert hasattr(libtuya.dps, '__author__')
        assert hasattr(libtuya.dps, '__description__')
        
        assert isinstance(libtuya.dps.__version__, str)
        assert isinstance(libtuya.dps.__author__, str)
        assert isinstance(libtuya.dps.__description__, str)
    
    def test_default_timeout(self):
        """Test default timeout value"""
        import libtuya.dps
        
        assert hasattr(libtuya.dps, 'DEFAULT_DISCOVERY_TIMEOUT')
        assert libtuya.dps.DEFAULT_DISCOVERY_TIMEOUT == 30.0
    
    def test_default_probe_delay(self):
        """Test default probe delay value"""
        import libtuya.dps
        
        assert hasattr(libtuya.dps, 'DEFAULT_PROBE_DELAY')
        assert libtuya.dps.DEFAULT_PROBE_DELAY == 0.1
    
    def test_default_max_retries(self):
        """Test default max retries value"""
        import libtuya.dps
        
        assert hasattr(libtuya.dps, 'DEFAULT_MAX_RETRIES')
        assert libtuya.dps.DEFAULT_MAX_RETRIES == 3


class TestIntegrationValidation:
    """Test integration between components"""
    
    def test_device_categories_match_rules(self):
        """Test that device categories match mapping rules"""
        supported_categories = get_supported_categories()
        
        # Test that all categories in DEVICE_CATEGORIES are supported
        for category in DEVICE_CATEGORIES.keys():
            assert category in supported_categories, f"Category {category} not supported by mapping rules"
    
    def test_confidence_levels_match_enum(self):
        """Test that confidence levels match enum values"""
        # Test that confidence levels match enum values
        assert CONFIDENCE_LEVELS["HIGH"] == DPSConfidence.HIGH.value
        assert CONFIDENCE_LEVELS["MEDIUM"] == DPSConfidence.MEDIUM.value
        assert CONFIDENCE_LEVELS["LOW"] == DPSConfidence.LOW.value
        assert CONFIDENCE_LEVELS["UNKNOWN"] == DPSConfidence.UNKNOWN.value
    
    def test_dps_patterns_match_rules(self):
        """Test that DPS patterns match mapping rules"""
        # Test that common patterns align with mapping rules
        assert DPSMappingRules.is_switch_dps(1) == True
        assert DPSMappingRules.is_brightness_dps(3) == True
        assert DPSMappingRules.is_color_dps(5) == True
        assert DPSMappingRules.is_switch_dps(20) == True
    
    def test_default_ranges_match_rules(self):
        """Test that default ranges match mapping rules"""
        rules_ranges = DPSMappingRules.get_common_dps_ranges()
        
        # Should have same number of ranges
        assert len(DEFAULT_DPS_RANGES) == len(rules_ranges)
        
        # Should have same ranges
        for i, r in enumerate(DEFAULT_DPS_RANGES):
            assert r == rules_ranges[i]


class TestUsageExamples:
    """Test usage examples from docstring"""
    
    def test_basic_usage_example(self):
        """Test basic usage example from module docstring"""
        from libtuya.dps import DPSMapper, DeviceInfo
        
        # Create mapper
        mapper = DPSMapper(enable_cache=False)  # Disable cache for testing
        assert isinstance(mapper, DPSMapper)
        
        # Define device info
        device_info = DeviceInfo(
            device_id="bf1234567890abcdef",
            category="dj",
            name="Living Room Light"
        )
        
        assert device_info.device_id == "bf1234567890abcdef"
        assert device_info.category == "dj"
        assert device_info.name == "Living Room Light"
        
        # Test mapper methods (without actual device)
        dps = mapper.get_dps_for_capability("bf1234567890abcdef", "switch_led")
        assert dps is None  # No mappings yet
        
        # Test validation
        validation = mapper.validate_mapping("bf1234567890abcdef")
        assert validation['valid'] == False  # No mappings yet
    
    def test_convenience_functions_example(self):
        """Test convenience functions example"""
        # Test create_device_info
        device_info = create_device_info("test_device", "dj", name="Test Light")
        assert device_info.device_id == "test_device"
        assert device_info.category == "dj"
        assert device_info.name == "Test Light"
        
        # Test validate_device_category
        assert validate_device_category("dj") == True
        assert validate_device_category("invalid") == False
        
        # Test get_supported_categories
        categories = get_supported_categories()
        assert "dj" in categories
        
        # Test create_mapper
        mapper = create_mapper(enable_cache=False)
        assert isinstance(mapper, DPSMapper)
        assert mapper.enable_cache == False