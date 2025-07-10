"""
Tests for specialized device types.

Tests the specialized device classes that extend IntelligentDevice
with device-specific functionality.
"""

import pytest
from unittest.mock import Mock, patch
import colorsys

from libtuya.devices.device_types import (
    IntelligentLight, IntelligentSwitch, IntelligentClimate, IntelligentCover,
    create_specialized_device
)
from libtuya.devices.intelligent_device import IntelligentDevice
from libtuya.auth.models import DeviceInfo
from libtuya.auth import TuyaAuthenticator
from libtuya.intelligence import DeviceIntelligence
from libtuya.dps import DPSMapper, DPSMappingInfo


class TestIntelligentLight:
    """Test IntelligentLight specialized device."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.device_info = DeviceInfo(
            id="light_123",
            name="Test Light",
            local_key="test_key",
            category="dj",
            product_id="test",
            product_name="test",
            online=True,
            ip="192.168.1.100",
            uuid="test",
            asset_id="test"
        )
        
        self.intelligence = Mock(spec=DeviceIntelligence)
        self.intelligence.analyze_device.return_value = Mock(
            capabilities=["switch_led", "bright_value", "colour_data", "temp_value"]
        )
        self.intelligence.convert_color_data.return_value = "#FF0000"
        self.intelligence.scale_value.return_value = 500
        
        self.auth_manager = Mock(spec=TuyaAuthenticator)
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
            ),
            "temp_value": DPSMappingInfo(
                capability="temp_value",
                dpcode="temp_value",
                dps=4,
                data_type="integer",
                confidence=0.8,
                scaling_info=None
            )
        }
        self.dps_mapper.discover_dps_mapping.return_value = self.dps_mappings
        
        # Mock TinyTuya device
        with patch('libtuya.devices.factory.DeviceFactory') as mock_factory_class:
            self.mock_factory = Mock()
            mock_factory_class.return_value = self.mock_factory
            
            self.mock_tinytuya_device = Mock()
            self.mock_tinytuya_device.status.return_value = {
                "dps": {1: True, 3: 500, 4: 3000, 5: "#FF0000"}
            }
            self.mock_factory.create_device.return_value = self.mock_tinytuya_device
            
            self.light = IntelligentLight(
                device_info=self.device_info,
                intelligence=self.intelligence,
                dps_mapper=self.dps_mapper,
                auth_manager=self.auth_manager
            )
    
    def test_light_initialization(self):
        """Test light initialization."""
        assert isinstance(self.light, IntelligentLight)
        assert isinstance(self.light, IntelligentDevice)
        assert self.light.brightness_capabilities == ["bright_value", "bright_value_v2", "bright_value_1"]
        assert self.light.color_capabilities == ["colour_data", "colour_data_v2", "colour_data_hsv"]
        assert self.light.color_temp_capabilities == ["temp_value", "temp_value_v2"]
        assert self.light.switch_capabilities == ["switch_led", "switch", "switch_1"]
    
    def test_light_is_on_property(self):
        """Test is_on property."""
        assert self.light.is_on is True
        
        # Test with different switch state
        self.mock_tinytuya_device.status.return_value = {"dps": {1: False}}
        self.light.cached_status = None  # Clear cache
        assert self.light.is_on is False
    
    def test_light_brightness_property(self):
        """Test brightness property."""
        brightness = self.light.brightness
        assert brightness == 49  # (500-10)/(1000-10) * 100 = 49.5 -> 49
    
    def test_light_color_rgb_property(self):
        """Test color_rgb property."""
        # Mock color parsing
        with patch.object(self.light, '_parse_color_value') as mock_parse:
            mock_parse.return_value = (255, 0, 0)
            
            color = self.light.color_rgb
            assert color == (255, 0, 0)
            mock_parse.assert_called_once_with("colour_data", "#FF0000")
    
    def test_light_color_temperature_property(self):
        """Test color_temperature property."""
        temp = self.light.color_temperature
        assert temp == 3000
    
    def test_light_supported_features(self):
        """Test supported_features property."""
        features = self.light.supported_features
        
        assert features["brightness"] is True
        assert features["color"] is True
        assert features["color_temperature"] is True
        assert features["switch"] is True
        assert isinstance(features["modes"], bool)
    
    def test_set_brightness(self):
        """Test setting brightness."""
        self.intelligence.scale_value.return_value = 505
        
        result = self.light.set_brightness(50)
        
        assert result is True
        self.mock_tinytuya_device.set_value.assert_called_once_with(3, 505)
        assert self.light._last_brightness == 50
    
    def test_set_brightness_invalid(self):
        """Test setting invalid brightness."""
        with pytest.raises(ValueError):
            self.light.set_brightness(150)
        
        with pytest.raises(ValueError):
            self.light.set_brightness(-10)
    
    def test_set_color_hsv(self):
        """Test setting color using HSV."""
        self.intelligence.scale_value.return_value = "#FF0000"
        
        result = self.light.set_color_hsv(0, 100, 100)  # Red
        
        assert result is True
        self.mock_tinytuya_device.set_value.assert_called_once_with(5, "#FF0000")
        assert self.light._last_color == (255, 0, 0)
    
    def test_set_color_hsv_invalid(self):
        """Test setting invalid HSV color."""
        with pytest.raises(ValueError):
            self.light.set_color_hsv(400, 100, 100)  # H out of range
        
        with pytest.raises(ValueError):
            self.light.set_color_hsv(0, 150, 100)  # S out of range
        
        with pytest.raises(ValueError):
            self.light.set_color_hsv(0, 100, 150)  # V out of range
    
    def test_set_color_hex(self):
        """Test setting color using hex string."""
        self.intelligence.scale_value.return_value = "#FF0000"
        
        result = self.light.set_color_hex("#FF0000")
        
        assert result is True
        self.mock_tinytuya_device.set_value.assert_called_once_with(5, "#FF0000")
        
        # Test without # prefix
        result = self.light.set_color_hex("00FF00")
        assert result is True
    
    def test_set_color_hex_invalid(self):
        """Test setting invalid hex color."""
        with pytest.raises(ValueError):
            self.light.set_color_hex("invalid")
        
        with pytest.raises(ValueError):
            self.light.set_color_hex("#GGGGGG")
    
    def test_set_scene(self):
        """Test setting light scene."""
        # Add mode capability
        self.light.dps_mappings["work_mode"] = DPSMappingInfo(
            capability="work_mode",
            dpcode="work_mode",
            dps_index=2,
            data_type="string",
            confidence=0.8,
            scaling_info=None
        )
        
        self.intelligence.scale_value.return_value = "white"
        
        result = self.light.set_scene("white")
        
        assert result is True
        self.mock_tinytuya_device.set_value.assert_called_once_with(2, "white")
    
    def test_pulse_light(self):
        """Test pulsing light."""
        self.intelligence.scale_value.side_effect = [True, 1000, 500]  # on, bright, restore
        
        with patch('time.sleep') as mock_sleep:
            result = self.light.pulse_light(duration=1, brightness=100)
        
        assert result is True
        mock_sleep.assert_called_once_with(1)
        assert self.mock_tinytuya_device.set_value.call_count >= 2
    
    def test_scale_brightness_to_percentage(self):
        """Test brightness scaling to percentage."""
        # Test with scaling info
        percentage = self.light._scale_brightness_to_percentage("bright_value", 505)
        assert percentage == 49  # (505-10)/(1000-10) * 100
        
        # Test without scaling info
        del self.light.dps_mappings["bright_value"].scaling_info
        percentage = self.light._scale_brightness_to_percentage("bright_value", 505)
        assert percentage == 49  # Default 10-1000 range
    
    def test_parse_color_value(self):
        """Test parsing color values."""
        # Test hex format
        rgb = self.light._parse_color_value("colour_data", "#FF0000")
        assert rgb == (255, 0, 0)
        
        # Test HSV format
        hsv_value = {"h": 0, "s": 100, "v": 100}
        rgb = self.light._parse_color_value("colour_data_hsv", hsv_value)
        assert rgb == (255, 0, 0)
        
        # Test invalid format
        rgb = self.light._parse_color_value("colour_data", "invalid")
        assert rgb is None
    
    def test_scale_color_temperature(self):
        """Test color temperature scaling."""
        temp = self.light._scale_color_temperature("temp_value", 3000)
        assert temp == 3000
        
        # Test with invalid value
        temp = self.light._scale_color_temperature("temp_value", "invalid")
        assert temp == 3000  # Default warm white


class TestIntelligentSwitch:
    """Test IntelligentSwitch specialized device."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.device_info = DeviceInfo(
            id="switch_123",
            name="Test Switch",
            local_key="test_key",
            category="kg",
            product_id="test",
            product_name="test",
            online=True,
            ip="192.168.1.100",
            uuid="test",
            asset_id="test"
        )
        
        self.intelligence = Mock(spec=DeviceIntelligence)
        self.intelligence.analyze_device.return_value = Mock(
            capabilities=["switch", "switch_1", "switch_2", "cur_power"]
        )
        self.intelligence.scale_value.return_value = True
        
        self.auth_manager = Mock(spec=TuyaAuthenticator)
        self.dps_mapper = Mock(spec=DPSMapper)
        self.dps_mappings = {
            "switch": DPSMappingInfo(
                capability="switch",
                dpcode="switch",
                dps=1,
                data_type="boolean",
                confidence=0.9,
                scaling_info=None
            ),
            "switch_1": DPSMappingInfo(
                capability="switch_1",
                dpcode="switch_1",
                dps=2,
                data_type="boolean",
                confidence=0.8,
                scaling_info=None
            ),
            "switch_2": DPSMappingInfo(
                capability="switch_2",
                dpcode="switch_2",
                dps=3,
                data_type="boolean",
                confidence=0.8,
                scaling_info=None
            ),
            "cur_power": DPSMappingInfo(
                capability="cur_power",
                dpcode="cur_power",
                dps=18,
                data_type="integer",
                confidence=0.7,
                scaling_info={"scale": 1.0}
            )
        }
        self.dps_mapper.discover_dps_mapping.return_value = self.dps_mappings
        
        # Mock TinyTuya device
        with patch('libtuya.devices.factory.DeviceFactory') as mock_factory_class:
            self.mock_factory = Mock()
            mock_factory_class.return_value = self.mock_factory
            
            self.mock_tinytuya_device = Mock()
            self.mock_tinytuya_device.status.return_value = {
                "dps": {1: True, 2: False, 3: True, 18: 500}
            }
            self.mock_factory.create_device.return_value = self.mock_tinytuya_device
            
            self.switch = IntelligentSwitch(
                device_info=self.device_info,
                intelligence=self.intelligence,
                dps_mapper=self.dps_mapper,
                auth_manager=self.auth_manager
            )
    
    def test_switch_initialization(self):
        """Test switch initialization."""
        assert isinstance(self.switch, IntelligentSwitch)
        assert isinstance(self.switch, IntelligentDevice)
        assert self.switch.channel_count == 3  # switch, switch_1, switch_2
    
    def test_switch_is_on_property(self):
        """Test is_on property."""
        assert self.switch.is_on is True
    
    def test_switch_power_consumption_property(self):
        """Test power_consumption property."""
        power = self.switch.power_consumption
        assert power == 500.0
    
    def test_switch_channel_states_property(self):
        """Test channel_states property."""
        states = self.switch.channel_states
        
        assert states == {1: True, 2: False, 3: True}
    
    def test_turn_on_channel(self):
        """Test turning on specific channel."""
        result = self.switch.turn_on_channel(2)
        
        assert result is True
        self.mock_tinytuya_device.set_value.assert_called_once_with(2, True)
    
    def test_turn_on_channel_invalid(self):
        """Test turning on invalid channel."""
        with pytest.raises(ValueError):
            self.switch.turn_on_channel(5)  # Channel out of range
    
    def test_turn_off_channel(self):
        """Test turning off specific channel."""
        result = self.switch.turn_off_channel(1)
        
        assert result is True
        self.mock_tinytuya_device.set_value.assert_called_once_with(1, False)
    
    def test_toggle_channel(self):
        """Test toggling channel."""
        # Channel 2 is off, should turn on
        result = self.switch.toggle_channel(2)
        
        assert result is True
        self.mock_tinytuya_device.set_value.assert_called_once_with(2, True)
        
        # Channel 1 is on, should turn off
        self.mock_tinytuya_device.reset_mock()
        result = self.switch.toggle_channel(1)
        
        assert result is True
        self.mock_tinytuya_device.set_value.assert_called_once_with(1, False)
    
    def test_turn_on_all_channels(self):
        """Test turning on all channels."""
        result = self.switch.turn_on_all_channels()
        
        assert result is True
        assert self.mock_tinytuya_device.set_value.call_count == 3
    
    def test_turn_off_all_channels(self):
        """Test turning off all channels."""
        result = self.switch.turn_off_all_channels()
        
        assert result is True
        assert self.mock_tinytuya_device.set_value.call_count == 3
    
    def test_get_power_stats(self):
        """Test getting power statistics."""
        # Mock voltage and current capabilities
        self.switch.dps_mappings["cur_voltage"] = DPSMappingInfo(
            capability="cur_voltage",
            dpcode="cur_voltage",
            dps_index=19,
            data_type="integer",
            confidence=0.7,
            scaling_info={"scale": 1.0}
        )
        self.switch.dps_mappings["cur_current"] = DPSMappingInfo(
            capability="cur_current",
            dpcode="cur_current",
            dps_index=20,
            data_type="integer",
            confidence=0.7,
            scaling_info={"scale": 0.001}
        )
        
        # Update mock status
        self.mock_tinytuya_device.status.return_value = {
            "dps": {1: True, 18: 500, 19: 230, 20: 2000}
        }
        self.switch.cached_status = None  # Clear cache
        
        stats = self.switch.get_power_stats()
        
        assert stats["power_watts"] == 500.0
        assert stats["voltage_volts"] == 230.0
        assert stats["current_amps"] == 2.0  # 2000 * 0.001
        assert stats["supported_monitoring"]["power"] is True
        assert stats["supported_monitoring"]["voltage"] is True
        assert stats["supported_monitoring"]["current"] is True
    
    def test_detect_channel_count(self):
        """Test detecting channel count."""
        # Test with single channel
        single_switch = IntelligentSwitch(
            device_info=self.device_info,
            intelligence=self.intelligence,
            dps_mapper=self.dps_mapper,
            auth_manager=self.auth_manager
        )
        single_switch.dps_mappings = {"switch": self.dps_mappings["switch"]}
        
        count = single_switch._detect_channel_count()
        assert count == 1
        
        # Test with multiple channels
        count = self.switch._detect_channel_count()
        assert count == 3
    
    def test_scale_power_value(self):
        """Test power value scaling."""
        # Test with scaling info
        power = self.switch._scale_power_value("cur_power", 500)
        assert power == 500.0
        
        # Test without scaling info
        del self.switch.dps_mappings["cur_power"].scaling_info
        power = self.switch._scale_power_value("cur_power", 500)
        assert power == 500.0
    
    def test_scale_voltage_value(self):
        """Test voltage value scaling."""
        power = self.switch._scale_voltage_value("cur_voltage", 230)
        assert power == 230.0
    
    def test_scale_current_value(self):
        """Test current value scaling."""
        # Test with default mA to A conversion
        current = self.switch._scale_current_value("cur_current", 2000)
        assert current == 2.0  # 2000 * 0.001


