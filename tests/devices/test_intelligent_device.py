"""
Tests for IntelligentDevice wrapper.

Tests the main IntelligentDevice class that integrates cloud discovery
with local control using TinyTuya, device intelligence, and DPS mapping.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from libtuya.devices.intelligent_device import IntelligentDevice, DeviceCapability, DeviceStatus, create_intelligent_device
from libtuya.auth.models import DeviceInfo
from libtuya.intelligence import DeviceIntelligence, DeviceAnalysis
from libtuya.dps import DPSMapper, DPSMappingInfo
from libtuya.devices.factory import DeviceFactory


class TestIntelligentDevice:
    """Test IntelligentDevice functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Mock device info
        self.device_info = DeviceInfo(
            id="test_device_123",
            name="Test Light",
            local_key="abcdef1234567890",
            category="dj",
            product_id="test_product",
            product_name="Test Smart Light",
            online=True,
            ip="192.168.1.100",
            uuid="test_uuid",
            asset_id="test_asset"
        )
        
        # Mock intelligence
        self.intelligence = Mock(spec=DeviceIntelligence)
        self.device_analysis = DeviceAnalysis(
            category_id="dj",
            canonical_category="dj",
            category_name="Smart Light",
            platform="light",
            capabilities=["switch_led", "bright_value", "colour_data"],
            supported_dpcodes=["switch_led", "bright_value", "colour_data"],
            quirks=[],
            has_quirks=False,
            is_multi_entity=False,
            entity_mappings=[],
            scaling_info={},
            recommendations=[]
        )
        self.intelligence.analyze_device.return_value = self.device_analysis
        
        # Mock DPS mapper
        self.dps_mapper = Mock(spec=DPSMapper)
        self.dps_mappings = {
            "switch_led": DPSMappingInfo(
                capability="switch_led",
                dpcode="switch_led",
                dps=1,
                data_type="boolean",
                confidence=0.9,
                scaling_info=None
            ),
            "bright_value": DPSMappingInfo(
                capability="bright_value",
                dpcode="bright_value",
                dps=3,
                data_type="integer",
                confidence=0.8,
                scaling_info={"min": 10, "max": 1000}
            ),
            "colour_data": DPSMappingInfo(
                capability="colour_data",
                dpcode="colour_data",
                dps=5,
                data_type="string",
                confidence=0.7,
                scaling_info=None
            )
        }
        self.dps_mapper.discover_dps_mapping.return_value = self.dps_mappings
        
        # Mock device factory
        self.device_factory = Mock(spec=DeviceFactory)
        self.mock_tinytuya_device = Mock()
        self.mock_tinytuya_device.status.return_value = {"dps": {1: True, 3: 500, 5: "#FF0000"}}
        self.device_factory.create_device.return_value = self.mock_tinytuya_device
    
    def test_intelligent_device_initialization(self):
        """Test IntelligentDevice initialization."""
        device = IntelligentDevice(
            device_info=self.device_info,
            intelligence=self.intelligence,
            dps_mapper=self.dps_mapper,
            device_factory=self.device_factory
        )
        
        assert device.device_info == self.device_info
        assert device.intelligence == self.intelligence
        assert device.dps_mapper == self.dps_mapper
        assert device.device_factory == self.device_factory
        assert device.device_analysis == self.device_analysis
        assert device.dps_mappings == self.dps_mappings
        assert device.tinytuya_device == self.mock_tinytuya_device
    
    def test_intelligent_device_properties(self):
        """Test IntelligentDevice properties."""
        device = IntelligentDevice(
            device_info=self.device_info,
            intelligence=self.intelligence,
            dps_mapper=self.dps_mapper,
            device_factory=self.device_factory
        )
        
        assert device.name == "Test Light"
        assert device.id == "test_device_123"
        assert device.category == "dj"
        assert device.is_online is True
        assert device.can_control_locally is True
        assert device.available_capabilities == ["switch_led", "bright_value", "colour_data"]
    
    def test_get_status(self):
        """Test getting device status."""
        device = IntelligentDevice(
            device_info=self.device_info,
            intelligence=self.intelligence,
            dps_mapper=self.dps_mapper,
            device_factory=self.device_factory
        )
        
        status = device.get_status()
        
        assert isinstance(status, DeviceStatus)
        assert status.online is True
        assert isinstance(status.last_update, datetime)
        assert len(status.capabilities) == 3
        assert status.raw_dps == {1: True, 3: 500, 5: "#FF0000"}
        assert len(status.errors) == 0
        
        # Check capabilities
        assert "switch_led" in status.capabilities
        assert status.capabilities["switch_led"].current_value is True
        assert status.capabilities["switch_led"].dps_index == 1
        
        assert "bright_value" in status.capabilities
        assert status.capabilities["bright_value"].current_value == 500
        assert status.capabilities["bright_value"].dps_index == 3
    
    def test_get_status_caching(self):
        """Test status caching functionality."""
        device = IntelligentDevice(
            device_info=self.device_info,
            intelligence=self.intelligence,
            dps_mapper=self.dps_mapper,
            device_factory=self.device_factory
        )
        
        # First call
        status1 = device.get_status()
        
        # Second call should return cached version
        status2 = device.get_status()
        
        assert status1 is status2
        assert self.mock_tinytuya_device.status.call_count == 1
        
        # Force refresh should call again
        status3 = device.get_status(force_refresh=True)
        
        assert status3 is not status1
        assert self.mock_tinytuya_device.status.call_count == 2
    
    def test_set_capability(self):
        """Test setting device capability."""
        device = IntelligentDevice(
            device_info=self.device_info,
            intelligence=self.intelligence,
            dps_mapper=self.dps_mapper,
            device_factory=self.device_factory
        )
        
        # Mock value scaling
        self.intelligence.scale_value.return_value = True
        
        result = device.set_capability("switch_led", True)
        
        assert result is True
        self.mock_tinytuya_device.set_value.assert_called_once_with(1, True)
        self.intelligence.scale_value.assert_called_once()
    
    def test_set_capability_unknown(self):
        """Test setting unknown capability."""
        device = IntelligentDevice(
            device_info=self.device_info,
            intelligence=self.intelligence,
            dps_mapper=self.dps_mapper,
            device_factory=self.device_factory
        )
        
        result = device.set_capability("unknown_capability", True)
        
        assert result is False
        self.mock_tinytuya_device.set_value.assert_not_called()
    
    def test_get_capability(self):
        """Test getting capability value."""
        device = IntelligentDevice(
            device_info=self.device_info,
            intelligence=self.intelligence,
            dps_mapper=self.dps_mapper,
            device_factory=self.device_factory
        )
        
        # Get switch state
        switch_value = device.get_capability("switch_led")
        assert switch_value is True
        
        # Get brightness value
        brightness_value = device.get_capability("bright_value")
        assert brightness_value == 500
        
        # Get unknown capability
        unknown_value = device.get_capability("unknown_capability")
        assert unknown_value is None
    
    def test_turn_on(self):
        """Test turning device on."""
        device = IntelligentDevice(
            device_info=self.device_info,
            intelligence=self.intelligence,
            dps_mapper=self.dps_mapper,
            device_factory=self.device_factory
        )
        
        self.intelligence.scale_value.return_value = True
        
        result = device.turn_on()
        
        assert result is True
        self.mock_tinytuya_device.set_value.assert_called_once_with(1, True)
    
    def test_turn_off(self):
        """Test turning device off."""
        device = IntelligentDevice(
            device_info=self.device_info,
            intelligence=self.intelligence,
            dps_mapper=self.dps_mapper,
            device_factory=self.device_factory
        )
        
        self.intelligence.scale_value.return_value = False
        
        result = device.turn_off()
        
        assert result is True
        self.mock_tinytuya_device.set_value.assert_called_once_with(1, False)
    
    def test_set_brightness_percentage(self):
        """Test setting brightness as percentage."""
        device = IntelligentDevice(
            device_info=self.device_info,
            intelligence=self.intelligence,
            dps_mapper=self.dps_mapper,
            device_factory=self.device_factory
        )
        
        self.intelligence.scale_value.return_value = 505  # 50% of 10-1000 range
        
        result = device.set_brightness_percentage(50)
        
        assert result is True
        self.mock_tinytuya_device.set_value.assert_called_once_with(3, 505)
    
    def test_set_brightness_percentage_invalid(self):
        """Test setting invalid brightness percentage."""
        device = IntelligentDevice(
            device_info=self.device_info,
            intelligence=self.intelligence,
            dps_mapper=self.dps_mapper,
            device_factory=self.device_factory
        )
        
        with pytest.raises(ValueError):
            device.set_brightness_percentage(150)
        
        with pytest.raises(ValueError):
            device.set_brightness_percentage(-10)
    
    def test_set_color_rgb(self):
        """Test setting color using RGB."""
        device = IntelligentDevice(
            device_info=self.device_info,
            intelligence=self.intelligence,
            dps_mapper=self.dps_mapper,
            device_factory=self.device_factory
        )
        
        self.intelligence.convert_color_data.return_value = "#FF0000"
        self.intelligence.scale_value.return_value = "#FF0000"
        
        result = device.set_color_rgb(255, 0, 0)
        
        assert result is True
        self.intelligence.convert_color_data.assert_called_once_with(255, 0, 0, "hex")
        self.mock_tinytuya_device.set_value.assert_called_once_with(5, "#FF0000")
    
    def test_set_color_rgb_invalid(self):
        """Test setting invalid RGB color."""
        device = IntelligentDevice(
            device_info=self.device_info,
            intelligence=self.intelligence,
            dps_mapper=self.dps_mapper,
            device_factory=self.device_factory
        )
        
        with pytest.raises(ValueError):
            device.set_color_rgb(300, 0, 0)
        
        with pytest.raises(ValueError):
            device.set_color_rgb(255, -10, 0)
    
    def test_set_color_temperature(self):
        """Test setting color temperature."""
        device = IntelligentDevice(
            device_info=self.device_info,
            intelligence=self.intelligence,
            dps_mapper=self.dps_mapper,
            device_factory=self.device_factory
        )
        
        # Add temperature capability
        device.dps_mappings["temp_value"] = DPSMappingInfo(
            capability="temp_value",
            dpcode="temp_value",
            dps_index=4,
            data_type="integer",
            confidence=0.8,
            scaling_info=None
        )
        
        self.intelligence.scale_value.return_value = 3000
        
        result = device.set_color_temperature(3000)
        
        assert result is True
        self.mock_tinytuya_device.set_value.assert_called_once_with(4, 3000)
    
    def test_set_color_temperature_invalid(self):
        """Test setting invalid color temperature."""
        device = IntelligentDevice(
            device_info=self.device_info,
            intelligence=self.intelligence,
            dps_mapper=self.dps_mapper,
            device_factory=self.device_factory
        )
        
        with pytest.raises(ValueError):
            device.set_color_temperature(500)  # Too low
        
        with pytest.raises(ValueError):
            device.set_color_temperature(15000)  # Too high
    
    def test_detect_available_dps(self):
        """Test detecting available DPS indices."""
        device = IntelligentDevice(
            device_info=self.device_info,
            intelligence=self.intelligence,
            dps_mapper=self.dps_mapper,
            device_factory=self.device_factory
        )
        
        # Mock detect_available_dps method
        self.mock_tinytuya_device.detect_available_dps.return_value = {1: True, 3: 500, 5: "#FF0000"}
        
        dps_data = device.detect_available_dps()
        
        assert dps_data == {1: True, 3: 500, 5: "#FF0000"}
        self.mock_tinytuya_device.detect_available_dps.assert_called_once()
    
    def test_detect_available_dps_fallback(self):
        """Test DPS detection fallback to status method."""
        device = IntelligentDevice(
            device_info=self.device_info,
            intelligence=self.intelligence,
            dps_mapper=self.dps_mapper,
            device_factory=self.device_factory
        )
        
        # Remove detect_available_dps method
        del self.mock_tinytuya_device.detect_available_dps
        
        dps_data = device.detect_available_dps()
        
        assert dps_data == {1: True, 3: 500, 5: "#FF0000"}
        self.mock_tinytuya_device.status.assert_called()
    
    def test_validate_setup(self):
        """Test device setup validation."""
        device = IntelligentDevice(
            device_info=self.device_info,
            intelligence=self.intelligence,
            dps_mapper=self.dps_mapper,
            device_factory=self.device_factory
        )
        
        validation = device.validate_setup()
        
        assert validation["valid"] is True
        assert len(validation["errors"]) == 0
        assert validation["device_info"] == self.device_info.to_dict()
        assert validation["tinytuya_available"] is True
        assert validation["connection_errors"] == 0
    
    def test_validate_setup_no_local_key(self):
        """Test validation with no local key."""
        device_info_no_key = DeviceInfo(
            id="test_device",
            name="Test Device",
            local_key="",  # No local key
            category="dj",
            product_id="test",
            product_name="test",
            online=True,
            ip="192.168.1.100",
            uuid="test",
            asset_id="test"
        )
        
        device = IntelligentDevice(
            device_info=device_info_no_key,
            intelligence=self.intelligence,
            dps_mapper=self.dps_mapper,
            device_factory=self.device_factory
        )
        
        validation = device.validate_setup()
        
        assert validation["valid"] is False
        assert "No local key available" in validation["errors"]
    
    def test_get_device_info(self):
        """Test getting comprehensive device information."""
        device = IntelligentDevice(
            device_info=self.device_info,
            intelligence=self.intelligence,
            dps_mapper=self.dps_mapper,
            device_factory=self.device_factory
        )
        
        info = device.get_device_info()
        
        assert "basic_info" in info
        assert "analysis" in info
        assert "capabilities" in info
        assert "dps_mappings" in info
        assert "status" in info
        assert "factory_info" in info
        assert "connection_info" in info
        
        assert info["basic_info"] == self.device_info.to_dict()
        assert info["capabilities"] == ["switch_led", "bright_value", "colour_data"]
        assert info["connection_info"]["tinytuya_available"] is True
    
    def test_close_device(self):
        """Test closing device connection."""
        device = IntelligentDevice(
            device_info=self.device_info,
            intelligence=self.intelligence,
            dps_mapper=self.dps_mapper,
            device_factory=self.device_factory
        )
        
        # Mock close method
        self.mock_tinytuya_device.close = Mock()
        
        device.close()
        
        self.mock_tinytuya_device.close.assert_called_once()
        assert device.cached_status is None
        assert device.last_status_update is None
    
    def test_context_manager(self):
        """Test device as context manager."""
        device = IntelligentDevice(
            device_info=self.device_info,
            intelligence=self.intelligence,
            dps_mapper=self.dps_mapper,
            device_factory=self.device_factory
        )
        
        # Mock close method
        self.mock_tinytuya_device.close = Mock()
        
        with device as d:
            assert d is device
        
        self.mock_tinytuya_device.close.assert_called_once()
    
    def test_string_representation(self):
        """Test string representation of device."""
        device = IntelligentDevice(
            device_info=self.device_info,
            intelligence=self.intelligence,
            dps_mapper=self.dps_mapper,
            device_factory=self.device_factory
        )
        
        str_repr = str(device)
        assert "IntelligentDevice" in str_repr
        assert "Test Light" in str_repr
        assert "dj" in str_repr
        assert "test_device_123" in str_repr
        
        repr_str = repr(device)
        assert "IntelligentDevice" in repr_str
        assert "name='Test Light'" in repr_str
        assert "category='dj'" in repr_str
        assert "id='test_device_123'" in repr_str
    
    def test_error_handling(self):
        """Test error handling in device operations."""
        device = IntelligentDevice(
            device_info=self.device_info,
            intelligence=self.intelligence,
            dps_mapper=self.dps_mapper,
            device_factory=self.device_factory
        )
        
        # Mock TinyTuya error
        self.mock_tinytuya_device.status.side_effect = Exception("Connection failed")
        
        status = device.get_status()
        
        assert status.online is False
        assert len(status.errors) == 1
        assert "Connection failed" in status.errors[0]
        assert device.connection_errors == 1
        assert device.last_error == "Connection failed"


