"""
Tests for device factory pattern.

Tests the DeviceFactory class and its ability to map device categories
to appropriate TinyTuya device classes.
"""

import pytest
from unittest.mock import Mock, patch
from libtuya.devices.factory import DeviceFactory, DeviceClassMapping, create_device_from_info
from libtuya.auth.models import DeviceInfo


class TestDeviceFactory:
    """Test DeviceFactory functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.factory = DeviceFactory()
        
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
    
    def test_device_factory_initialization(self):
        """Test DeviceFactory initialization."""
        factory = DeviceFactory()
        
        assert factory.enable_auto_discovery is True
        assert factory.default_timeout == 5
        assert factory.default_version == 3.3
        assert len(factory._device_cache) == 0
    
    def test_device_factory_custom_settings(self):
        """Test DeviceFactory with custom settings."""
        factory = DeviceFactory(
            enable_auto_discovery=False,
            default_timeout=10,
            default_version=3.4
        )
        
        assert factory.enable_auto_discovery is False
        assert factory.default_timeout == 10
        assert factory.default_version == 3.4
    
    def test_get_device_mapping_light(self):
        """Test getting device mapping for light category."""
        mapping = self.factory.get_device_mapping("dj")
        
        assert mapping is not None
        assert mapping.description == "Smart Light/Bulb"
        assert "switch_led" in mapping.capabilities
        assert "bright_value" in mapping.capabilities
        assert "colour_data" in mapping.capabilities
    
    def test_get_device_mapping_switch(self):
        """Test getting device mapping for switch category."""
        mapping = self.factory.get_device_mapping("kg")
        
        assert mapping is not None
        assert mapping.description == "Switch"
        assert "switch" in mapping.capabilities
    
    def test_get_device_mapping_unknown(self):
        """Test getting device mapping for unknown category."""
        mapping = self.factory.get_device_mapping("unknown")
        
        assert mapping is None
    
    def test_get_supported_categories(self):
        """Test getting supported categories."""
        categories = self.factory.get_supported_categories()
        
        assert isinstance(categories, list)
        assert len(categories) > 0
        assert "dj" in categories  # Light
        assert "kg" in categories  # Switch
        assert "cl" in categories  # Curtain
    
    def test_get_category_info(self):
        """Test getting category information."""
        info = self.factory.get_category_info("dj")
        
        assert info is not None
        assert info["category"] == "dj"
        assert info["description"] == "Smart Light/Bulb"
        assert info["is_light"] is True
        assert info["is_switch"] is False
        assert isinstance(info["capabilities"], list)
        assert isinstance(info["typical_dps"], dict)
    
    def test_detect_device_category(self):
        """Test device category detection from capabilities."""
        # Light capabilities
        light_capabilities = ["switch_led", "bright_value", "colour_data"]
        suggestions = self.factory.detect_device_category(light_capabilities)
        
        assert isinstance(suggestions, list)
        assert len(suggestions) > 0
        assert "dj" in suggestions[:3]  # Should be in top suggestions
        
        # Switch capabilities
        switch_capabilities = ["switch", "cur_power"]
        suggestions = self.factory.detect_device_category(switch_capabilities)
        
        assert isinstance(suggestions, list)
        assert len(suggestions) > 0
        # Should suggest switch or socket categories
        assert any(cat in ["kg", "pc", "cz"] for cat in suggestions[:3])
    
    @patch('libtuya.devices.factory.BulbDevice')
    def test_create_device_light(self, mock_bulb):
        """Test creating a light device."""
        mock_device = Mock()
        mock_bulb.return_value = mock_device
        
        device = self.factory.create_device(self.device_info)
        
        assert device is mock_device
        mock_bulb.assert_called_once()
        
        # Check call arguments
        call_args = mock_bulb.call_args
        assert call_args[1]["dev_id"] == "test_device_123"
        assert call_args[1]["address"] == "192.168.1.100"
        assert call_args[1]["local_key"] == "abcdef1234567890"
        assert call_args[1]["version"] == 3.3
    
    @patch('libtuya.devices.factory.Device')
    def test_create_device_unknown_category(self, mock_device):
        """Test creating device with unknown category."""
        mock_device_instance = Mock()
        mock_device.return_value = mock_device_instance
        
        # Unknown category device
        unknown_device_info = DeviceInfo(
            id="unknown_device",
            name="Unknown Device",
            local_key="test_key",
            category="unknown_category",
            product_id="test",
            product_name="test",
            online=True,
            ip="192.168.1.100",
            uuid="test",
            asset_id="test"
        )
        
        device = self.factory.create_device(unknown_device_info)
        
        assert device is mock_device_instance
        mock_device.assert_called_once()
    
    def test_create_device_auto_discovery(self):
        """Test creating device with auto-discovery."""
        # Device with no IP
        no_ip_device = DeviceInfo(
            id="no_ip_device",
            name="No IP Device",
            local_key="test_key",
            category="dj",
            product_id="test",
            product_name="test",
            online=True,
            ip="",
            uuid="test",
            asset_id="test"
        )
        
        with patch('libtuya.devices.factory.BulbDevice') as mock_bulb:
            mock_device = Mock()
            mock_bulb.return_value = mock_device
            
            device = self.factory.create_device(no_ip_device)
            
            call_args = mock_bulb.call_args
            assert call_args[1]["address"] == "Auto"
    
    def test_create_device_caching(self):
        """Test device caching functionality."""
        with patch('libtuya.devices.factory.BulbDevice') as mock_bulb:
            mock_device = Mock()
            mock_bulb.return_value = mock_device
            
            # First call
            device1 = self.factory.create_device(self.device_info)
            
            # Second call should return cached device
            device2 = self.factory.create_device(self.device_info)
            
            assert device1 is device2
            assert mock_bulb.call_count == 1  # Only called once
    
    def test_validate_device_info_valid(self):
        """Test validating valid device info."""
        validation = self.factory.validate_device_info(self.device_info)
        
        assert validation["valid"] is True
        assert len(validation["errors"]) == 0
        assert validation["category_supported"] is True
        assert validation["category_info"] is not None
    
    def test_validate_device_info_missing_fields(self):
        """Test validating device info with missing fields."""
        invalid_device = DeviceInfo(
            id="",  # Missing ID
            name="Test",
            local_key="",  # Missing local key
            category="",  # Missing category
            product_id="test",
            product_name="test",
            online=True,
            ip="192.168.1.100",
            uuid="test",
            asset_id="test"
        )
        
        validation = self.factory.validate_device_info(invalid_device)
        
        assert validation["valid"] is False
        assert len(validation["errors"]) == 3
        assert "Device ID is required" in validation["errors"]
        assert "Local key is required" in validation["errors"]
        assert "Device category is required" in validation["errors"]
    
    def test_validate_device_info_unknown_category(self):
        """Test validating device info with unknown category."""
        unknown_device = DeviceInfo(
            id="test_device",
            name="Test Device",
            local_key="test_key",
            category="unknown_category",
            product_id="test",
            product_name="test",
            online=True,
            ip="192.168.1.100",
            uuid="test",
            asset_id="test"
        )
        
        validation = self.factory.validate_device_info(unknown_device)
        
        assert validation["valid"] is True  # Still valid, just unknown category
        assert len(validation["warnings"]) > 0
        assert validation["category_supported"] is False
    
    def test_clear_cache(self):
        """Test clearing device cache."""
        with patch('libtuya.devices.factory.BulbDevice') as mock_bulb:
            mock_device = Mock()
            mock_bulb.return_value = mock_device
            
            # Create device to populate cache
            self.factory.create_device(self.device_info)
            assert len(self.factory._device_cache) == 1
            
            # Clear cache
            self.factory.clear_cache()
            assert len(self.factory._device_cache) == 0
    
    def test_get_cache_stats(self):
        """Test getting cache statistics."""
        with patch('libtuya.devices.factory.BulbDevice') as mock_bulb:
            mock_device = Mock()
            mock_bulb.return_value = mock_device
            
            # Empty cache
            stats = self.factory.get_cache_stats()
            assert stats["cached_devices"] == 0
            assert stats["device_ids"] == []
            assert stats["total_categories"] > 0
            
            # Create device
            self.factory.create_device(self.device_info)
            
            # Check stats
            stats = self.factory.get_cache_stats()
            assert stats["cached_devices"] == 1
            assert "test_device_123" in stats["device_ids"]


class TestDeviceClassMapping:
    """Test DeviceClassMapping functionality."""
    
    def test_device_class_mapping_creation(self):
        """Test creating DeviceClassMapping."""
        from libtuya.devices.factory import Device
        
        mapping = DeviceClassMapping(
            tinytuya_class=Device,
            capabilities=["switch", "power"],
            typical_dps={1: "switch", 2: "power"},
            description="Test Device"
        )
        
        assert mapping.tinytuya_class == Device
        assert mapping.capabilities == ["switch", "power"]
        assert mapping.typical_dps == {1: "switch", 2: "power"}
        assert mapping.description == "Test Device"


class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_create_device_from_info(self):
        """Test create_device_from_info function."""
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
        
        with patch('libtuya.devices.factory.device_factory') as mock_factory:
            mock_device = Mock()
            mock_factory.create_device.return_value = mock_device
            
            result = create_device_from_info(device_info)
            
            assert result is mock_device
            mock_factory.create_device.assert_called_once_with(device_info)
    
    def test_get_supported_categories_function(self):
        """Test get_supported_categories function."""
        from libtuya.devices.factory import get_supported_categories
        
        categories = get_supported_categories()
        
        assert isinstance(categories, list)
        assert len(categories) > 0
        assert "dj" in categories