class TestIntelligentClimate:
    """Test IntelligentClimate specialized device."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.device_info = DeviceInfo(
            id="climate_123",
            name="Test Thermostat",
            local_key="test_key",
            category="wk",
            product_id="test",
            product_name="test",
            online=True,
            ip="192.168.1.100",
            uuid="test",
            asset_id="test"
        )
        
        self.intelligence = Mock(spec=DeviceIntelligence)
        self.intelligence.analyze_device.return_value = Mock(
            capabilities=["temp_set", "temp_current", "mode", "switch"]
        )
        self.intelligence.scale_value.return_value = 22
        
        self.auth_manager = Mock(spec=TuyaAuthenticator)
        self.dps_mapper = Mock(spec=DPSMapper)
        self.dps_mappings = {
            "temp_set": DPSMappingInfo(
                capability="temp_set",
                dpcode="temp_set",
                dps=2,
                data_type="integer",
                confidence=0.9,
                scaling_info={"scale": 1.0, "offset": 0.0}
            ),
            "temp_current": DPSMappingInfo(
                capability="temp_current",
                dpcode="temp_current",
                dps=3,
                data_type="integer",
                confidence=0.8,
                scaling_info={"scale": 1.0, "offset": 0.0}
            ),
            "mode": DPSMappingInfo(
                capability="mode",
                dpcode="mode",
                dps=4,
                data_type="string",
                confidence=0.8,
                scaling_info=None
            ),
            "switch": DPSMappingInfo(
                capability="switch",
                dpcode="switch",
                dps=1,
                data_type="boolean",
                confidence=0.9,
                scaling_info=None
            )
        }
        self.dps_mapper.discover_dps_mapping.return_value = self.dps_mappings
        
        # Mock TinyTuya device
        with patch('libtuya.devices.factory.DeviceFactory') as mock_factory_class:
            self.mock_factory = Mock()
            mock_factory_class.return_value = self.mock_factory
            
            self.mock_tinytuya_device = Mock()
            self.mock_tinytuya_device.status.return_value = {
                "dps": {1: True, 2: 22, 3: 20, 4: "auto"}
            }
            self.mock_factory.create_device.return_value = self.mock_tinytuya_device
            
            self.climate = IntelligentClimate(
                device_info=self.device_info,
                intelligence=self.intelligence,
                dps_mapper=self.dps_mapper,
                auth_manager=self.auth_manager
            )
    
    def test_climate_initialization(self):
        """Test climate device initialization."""
        assert isinstance(self.climate, IntelligentClimate)
        assert isinstance(self.climate, IntelligentDevice)
        assert self.climate.supported_modes == ["auto", "cool", "heat", "dry", "fan_only", "off"]
    
    def test_climate_temperature_properties(self):
        """Test temperature properties."""
        assert self.climate.current_temperature == 20.0
        assert self.climate.target_temperature == 22.0
    
    def test_climate_current_mode_property(self):
        """Test current_mode property."""
        assert self.climate.current_mode == "auto"
    
    def test_set_temperature(self):
        """Test setting temperature."""
        result = self.climate.set_temperature(25.0)
        
        assert result is True
        self.mock_tinytuya_device.set_value.assert_called_once_with(2, 25)
    
    def test_set_humidity(self):
        """Test setting humidity."""
        # Add humidity capability
        self.climate.dps_mappings["humidity_set"] = DPSMappingInfo(
            capability="humidity_set",
            dpcode="humidity_set",
            dps_index=5,
            data_type="integer",
            confidence=0.8,
            scaling_info=None
        )
        
        result = self.climate.set_humidity(60.0)
        
        assert result is True
        self.mock_tinytuya_device.set_value.assert_called_once_with(5, 60)
    
    def test_set_humidity_invalid(self):
        """Test setting invalid humidity."""
        with pytest.raises(ValueError):
            self.climate.set_humidity(150.0)
        
        with pytest.raises(ValueError):
            self.climate.set_humidity(-10.0)
    
    def test_set_mode(self):
        """Test setting mode."""
        result = self.climate.set_mode("cool")
        
        assert result is True
        self.mock_tinytuya_device.set_value.assert_called_once_with(4, "cool")
    
    def test_scale_temperature_value(self):
        """Test temperature value scaling."""
        # Test with scaling info
        temp = self.climate._scale_temperature_value("temp_current", 200)
        assert temp == 200.0
        
        # Test without scaling info
        del self.climate.dps_mappings["temp_current"].scaling_info
        temp = self.climate._scale_temperature_value("temp_current", 200)
        assert temp == 200.0
    
    def test_scale_temperature_for_device(self):
        """Test temperature scaling for device."""
        # Test with scaling info
        temp = self.climate._scale_temperature_for_device("temp_set", 25.0)
        assert temp == 25
        
        # Test without scaling info
        del self.climate.dps_mappings["temp_set"].scaling_info
        temp = self.climate._scale_temperature_for_device("temp_set", 25.0)
        assert temp == 25


class TestIntelligentCover:
    """Test IntelligentCover specialized device."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.device_info = DeviceInfo(
            id="cover_123",
            name="Test Curtain",
            local_key="test_key",
            category="cl",
            product_id="test",
            product_name="test",
            online=True,
            ip="192.168.1.100",
            uuid="test",
            asset_id="test"
        )
        
        self.intelligence = Mock(spec=DeviceIntelligence)
        self.intelligence.analyze_device.return_value = Mock(
            capabilities=["control", "percent_control"]
        )
        self.intelligence.scale_value.return_value = "open"
        
        self.auth_manager = Mock(spec=TuyaAuthenticator)
        self.dps_mapper = Mock(spec=DPSMapper)
        self.dps_mappings = {
            "control": DPSMappingInfo(
                capability="control",
                dpcode="control",
                dps=1,
                data_type="string",
                confidence=0.9,
                scaling_info=None
            ),
            "percent_control": DPSMappingInfo(
                capability="percent_control",
                dpcode="percent_control",
                dps=2,
                data_type="integer",
                confidence=0.8,
                scaling_info=None
            )
        }
        self.dps_mapper.discover_dps_mapping.return_value = self.dps_mappings
        
        # Mock TinyTuya device
        with patch('libtuya.devices.factory.DeviceFactory') as mock_factory_class:
            self.mock_factory = Mock()
            mock_factory_class.return_value = self.mock_factory
            
            self.mock_tinytuya_device = Mock()
            self.mock_tinytuya_device.status.return_value = {
                "dps": {1: "stop", 2: 50}
            }
            self.mock_factory.create_device.return_value = self.mock_tinytuya_device
            
            self.cover = IntelligentCover(
                device_info=self.device_info,
                intelligence=self.intelligence,
                dps_mapper=self.dps_mapper,
                auth_manager=self.auth_manager
            )
    
    def test_cover_initialization(self):
        """Test cover device initialization."""
        assert isinstance(self.cover, IntelligentCover)
        assert isinstance(self.cover, IntelligentDevice)
        assert self.cover.control_commands == {
            "open": "open",
            "close": "close",
            "stop": "stop",
            "pause": "pause"
        }
    
    def test_cover_position_property(self):
        """Test current_position property."""
        assert self.cover.current_position == 50
    
    def test_cover_state_properties(self):
        """Test cover state properties."""
        assert self.cover.is_opening is False
        assert self.cover.is_closing is False
        assert self.cover.is_stopped is True
        
        # Test opening state
        self.mock_tinytuya_device.status.return_value = {"dps": {1: "open", 2: 50}}
        self.cover.cached_status = None
        assert self.cover.is_opening is True
        
        # Test closing state
        self.mock_tinytuya_device.status.return_value = {"dps": {1: "close", 2: 50}}
        self.cover.cached_status = None
        assert self.cover.is_closing is True
    
    def test_open_cover(self):
        """Test opening cover."""
        result = self.cover.open_cover()
        
        assert result is True
        self.mock_tinytuya_device.set_value.assert_called_once_with(1, "open")
    
    def test_close_cover(self):
        """Test closing cover."""
        result = self.cover.close_cover()
        
        assert result is True
        self.mock_tinytuya_device.set_value.assert_called_once_with(1, "close")
    
    def test_stop_cover(self):
        """Test stopping cover."""
        result = self.cover.stop_cover()
        
        assert result is True
        self.mock_tinytuya_device.set_value.assert_called_once_with(1, "stop")
    
    def test_set_position(self):
        """Test setting cover position."""
        result = self.cover.set_position(75)
        
        assert result is True
        self.mock_tinytuya_device.set_value.assert_called_once_with(2, 75)
    
    def test_set_position_invalid(self):
        """Test setting invalid position."""
        with pytest.raises(ValueError):
            self.cover.set_position(150)
        
        with pytest.raises(ValueError):
            self.cover.set_position(-10)


