"""
Tests for libtuya recovery exceptions.

This module tests the custom exception hierarchy and error categorization
functionality.
"""

import pytest
import time
from unittest.mock import patch

from libtuya.recovery.exceptions import (
    TuyaError,
    AuthenticationError,
    QRCodeError,
    TokenError,
    DeviceConnectionError,
    LocalKeyError,
    IPDiscoveryError,
    DPSMappingError,
    UnknownDeviceError,
    CapabilityMismatchError,
    ProtocolError,
    VersionDetectionError,
    CommandError,
    NetworkError,
    ConnectivityError,
    DNSError,
    TimeoutError,
    DeviceError,
    HardwareError,
    FirmwareError,
    ConfigurationError,
    get_error_category,
    is_retryable_error,
    EXCEPTION_HIERARCHY
)


class TestTuyaError:
    """Test the base TuyaError class."""
    
    def test_basic_error_creation(self):
        """Test basic error creation."""
        error = TuyaError("Test error")
        assert str(error) == "Test error"
        assert error.message == "Test error"
        assert error.error_code is None
        assert error.context == {}
        assert error.recovery_suggestions == []
        assert error.retryable is True
        assert error.retry_count == 0
        assert isinstance(error.timestamp, float)
    
    def test_error_with_all_parameters(self):
        """Test error creation with all parameters."""
        context = {"key": "value"}
        suggestions = ["Try again", "Check settings"]
        
        error = TuyaError(
            "Test error",
            error_code="TEST_001",
            context=context,
            recovery_suggestions=suggestions,
            retryable=False
        )
        
        assert error.message == "Test error"
        assert error.error_code == "TEST_001"
        assert error.context == context
        assert error.recovery_suggestions == suggestions
        assert error.retryable is False
    
    def test_add_context(self):
        """Test adding context to error."""
        error = TuyaError("Test error")
        error.add_context("new_key", "new_value")
        
        assert error.context["new_key"] == "new_value"
    
    def test_increment_retry_count(self):
        """Test incrementing retry count."""
        error = TuyaError("Test error")
        assert error.retry_count == 0
        
        error.increment_retry_count()
        assert error.retry_count == 1
        
        error.increment_retry_count()
        assert error.retry_count == 2
    
    def test_get_diagnostic_info(self):
        """Test getting diagnostic information."""
        error = TuyaError("Test error", error_code="TEST_001")
        error.add_context("key", "value")
        error.increment_retry_count()
        
        info = error.get_diagnostic_info()
        
        assert info["error_type"] == "TuyaError"
        assert info["message"] == "Test error"
        assert info["error_code"] == "TEST_001"
        assert info["context"]["key"] == "value"
        assert info["retryable"] is True
        assert info["retry_count"] == 1
        assert "timestamp" in info


class TestAuthenticationErrors:
    """Test authentication error classes."""
    
    def test_authentication_error(self):
        """Test AuthenticationError."""
        error = AuthenticationError(
            "Auth failed",
            auth_stage="login",
            user_code="USER123"
        )
        
        assert isinstance(error, TuyaError)
        assert error.auth_stage == "login"
        assert error.user_code == "USER123"
        assert error.context["auth_stage"] == "login"
        assert error.context["user_code"] == "USER123"
    
    def test_qr_code_error(self):
        """Test QRCodeError."""
        error = QRCodeError("QR code expired", qr_code="QR123")
        
        assert isinstance(error, AuthenticationError)
        assert error.auth_stage == "qr_code"
        assert error.qr_code == "QR123"
        assert error.context["qr_code"] == "QR123"
    
    def test_token_error(self):
        """Test TokenError."""
        error = TokenError(
            "Token expired",
            token_type="access",
            expired=True
        )
        
        assert isinstance(error, AuthenticationError)
        assert error.auth_stage == "token"
        assert error.token_type == "access"
        assert error.expired is True
        assert error.context["token_type"] == "access"
        assert error.context["expired"] is True


class TestDeviceConnectionErrors:
    """Test device connection error classes."""
    
    def test_device_connection_error(self):
        """Test DeviceConnectionError."""
        error = DeviceConnectionError(
            "Connection failed",
            device_id="DEV123",
            device_ip="192.168.1.100",
            local_key="KEY123"
        )
        
        assert isinstance(error, TuyaError)
        assert error.device_id == "DEV123"
        assert error.device_ip == "192.168.1.100"
        assert error.local_key == "KEY123"
        assert error.context["device_id"] == "DEV123"
        assert error.context["device_ip"] == "192.168.1.100"
        assert error.context["local_key_present"] is True
    
    def test_local_key_error(self):
        """Test LocalKeyError."""
        error = LocalKeyError(
            "Invalid key",
            device_id="DEV123",
            key_validation_failed=True,
            encryption_error=False
        )
        
        assert isinstance(error, DeviceConnectionError)
        assert error.key_validation_failed is True
        assert error.encryption_error is False
        assert error.context["key_validation_failed"] is True
        assert error.context["encryption_error"] is False
    
    def test_ip_discovery_error(self):
        """Test IPDiscoveryError."""
        error = IPDiscoveryError(
            "IP not found",
            device_id="DEV123",
            network_scan_failed=True,
            device_offline=False
        )
        
        assert isinstance(error, DeviceConnectionError)
        assert error.network_scan_failed is True
        assert error.device_offline is False
        assert error.context["network_scan_failed"] is True
        assert error.context["device_offline"] is False


