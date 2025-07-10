"""
Tests for QR code authentication functionality.

These tests validate the QR code authentication flow including
QR code generation, authentication polling, and error handling.
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from libtuya.auth.qr_auth import QRAuthenticator
from libtuya.auth.models import QRCodeData, AuthSession, AuthenticationError


class TestQRAuthenticator:
    """Test QR code authentication functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.authenticator = QRAuthenticator()
        self.mock_login_control = Mock()
        self.authenticator.login_control = self.mock_login_control
    
    def test_init(self):
        """Test QRAuthenticator initialization."""
        auth = QRAuthenticator()
        assert auth.endpoint == "https://apigw.iotbing.com"
        assert auth.CLIENT_ID == "HA_3y9q4ak7g4ephrvke"
        assert auth.SCHEMA == "haauthorize"
        assert auth.login_control is None
    
    def test_init_custom_endpoint(self):
        """Test QRAuthenticator with custom endpoint."""
        custom_endpoint = "https://custom-api.example.com"
        auth = QRAuthenticator(endpoint=custom_endpoint)
        assert auth.endpoint == custom_endpoint
    
    @patch('libtuya.auth.qr_auth.LoginControl')
    def test_ensure_login_control_success(self, mock_login_control_class):
        """Test successful LoginControl initialization."""
        mock_instance = Mock()
        mock_login_control_class.return_value = mock_instance
        
        auth = QRAuthenticator()
        auth._ensure_login_control()
        
        assert auth.login_control == mock_instance
        mock_login_control_class.assert_called_once()
    
    @patch('libtuya.auth.qr_auth.LoginControl', side_effect=ImportError("Module not found"))
    def test_ensure_login_control_import_error(self, mock_login_control_class):
        """Test LoginControl initialization with missing dependency."""
        auth = QRAuthenticator()
        
        with pytest.raises(AuthenticationError) as exc_info:
            auth._ensure_login_control()
        
        assert exc_info.value.error_code == "MISSING_DEPENDENCY"
        assert "tuya-device-sharing-sdk not installed" in str(exc_info.value)
    
    def test_generate_qr_code_success(self):
        """Test successful QR code generation."""
        # Mock successful response
        mock_response = {
            "success": True,
            "result": {
                "qrcode": "https://example.com/qr/12345",
                "token": "test-token-123",
                "expires_in": 600
            }
        }
        self.mock_login_control.qr_code.return_value = mock_response
        
        # Generate QR code
        qr_data = self.authenticator.generate_qr_code("test-user-123")
        
        # Verify result
        assert isinstance(qr_data, QRCodeData)
        assert qr_data.qr_code == "https://example.com/qr/12345"
        assert qr_data.token == "test-token-123"
        assert qr_data.expires_in == 600
        
        # Verify method call
        self.mock_login_control.qr_code.assert_called_once_with(
            client_id="HA_3y9q4ak7g4ephrvke",
            schema="haauthorize",
            user_code="test-user-123"
        )
    
    def test_generate_qr_code_no_user_code(self):
        """Test QR code generation without user code."""
        mock_response = {
            "success": True,
            "result": {
                "qrcode": "https://example.com/qr/12345",
                "token": "test-token-123"
            }
        }
        self.mock_login_control.qr_code.return_value = mock_response
        
        # Generate QR code without user code
        qr_data = self.authenticator.generate_qr_code()
        
        # Verify result
        assert isinstance(qr_data, QRCodeData)
        assert qr_data.qr_code == "https://example.com/qr/12345"
        
        # Verify method was called with generated user code
        call_args = self.mock_login_control.qr_code.call_args
        assert call_args[1]['client_id'] == "HA_3y9q4ak7g4ephrvke"
        assert call_args[1]['schema'] == "haauthorize"
        assert len(call_args[1]['user_code']) > 0  # Generated UUID
    
    def test_generate_qr_code_api_failure(self):
        """Test QR code generation with API failure."""
        mock_response = {
            "success": False,
            "msg": "Invalid client ID"
        }
        self.mock_login_control.qr_code.return_value = mock_response
        
        # Test failure
        with pytest.raises(AuthenticationError) as exc_info:
            self.authenticator.generate_qr_code("test-user-123")
        
        assert exc_info.value.error_code == "QR_GENERATION_FAILED"
        assert "Invalid client ID" in str(exc_info.value)
    
    def test_generate_qr_code_missing_fields(self):
        """Test QR code generation with missing fields."""
        mock_response = {
            "success": True,
            "result": {
                "qrcode": "https://example.com/qr/12345"
                # Missing token
            }
        }
        self.mock_login_control.qr_code.return_value = mock_response
        
        # Test missing token
        with pytest.raises(AuthenticationError) as exc_info:
            self.authenticator.generate_qr_code("test-user-123")
        
        assert exc_info.value.error_code == "INVALID_QR_RESPONSE"
    
    def test_generate_qr_code_exception(self):
        """Test QR code generation with unexpected exception."""
        self.mock_login_control.qr_code.side_effect = Exception("Network error")
        
        with pytest.raises(AuthenticationError) as exc_info:
            self.authenticator.generate_qr_code("test-user-123")
        
        assert exc_info.value.error_code == "QR_GENERATION_ERROR"
        assert "Network error" in str(exc_info.value)
    
    def test_check_login_status_success(self):
        """Test successful login status check."""
        mock_token_info = {
            "access_token": "test-access-token",
            "refresh_token": "test-refresh-token",
            "uid": "test-uid",
            "expire_time": 1234567890,
            "t": 1234567890
        }
        self.mock_login_control.login_result.return_value = (True, mock_token_info)
        
        qr_data = QRCodeData(qr_code="test-qr", token="test-token")
        success, result = self.authenticator.check_login_status(qr_data, "test-user")
        
        assert success is True
        assert result == mock_token_info
        
        self.mock_login_control.login_result.assert_called_once_with(
            token="test-token",
            client_id="HA_3y9q4ak7g4ephrvke",
            user_code="test-user"
        )
    
    def test_check_login_status_waiting(self):
        """Test login status check while waiting."""
        mock_error = {
            "success": False,
            "msg": "QR code not scanned yet"
        }
        self.mock_login_control.login_result.return_value = (False, mock_error)
        
        qr_data = QRCodeData(qr_code="test-qr", token="test-token")
        success, result = self.authenticator.check_login_status(qr_data, "test-user")
        
        assert success is False
        assert result is None
    
    def test_check_login_status_auth_failed(self):
        """Test login status check with authentication failure."""
        mock_error = {
            "success": False,
            "msg": "Authentication denied"
        }
        self.mock_login_control.login_result.return_value = (False, mock_error)
        
        qr_data = QRCodeData(qr_code="test-qr", token="test-token")
        
        with pytest.raises(AuthenticationError) as exc_info:
            self.authenticator.check_login_status(qr_data, "test-user")
        
        assert exc_info.value.error_code == "AUTH_FAILED"
        assert "Authentication denied" in str(exc_info.value)
    
    def test_check_login_status_exception(self):
        """Test login status check with exception."""
        self.mock_login_control.login_result.side_effect = Exception("Network error")
        
        qr_data = QRCodeData(qr_code="test-qr", token="test-token")
        
        with pytest.raises(AuthenticationError) as exc_info:
            self.authenticator.check_login_status(qr_data, "test-user")
        
        assert exc_info.value.error_code == "LOGIN_CHECK_ERROR"
    
    def test_wait_for_authentication_success(self):
        """Test successful authentication wait."""
        mock_token_info = {
            "access_token": "test-access-token",
            "refresh_token": "test-refresh-token",
            "uid": "test-uid",
            "expire_time": 1234567890,
            "t": 1234567890
        }
        
        # Mock successful authentication on first poll
        self.mock_login_control.login_result.return_value = (True, mock_token_info)
        
        qr_data = QRCodeData(qr_code="test-qr", token="test-token")
        session = self.authenticator.wait_for_authentication(qr_data, "test-user", timeout=10)
        
        assert isinstance(session, AuthSession)
        assert session.access_token == "test-access-token"
        assert session.uid == "test-uid"
    
    def test_wait_for_authentication_timeout(self):
        """Test authentication wait with timeout."""
        # Mock waiting response
        mock_error = {
            "success": False,
            "msg": "QR code not scanned yet"
        }
        self.mock_login_control.login_result.return_value = (False, mock_error)
        
        qr_data = QRCodeData(qr_code="test-qr", token="test-token")
        
        with pytest.raises(AuthenticationError) as exc_info:
            self.authenticator.wait_for_authentication(qr_data, "test-user", timeout=1)
        
        assert exc_info.value.error_code == "AUTH_TIMEOUT"
    
    def test_wait_for_authentication_missing_token(self):
        """Test authentication wait with missing access token."""
        mock_token_info = {
            "refresh_token": "test-refresh-token",
            "uid": "test-uid"
            # Missing access_token
        }
        self.mock_login_control.login_result.return_value = (True, mock_token_info)
        
        qr_data = QRCodeData(qr_code="test-qr", token="test-token")
        
        with pytest.raises(AuthenticationError) as exc_info:
            self.authenticator.wait_for_authentication(qr_data, "test-user", timeout=10)
        
        assert exc_info.value.error_code == "INVALID_AUTH_RESPONSE"
    
    def test_authenticate_with_qr_success(self):
        """Test complete QR authentication flow."""
        # Mock QR code generation
        mock_qr_response = {
            "success": True,
            "result": {
                "qrcode": "https://example.com/qr/12345",
                "token": "test-token-123"
            }
        }
        
        # Mock successful authentication
        mock_token_info = {
            "access_token": "test-access-token",
            "refresh_token": "test-refresh-token",
            "uid": "test-uid",
            "expire_time": 1234567890,
            "t": 1234567890
        }
        
        self.mock_login_control.qr_code.return_value = mock_qr_response
        self.mock_login_control.login_result.return_value = (True, mock_token_info)
        
        # Run complete flow
        qr_data, session = self.authenticator.authenticate_with_qr(
            user_code="test-user", 
            timeout=10
        )
        
        # Verify results
        assert isinstance(qr_data, QRCodeData)
        assert qr_data.qr_code == "https://example.com/qr/12345"
        
        assert isinstance(session, AuthSession)
        assert session.access_token == "test-access-token"
        assert session.user_code == "test-user"
    
    def test_format_qr_for_display(self):
        """Test QR code formatting for display."""
        qr_data = QRCodeData(qr_code="https://example.com/qr/12345", token="test-token")
        
        formatted = self.authenticator.format_qr_for_display(qr_data)
        
        assert "TUYA AUTHENTICATION" in formatted
        assert "https://example.com/qr/12345" in formatted
        assert "Smart Life" in formatted
        assert "Scan" in formatted
    
    def test_get_current_session(self):
        """Test getting current session."""
        # Initially no session
        assert self.authenticator.get_current_session() is None
        
        # Mock session after authentication
        mock_session = AuthSession(
            access_token="test-token",
            refresh_token="test-refresh",
            uid="test-uid",
            expire_time=1234567890,
            t=1234567890
        )
        self.authenticator._current_session = mock_session
        
        assert self.authenticator.get_current_session() == mock_session
    
    def test_get_current_qr_data(self):
        """Test getting current QR data."""
        # Initially no QR data
        assert self.authenticator.get_current_qr_data() is None
        
        # Mock QR data after generation
        mock_qr_data = QRCodeData(qr_code="test-qr", token="test-token")
        self.authenticator._current_qr_data = mock_qr_data
        
        assert self.authenticator.get_current_qr_data() == mock_qr_data


class TestQRCodeData:
    """Test QR code data model."""
    
    def test_init(self):
        """Test QRCodeData initialization."""
        qr_data = QRCodeData(qr_code="test-qr", token="test-token")
        
        assert qr_data.qr_code == "test-qr"
        assert qr_data.token == "test-token"
        assert qr_data.expires_in == 600  # Default
    
    def test_init_custom_expiry(self):
        """Test QRCodeData with custom expiry."""
        qr_data = QRCodeData(qr_code="test-qr", token="test-token", expires_in=300)
        
        assert qr_data.expires_in == 300
    
    def test_to_dict(self):
        """Test QRCodeData to dictionary conversion."""
        qr_data = QRCodeData(qr_code="test-qr", token="test-token", expires_in=300)
        
        expected = {
            "qr_code": "test-qr",
            "token": "test-token",
            "expires_in": 300
        }
        
        assert qr_data.to_dict() == expected
    
    def test_is_expired(self):
        """Test QRCodeData expiry check."""
        qr_data = QRCodeData(qr_code="test-qr", token="test-token")
        
        # Currently always returns False (placeholder implementation)
        assert qr_data.is_expired is False