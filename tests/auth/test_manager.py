"""
Tests for device manager functionality.

These tests validate device discovery, token management, and real-time updates
using mocked tuya-device-sharing-sdk components.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import uuid

from libtuya.auth.manager import DeviceManager, TokenListener, DeviceListener
from libtuya.auth.models import AuthSession, DeviceInfo, DeviceDiscoveryResult, AuthenticationError


class TestTokenListener:
    """Test token listener functionality."""
    
    def test_init(self):
        """Test TokenListener initialization."""
        listener = TokenListener()
        assert listener.callback is None
        assert listener.last_update is None
    
    def test_init_with_callback(self):
        """Test TokenListener with callback."""
        callback = Mock()
        listener = TokenListener(callback)
        assert listener.callback == callback
    
    def test_update_token_no_callback(self):
        """Test token update without callback."""
        listener = TokenListener()
        
        token_info = {
            "access_token": "new-token",
            "refresh_token": "new-refresh",
            "expire_time": 1234567890
        }
        
        listener.update_token(token_info)
        
        assert listener.last_update is not None
        assert isinstance(listener.last_update, datetime)
    
    def test_update_token_with_callback(self):
        """Test token update with callback."""
        callback = Mock()
        listener = TokenListener(callback)
        
        token_info = {
            "access_token": "new-token",
            "refresh_token": "new-refresh",
            "expire_time": 1234567890
        }
        
        listener.update_token(token_info)
        
        callback.assert_called_once_with(token_info)
        assert listener.last_update is not None
    
    def test_update_token_callback_exception(self):
        """Test token update with callback exception."""
        callback = Mock(side_effect=Exception("Callback error"))
        listener = TokenListener(callback)
        
        token_info = {"access_token": "new-token"}
        
        # Should not raise exception
        listener.update_token(token_info)
        
        callback.assert_called_once_with(token_info)
        assert listener.last_update is not None


class TestDeviceListener:
    """Test device listener functionality."""
    
    def test_init(self):
        """Test DeviceListener initialization."""
        listener = DeviceListener()
        assert listener.device_callback is None
        assert listener.add_callback is None
        assert listener.remove_callback is None
    
    def test_init_with_callbacks(self):
        """Test DeviceListener with callbacks."""
        device_cb = Mock()
        add_cb = Mock()
        remove_cb = Mock()
        
        listener = DeviceListener(device_cb, add_cb, remove_cb)
        
        assert listener.device_callback == device_cb
        assert listener.add_callback == add_cb
        assert listener.remove_callback == remove_cb
    
    def test_update_device(self):
        """Test device update handling."""
        device_cb = Mock()
        listener = DeviceListener(device_callback=device_cb)
        
        # Mock CustomerDevice
        mock_device = Mock()
        mock_device.id = "test-device-1"
        mock_device.name = "Test Device"
        mock_device.local_key = "test-local-key"
        mock_device.category = "dj"
        mock_device.online = True
        mock_device.ip = "192.168.1.100"
        
        listener.update_device(mock_device)
        
        device_cb.assert_called_once()
        called_device = device_cb.call_args[0][0]
        assert isinstance(called_device, DeviceInfo)
        assert called_device.id == "test-device-1"
    
    def test_add_device(self):
        """Test device addition handling."""
        add_cb = Mock()
        listener = DeviceListener(add_callback=add_cb)
        
        # Mock CustomerDevice
        mock_device = Mock()
        mock_device.id = "test-device-1"
        mock_device.name = "Test Device"
        mock_device.local_key = "test-local-key"
        mock_device.category = "dj"
        mock_device.online = True
        mock_device.ip = "192.168.1.100"
        
        listener.add_device(mock_device)
        
        add_cb.assert_called_once()
        called_device = add_cb.call_args[0][0]
        assert isinstance(called_device, DeviceInfo)
        assert called_device.id == "test-device-1"
    
    def test_remove_device(self):
        """Test device removal handling."""
        remove_cb = Mock()
        listener = DeviceListener(remove_callback=remove_cb)
        
        listener.remove_device("test-device-1")
        
        remove_cb.assert_called_once_with("test-device-1")
    
    def test_callback_exception(self):
        """Test callback exception handling."""
        device_cb = Mock(side_effect=Exception("Callback error"))
        listener = DeviceListener(device_callback=device_cb)
        
        mock_device = Mock()
        mock_device.id = "test-device-1"
        mock_device.name = "Test Device"
        mock_device.local_key = "test-local-key"
        mock_device.category = "dj"
        mock_device.online = True
        mock_device.ip = "192.168.1.100"
        
        # Should not raise exception
        listener.update_device(mock_device)
        
        device_cb.assert_called_once()


class TestDeviceManager:
    """Test device manager functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.session = AuthSession(
            access_token="test-access-token",
            refresh_token="test-refresh-token",
            uid="test-uid",
            expire_time=int((datetime.now() + timedelta(hours=1)).timestamp() * 1000),
            t=int(datetime.now().timestamp() * 1000),
            client_id="HA_3y9q4ak7g4ephrvke",
            user_code="test-user-code"
        )
        
        self.mock_manager = Mock()
        self.mock_manager.device_map = {}
        self.mock_manager.customer_api = Mock()
        
    @patch('libtuya.auth.manager.Manager')
    def test_init_success(self, mock_manager_class):
        """Test successful DeviceManager initialization."""
        mock_manager_class.return_value = self.mock_manager
        
        device_manager = DeviceManager(self.session)
        
        assert device_manager.session == self.session
        assert device_manager.endpoint == "https://apigw.iotbing.com"
        assert device_manager.manager == self.mock_manager
        assert len(device_manager.terminal_id) > 0
        
        # Verify Manager was initialized correctly
        mock_manager_class.assert_called_once()
        call_args = mock_manager_class.call_args
        assert call_args[1]['client_id'] == "HA_3y9q4ak7g4ephrvke"
        assert call_args[1]['user_code'] == "test-user-code"
        assert call_args[1]['end_point'] == "https://apigw.iotbing.com"
        assert 'token_response' in call_args[1]
    
    @patch('libtuya.auth.manager.Manager')
    def test_init_custom_params(self, mock_manager_class):
        """Test DeviceManager with custom parameters."""
        mock_manager_class.return_value = self.mock_manager
        
        custom_endpoint = "https://custom-api.example.com"
        custom_terminal_id = "custom-terminal-123"
        callback = Mock()
        
        device_manager = DeviceManager(
            self.session,
            endpoint=custom_endpoint,
            terminal_id=custom_terminal_id,
            token_callback=callback
        )
        
        assert device_manager.endpoint == custom_endpoint
        assert device_manager.terminal_id == custom_terminal_id
        assert device_manager.token_listener.callback == callback
    
    @patch('libtuya.auth.manager.Manager', side_effect=ImportError("Module not found"))
    def test_init_missing_dependency(self, mock_manager_class):
        """Test DeviceManager initialization with missing dependency."""
        with pytest.raises(AuthenticationError) as exc_info:
            DeviceManager(self.session)
        
        assert exc_info.value.error_code == "MISSING_DEPENDENCY"
    
    @patch('libtuya.auth.manager.Manager')
    def test_init_manager_error(self, mock_manager_class):
        """Test DeviceManager initialization with manager error."""
        mock_manager_class.side_effect = Exception("Manager initialization failed")
        
        with pytest.raises(AuthenticationError) as exc_info:
            DeviceManager(self.session)
        
        assert exc_info.value.error_code == "MANAGER_INIT_ERROR"
    
    @patch('libtuya.auth.manager.Manager')
    def test_discover_devices_success(self, mock_manager_class):
        """Test successful device discovery."""
        mock_manager_class.return_value = self.mock_manager
        
        # Mock device data
        mock_device1 = Mock()
        mock_device1.id = "device-1"
        mock_device1.name = "Light 1"
        mock_device1.local_key = "local-key-1"
        mock_device1.category = "dj"
        mock_device1.online = True
        mock_device1.ip = "192.168.1.100"
        mock_device1.uuid = "uuid-1"
        mock_device1.asset_id = "asset-1"
        mock_device1.product_id = "product-1"
        mock_device1.product_name = "Smart Light"
        mock_device1.sub = False
        
        mock_device2 = Mock()
        mock_device2.id = "device-2"
        mock_device2.name = "Switch 1"
        mock_device2.local_key = "local-key-2"
        mock_device2.category = "kg"
        mock_device2.online = False
        mock_device2.ip = "192.168.1.101"
        mock_device2.uuid = "uuid-2"
        mock_device2.asset_id = "asset-2"
        mock_device2.product_id = "product-2"
        mock_device2.product_name = "Smart Switch"
        mock_device2.sub = False
        
        self.mock_manager.device_map = {
            "device-1": mock_device1,
            "device-2": mock_device2
        }
        
        device_manager = DeviceManager(self.session)
        result = device_manager.discover_devices()
        
        assert isinstance(result, DeviceDiscoveryResult)
        assert len(result.devices) == 2
        assert result.total_count == 2
        assert result.success is True
        assert len(result.errors) == 0
        
        # Verify devices were converted correctly
        device_names = [device.name for device in result.devices]
        assert "Light 1" in device_names
        assert "Switch 1" in device_names
        
        # Verify devices with local keys
        assert len(result.devices_with_local_keys) == 2
        
        # Verify online devices
        assert len(result.online_devices) == 1
        assert result.online_devices[0].name == "Light 1"
        
        # Verify manager method was called
        self.mock_manager.update_device_cache.assert_called_once()
    
    @patch('libtuya.auth.manager.Manager')
    def test_discover_devices_cached(self, mock_manager_class):
        """Test device discovery with cached results."""
        mock_manager_class.return_value = self.mock_manager
        
        device_manager = DeviceManager(self.session)
        
        # Mock first discovery
        mock_device = Mock()
        mock_device.id = "device-1"
        mock_device.name = "Light 1"
        mock_device.local_key = "local-key-1"
        mock_device.category = "dj"
        mock_device.online = True
        mock_device.ip = "192.168.1.100"
        mock_device.uuid = "uuid-1"
        mock_device.asset_id = "asset-1"
        mock_device.product_id = "product-1"
        mock_device.product_name = "Smart Light"
        mock_device.sub = False
        
        self.mock_manager.device_map = {"device-1": mock_device}
        
        # First discovery
        result1 = device_manager.discover_devices()
        assert self.mock_manager.update_device_cache.call_count == 1
        
        # Second discovery (should use cache)
        result2 = device_manager.discover_devices()
        assert self.mock_manager.update_device_cache.call_count == 1  # Not called again
        
        # Force refresh
        result3 = device_manager.discover_devices(force_refresh=True)
        assert self.mock_manager.update_device_cache.call_count == 2  # Called again
    
    @patch('libtuya.auth.manager.Manager')
    def test_discover_devices_device_error(self, mock_manager_class):
        """Test device discovery with device processing error."""
        mock_manager_class.return_value = self.mock_manager
        
        # Mock device that will cause error
        mock_device = Mock()
        mock_device.id = "device-1"
        # Missing required attributes to cause error
        
        self.mock_manager.device_map = {"device-1": mock_device}
        
        device_manager = DeviceManager(self.session)
        result = device_manager.discover_devices()
        
        assert len(result.devices) == 0
        assert len(result.errors) == 1
        assert "Error processing device device-1" in result.errors[0]
    
    @patch('libtuya.auth.manager.Manager')
    def test_discover_devices_manager_error(self, mock_manager_class):
        """Test device discovery with manager error."""
        mock_manager_class.return_value = self.mock_manager
        self.mock_manager.update_device_cache.side_effect = Exception("Network error")
        
        device_manager = DeviceManager(self.session)
        
        with pytest.raises(AuthenticationError) as exc_info:
            device_manager.discover_devices()
        
        assert exc_info.value.error_code == "DISCOVERY_ERROR"
    
    @patch('libtuya.auth.manager.Manager')
    def test_get_device(self, mock_manager_class):
        """Test getting specific device."""
        mock_manager_class.return_value = self.mock_manager
        
        device_manager = DeviceManager(self.session)
        
        # Mock device in cache
        mock_device = Mock()
        mock_device.id = "device-1"
        mock_device.name = "Light 1"
        mock_device.local_key = "local-key-1"
        mock_device.category = "dj"
        mock_device.online = True
        mock_device.ip = "192.168.1.100"
        mock_device.uuid = "uuid-1"
        mock_device.asset_id = "asset-1"
        mock_device.product_id = "product-1"
        mock_device.product_name = "Smart Light"
        mock_device.sub = False
        
        device_info = DeviceInfo.from_customer_device(mock_device)
        device_manager._devices["device-1"] = device_info
        
        # Test getting existing device
        result = device_manager.get_device("device-1")
        assert result is not None
        assert result.id == "device-1"
        assert result.name == "Light 1"
        
        # Test getting non-existent device
        result = device_manager.get_device("device-999")
        assert result is None
    
    @patch('libtuya.auth.manager.Manager')
    def test_get_devices_with_local_keys(self, mock_manager_class):
        """Test getting devices with local keys."""
        mock_manager_class.return_value = self.mock_manager
        
        device_manager = DeviceManager(self.session)
        
        # Mock devices - one with local key, one without
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
        
        device_manager._devices = {
            "device-1": device1,
            "device-2": device2
        }
        
        result = device_manager.get_devices_with_local_keys()
        
        assert len(result) == 1
        assert result[0].id == "device-1"
        assert result[0].has_local_key is True
    
    @patch('libtuya.auth.manager.Manager')
    def test_get_online_devices(self, mock_manager_class):
        """Test getting online devices."""
        mock_manager_class.return_value = self.mock_manager
        
        device_manager = DeviceManager(self.session)
        
        # Mock devices - one online, one offline
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
        
        device_manager._devices = {
            "device-1": device1,
            "device-2": device2
        }
        
        result = device_manager.get_online_devices()
        
        assert len(result) == 1
        assert result[0].id == "device-1"
        assert result[0].online is True
    
    @patch('libtuya.auth.manager.Manager')
    def test_get_controllable_devices(self, mock_manager_class):
        """Test getting controllable devices."""
        mock_manager_class.return_value = self.mock_manager
        
        device_manager = DeviceManager(self.session)
        
        # Mock devices with different controllability
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
        
        device3 = DeviceInfo(
            id="device-3", name="Light 2", local_key="local-key-3",
            category="dj", product_id="p3", product_name="Light", 
            online=False, ip="", uuid="uuid-3", asset_id="a3"  # Offline, no IP
        )
        
        device_manager._devices = {
            "device-1": device1,
            "device-2": device2,
            "device-3": device3
        }
        
        result = device_manager.get_controllable_devices()
        
        assert len(result) == 1
        assert result[0].id == "device-1"
        assert result[0].can_control_locally is True
    
    @patch('libtuya.auth.manager.Manager')
    def test_get_devices_by_category(self, mock_manager_class):
        """Test getting devices by category."""
        mock_manager_class.return_value = self.mock_manager
        
        device_manager = DeviceManager(self.session)
        
        # Mock devices with different categories
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
        
        device_manager._devices = {
            "device-1": device1,
            "device-2": device2,
            "device-3": device3
        }
        
        # Test getting lights
        lights = device_manager.get_devices_by_category("dj")
        assert len(lights) == 2
        assert all(device.category == "dj" for device in lights)
        
        # Test getting switches
        switches = device_manager.get_devices_by_category("kg")
        assert len(switches) == 1
        assert switches[0].id == "device-2"
        
        # Test getting non-existent category
        result = device_manager.get_devices_by_category("nonexistent")
        assert len(result) == 0
    
    @patch('libtuya.auth.manager.Manager')
    def test_send_command_success(self, mock_manager_class):
        """Test successful command sending."""
        mock_manager_class.return_value = self.mock_manager
        self.mock_manager.send_commands.return_value = True
        
        device_manager = DeviceManager(self.session)
        
        commands = [
            {"code": "switch_1", "value": True},
            {"code": "bright_value", "value": 800}
        ]
        
        result = device_manager.send_command("device-1", commands)
        
        assert result is True
        self.mock_manager.send_commands.assert_called_once_with("device-1", commands)
    
    @patch('libtuya.auth.manager.Manager')
    def test_send_command_failure(self, mock_manager_class):
        """Test command sending failure."""
        mock_manager_class.return_value = self.mock_manager
        self.mock_manager.send_commands.side_effect = Exception("Command failed")
        
        device_manager = DeviceManager(self.session)
        
        commands = [{"code": "switch_1", "value": True}]
        result = device_manager.send_command("device-1", commands)
        
        assert result is False
    
    @patch('libtuya.auth.manager.Manager')
    def test_start_real_time_updates(self, mock_manager_class):
        """Test starting real-time updates."""
        mock_manager_class.return_value = self.mock_manager
        
        device_manager = DeviceManager(self.session)
        
        device_cb = Mock()
        add_cb = Mock()
        remove_cb = Mock()
        
        device_manager.start_real_time_updates(device_cb, add_cb, remove_cb)
        
        assert device_manager.device_listener is not None
        assert device_manager.device_listener.device_callback == device_cb
        assert device_manager.device_listener.add_callback == add_cb
        assert device_manager.device_listener.remove_callback == remove_cb
        
        self.mock_manager.add_device_listener.assert_called_once()
        self.mock_manager.refresh_mq.assert_called_once()
    
    @patch('libtuya.auth.manager.Manager')
    def test_stop_real_time_updates(self, mock_manager_class):
        """Test stopping real-time updates."""
        mock_manager_class.return_value = self.mock_manager
        
        device_manager = DeviceManager(self.session)
        
        # Start updates first
        device_manager.start_real_time_updates()
        assert device_manager.device_listener is not None
        
        # Stop updates
        device_manager.stop_real_time_updates()
        assert device_manager.device_listener is None
        
        self.mock_manager.remove_device_listener.assert_called_once()
    
    @patch('libtuya.auth.manager.Manager')
    def test_refresh_token_if_needed(self, mock_manager_class):
        """Test token refresh when needed."""
        mock_manager_class.return_value = self.mock_manager
        
        # Create expired session
        expired_session = AuthSession(
            access_token="expired-token",
            refresh_token="refresh-token",
            uid="test-uid",
            expire_time=int((datetime.now() - timedelta(hours=1)).timestamp() * 1000),  # Expired
            t=int(datetime.now().timestamp() * 1000)
        )
        
        device_manager = DeviceManager(expired_session)
        
        result = device_manager.refresh_token_if_needed()
        
        assert result is True
        self.mock_manager.customer_api.refresh_access_token_if_need.assert_called_once()
    
    @patch('libtuya.auth.manager.Manager')
    def test_refresh_token_not_needed(self, mock_manager_class):
        """Test token refresh when not needed."""
        mock_manager_class.return_value = self.mock_manager
        
        device_manager = DeviceManager(self.session)  # Valid session
        
        result = device_manager.refresh_token_if_needed()
        
        assert result is True
        self.mock_manager.customer_api.refresh_access_token_if_need.assert_not_called()
    
    @patch('libtuya.auth.manager.Manager')
    def test_get_session_info(self, mock_manager_class):
        """Test getting session information."""
        mock_manager_class.return_value = self.mock_manager
        
        device_manager = DeviceManager(self.session)
        
        # Add some mock devices
        device1 = DeviceInfo(
            id="device-1", name="Light 1", local_key="local-key-1",
            category="dj", product_id="p1", product_name="Light", 
            online=True, ip="192.168.1.100", uuid="uuid-1", asset_id="a1"
        )
        device_manager._devices = {"device-1": device1}
        
        info = device_manager.get_session_info()
        
        assert info["uid"] == "test-uid"
        assert info["client_id"] == "HA_3y9q4ak7g4ephrvke"
        assert info["terminal_id"] == device_manager.terminal_id
        assert info["device_count"] == 1
        assert info["devices_with_keys"] == 1
        assert info["online_devices"] == 1
    
    @patch('libtuya.auth.manager.Manager')
    def test_close(self, mock_manager_class):
        """Test closing device manager."""
        mock_manager_class.return_value = self.mock_manager
        
        device_manager = DeviceManager(self.session)
        
        # Add some mock data
        device1 = DeviceInfo(
            id="device-1", name="Light 1", local_key="local-key-1",
            category="dj", product_id="p1", product_name="Light", 
            online=True, ip="192.168.1.100", uuid="uuid-1", asset_id="a1"
        )
        device_manager._devices = {"device-1": device1}
        
        # Start real-time updates
        device_manager.start_real_time_updates()
        
        # Close
        device_manager.close()
        
        assert len(device_manager._devices) == 0
        assert device_manager.device_listener is None