class TestCreateIntelligentDevice:
    """Test create_intelligent_device function."""
    
    def test_create_intelligent_device_with_defaults(self):
        """Test creating device with default components."""
        device_info = DeviceInfo(
            id="test_device",
            name="Test Device",
            local_key="test_key",
            category="dj",
            product_id="test",
            product_name="test",
            online=True,
            ip="192.168.1.100",
            uuid="test",
            asset_id="test"
        )
        
        with patch('libtuya.devices.intelligent_device.IntelligentDevice') as mock_class:
            mock_device = Mock()
            mock_class.return_value = mock_device
            
            result = create_intelligent_device(device_info)
            
            assert result is mock_device
            mock_class.assert_called_once()
            
            # Check that default components were created
            call_args = mock_class.call_args
            assert call_args[1]["device_info"] == device_info
            assert call_args[1]["intelligence"] is not None
            assert call_args[1]["dps_mapper"] is not None
    
    def test_create_intelligent_device_with_custom_components(self):
        """Test creating device with custom components."""
        device_info = DeviceInfo(
            id="test_device",
            name="Test Device",
            local_key="test_key",
            category="dj",
            product_id="test",
            product_name="test",
            online=True,
            ip="192.168.1.100",
            uuid="test",
            asset_id="test"
        )
        
        intelligence = Mock()
        dps_mapper = Mock()
        
        with patch('libtuya.devices.intelligent_device.IntelligentDevice') as mock_class:
            mock_device = Mock()
            mock_class.return_value = mock_device
            
            result = create_intelligent_device(device_info, intelligence, dps_mapper)
            
            assert result is mock_device
            mock_class.assert_called_once()
            
            # Check that custom components were used
            call_args = mock_class.call_args
            assert call_args[1]["device_info"] == device_info
            assert call_args[1]["intelligence"] is intelligence
            assert call_args[1]["dps_mapper"] is dps_mapper