class TestCreateSpecializedDevice:
    """Test create_specialized_device function."""
    
    def test_create_light_device(self):
        """Test creating light device."""
        device_info = DeviceInfo(
            id="light_123",
            name="Test Light",
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
        auth_manager = Mock(spec=TuyaAuthenticator)
        
        device = create_specialized_device(device_info, intelligence, dps_mapper, auth_manager=auth_manager)
        
        assert isinstance(device, IntelligentLight)
    
    def test_create_switch_device(self):
        """Test creating switch device."""
        device_info = DeviceInfo(
            id="switch_123",
            name="Test Switch",
            local_key="test_key",
            category="kg",
            product_id="test",
            product_name="test",
            online=True,
            ip="192.168.1.100",
            uuid="test",
            asset_id="test"
        )
        
        intelligence = Mock()
        dps_mapper = Mock()
        auth_manager = Mock(spec=TuyaAuthenticator)
        
        device = create_specialized_device(device_info, intelligence, dps_mapper, auth_manager=auth_manager)
        
        assert isinstance(device, IntelligentSwitch)
    
    def test_create_climate_device(self):
        """Test creating climate device."""
        device_info = DeviceInfo(
            id="climate_123",
            name="Test Thermostat",
            local_key="test_key",
            category="wk",
            product_id="test",
            product_name="test",
            online=True,
            ip="192.168.1.100",
            uuid="test",
            asset_id="test"
        )
        
        intelligence = Mock()
        dps_mapper = Mock()
        auth_manager = Mock(spec=TuyaAuthenticator)
        
        device = create_specialized_device(device_info, intelligence, dps_mapper, auth_manager=auth_manager)
        
        assert isinstance(device, IntelligentClimate)
    
    def test_create_cover_device(self):
        """Test creating cover device."""
        device_info = DeviceInfo(
            id="cover_123",
            name="Test Curtain",
            local_key="test_key",
            category="cl",
            product_id="test",
            product_name="test",
            online=True,
            ip="192.168.1.100",
            uuid="test",
            asset_id="test"
        )
        
        intelligence = Mock()
        dps_mapper = Mock()
        auth_manager = Mock(spec=TuyaAuthenticator)
        
        device = create_specialized_device(device_info, intelligence, dps_mapper, auth_manager=auth_manager)
        
        assert isinstance(device, IntelligentCover)
    
    def test_create_generic_device(self):
        """Test creating generic device for unknown category."""
        device_info = DeviceInfo(
            id="unknown_123",
            name="Test Unknown",
            local_key="test_key",
            category="unknown",
            product_id="test",
            product_name="test",
            online=True,
            ip="192.168.1.100",
            uuid="test",
            asset_id="test"
        )
        
        intelligence = Mock()
        dps_mapper = Mock()
        auth_manager = Mock(spec=TuyaAuthenticator)
        
        device = create_specialized_device(device_info, intelligence, dps_mapper, auth_manager=auth_manager)
        
        assert isinstance(device, IntelligentDevice)
        assert not isinstance(device, IntelligentLight)
        assert not isinstance(device, IntelligentSwitch)