class TestDPSMappingErrors:
    """Test DPS mapping error classes."""
    
    def test_dps_mapping_error(self):
        """Test DPSMappingError."""
        error = DPSMappingError(
            "Mapping failed",
            device_category="light",
            available_dps=[1, 2, 3],
            expected_dps=[1, 3, 5]
        )
        
        assert isinstance(error, TuyaError)
        assert error.device_category == "light"
        assert error.available_dps == [1, 2, 3]
        assert error.expected_dps == [1, 3, 5]
        assert error.context["device_category"] == "light"
        assert error.context["available_dps"] == [1, 2, 3]
        assert error.context["expected_dps"] == [1, 3, 5]
    
    def test_unknown_device_error(self):
        """Test UnknownDeviceError."""
        device_info = {"model": "TEST123", "category": "unknown"}
        error = UnknownDeviceError("Unknown device", device_info=device_info)
        
        assert isinstance(error, DPSMappingError)
        assert error.device_info == device_info
        assert error.context["device_info"] == device_info
    
    def test_capability_mismatch_error(self):
        """Test CapabilityMismatchError."""
        error = CapabilityMismatchError(
            "Capability mismatch",
            missing_capabilities=["brightness"],
            unexpected_capabilities=["color_temp"]
        )
        
        assert isinstance(error, DPSMappingError)
        assert error.missing_capabilities == ["brightness"]
        assert error.unexpected_capabilities == ["color_temp"]
        assert error.context["missing_capabilities"] == ["brightness"]
        assert error.context["unexpected_capabilities"] == ["color_temp"]


class TestProtocolErrors:
    """Test protocol error classes."""
    
    def test_protocol_error(self):
        """Test ProtocolError."""
        error = ProtocolError(
            "Protocol error",
            protocol_version="3.3",
            command="status",
            response="error"
        )
        
        assert isinstance(error, TuyaError)
        assert error.protocol_version == "3.3"
        assert error.command == "status"
        assert error.response == "error"
        assert error.context["protocol_version"] == "3.3"
        assert error.context["command"] == "status"
        assert error.context["response"] == "error"
    
    def test_version_detection_error(self):
        """Test VersionDetectionError."""
        error = VersionDetectionError(
            "Version detection failed",
            attempted_versions=["3.1", "3.3"]
        )
        
        assert isinstance(error, ProtocolError)
        assert error.attempted_versions == ["3.1", "3.3"]
        assert error.context["attempted_versions"] == ["3.1", "3.3"]
    
    def test_command_error(self):
        """Test CommandError."""
        error = CommandError(
            "Command failed",
            command_type="set",
            dps_data={1: True}
        )
        
        assert isinstance(error, ProtocolError)
        assert error.command_type == "set"
        assert error.dps_data == {1: True}
        assert error.context["command_type"] == "set"
        assert error.context["dps_data"] == {1: True}


class TestNetworkErrors:
    """Test network error classes."""
    
    def test_network_error(self):
        """Test NetworkError."""
        error = NetworkError(
            "Network error",
            network_type="wifi",
            host="192.168.1.1",
            port=6668
        )
        
        assert isinstance(error, TuyaError)
        assert error.network_type == "wifi"
        assert error.host == "192.168.1.1"
        assert error.port == 6668
        assert error.context["network_type"] == "wifi"
        assert error.context["host"] == "192.168.1.1"
        assert error.context["port"] == 6668
    
    def test_connectivity_error(self):
        """Test ConnectivityError."""
        error = ConnectivityError(
            "No connection",
            connection_type="internet"
        )
        
        assert isinstance(error, NetworkError)
        assert error.connection_type == "internet"
        assert error.context["connection_type"] == "internet"
    
    def test_dns_error(self):
        """Test DNSError."""
        error = DNSError("DNS failed", hostname="example.com")
        
        assert isinstance(error, NetworkError)
        assert error.hostname == "example.com"
        assert error.context["hostname"] == "example.com"
    
    def test_timeout_error(self):
        """Test TimeoutError."""
        error = TimeoutError(
            "Operation timed out",
            timeout_duration=30.0,
            operation="connect"
        )
        
        assert isinstance(error, NetworkError)
        assert error.timeout_duration == 30.0
        assert error.operation == "connect"
        assert error.context["timeout_duration"] == 30.0
        assert error.context["operation"] == "connect"


