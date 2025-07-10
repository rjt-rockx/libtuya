"""
Tests for authentication models.

These tests validate the data models used throughout the authentication system
including AuthSession, DeviceInfo, and related data structures.
"""

import pytest
import json
from unittest.mock import Mock
from datetime import datetime, timedelta

from libtuya.auth.models import (
    AuthSession, DeviceInfo, QRCodeData, AuthenticationError,
    DeviceDiscoveryResult
)


class TestAuthSession:
    """Test AuthSession model."""
    
    def test_init(self):
        """Test AuthSession initialization."""
        session = AuthSession(
            access_token="test-access-token",
            refresh_token="test-refresh-token",
            uid="test-uid",
            expire_time=1234567890,
            t=1234567890
        )
        
        assert session.access_token == "test-access-token"
        assert session.refresh_token == "test-refresh-token"
        assert session.uid == "test-uid"
        assert session.expire_time == 1234567890
        assert session.t == 1234567890
        assert session.client_id == "HA_3y9q4ak7g4ephrvke"
        assert session.user_code == ""
        assert session.terminal_id == ""
    
    def test_init_with_optional_fields(self):
        """Test AuthSession with optional fields."""
        session = AuthSession(
            access_token="test-access-token",
            refresh_token="test-refresh-token",
            uid="test-uid",
            expire_time=1234567890,
            t=1234567890,
            client_id="custom-client-id",
            user_code="custom-user-code",
            terminal_id="custom-terminal-id"
        )
        
        assert session.client_id == "custom-client-id"
        assert session.user_code == "custom-user-code"
        assert session.terminal_id == "custom-terminal-id"
    
    def test_is_expired_false(self):
        """Test is_expired when token is valid."""
        # Token expires in 2 hours
        future_time = int((datetime.now() + timedelta(hours=2)).timestamp() * 1000)
        
        session = AuthSession(
            access_token="test-token",
            refresh_token="test-refresh",
            uid="test-uid",
            expire_time=future_time,
            t=1234567890
        )
        
        assert session.is_expired is False
    
    def test_is_expired_true(self):
        """Test is_expired when token is expired."""
        # Token expired 1 hour ago
        past_time = int((datetime.now() - timedelta(hours=1)).timestamp() * 1000)
        
        session = AuthSession(
            access_token="test-token",
            refresh_token="test-refresh",
            uid="test-uid",
            expire_time=past_time,
            t=1234567890
        )
        
        assert session.is_expired is True
    
    def test_is_expired_near_expiry(self):
        """Test is_expired when token is near expiry (within 1 minute)."""
        # Token expires in 30 seconds (within 1 minute buffer)
        near_future = int((datetime.now() + timedelta(seconds=30)).timestamp() * 1000)
        
        session = AuthSession(
            access_token="test-token",
            refresh_token="test-refresh",
            uid="test-uid",
            expire_time=near_future,
            t=1234567890
        )
        
        assert session.is_expired is True
    
    def test_expires_in_minutes(self):
        """Test expires_in_minutes calculation."""
        # Token expires in 2 hours
        future_time = int((datetime.now() + timedelta(hours=2)).timestamp() * 1000)
        
        session = AuthSession(
            access_token="test-token",
            refresh_token="test-refresh",
            uid="test-uid",
            expire_time=future_time,
            t=1234567890
        )
        
        # Should be approximately 120 minutes (allow some variance for test execution time)
        assert 118 <= session.expires_in_minutes <= 120
    
    def test_expires_in_minutes_expired(self):
        """Test expires_in_minutes when token is expired."""
        # Token expired 1 hour ago
        past_time = int((datetime.now() - timedelta(hours=1)).timestamp() * 1000)
        
        session = AuthSession(
            access_token="test-token",
            refresh_token="test-refresh",
            uid="test-uid",
            expire_time=past_time,
            t=1234567890
        )
        
        assert session.expires_in_minutes == 0
    
    def test_to_dict(self):
        """Test AuthSession to dictionary conversion."""
        session = AuthSession(
            access_token="test-access-token",
            refresh_token="test-refresh-token",
            uid="test-uid",
            expire_time=1234567890,
            t=1234567890,
            client_id="test-client-id",
            user_code="test-user-code",
            terminal_id="test-terminal-id"
        )
        
        expected = {
            "access_token": "test-access-token",
            "refresh_token": "test-refresh-token",
            "uid": "test-uid",
            "expire_time": 1234567890,
            "t": 1234567890,
            "client_id": "test-client-id",
            "user_code": "test-user-code",
            "terminal_id": "test-terminal-id"
        }
        
        assert session.to_dict() == expected
    
    def test_from_dict(self):
        """Test AuthSession from dictionary creation."""
        data = {
            "access_token": "test-access-token",
            "refresh_token": "test-refresh-token",
            "uid": "test-uid",
            "expire_time": 1234567890,
            "t": 1234567890,
            "client_id": "test-client-id",
            "user_code": "test-user-code",
            "terminal_id": "test-terminal-id"
        }
        
        session = AuthSession.from_dict(data)
        
        assert session.access_token == "test-access-token"
        assert session.refresh_token == "test-refresh-token"
        assert session.uid == "test-uid"
        assert session.expire_time == 1234567890
        assert session.t == 1234567890
        assert session.client_id == "test-client-id"
        assert session.user_code == "test-user-code"
        assert session.terminal_id == "test-terminal-id"
    
    def test_to_json(self):
        """Test AuthSession to JSON conversion."""
        session = AuthSession(
            access_token="test-access-token",
            refresh_token="test-refresh-token",
            uid="test-uid",
            expire_time=1234567890,
            t=1234567890
        )
        
        json_str = session.to_json()
        parsed = json.loads(json_str)
        
        assert parsed["access_token"] == "test-access-token"
        assert parsed["refresh_token"] == "test-refresh-token"
        assert parsed["uid"] == "test-uid"
    
    def test_from_json(self):
        """Test AuthSession from JSON creation."""
        data = {
            "access_token": "test-access-token",
            "refresh_token": "test-refresh-token",
            "uid": "test-uid",
            "expire_time": 1234567890,
            "t": 1234567890
        }
        
        json_str = json.dumps(data)
        session = AuthSession.from_json(json_str)
        
        assert session.access_token == "test-access-token"
        assert session.refresh_token == "test-refresh-token"
        assert session.uid == "test-uid"


