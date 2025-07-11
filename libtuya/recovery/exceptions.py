"""
Custom exception hierarchy for libtuya error handling and recovery.

This module defines a comprehensive exception hierarchy that categorizes
all possible errors in the libtuya system, enabling targeted error handling
and recovery strategies.
"""

import time
from typing import Any, Dict, List, Optional


class TuyaError(Exception):
    """
    Base exception class for all Tuya-related errors.

    Provides common error handling functionality including:
    - Error categorization and severity
    - Contextual information for debugging
    - Recovery suggestions
    - Error timing and tracking
    """

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        recovery_suggestions: Optional[List[str]] = None,
        retryable: bool = True,
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.context = context or {}
        self.recovery_suggestions = recovery_suggestions or []
        self.retryable = retryable
        self.timestamp = time.time()
        self.retry_count = 0

    def add_context(self, key: str, value: Any) -> None:
        """Add contextual information to the error."""
        self.context[key] = value

    def increment_retry_count(self) -> None:
        """Increment the retry count for this error."""
        self.retry_count += 1

    def get_diagnostic_info(self) -> Dict[str, Any]:
        """Get comprehensive diagnostic information."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "error_code": self.error_code,
            "context": self.context,
            "recovery_suggestions": self.recovery_suggestions,
            "retryable": self.retryable,
            "timestamp": self.timestamp,
            "retry_count": self.retry_count,
        }


class AuthenticationError(TuyaError):
    """
    Authentication-related errors.

    Covers all authentication failures including:
    - QR code timeout or invalid codes
    - Token expiration or invalid tokens
    - Permission denied errors
    - Network issues during authentication
    """

    def __init__(
        self,
        message: str,
        auth_stage: Optional[str] = None,
        user_code: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.auth_stage = auth_stage
        self.user_code = user_code
        self.add_context("auth_stage", auth_stage)
        self.add_context("user_code", user_code)


class QRCodeError(AuthenticationError):
    """QR code specific authentication errors."""

    def __init__(self, message: str, qr_code: Optional[str] = None, **kwargs):
        super().__init__(message, auth_stage="qr_code", **kwargs)
        self.qr_code = qr_code
        self.add_context("qr_code", qr_code)


class TokenError(AuthenticationError):
    """Token-related authentication errors."""

    def __init__(
        self, message: str, token_type: Optional[str] = None, expired: bool = False, **kwargs
    ):
        super().__init__(message, auth_stage="token", **kwargs)
        self.token_type = token_type
        self.expired = expired
        self.add_context("token_type", token_type)
        self.add_context("expired", expired)


class DeviceConnectionError(TuyaError):
    """
    Device connection and communication errors.

    Covers all device-level connection issues including:
    - IP discovery failures
    - Local key validation errors
    - Network unreachability
    - Device offline errors
    """

    def __init__(
        self,
        message: str,
        device_id: Optional[str] = None,
        device_ip: Optional[str] = None,
        local_key: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.device_id = device_id
        self.device_ip = device_ip
        self.local_key = local_key
        self.add_context("device_id", device_id)
        self.add_context("device_ip", device_ip)
        self.add_context("local_key_present", bool(local_key))


class LocalKeyError(DeviceConnectionError):
    """Local key specific errors."""

    def __init__(
        self,
        message: str,
        key_validation_failed: bool = False,
        encryption_error: bool = False,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.key_validation_failed = key_validation_failed
        self.encryption_error = encryption_error
        self.add_context("key_validation_failed", key_validation_failed)
        self.add_context("encryption_error", encryption_error)


class IPDiscoveryError(DeviceConnectionError):
    """IP discovery specific errors."""

    def __init__(
        self,
        message: str,
        network_scan_failed: bool = False,
        device_offline: bool = False,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.network_scan_failed = network_scan_failed
        self.device_offline = device_offline
        self.add_context("network_scan_failed", network_scan_failed)
        self.add_context("device_offline", device_offline)


class DPSMappingError(TuyaError):
    """
    DPS mapping and capability errors.

    Covers all DPS-related issues including:
    - Unknown device categories
    - Capability mismatches
    - DPS detection failures
    - Mapping rule conflicts
    """

    def __init__(
        self,
        message: str,
        device_category: Optional[str] = None,
        available_dps: Optional[List[int]] = None,
        expected_dps: Optional[List[int]] = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.device_category = device_category
        self.available_dps = available_dps or []
        self.expected_dps = expected_dps or []
        self.add_context("device_category", device_category)
        self.add_context("available_dps", available_dps)
        self.add_context("expected_dps", expected_dps)


class UnknownDeviceError(DPSMappingError):
    """Unknown device category errors."""

    def __init__(self, message: str, device_info: Optional[Dict[str, Any]] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.device_info = device_info or {}
        self.add_context("device_info", device_info)


class CapabilityMismatchError(DPSMappingError):
    """Capability mismatch errors."""

    def __init__(
        self,
        message: str,
        missing_capabilities: Optional[List[str]] = None,
        unexpected_capabilities: Optional[List[str]] = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.missing_capabilities = missing_capabilities or []
        self.unexpected_capabilities = unexpected_capabilities or []
        self.add_context("missing_capabilities", missing_capabilities)
        self.add_context("unexpected_capabilities", unexpected_capabilities)


class ProtocolError(TuyaError):
    """
    Protocol and communication errors.

    Covers all protocol-level issues including:
    - Version detection failures
    - Compatibility issues
    - Command format errors
    - Response parsing errors
    """

    def __init__(
        self,
        message: str,
        protocol_version: Optional[str] = None,
        command: Optional[str] = None,
        response: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.protocol_version = protocol_version
        self.command = command
        self.response = response
        self.add_context("protocol_version", protocol_version)
        self.add_context("command", command)
        self.add_context("response", response)


class VersionDetectionError(ProtocolError):
    """Protocol version detection errors."""

    def __init__(self, message: str, attempted_versions: Optional[List[str]] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.attempted_versions = attempted_versions or []
        self.add_context("attempted_versions", attempted_versions)


class CommandError(ProtocolError):
    """Command execution errors."""

    def __init__(
        self,
        message: str,
        command_type: Optional[str] = None,
        dps_data: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.command_type = command_type
        self.dps_data = dps_data
        self.add_context("command_type", command_type)
        self.add_context("dps_data", dps_data)


class NetworkError(TuyaError):
    """
    Network connectivity and communication errors.

    Covers all network-level issues including:
    - WiFi connectivity problems
    - DNS resolution failures
    - Firewall blocking
    - Timeout errors
    """

    def __init__(
        self,
        message: str,
        network_type: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.network_type = network_type
        self.host = host
        self.port = port
        self.add_context("network_type", network_type)
        self.add_context("host", host)
        self.add_context("port", port)


class ConnectivityError(NetworkError):
    """General connectivity errors."""

    def __init__(self, message: str, connection_type: Optional[str] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.connection_type = connection_type
        self.add_context("connection_type", connection_type)


class DNSError(NetworkError):
    """DNS resolution errors."""

    def __init__(self, message: str, hostname: Optional[str] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.hostname = hostname
        self.add_context("hostname", hostname)


class TimeoutError(NetworkError):
    """Network timeout errors."""

    def __init__(
        self,
        message: str,
        timeout_duration: Optional[float] = None,
        operation: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.timeout_duration = timeout_duration
        self.operation = operation
        self.add_context("timeout_duration", timeout_duration)
        self.add_context("operation", operation)


class DeviceError(TuyaError):
    """
    Device-specific errors.

    Covers all device-level issues including:
    - Hardware failures
    - Firmware issues
    - Device-specific quirks
    - Capability limitations
    """

    def __init__(
        self,
        message: str,
        device_id: Optional[str] = None,
        device_model: Optional[str] = None,
        firmware_version: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.device_id = device_id
        self.device_model = device_model
        self.firmware_version = firmware_version
        self.add_context("device_id", device_id)
        self.add_context("device_model", device_model)
        self.add_context("firmware_version", firmware_version)


class HardwareError(DeviceError):
    """Hardware-specific errors."""

    def __init__(self, message: str, hardware_issue: Optional[str] = None, **kwargs):
        super().__init__(message, retryable=False, **kwargs)
        self.hardware_issue = hardware_issue
        self.add_context("hardware_issue", hardware_issue)


class FirmwareError(DeviceError):
    """Firmware-specific errors."""

    def __init__(
        self,
        message: str,
        firmware_issue: Optional[str] = None,
        update_available: bool = False,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.firmware_issue = firmware_issue
        self.update_available = update_available
        self.add_context("firmware_issue", firmware_issue)
        self.add_context("update_available", update_available)


class ConfigurationError(TuyaError):
    """
    Configuration and setup errors.

    Covers all configuration-related issues including:
    - Invalid settings
    - Missing configuration
    - Environment setup issues
    """

    def __init__(
        self,
        message: str,
        config_section: Optional[str] = None,
        config_key: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.config_section = config_section
        self.config_key = config_key
        self.add_context("config_section", config_section)
        self.add_context("config_key", config_key)


# Exception hierarchy map for error categorization
EXCEPTION_HIERARCHY = {
    "authentication": [AuthenticationError, QRCodeError, TokenError],
    "device_connection": [
        DeviceConnectionError,
        LocalKeyError,
        IPDiscoveryError,
    ],
    "dps_mapping": [
        DPSMappingError,
        UnknownDeviceError,
        CapabilityMismatchError,
    ],
    "protocol": [ProtocolError, VersionDetectionError, CommandError],
    "network": [NetworkError, ConnectivityError, DNSError, TimeoutError],
    "device": [DeviceError, HardwareError, FirmwareError],
    "configuration": [ConfigurationError],
}


def get_error_category(error: Exception) -> str:
    """
    Get the category of an error based on its type.

    Args:
        error: The error to categorize

    Returns:
        The category name, or "unknown" if not categorized
    """
    for category, exception_types in EXCEPTION_HIERARCHY.items():
        if any(isinstance(error, exc_type) for exc_type in exception_types):
            return category
    return "unknown"


def is_retryable_error(error: Exception) -> bool:
    """
    Check if an error is retryable.

    Args:
        error: The error to check

    Returns:
        True if the error is retryable, False otherwise
    """
    if isinstance(error, TuyaError):
        return error.retryable

    # Network errors are generally retryable
    if isinstance(error, (ConnectionError, TimeoutError)):
        return True

    # Other errors are not retryable by default
    return False