class TestDeviceErrors:
    """Test device error classes."""
    
    def test_device_error(self):
        """Test DeviceError."""
        error = DeviceError(
            "Device error",
            device_id="DEV123",
            device_model="MODEL_A",
            firmware_version="1.0.0"
        )
        
        assert isinstance(error, TuyaError)
        assert error.device_id == "DEV123"
        assert error.device_model == "MODEL_A"
        assert error.firmware_version == "1.0.0"
        assert error.context["device_id"] == "DEV123"
        assert error.context["device_model"] == "MODEL_A"
        assert error.context["firmware_version"] == "1.0.0"
    
    def test_hardware_error(self):
        """Test HardwareError."""
        error = HardwareError(
            "Hardware failure",
            hardware_issue="sensor_failure"
        )
        
        assert isinstance(error, DeviceError)
        assert error.hardware_issue == "sensor_failure"
        assert error.retryable is False  # Hardware errors are not retryable
        assert error.context["hardware_issue"] == "sensor_failure"
    
    def test_firmware_error(self):
        """Test FirmwareError."""
        error = FirmwareError(
            "Firmware issue",
            firmware_issue="corruption",
            update_available=True
        )
        
        assert isinstance(error, DeviceError)
        assert error.firmware_issue == "corruption"
        assert error.update_available is True
        assert error.context["firmware_issue"] == "corruption"
        assert error.context["update_available"] is True


class TestConfigurationError:
    """Test configuration error class."""
    
    def test_configuration_error(self):
        """Test ConfigurationError."""
        error = ConfigurationError(
            "Config error",
            config_section="auth",
            config_key="client_id"
        )
        
        assert isinstance(error, TuyaError)
        assert error.config_section == "auth"
        assert error.config_key == "client_id"
        assert error.context["config_section"] == "auth"
        assert error.context["config_key"] == "client_id"


class TestErrorUtilities:
    """Test error utility functions."""
    
    def test_get_error_category(self):
        """Test error category detection."""
        assert get_error_category(AuthenticationError("test")) == "authentication"
        assert get_error_category(QRCodeError("test")) == "authentication"
        assert get_error_category(DeviceConnectionError("test")) == "device_connection"
        assert get_error_category(LocalKeyError("test")) == "device_connection"
        assert get_error_category(DPSMappingError("test")) == "dps_mapping"
        assert get_error_category(UnknownDeviceError("test")) == "dps_mapping"
        assert get_error_category(ProtocolError("test")) == "protocol"
        assert get_error_category(VersionDetectionError("test")) == "protocol"
        assert get_error_category(NetworkError("test")) == "network"
        assert get_error_category(ConnectivityError("test")) == "network"
        assert get_error_category(DeviceError("test")) == "device"
        assert get_error_category(HardwareError("test")) == "device"
        assert get_error_category(ConfigurationError("test")) == "configuration"
        assert get_error_category(ValueError("test")) == "unknown"
    
    def test_is_retryable_error(self):
        """Test retryable error detection."""
        # TuyaError with retryable=True
        assert is_retryable_error(TuyaError("test", retryable=True)) is True
        
        # TuyaError with retryable=False
        assert is_retryable_error(TuyaError("test", retryable=False)) is False
        
        # HardwareError (retryable=False by default)
        assert is_retryable_error(HardwareError("test")) is False
        
        # Standard exceptions
        assert is_retryable_error(ConnectionError("test")) is True
        assert is_retryable_error(TimeoutError("test")) is True
        assert is_retryable_error(ValueError("test")) is False
    
    def test_exception_hierarchy(self):
        """Test exception hierarchy structure."""
        assert "authentication" in EXCEPTION_HIERARCHY
        assert "device_connection" in EXCEPTION_HIERARCHY
        assert "dps_mapping" in EXCEPTION_HIERARCHY
        assert "protocol" in EXCEPTION_HIERARCHY
        assert "network" in EXCEPTION_HIERARCHY
        assert "device" in EXCEPTION_HIERARCHY
        assert "configuration" in EXCEPTION_HIERARCHY
        
        # Check that classes are in the right categories
        assert AuthenticationError in EXCEPTION_HIERARCHY["authentication"]
        assert QRCodeError in EXCEPTION_HIERARCHY["authentication"]
        assert DeviceConnectionError in EXCEPTION_HIERARCHY["device_connection"]
        assert LocalKeyError in EXCEPTION_HIERARCHY["device_connection"]
        assert DPSMappingError in EXCEPTION_HIERARCHY["dps_mapping"]
        assert ProtocolError in EXCEPTION_HIERARCHY["protocol"]
        assert NetworkError in EXCEPTION_HIERARCHY["network"]
        assert DeviceError in EXCEPTION_HIERARCHY["device"]
        assert ConfigurationError in EXCEPTION_HIERARCHY["configuration"]


if __name__ == "__main__":
    pytest.main([__file__])