class TestDeviceInfo:
    """Test DeviceInfo model."""
    
    def test_init(self):
        """Test DeviceInfo initialization."""
        device = DeviceInfo(
            id="device-1",
            name="Test Light",
            local_key="test-local-key",
            category="dj",
            product_id="test-product",
            product_name="Smart Light",
            online=True,
            ip="192.168.1.100",
            uuid="test-uuid",
            asset_id="test-asset"
        )
        
        assert device.id == "device-1"
        assert device.name == "Test Light"
        assert device.local_key == "test-local-key"
        assert device.category == "dj"
        assert device.product_id == "test-product"
        assert device.product_name == "Smart Light"
        assert device.online is True
        assert device.ip == "192.168.1.100"
        assert device.uuid == "test-uuid"
        assert device.asset_id == "test-asset"
        
        # Test defaults
        assert device.sub is False
        assert device.icon == ""
        assert device.time_zone == ""
        assert device.active_time == 0
        assert device.create_time == 0
        assert device.update_time == 0
        assert device.set_up is False
        assert device.support_local is False
        assert device.local_strategy == {}
        assert device.status == {}
        assert device.function == {}
        assert device.status_range == {}
    
    def test_init_with_optional_fields(self):
        """Test DeviceInfo with optional fields."""
        device = DeviceInfo(
            id="device-1",
            name="Test Light",
            local_key="test-local-key",
            category="dj",
            product_id="test-product",
            product_name="Smart Light",
            online=True,
            ip="192.168.1.100",
            uuid="test-uuid",
            asset_id="test-asset",
            sub=True,
            icon="light-icon",
            time_zone="UTC",
            active_time=1234567890,
            create_time=1234567890,
            update_time=1234567890,
            set_up=True,
            support_local=True,
            local_strategy={1: {"test": "value"}},
            status={"switch_1": True},
            function={"switch_1": "toggle"},
            status_range={"switch_1": {"type": "bool"}}
        )
        
        assert device.sub is True
        assert device.icon == "light-icon"
        assert device.time_zone == "UTC"
        assert device.active_time == 1234567890
        assert device.create_time == 1234567890
        assert device.update_time == 1234567890
        assert device.set_up is True
        assert device.support_local is True
        assert device.local_strategy == {1: {"test": "value"}}
        assert device.status == {"switch_1": True}
        assert device.function == {"switch_1": "toggle"}
        assert device.status_range == {"switch_1": {"type": "bool"}}
    
    def test_from_customer_device(self):
        """Test DeviceInfo creation from CustomerDevice."""
        # Mock CustomerDevice
        mock_customer_device = Mock()
        mock_customer_device.id = "device-1"
        mock_customer_device.name = "Test Light"
        mock_customer_device.local_key = "test-local-key"
        mock_customer_device.category = "dj"
        mock_customer_device.product_id = "test-product"
        mock_customer_device.product_name = "Smart Light"
        mock_customer_device.online = True
        mock_customer_device.ip = "192.168.1.100"
        mock_customer_device.uuid = "test-uuid"
        mock_customer_device.asset_id = "test-asset"
        mock_customer_device.sub = True
        mock_customer_device.icon = "light-icon"
        mock_customer_device.time_zone = "UTC"
        mock_customer_device.active_time = 1234567890
        mock_customer_device.create_time = 1234567890
        mock_customer_device.update_time = 1234567890
        mock_customer_device.set_up = True
        mock_customer_device.support_local = True
        mock_customer_device.local_strategy = {1: {"test": "value"}}
        mock_customer_device.status = {"switch_1": True}
        mock_customer_device.function = {"switch_1": "toggle"}
        mock_customer_device.status_range = {"switch_1": {"type": "bool"}}
        
        device = DeviceInfo.from_customer_device(mock_customer_device)
        
        assert device.id == "device-1"
        assert device.name == "Test Light"
        assert device.local_key == "test-local-key"
        assert device.category == "dj"
        assert device.product_id == "test-product"
        assert device.product_name == "Smart Light"
        assert device.online is True
        assert device.ip == "192.168.1.100"
        assert device.uuid == "test-uuid"
        assert device.asset_id == "test-asset"
        assert device.sub is True
        assert device.icon == "light-icon"
        assert device.time_zone == "UTC"
        assert device.active_time == 1234567890
        assert device.create_time == 1234567890
        assert device.update_time == 1234567890
        assert device.set_up is True
        assert device.support_local is True
        assert device.local_strategy == {1: {"test": "value"}}
        assert device.status == {"switch_1": True}
        assert device.function == {"switch_1": "toggle"}
        assert device.status_range == {"switch_1": {"type": "bool"}}
    
    def test_from_customer_device_missing_attributes(self):
        """Test DeviceInfo creation from CustomerDevice with missing attributes."""
        # Mock CustomerDevice with only required attributes
        mock_customer_device = Mock()
        mock_customer_device.id = "device-1"
        mock_customer_device.name = "Test Light"
        mock_customer_device.local_key = "test-local-key"
        mock_customer_device.category = "dj"
        mock_customer_device.product_id = "test-product"
        mock_customer_device.product_name = "Smart Light"
        mock_customer_device.online = True
        mock_customer_device.ip = "192.168.1.100"
        mock_customer_device.uuid = "test-uuid"
        mock_customer_device.asset_id = "test-asset"
        
        # Remove optional attributes to test defaults
        del mock_customer_device.sub
        del mock_customer_device.icon
        del mock_customer_device.time_zone
        del mock_customer_device.active_time
        del mock_customer_device.create_time
        del mock_customer_device.update_time
        del mock_customer_device.set_up
        del mock_customer_device.support_local
        del mock_customer_device.local_strategy
        del mock_customer_device.status
        del mock_customer_device.function
        del mock_customer_device.status_range
        
        device = DeviceInfo.from_customer_device(mock_customer_device)
        
        assert device.id == "device-1"
        assert device.name == "Test Light"
        assert device.local_key == "test-local-key"
        # Test defaults for missing attributes
        assert device.sub is False
        assert device.icon == ""
        assert device.time_zone == ""
        assert device.active_time == 0
        assert device.create_time == 0
        assert device.update_time == 0
        assert device.set_up is False
        assert device.support_local is False
        assert device.local_strategy == {}
        assert device.status == {}
        assert device.function == {}
        assert device.status_range == {}
    
    def test_has_local_key_true(self):
        """Test has_local_key when device has local key."""
        device = DeviceInfo(
            id="device-1",
            name="Test Light",
            local_key="test-local-key",
            category="dj",
            product_id="test-product",
            product_name="Smart Light",
            online=True,
            ip="192.168.1.100",
            uuid="test-uuid",
            asset_id="test-asset"
        )
        
        assert device.has_local_key is True
    
    def test_has_local_key_false_empty(self):
        """Test has_local_key when device has empty local key."""
        device = DeviceInfo(
            id="device-1",
            name="Test Light",
            local_key="",
            category="dj",
            product_id="test-product",
            product_name="Smart Light",
            online=True,
            ip="192.168.1.100",
            uuid="test-uuid",
            asset_id="test-asset"
        )
        
        assert device.has_local_key is False
    
    def test_has_local_key_false_whitespace(self):
        """Test has_local_key when device has whitespace local key."""
        device = DeviceInfo(
            id="device-1",
            name="Test Light",
            local_key="   ",
            category="dj",
            product_id="test-product",
            product_name="Smart Light",
            online=True,
            ip="192.168.1.100",
            uuid="test-uuid",
            asset_id="test-asset"
        )
        
        assert device.has_local_key is False
    
    def test_can_control_locally_true(self):
        """Test can_control_locally when device can be controlled locally."""
        device = DeviceInfo(
            id="device-1",
            name="Test Light",
            local_key="test-local-key",
            category="dj",
            product_id="test-product",
            product_name="Smart Light",
            online=True,
            ip="192.168.1.100",
            uuid="test-uuid",
            asset_id="test-asset"
        )
        
        assert device.can_control_locally is True
    
    def test_can_control_locally_false_no_local_key(self):
        """Test can_control_locally when device has no local key."""
        device = DeviceInfo(
            id="device-1",
            name="Test Light",
            local_key="",
            category="dj",
            product_id="test-product",
            product_name="Smart Light",
            online=True,
            ip="192.168.1.100",
            uuid="test-uuid",
            asset_id="test-asset"
        )
        
        assert device.can_control_locally is False
    
    def test_can_control_locally_false_offline(self):
        """Test can_control_locally when device is offline."""
        device = DeviceInfo(
            id="device-1",
            name="Test Light",
            local_key="test-local-key",
            category="dj",
            product_id="test-product",
            product_name="Smart Light",
            online=False,
            ip="192.168.1.100",
            uuid="test-uuid",
            asset_id="test-asset"
        )
        
        assert device.can_control_locally is False
    
    def test_can_control_locally_false_no_ip(self):
        """Test can_control_locally when device has no IP."""
        device = DeviceInfo(
            id="device-1",
            name="Test Light",
            local_key="test-local-key",
            category="dj",
            product_id="test-product",
            product_name="Smart Light",
            online=True,
            ip="",
            uuid="test-uuid",
            asset_id="test-asset"
        )
        
        assert device.can_control_locally is False
    
    def test_device_type_known_categories(self):
        """Test device_type for known categories."""
        test_cases = [
            ("dj", "Light"),
            ("cz", "Socket"),
            ("kg", "Switch"),
            ("pc", "Power Strip"),
            ("xdd", "Bulb"),
            ("fsd", "Fan"),
            ("cl", "Curtain"),
            ("ms", "Sensor"),
            ("wk", "Thermostat"),
            ("sp", "Smart Plug")
        ]
        
        for category, expected_type in test_cases:
            device = DeviceInfo(
                id="device-1",
                name="Test Device",
                local_key="test-local-key",
                category=category,
                product_id="test-product",
                product_name="Smart Device",
                online=True,
                ip="192.168.1.100",
                uuid="test-uuid",
                asset_id="test-asset"
            )
            
            assert device.device_type == expected_type
    
    def test_device_type_unknown_category(self):
        """Test device_type for unknown category."""
        device = DeviceInfo(
            id="device-1",
            name="Test Device",
            local_key="test-local-key",
            category="unknown",
            product_id="test-product",
            product_name="Smart Device",
            online=True,
            ip="192.168.1.100",
            uuid="test-uuid",
            asset_id="test-asset"
        )
        
        assert device.device_type == "Unknown (unknown)"
    
    def test_get_status_value(self):
        """Test get_status_value method."""
        device = DeviceInfo(
            id="device-1",
            name="Test Light",
            local_key="test-local-key",
            category="dj",
            product_id="test-product",
            product_name="Smart Light",
            online=True,
            ip="192.168.1.100",
            uuid="test-uuid",
            asset_id="test-asset",
            status={"switch_1": True, "bright_value": 800}
        )
        
        assert device.get_status_value("switch_1") is True
        assert device.get_status_value("bright_value") == 800
        assert device.get_status_value("nonexistent") is None
        assert device.get_status_value("nonexistent", "default") == "default"
    
    def test_has_function(self):
        """Test has_function method."""
        device = DeviceInfo(
            id="device-1",
            name="Test Light",
            local_key="test-local-key",
            category="dj",
            product_id="test-product",
            product_name="Smart Light",
            online=True,
            ip="192.168.1.100",
            uuid="test-uuid",
            asset_id="test-asset",
            function={"switch_1": "toggle", "bright_value": "brightness"}
        )
        
        assert device.has_function("switch_1") is True
        assert device.has_function("bright_value") is True
        assert device.has_function("nonexistent") is False
    
    def test_get_function_range(self):
        """Test get_function_range method."""
        device = DeviceInfo(
            id="device-1",
            name="Test Light",
            local_key="test-local-key",
            category="dj",
            product_id="test-product",
            product_name="Smart Light",
            online=True,
            ip="192.168.1.100",
            uuid="test-uuid",
            asset_id="test-asset",
            status_range={"switch_1": {"type": "bool"}, "bright_value": {"min": 10, "max": 1000}}
        )
        
        assert device.get_function_range("switch_1") == {"type": "bool"}
        assert device.get_function_range("bright_value") == {"min": 10, "max": 1000}
        assert device.get_function_range("nonexistent") is None
    
    def test_to_dict(self):
        """Test DeviceInfo to dictionary conversion."""
        device = DeviceInfo(
            id="device-1",
            name="Test Light",
            local_key="test-local-key",
            category="dj",
            product_id="test-product",
            product_name="Smart Light",
            online=True,
            ip="192.168.1.100",
            uuid="test-uuid",
            asset_id="test-asset",
            status={"switch_1": True}
        )
        
        result = device.to_dict()
        
        assert result["id"] == "device-1"
        assert result["name"] == "Test Light"
        assert result["local_key"] == "test-local-key"
        assert result["category"] == "dj"
        assert result["device_type"] == "Light"
        assert result["can_control_locally"] is True
        assert result["status"] == {"switch_1": True}


