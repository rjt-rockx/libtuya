"""
Tests for DeviceManager.

Tests the main DeviceManager class that provides unified interface
for device discovery, creation, and management.
"""

import pytest
from unittest.mock import Mock, patch

from libtuya.devices import DeviceManager
from libtuya.devices.device_types import IntelligentLight, IntelligentSwitch
from libtuya.devices.intelligent_device import IntelligentDevice
from libtuya.auth.models import DeviceInfo, DeviceDiscoveryResult
from libtuya.intelligence import DeviceIntelligence
from libtuya.dps import DPSMapper
from libtuya.devices.factory import DeviceFactory


class TestDeviceManager:
    """Test DeviceManager functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Mock auth manager
        self.auth_manager = Mock()
        self.device_discovery_result = DeviceDiscoveryResult(
            devices=[
                DeviceInfo(
                    id="light_123",
                    name="Test Light",
                    local_key="test_key_1",
                    category="dj",
                    product_id="test",
                    product_name="test",
                    online=True,
                    ip="192.168.1.100",
                    uuid="test",
                    asset_id="test"
                ),
                DeviceInfo(
                    id="switch_123",
                    name="Test Switch",
                    local_key="test_key_2",
                    category="kg",
                    product_id="test",
                    product_name="test",
                    online=True,
                    ip="192.168.1.101",
                    uuid="test",
                    asset_id="test"
                )
            ],
            total_count=2
        )
        self.auth_manager.discover_devices.return_value = self.device_discovery_result
        
        # Mock components
        self.intelligence = Mock(spec=DeviceIntelligence)
        self.dps_mapper = Mock(spec=DPSMapper)
        self.device_factory = Mock(spec=DeviceFactory)
        
        # Mock device factory validation
        self.device_factory.validate_device_info.return_value = {
            "valid": True,
            "errors": [],
            "warnings": []
        }
        
        # Create device manager
        self.manager = DeviceManager(
            auth_manager=self.auth_manager,
            intelligence=self.intelligence,
            dps_mapper=self.dps_mapper,
            device_factory=self.device_factory
        )
    
    def test_device_manager_initialization(self):
        """Test DeviceManager initialization."""
        assert self.manager.auth_manager == self.auth_manager
        assert self.manager.intelligence == self.intelligence
        assert self.manager.dps_mapper == self.dps_mapper
        assert self.manager.device_factory == self.device_factory
        assert len(self.manager.active_devices) == 0
    
    def test_device_manager_default_components(self):
        """Test DeviceManager with default components."""
        manager = DeviceManager(auth_manager=self.auth_manager)
        
        assert manager.auth_manager == self.auth_manager
        assert isinstance(manager.intelligence, DeviceIntelligence)
        assert isinstance(manager.dps_mapper, DPSMapper)
        assert isinstance(manager.device_factory, DeviceFactory)
    
    def test_discover_devices(self):
        """Test device discovery."""
        devices = self.manager.discover_devices()
        
        assert len(devices) == 2
        assert devices[0].id == "light_123"
        assert devices[1].id == "switch_123"
        self.auth_manager.discover_devices.assert_called_once()
    
    def test_discover_devices_no_auth_manager(self):
        """Test device discovery without auth manager."""
        manager = DeviceManager()
        
        with pytest.raises(RuntimeError, match="Auth manager not configured"):
            manager.discover_devices()
    
    def test_create_device_specialized(self):
        """Test creating specialized device."""
        device_info = self.device_discovery_result.devices[0]  # Light
        
        with patch('libtuya.devices.create_specialized_device') as mock_create:
            mock_device = Mock(spec=IntelligentLight)
            mock_create.return_value = mock_device
            
            device = self.manager.create_device(device_info, use_specialized_type=True)
            
            assert device == mock_device
            assert self.manager.active_devices["light_123"] == mock_device
            mock_create.assert_called_once_with(
                device_info=device_info,
                intelligence=self.intelligence,
                dps_mapper=self.dps_mapper,
                device_factory=self.device_factory
            )
    
    def test_create_device_generic(self):
        """Test creating generic device."""
        device_info = self.device_discovery_result.devices[0]
        
        with patch('libtuya.devices.create_intelligent_device') as mock_create:
            mock_device = Mock(spec=IntelligentDevice)
            mock_create.return_value = mock_device
            
            device = self.manager.create_device(device_info, use_specialized_type=False)
            
            assert device == mock_device
            assert self.manager.active_devices["light_123"] == mock_device
            mock_create.assert_called_once_with(
                device_info=device_info,
                intelligence=self.intelligence,
                dps_mapper=self.dps_mapper
            )
    
    def test_create_device_validation_failure(self):
        """Test creating device with validation failure."""
        device_info = self.device_discovery_result.devices[0]
        
        # Mock validation failure
        self.device_factory.validate_device_info.return_value = {
            "valid": False,
            "errors": ["Test error"],
            "warnings": []
        }
        
        with patch('libtuya.devices.create_specialized_device') as mock_create:
            mock_device = Mock(spec=IntelligentLight)
            mock_create.return_value = mock_device
            
            # Should still create device but log warning
            device = self.manager.create_device(device_info)
            
            assert device == mock_device
            assert self.manager.active_devices["light_123"] == mock_device
    
    def test_get_device(self):
        """Test getting device by ID."""
        device_info = self.device_discovery_result.devices[0]
        
        with patch('libtuya.devices.create_specialized_device') as mock_create:
            mock_device = Mock(spec=IntelligentLight)
            mock_create.return_value = mock_device
            
            created_device = self.manager.create_device(device_info)
            retrieved_device = self.manager.get_device("light_123")
            
            assert retrieved_device == mock_device
            assert retrieved_device == created_device
    
    def test_get_device_not_found(self):
        """Test getting non-existent device."""
        device = self.manager.get_device("nonexistent")
        assert device is None
    
    def test_get_devices_by_category(self):
        """Test getting devices by category."""
        # Create devices
        light_info = self.device_discovery_result.devices[0]
        switch_info = self.device_discovery_result.devices[1]
        
        with patch('libtuya.devices.create_specialized_device') as mock_create:
            mock_light = Mock(spec=IntelligentLight)
            mock_light.category = "dj"
            mock_switch = Mock(spec=IntelligentSwitch)
            mock_switch.category = "kg"
            
            mock_create.side_effect = [mock_light, mock_switch]
            
            self.manager.create_device(light_info)
            self.manager.create_device(switch_info)
            
            # Get lights
            lights = self.manager.get_devices_by_category("dj")
            assert len(lights) == 1
            assert lights[0] == mock_light
            
            # Get switches
            switches = self.manager.get_devices_by_category("kg")
            assert len(switches) == 1
            assert switches[0] == mock_switch
    
    def test_get_devices_by_type(self):
        """Test getting devices by type."""
        # Create devices
        light_info = self.device_discovery_result.devices[0]
        switch_info = self.device_discovery_result.devices[1]
        
        with patch('libtuya.devices.create_specialized_device') as mock_create:
            mock_light = Mock(spec=IntelligentLight)
            mock_switch = Mock(spec=IntelligentSwitch)
            
            mock_create.side_effect = [mock_light, mock_switch]
            
            self.manager.create_device(light_info)
            self.manager.create_device(switch_info)
            
            # Get lights by type
            lights = self.manager.get_devices_by_type(IntelligentLight)
            assert len(lights) == 1
            assert lights[0] == mock_light
            
            # Get switches by type
            switches = self.manager.get_devices_by_type(IntelligentSwitch)
            assert len(switches) == 1
            assert switches[0] == mock_switch
    
    def test_get_lights(self):
        """Test getting all light devices."""
        light_info = self.device_discovery_result.devices[0]
        
        with patch('libtuya.devices.create_specialized_device') as mock_create:
            mock_light = Mock(spec=IntelligentLight)
            mock_create.return_value = mock_light
            
            self.manager.create_device(light_info)
            
            lights = self.manager.get_lights()
            assert len(lights) == 1
            assert lights[0] == mock_light
    
    def test_get_switches(self):
        """Test getting all switch devices."""
        switch_info = self.device_discovery_result.devices[1]
        
        with patch('libtuya.devices.create_specialized_device') as mock_create:
            mock_switch = Mock(spec=IntelligentSwitch)
            mock_create.return_value = mock_switch
            
            self.manager.create_device(switch_info)
            
            switches = self.manager.get_switches()
            assert len(switches) == 1
            assert switches[0] == mock_switch
    
    def test_close_device(self):
        """Test closing a device."""
        device_info = self.device_discovery_result.devices[0]
        
        with patch('libtuya.devices.create_specialized_device') as mock_create:
            mock_device = Mock(spec=IntelligentLight)
            mock_create.return_value = mock_device
            
            self.manager.create_device(device_info)
            assert len(self.manager.active_devices) == 1
            
            self.manager.close_device("light_123")
            
            assert len(self.manager.active_devices) == 0
            mock_device.close.assert_called_once()
    
    def test_close_device_not_found(self):
        """Test closing non-existent device."""
        # Should not raise error
        self.manager.close_device("nonexistent")
    
    def test_close_all_devices(self):
        """Test closing all devices."""
        # Create devices
        light_info = self.device_discovery_result.devices[0]
        switch_info = self.device_discovery_result.devices[1]
        
        with patch('libtuya.devices.create_specialized_device') as mock_create:
            mock_light = Mock(spec=IntelligentLight)
            mock_switch = Mock(spec=IntelligentSwitch)
            
            mock_create.side_effect = [mock_light, mock_switch]
            
            self.manager.create_device(light_info)
            self.manager.create_device(switch_info)
            
            assert len(self.manager.active_devices) == 2
            
            self.manager.close_all_devices()
            
            assert len(self.manager.active_devices) == 0
            mock_light.close.assert_called_once()
            mock_switch.close.assert_called_once()
    
    def test_get_device_stats(self):
        """Test getting device statistics."""
        # Create devices
        light_info = self.device_discovery_result.devices[0]
        switch_info = self.device_discovery_result.devices[1]
        
        with patch('libtuya.devices.create_specialized_device') as mock_create:
            mock_light = Mock(spec=IntelligentLight)
            mock_light.category = "dj"
            mock_light.is_online = True
            
            mock_switch = Mock(spec=IntelligentSwitch)
            mock_switch.category = "kg"
            mock_switch.is_online = False
            
            mock_create.side_effect = [mock_light, mock_switch]
            
            self.manager.create_device(light_info)
            self.manager.create_device(switch_info)
            
            stats = self.manager.get_device_stats()
            
            assert stats["total_devices"] == 2
            assert stats["devices_by_category"]["dj"] == 1
            assert stats["devices_by_category"]["kg"] == 1
            assert stats["devices_by_type"]["IntelligentLight"] == 1
            assert stats["devices_by_type"]["IntelligentSwitch"] == 1
            assert stats["online_devices"] == 1
            assert stats["offline_devices"] == 1
    
    def test_discover_and_create_all(self):
        """Test discovering and creating all devices."""
        with patch('libtuya.devices.create_specialized_device') as mock_create:
            mock_light = Mock(spec=IntelligentLight)
            mock_switch = Mock(spec=IntelligentSwitch)
            
            mock_create.side_effect = [mock_light, mock_switch]
            
            devices = self.manager.discover_and_create_all()
            
            assert len(devices) == 2
            assert devices[0] == mock_light
            assert devices[1] == mock_switch
            assert len(self.manager.active_devices) == 2
    
    def test_discover_and_create_all_with_errors(self):
        """Test discovering and creating devices with errors."""
        with patch('libtuya.devices.create_specialized_device') as mock_create:
            mock_light = Mock(spec=IntelligentLight)
            mock_create.side_effect = [mock_light, Exception("Creation failed")]
            
            devices = self.manager.discover_and_create_all()
            
            assert len(devices) == 1  # Only successful device
            assert devices[0] == mock_light
            assert len(self.manager.active_devices) == 1
    
    def test_validate_all_devices(self):
        """Test validating all devices."""
        # Create devices
        light_info = self.device_discovery_result.devices[0]
        switch_info = self.device_discovery_result.devices[1]
        
        with patch('libtuya.devices.create_specialized_device') as mock_create:
            mock_light = Mock(spec=IntelligentLight)
            mock_light.validate_setup.return_value = {"valid": True, "errors": []}
            
            mock_switch = Mock(spec=IntelligentSwitch)
            mock_switch.validate_setup.return_value = {"valid": False, "errors": ["Test error"]}
            
            mock_create.side_effect = [mock_light, mock_switch]
            
            self.manager.create_device(light_info)
            self.manager.create_device(switch_info)
            
            validation = self.manager.validate_all_devices()
            
            assert validation["total_devices"] == 2
            assert validation["valid_devices"] == 1
            assert validation["invalid_devices"] == 1
            assert len(validation["validation_results"]) == 2
            assert validation["validation_results"]["light_123"]["valid"] is True
            assert validation["validation_results"]["switch_123"]["valid"] is False
    
    def test_validate_all_devices_with_exceptions(self):
        """Test validating devices with exceptions."""
        device_info = self.device_discovery_result.devices[0]
        
        with patch('libtuya.devices.create_specialized_device') as mock_create:
            mock_device = Mock(spec=IntelligentLight)
            mock_device.validate_setup.side_effect = Exception("Validation failed")
            
            mock_create.return_value = mock_device
            
            self.manager.create_device(device_info)
            
            validation = self.manager.validate_all_devices()
            
            assert validation["total_devices"] == 1
            assert validation["valid_devices"] == 0
            assert validation["invalid_devices"] == 1
            assert validation["validation_results"]["light_123"]["valid"] is False
            assert "Validation failed" in validation["validation_results"]["light_123"]["errors"][0]
    
    def test_context_manager(self):
        """Test DeviceManager as context manager."""
        # Create devices
        light_info = self.device_discovery_result.devices[0]
        
        with patch('libtuya.devices.create_specialized_device') as mock_create:
            mock_light = Mock(spec=IntelligentLight)
            mock_create.return_value = mock_light
            
            with DeviceManager(auth_manager=self.auth_manager) as manager:
                manager.create_device(light_info)
                assert len(manager.active_devices) == 1
            
            # Should have closed all devices
            mock_light.close.assert_called_once()


class TestDeviceManagerConvenienceFunctions:
    """Test convenience functions for DeviceManager."""
    
    def test_discover_and_create_devices(self):
        """Test discover_and_create_devices function."""
        from libtuya.devices import discover_and_create_devices
        
        auth_manager = Mock()
        device_discovery_result = DeviceDiscoveryResult(
            devices=[
                DeviceInfo(
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
            ],
            total_count=1
        )
        auth_manager.discover_devices.return_value = device_discovery_result
        
        with patch('libtuya.devices.DeviceManager') as mock_manager_class:
            mock_manager = Mock()
            mock_device = Mock()
            mock_manager.discover_and_create_all.return_value = [mock_device]
            mock_manager_class.return_value = mock_manager
            
            devices = discover_and_create_devices(auth_manager)
            
            assert len(devices) == 1
            assert devices[0] == mock_device
            mock_manager_class.assert_called_once_with(auth_manager=auth_manager)
            mock_manager.discover_and_create_all.assert_called_once()