"""
Tests for main TuyaAuthenticator interface.

These tests validate the complete authentication flow and device management
through the main TuyaAuthenticator class.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from libtuya.auth import TuyaAuthenticator
from libtuya.auth.models import AuthSession, DeviceInfo, QRCodeData, DeviceDiscoveryResult, AuthenticationError


class TestTuyaAuthenticator:
    """Test main TuyaAuthenticator interface."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.authenticator = TuyaAuthenticator()
        
        # Mock session
        self.mock_session = AuthSession(
            access_token="test-access-token",
            refresh_token="test-refresh-token",
            uid="test-uid",
            expire_time=int((datetime.now() + timedelta(hours=1)).timestamp() * 1000),
            t=int(datetime.now().timestamp() * 1000),
            client_id="HA_3y9q4ak7g4ephrvke",
            user_code="test-user-code"
        )
        
        # Mock device info
        self.mock_device = DeviceInfo(
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
    
    def test_init(self):
        """Test TuyaAuthenticator initialization."""
        auth = TuyaAuthenticator()
        
        assert auth.endpoint == "https://apigw.iotbing.com"
        assert auth.token_callback is None
        assert auth.qr_authenticator is not None
        assert auth.device_manager is None
        assert auth._current_session is None
        assert auth._last_qr_data is None
    
    def test_init_custom_params(self):
        """Test TuyaAuthenticator with custom parameters."""
        custom_endpoint = "https://custom-api.example.com"
        callback = Mock()
        
        auth = TuyaAuthenticator(endpoint=custom_endpoint, token_callback=callback)
        
        assert auth.endpoint == custom_endpoint
        assert auth.token_callback == callback
    
    def test_start_qr_auth(self):
        """Test starting QR authentication."""
        # Mock QR authenticator
        mock_qr_data = QRCodeData(
            qr_code="https://example.com/qr/12345",
            token="test-token"
        )
        
        self.authenticator.qr_authenticator = Mock()
        self.authenticator.qr_authenticator.generate_qr_code.return_value = mock_qr_data
        self.authenticator.qr_authenticator.format_qr_for_display.return_value = "Formatted QR"
        
        result = self.authenticator.start_qr_auth("test-user-code")
        
        assert result == "Formatted QR"
        assert self.authenticator._last_qr_data == mock_qr_data
        
        self.authenticator.qr_authenticator.generate_qr_code.assert_called_once_with("test-user-code")
        self.authenticator.qr_authenticator.format_qr_for_display.assert_called_once_with(mock_qr_data)
    
    def test_start_qr_auth_no_user_code(self):
        """Test starting QR authentication without user code."""
        mock_qr_data = QRCodeData(
            qr_code="https://example.com/qr/12345",
            token="test-token"
        )
        
        self.authenticator.qr_authenticator = Mock()
        self.authenticator.qr_authenticator.generate_qr_code.return_value = mock_qr_data
        self.authenticator.qr_authenticator.format_qr_for_display.return_value = "Formatted QR"
        
        result = self.authenticator.start_qr_auth()
        
        assert result == "Formatted QR"
        
        # Should call with None (will generate UUID internally)
        self.authenticator.qr_authenticator.generate_qr_code.assert_called_once_with(None)
    
    def test_wait_for_auth_success(self):
        """Test waiting for authentication success."""
        # Set up QR data
        mock_qr_data = QRCodeData(
            qr_code="https://example.com/qr/12345",
            token="test-token"
        )
        self.authenticator._last_qr_data = mock_qr_data
        
        # Mock QR authenticator
        self.authenticator.qr_authenticator = Mock()
        self.authenticator.qr_authenticator.wait_for_authentication.return_value = self.mock_session
        
        # Mock device manager initialization
        with patch('libtuya.auth.DeviceManager') as mock_device_manager_class:
            mock_device_manager = Mock()
            mock_device_manager_class.return_value = mock_device_manager
            
            result = self.authenticator.wait_for_auth(timeout=60)
            
            assert result == self.mock_session
            assert self.authenticator._current_session == self.mock_session
            assert self.authenticator.device_manager == mock_device_manager
            
            # Verify device manager was initialized
            mock_device_manager_class.assert_called_once()
    
    def test_wait_for_auth_no_qr_data(self):
        """Test waiting for authentication without QR data."""
        # No QR data set
        self.authenticator._last_qr_data = None
        
        with pytest.raises(AuthenticationError) as exc_info:
            self.authenticator.wait_for_auth()
        
        assert exc_info.value.error_code == "NO_QR_CODE"
    
    def test_authenticate_with_qr_success(self):
        """Test complete QR authentication flow."""
        # Mock QR authenticator
        mock_qr_data = QRCodeData(
            qr_code="https://example.com/qr/12345",
            token="test-token"
        )
        
        self.authenticator.qr_authenticator = Mock()
        self.authenticator.qr_authenticator.authenticate_with_qr.return_value = (mock_qr_data, self.mock_session)
        
        # Mock device manager initialization
        with patch('libtuya.auth.DeviceManager') as mock_device_manager_class:
            mock_device_manager = Mock()
            mock_device_manager_class.return_value = mock_device_manager
            
            result = self.authenticator.authenticate_with_qr("test-user-code", timeout=60)
            
            assert result == self.mock_session
            assert self.authenticator._current_session == self.mock_session
            assert self.authenticator._last_qr_data == mock_qr_data
            assert self.authenticator.device_manager == mock_device_manager
            
            # Verify QR authenticator was called
            self.authenticator.qr_authenticator.authenticate_with_qr.assert_called_once_with(
                "test-user-code", 60, 2
            )
    
    def test_authenticate_with_qr_no_user_code(self):
        """Test complete QR authentication without user code."""
        mock_qr_data = QRCodeData(
            qr_code="https://example.com/qr/12345",
            token="test-token"
        )
        
        self.authenticator.qr_authenticator = Mock()
        self.authenticator.qr_authenticator.authenticate_with_qr.return_value = (mock_qr_data, self.mock_session)
        
        with patch('libtuya.auth.DeviceManager') as mock_device_manager_class:
            mock_device_manager = Mock()
            mock_device_manager_class.return_value = mock_device_manager
            
            result = self.authenticator.authenticate_with_qr()
            
            assert result == self.mock_session
            
            # Should call with generated UUID
            call_args = self.authenticator.qr_authenticator.authenticate_with_qr.call_args
            assert len(call_args[0][0]) > 0  # Generated user code
    
    def test_get_devices_with_keys_success(self):
        """Test getting devices with local keys."""
        # Set up authenticated state
        self.authenticator._current_session = self.mock_session
        
        # Mock device manager
        mock_device_manager = Mock()
        mock_discovery_result = DeviceDiscoveryResult(
            devices=[self.mock_device],
            total_count=1
        )
        mock_device_manager.discover_devices.return_value = mock_discovery_result
        self.authenticator.device_manager = mock_device_manager
        
        result = self.authenticator.get_devices_with_keys()
        
        assert len(result) == 1
        assert result[0] == self.mock_device
        
        mock_device_manager.discover_devices.assert_called_once_with(False)
    
    def test_get_devices_with_keys_force_refresh(self):
        """Test getting devices with forced refresh."""
        # Set up authenticated state
        self.authenticator._current_session = self.mock_session
        
        # Mock device manager
        mock_device_manager = Mock()
        mock_discovery_result = DeviceDiscoveryResult(
            devices=[self.mock_device],
            total_count=1
        )
        mock_device_manager.discover_devices.return_value = mock_discovery_result
        self.authenticator.device_manager = mock_device_manager
        
        result = self.authenticator.get_devices_with_keys(force_refresh=True)
        
        assert len(result) == 1
        mock_device_manager.discover_devices.assert_called_once_with(True)
    
    def test_get_devices_with_keys_not_authenticated(self):
        """Test getting devices when not authenticated."""
        # Not authenticated
        self.authenticator.device_manager = None
        
        with pytest.raises(AuthenticationError) as exc_info:
            self.authenticator.get_devices_with_keys()
        
        assert exc_info.value.error_code == "NOT_AUTHENTICATED"
    
    def test_get_all_devices_success(self):
        """Test getting all devices."""
        # Set up authenticated state
        self.authenticator._current_session = self.mock_session
        
        # Mock device manager
        mock_device_manager = Mock()
        mock_discovery_result = DeviceDiscoveryResult(
            devices=[self.mock_device],
            total_count=1
        )
        mock_device_manager.discover_devices.return_value = mock_discovery_result
        self.authenticator.device_manager = mock_device_manager
        
        result = self.authenticator.get_all_devices()
        
        assert isinstance(result, DeviceDiscoveryResult)
        assert len(result.devices) == 1
        assert result.devices[0] == self.mock_device
        
        mock_device_manager.discover_devices.assert_called_once_with(False)
    
    def test_get_all_devices_not_authenticated(self):
        """Test getting all devices when not authenticated."""
        # Not authenticated
        self.authenticator.device_manager = None
        
        with pytest.raises(AuthenticationError) as exc_info:
            self.authenticator.get_all_devices()
        
        assert exc_info.value.error_code == "NOT_AUTHENTICATED"
    
    def test_get_device_success(self):
        """Test getting specific device."""
        # Set up authenticated state
        self.authenticator._current_session = self.mock_session
        
        # Mock device manager
        mock_device_manager = Mock()
        mock_device_manager.get_device.return_value = self.mock_device
        self.authenticator.device_manager = mock_device_manager
        
        result = self.authenticator.get_device("device-1")
        
        assert result == self.mock_device
        mock_device_manager.get_device.assert_called_once_with("device-1")
    
    def test_get_device_not_authenticated(self):
        """Test getting device when not authenticated."""
        # Not authenticated
        self.authenticator.device_manager = None
        
        result = self.authenticator.get_device("device-1")
        
        assert result is None
    
    def test_get_online_devices(self):
        """Test getting online devices."""
        # Set up authenticated state
        self.authenticator._current_session = self.mock_session
        
        # Mock device manager
        mock_device_manager = Mock()
        mock_device_manager.get_online_devices.return_value = [self.mock_device]
        self.authenticator.device_manager = mock_device_manager
        
        result = self.authenticator.get_online_devices()
        
        assert len(result) == 1
        assert result[0] == self.mock_device
        mock_device_manager.get_online_devices.assert_called_once()
    
    def test_get_online_devices_not_authenticated(self):
        """Test getting online devices when not authenticated."""
        # Not authenticated
        self.authenticator.device_manager = None
        
        result = self.authenticator.get_online_devices()
        
        assert result == []
    
    def test_get_controllable_devices(self):
        """Test getting controllable devices."""
        # Set up authenticated state
        self.authenticator._current_session = self.mock_session
        
        # Mock device manager
        mock_device_manager = Mock()
        mock_device_manager.get_controllable_devices.return_value = [self.mock_device]
        self.authenticator.device_manager = mock_device_manager
        
        result = self.authenticator.get_controllable_devices()
        
        assert len(result) == 1
        assert result[0] == self.mock_device
        mock_device_manager.get_controllable_devices.assert_called_once()
    
    def test_get_devices_by_category(self):
        """Test getting devices by category."""
        # Set up authenticated state
        self.authenticator._current_session = self.mock_session
        
        # Mock device manager
        mock_device_manager = Mock()
        mock_device_manager.get_devices_by_category.return_value = [self.mock_device]
        self.authenticator.device_manager = mock_device_manager
        
        result = self.authenticator.get_devices_by_category("dj")
        
        assert len(result) == 1
        assert result[0] == self.mock_device
        mock_device_manager.get_devices_by_category.assert_called_once_with("dj")
    
    def test_send_command_success(self):
        """Test sending command to device."""
        # Set up authenticated state
        self.authenticator._current_session = self.mock_session
        
        # Mock device manager
        mock_device_manager = Mock()
        mock_device_manager.send_command.return_value = True
        self.authenticator.device_manager = mock_device_manager
        
        commands = [{"code": "switch_1", "value": True}]
        result = self.authenticator.send_command("device-1", commands)
        
        assert result is True
        mock_device_manager.send_command.assert_called_once_with("device-1", commands)
    
    def test_send_command_not_authenticated(self):
        """Test sending command when not authenticated."""
        # Not authenticated
        self.authenticator.device_manager = None
        
        commands = [{"code": "switch_1", "value": True}]
        result = self.authenticator.send_command("device-1", commands)
        
        assert result is False
    
    def test_start_real_time_updates(self):
        """Test starting real-time updates."""
        # Set up authenticated state
        self.authenticator._current_session = self.mock_session
        
        # Mock device manager
        mock_device_manager = Mock()
        self.authenticator.device_manager = mock_device_manager
        
        device_cb = Mock()
        add_cb = Mock()
        remove_cb = Mock()
        
        self.authenticator.start_real_time_updates(device_cb, add_cb, remove_cb)
        
        mock_device_manager.start_real_time_updates.assert_called_once_with(
            device_cb, add_cb, remove_cb
        )
    
    def test_start_real_time_updates_not_authenticated(self):
        """Test starting real-time updates when not authenticated."""
        # Not authenticated
        self.authenticator.device_manager = None
        
        # Should not raise error
        self.authenticator.start_real_time_updates(Mock(), Mock(), Mock())
    
    def test_stop_real_time_updates(self):
        """Test stopping real-time updates."""
        # Set up authenticated state
        self.authenticator._current_session = self.mock_session
        
        # Mock device manager
        mock_device_manager = Mock()
        self.authenticator.device_manager = mock_device_manager
        
        self.authenticator.stop_real_time_updates()
        
        mock_device_manager.stop_real_time_updates.assert_called_once()
    
    def test_get_session(self):
        """Test getting current session."""
        # Initially no session
        assert self.authenticator.get_session() is None
        
        # Set session
        self.authenticator._current_session = self.mock_session
        assert self.authenticator.get_session() == self.mock_session
    
    def test_get_session_info_authenticated(self):
        """Test getting session info when authenticated."""
        # Set up authenticated state
        self.authenticator._current_session = self.mock_session
        
        # Mock device manager
        mock_device_manager = Mock()
        mock_device_manager.get_session_info.return_value = {
            "uid": "test-uid",
            "device_count": 5,
            "online_devices": 3
        }
        self.authenticator.device_manager = mock_device_manager
        
        info = self.authenticator.get_session_info()
        
        assert info["authenticated"] is True
        assert info["uid"] == "test-uid"
        assert info["device_count"] == 5
        assert info["online_devices"] == 3
    
    def test_get_session_info_not_authenticated(self):
        """Test getting session info when not authenticated."""
        # Not authenticated
        self.authenticator._current_session = None
        
        info = self.authenticator.get_session_info()
        
        assert info == {"authenticated": False}
    
    def test_get_session_info_no_device_manager(self):
        """Test getting session info without device manager."""
        # Set session but no device manager
        self.authenticator._current_session = self.mock_session
        self.authenticator.device_manager = None
        
        info = self.authenticator.get_session_info()
        
        assert info["authenticated"] is True
        assert info["uid"] == "test-uid"
        assert info["client_id"] == "HA_3y9q4ak7g4ephrvke"
        assert "device_count" not in info
    
    def test_is_authenticated_true(self):
        """Test authentication check when authenticated."""
        # Set valid session
        self.authenticator._current_session = self.mock_session
        
        assert self.authenticator.is_authenticated() is True
    
    def test_is_authenticated_false_no_session(self):
        """Test authentication check without session."""
        # No session
        self.authenticator._current_session = None
        
        assert self.authenticator.is_authenticated() is False
    
    def test_is_authenticated_false_expired_session(self):
        """Test authentication check with expired session."""
        # Create expired session
        expired_session = AuthSession(
            access_token="expired-token",
            refresh_token="refresh-token",
            uid="test-uid",
            expire_time=int((datetime.now() - timedelta(hours=1)).timestamp() * 1000),  # Expired
            t=int(datetime.now().timestamp() * 1000)
        )
        self.authenticator._current_session = expired_session
        
        assert self.authenticator.is_authenticated() is False
    
    def test_restore_session_success(self):
        """Test successful session restoration."""
        # Mock device manager initialization
        with patch('libtuya.auth.DeviceManager') as mock_device_manager_class:
            mock_device_manager = Mock()
            mock_discovery_result = DeviceDiscoveryResult(
                devices=[self.mock_device],
                total_count=1
            )
            mock_device_manager.discover_devices.return_value = mock_discovery_result
            mock_device_manager_class.return_value = mock_device_manager
            
            result = self.authenticator.restore_session(self.mock_session)
            
            assert result is True
            assert self.authenticator._current_session == self.mock_session
            assert self.authenticator.device_manager == mock_device_manager
            
            # Verify device manager was tested
            mock_device_manager.discover_devices.assert_called_once()
    
    def test_restore_session_expired(self):
        """Test session restoration with expired session."""
        # Create expired session
        expired_session = AuthSession(
            access_token="expired-token",
            refresh_token="refresh-token",
            uid="test-uid",
            expire_time=int((datetime.now() - timedelta(hours=1)).timestamp() * 1000),  # Expired
            t=int(datetime.now().timestamp() * 1000)
        )
        
        result = self.authenticator.restore_session(expired_session)
        
        assert result is False
        assert self.authenticator._current_session is None
        assert self.authenticator.device_manager is None
    
    def test_restore_session_failure(self):
        """Test session restoration failure."""
        # Mock device manager initialization that fails
        with patch('libtuya.auth.DeviceManager') as mock_device_manager_class:
            mock_device_manager = Mock()
            mock_device_manager.discover_devices.side_effect = Exception("Discovery failed")
            mock_device_manager_class.return_value = mock_device_manager
            
            result = self.authenticator.restore_session(self.mock_session)
            
            assert result is False
            assert self.authenticator._current_session is None
            assert self.authenticator.device_manager is None
    
    def test_close(self):
        """Test closing authenticator."""
        # Set up authenticated state
        self.authenticator._current_session = self.mock_session
        
        # Mock device manager
        mock_device_manager = Mock()
        self.authenticator.device_manager = mock_device_manager
        
        self.authenticator.close()
        
        mock_device_manager.close.assert_called_once()
        assert self.authenticator._current_session is None
        assert self.authenticator.device_manager is None
    
    def test_close_no_device_manager(self):
        """Test closing authenticator without device manager."""
        # Set up state without device manager
        self.authenticator._current_session = self.mock_session
        self.authenticator.device_manager = None
        
        # Should not raise error
        self.authenticator.close()
        
        assert self.authenticator._current_session is None