class TestDeviceDiscoveryResult:
    """Test DeviceDiscoveryResult model."""
    
    def test_init(self):
        """Test DeviceDiscoveryResult initialization."""
        device = DeviceInfo(
            id="device-1",
            name="Test Light",
            local_key="test-local-key",
            category="dj",
            product_id="test-product",
            product_name="Smart Light",
            online=True,
            ip="192.168.1.100",
            uuid="test-uuid",
            asset_id="test-asset"
        )
        
        result = DeviceDiscoveryResult(
            devices=[device],
            total_count=1
        )
        
        assert len(result.devices) == 1
        assert result.total_count == 1
        assert isinstance(result.discovery_time, datetime)
        assert result.errors == []
    
    def test_init_with_errors(self):
        """Test DeviceDiscoveryResult with errors."""
        result = DeviceDiscoveryResult(
            devices=[],
            total_count=0,
            errors=["Error 1", "Error 2"]
        )
        
        assert len(result.devices) == 0
        assert result.total_count == 0
        assert result.errors == ["Error 1", "Error 2"]
    
    def test_success_property(self):
        """Test success property."""
        # Success case
        result1 = DeviceDiscoveryResult(devices=[], total_count=0)
        assert result1.success is True
        
        # Error case
        result2 = DeviceDiscoveryResult(devices=[], total_count=0, errors=["Error 1"])
        assert result2.success is False
    
    def test_devices_with_local_keys(self):
        """Test devices_with_local_keys property."""
        device1 = DeviceInfo(
            id="device-1", name="Light 1", local_key="local-key-1",
            category="dj", product_id="p1", product_name="Light", 
            online=True, ip="192.168.1.100", uuid="uuid-1", asset_id="a1"
        )
        
        device2 = DeviceInfo(
            id="device-2", name="Switch 1", local_key="",  # No local key
            category="kg", product_id="p2", product_name="Switch",
            online=True, ip="192.168.1.101", uuid="uuid-2", asset_id="a2"
        )
        
        result = DeviceDiscoveryResult(
            devices=[device1, device2],
            total_count=2
        )
        
        devices_with_keys = result.devices_with_local_keys
        assert len(devices_with_keys) == 1
        assert devices_with_keys[0].id == "device-1"
    
    def test_online_devices(self):
        """Test online_devices property."""
        device1 = DeviceInfo(
            id="device-1", name="Light 1", local_key="local-key-1",
            category="dj", product_id="p1", product_name="Light", 
            online=True, ip="192.168.1.100", uuid="uuid-1", asset_id="a1"
        )
        
        device2 = DeviceInfo(
            id="device-2", name="Switch 1", local_key="local-key-2",
            category="kg", product_id="p2", product_name="Switch",
            online=False, ip="192.168.1.101", uuid="uuid-2", asset_id="a2"
        )
        
        result = DeviceDiscoveryResult(
            devices=[device1, device2],
            total_count=2
        )
        
        online_devices = result.online_devices
        assert len(online_devices) == 1
        assert online_devices[0].id == "device-1"
    
    def test_controllable_devices(self):
        """Test controllable_devices property."""
        device1 = DeviceInfo(
            id="device-1", name="Light 1", local_key="local-key-1",
            category="dj", product_id="p1", product_name="Light", 
            online=True, ip="192.168.1.100", uuid="uuid-1", asset_id="a1"
        )
        
        device2 = DeviceInfo(
            id="device-2", name="Switch 1", local_key="",  # No local key
            category="kg", product_id="p2", product_name="Switch",
            online=True, ip="192.168.1.101", uuid="uuid-2", asset_id="a2"
        )
        
        result = DeviceDiscoveryResult(
            devices=[device1, device2],
            total_count=2
        )
        
        controllable_devices = result.controllable_devices
        assert len(controllable_devices) == 1
        assert controllable_devices[0].id == "device-1"
    
    def test_get_devices_by_category(self):
        """Test get_devices_by_category method."""
        device1 = DeviceInfo(
            id="device-1", name="Light 1", local_key="local-key-1",
            category="dj", product_id="p1", product_name="Light", 
            online=True, ip="192.168.1.100", uuid="uuid-1", asset_id="a1"
        )
        
        device2 = DeviceInfo(
            id="device-2", name="Switch 1", local_key="local-key-2",
            category="kg", product_id="p2", product_name="Switch",
            online=True, ip="192.168.1.101", uuid="uuid-2", asset_id="a2"
        )
        
        device3 = DeviceInfo(
            id="device-3", name="Light 2", local_key="local-key-3",
            category="dj", product_id="p3", product_name="Light", 
            online=True, ip="192.168.1.102", uuid="uuid-3", asset_id="a3"
        )
        
        result = DeviceDiscoveryResult(
            devices=[device1, device2, device3],
            total_count=3
        )
        
        # Test getting lights
        lights = result.get_devices_by_category("dj")
        assert len(lights) == 2
        assert all(device.category == "dj" for device in lights)
        
        # Test getting switches
        switches = result.get_devices_by_category("kg")
        assert len(switches) == 1
        assert switches[0].id == "device-2"
        
        # Test getting non-existent category
        result_empty = result.get_devices_by_category("nonexistent")
        assert len(result_empty) == 0
    
    def test_to_dict(self):
        """Test DeviceDiscoveryResult to dictionary conversion."""
        device = DeviceInfo(
            id="device-1",
            name="Test Light",
            local_key="test-local-key",
            category="dj",
            product_id="test-product",
            product_name="Smart Light",
            online=True,
            ip="192.168.1.100",
            uuid="test-uuid",
            asset_id="test-asset"
        )
        
        result = DeviceDiscoveryResult(
            devices=[device],
            total_count=1,
            errors=["Test error"]
        )
        
        result_dict = result.to_dict()
        
        assert len(result_dict["devices"]) == 1
        assert result_dict["total_count"] == 1
        assert result_dict["errors"] == ["Test error"]
        assert result_dict["success"] is False
        assert result_dict["devices_with_keys"] == 1
        assert result_dict["online_devices"] == 1
        assert result_dict["controllable_devices"] == 1
        assert "discovery_time" in result_dict


class TestAuthenticationError:
    """Test AuthenticationError model."""
    
    def test_init(self):
        """Test AuthenticationError initialization."""
        error = AuthenticationError(
            message="Test error message",
            error_code="TEST_ERROR",
            details={"key": "value"}
        )
        
        assert error.message == "Test error message"
        assert error.error_code == "TEST_ERROR"
        assert error.details == {"key": "value"}
    
    def test_init_defaults(self):
        """Test AuthenticationError with default values."""
        error = AuthenticationError("Test error message")
        
        assert error.message == "Test error message"
        assert error.error_code == "UNKNOWN"
        assert error.details == {}
    
    def test_str(self):
        """Test AuthenticationError string representation."""
        error = AuthenticationError(
            message="Test error message",
            error_code="TEST_ERROR"
        )
        
        assert str(error) == "Authentication Error [TEST_ERROR]: Test error message"
    
    def test_str_default_code(self):
        """Test AuthenticationError string with default code."""
        error = AuthenticationError("Test error message")
        
        assert str(error) == "Authentication Error [UNKNOWN]: Test error message"