"""
Error handlers and recovery mechanisms for libtuya.

This module provides comprehensive error handling and recovery strategies
for all types of failures in the libtuya system, enabling graceful
degradation and automatic recovery.
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple, Union

from .exceptions import (
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
)
from .retry_strategies import RetryManager, RetryConfig, RETRY_CONFIGS

logger = logging.getLogger(__name__)


class RecoveryResult:
    """Result of a recovery operation."""

    def __init__(
        self,
        success: bool,
        message: str,
        recovered_data: Optional[Dict[str, Any]] = None,
        fallback_used: bool = False,
        retry_recommended: bool = False,
    ):
        self.success = success
        self.message = message
        self.recovered_data = recovered_data or {}
        self.fallback_used = fallback_used
        self.retry_recommended = retry_recommended
        self.timestamp = time.time()


class BaseRecoveryHandler(ABC):
    """Base class for all recovery handlers."""

    def __init__(self, retry_manager: Optional[RetryManager] = None):
        self.retry_manager = retry_manager or RetryManager()
        self.recovery_attempts = 0
        self.last_recovery_time = 0

    @abstractmethod
    def can_handle(self, error: Exception) -> bool:
        """Check if this handler can handle the given error."""
        pass

    @abstractmethod
    def recover(self, error: Exception, context: Dict[str, Any]) -> RecoveryResult:
        """Attempt to recover from the given error."""
        pass

    def get_priority(self) -> int:
        """Get the priority of this handler (lower number = higher priority)."""
        return 50  # Default priority

    def reset_recovery_state(self):
        """Reset the recovery state."""
        self.recovery_attempts = 0
        self.last_recovery_time = 0


class AuthenticationRecovery(BaseRecoveryHandler):
    """Recovery handler for authentication errors."""

    def __init__(self, retry_manager: Optional[RetryManager] = None):
        super().__init__(retry_manager)
        self.token_refresh_cache = {}

    def can_handle(self, error: Exception) -> bool:
        """Check if this handler can handle authentication errors."""
        return isinstance(error, AuthenticationError)

    def get_priority(self) -> int:
        """Authentication recovery has high priority."""
        return 10

    def recover(self, error: Exception, context: Dict[str, Any]) -> RecoveryResult:
        """Recover from authentication errors."""
        self.recovery_attempts += 1
        self.last_recovery_time = time.time()

        logger.info(
            f"Attempting authentication recovery (attempt {self.recovery_attempts})"
        )

        if isinstance(error, QRCodeError):
            return self._recover_qr_code_error(error, context)
        elif isinstance(error, TokenError):
            return self._recover_token_error(error, context)
        else:
            return self._recover_generic_auth_error(error, context)

    def _recover_qr_code_error(
        self, error: QRCodeError, context: Dict[str, Any]
    ) -> RecoveryResult:
        """Recover from QR code errors."""
        logger.debug("Recovering from QR code error")

        # Check if QR code timeout
        if "timeout" in error.message.lower():
            return RecoveryResult(
                success=False,
                message="QR code expired. Please generate a new QR code and try again.",
                retry_recommended=True,
            )

        # Check if QR code is invalid
        if "invalid" in error.message.lower():
            return RecoveryResult(
                success=False,
                message="Invalid QR code. Please check the QR code and try again.",
                retry_recommended=True,
            )

        # Generic QR code recovery
        return RecoveryResult(
            success=False,
            message="QR code authentication failed. Please try generating a new QR code.",
            retry_recommended=True,
        )

    def _recover_token_error(
        self, error: TokenError, context: Dict[str, Any]
    ) -> RecoveryResult:
        """Recover from token errors."""
        logger.debug("Recovering from token error")

        # Check if token is expired
        if error.expired or "expired" in error.message.lower():
            return self._attempt_token_refresh(error, context)

        # Check if token is invalid
        if "invalid" in error.message.lower():
            return RecoveryResult(
                success=False,
                message="Invalid authentication token. Please re-authenticate.",
                retry_recommended=False,
            )

        # Generic token recovery
        return RecoveryResult(
            success=False,
            message="Token authentication failed. Please check your credentials.",
            retry_recommended=True,
        )

    def _recover_generic_auth_error(
        self, error: AuthenticationError, context: Dict[str, Any]
    ) -> RecoveryResult:
        """Recover from generic authentication errors."""
        logger.debug("Recovering from generic authentication error")

        # Check for network issues
        if isinstance(error.__cause__, NetworkError):
            return RecoveryResult(
                success=False,
                message="Network error during authentication. Please check your connection.",
                retry_recommended=True,
            )

        # Check for permission issues
        if (
            "permission" in error.message.lower()
            or "unauthorized" in error.message.lower()
        ):
            return RecoveryResult(
                success=False,
                message="Authentication failed due to insufficient permissions.",
                retry_recommended=False,
            )

        return RecoveryResult(
            success=False,
            message="Authentication failed. Please try again.",
            retry_recommended=True,
        )

    def _attempt_token_refresh(
        self, error: TokenError, context: Dict[str, Any]
    ) -> RecoveryResult:
        """Attempt to refresh the authentication token."""
        logger.debug("Attempting token refresh")

        # Get authenticator from context
        authenticator = context.get("authenticator")
        if not authenticator:
            return RecoveryResult(
                success=False,
                message="No authenticator available for token refresh.",
                retry_recommended=False,
            )

        # Attempt token refresh using the auth system
        try:
            logger.info("Attempting token refresh with authentication system")

            # Check if we have a current session
            current_session = authenticator.get_session()
            if not current_session:
                return RecoveryResult(
                    success=False,
                    message="No current session available for token refresh.",
                    retry_recommended=False,
                )

            # Check if session is expired
            if current_session.is_expired:
                return RecoveryResult(
                    success=False,
                    message="Session expired. Please re-authenticate.",
                    retry_recommended=False,
                )

            # The tuya-device-sharing-sdk handles token refresh automatically
            # through the CustomerApi.refresh_access_token_if_need() method
            # We just need to trigger a device discovery to force token refresh
            if authenticator.device_manager:
                logger.info("Triggering device discovery to force token refresh")

                # This will trigger the SDK's automatic token refresh if needed
                result = authenticator.device_manager.discover_devices(
                    force_refresh=True
                )

                # Check if we got devices back (indicating successful refresh)
                if result.devices:
                    return RecoveryResult(
                        success=True,
                        message="Token refresh successful via device discovery.",
                        recovered_data={"session": current_session},
                        retry_recommended=True,
                    )

            # If device manager approach failed, try creating new manager
            # This will force re-initialization and token refresh
            try:
                authenticator._initialize_device_manager()
                if authenticator.device_manager:
                    return RecoveryResult(
                        success=True,
                        message="Token refresh successful via manager re-initialization.",
                        recovered_data={"session": current_session},
                        retry_recommended=True,
                    )
            except Exception as reinit_error:
                logger.warning(f"Manager re-initialization failed: {reinit_error}")

            return RecoveryResult(
                success=False,
                message="Token refresh failed. Please re-authenticate.",
                retry_recommended=False,
            )

        except Exception as e:
            logger.error(f"Token refresh failed: {e}")
            return RecoveryResult(
                success=False,
                message=f"Token refresh failed: {str(e)}. Please re-authenticate.",
                retry_recommended=False,
            )


class DeviceConnectionRecovery(BaseRecoveryHandler):
    """Recovery handler for device connection errors."""

    def __init__(self, retry_manager: Optional[RetryManager] = None):
        super().__init__(retry_manager)
        self.ip_discovery_cache = {}
        self.local_key_cache = {}

    def can_handle(self, error: Exception) -> bool:
        """Check if this handler can handle device connection errors."""
        return isinstance(error, DeviceConnectionError)

    def get_priority(self) -> int:
        """Device connection recovery has medium priority."""
        return 20

    def recover(self, error: Exception, context: Dict[str, Any]) -> RecoveryResult:
        """Recover from device connection errors."""
        self.recovery_attempts += 1
        self.last_recovery_time = time.time()

        logger.info(
            f"Attempting device connection recovery (attempt {self.recovery_attempts})"
        )

        if isinstance(error, LocalKeyError):
            return self._recover_local_key_error(error, context)
        elif isinstance(error, IPDiscoveryError):
            return self._recover_ip_discovery_error(error, context)
        else:
            return self._recover_generic_connection_error(error, context)

    def _recover_local_key_error(
        self, error: LocalKeyError, context: Dict[str, Any]
    ) -> RecoveryResult:
        """Recover from local key errors."""
        logger.debug("Recovering from local key error")

        device_id = error.device_id
        if not device_id:
            return RecoveryResult(
                success=False,
                message="No device ID available for local key recovery.",
                retry_recommended=False,
            )

        # Check if key validation failed
        if error.key_validation_failed:
            return self._attempt_local_key_refresh(device_id, context)

        # Check if encryption error
        if error.encryption_error:
            return self._attempt_encryption_recovery(device_id, context)

        # Generic local key recovery
        return RecoveryResult(
            success=False,
            message="Local key error. Try re-discovering the device.",
            retry_recommended=True,
        )

    def _recover_ip_discovery_error(
        self, error: IPDiscoveryError, context: Dict[str, Any]
    ) -> RecoveryResult:
        """Recover from IP discovery errors."""
        logger.debug("Recovering from IP discovery error")

        device_id = error.device_id
        if not device_id:
            return RecoveryResult(
                success=False,
                message="No device ID available for IP discovery recovery.",
                retry_recommended=False,
            )

        # Check if network scan failed
        if error.network_scan_failed:
            return self._attempt_network_scan_recovery(device_id, context)

        # Check if device is offline
        if error.device_offline:
            return RecoveryResult(
                success=False,
                message="Device appears to be offline. Please check device power and network.",
                retry_recommended=True,
            )

        # Generic IP discovery recovery
        return self._attempt_ip_discovery_fallback(device_id, context)

    def _recover_generic_connection_error(
        self, error: DeviceConnectionError, context: Dict[str, Any]
    ) -> RecoveryResult:
        """Recover from generic connection errors."""
        logger.debug("Recovering from generic connection error")

        # Check for network issues
        if isinstance(error.__cause__, NetworkError):
            return RecoveryResult(
                success=False,
                message="Network error during device connection. Please check your connection.",
                retry_recommended=True,
            )

        # Check if device is unreachable
        if "unreachable" in error.message.lower():
            return RecoveryResult(
                success=False,
                message="Device unreachable. Please check device power and network.",
                retry_recommended=True,
            )

        return RecoveryResult(
            success=False,
            message="Device connection failed. Please try again.",
            retry_recommended=True,
        )

    def _attempt_local_key_refresh(
        self, device_id: str, context: Dict[str, Any]
    ) -> RecoveryResult:
        """Attempt to refresh the local key."""
        logger.debug(f"Attempting local key refresh for device {device_id}")

        # Get authenticator from context
        authenticator = context.get("authenticator")
        if not authenticator:
            return RecoveryResult(
                success=False,
                message="No authenticator available for local key refresh.",
                retry_recommended=False,
            )

        # Attempt local key refresh by re-discovering devices
        try:
            logger.info(f"Attempting local key refresh for device {device_id}")

            # Check if we have a device manager
            if not authenticator.device_manager:
                return RecoveryResult(
                    success=False,
                    message="No device manager available for local key refresh.",
                    retry_recommended=False,
                )

            # Force device discovery to get fresh local keys
            logger.info("Forcing device discovery to refresh local keys")
            result = authenticator.device_manager.discover_devices(force_refresh=True)

            # Check if we got the specific device back with a local key
            for device in result.devices:
                if device.device_id == device_id:
                    if device.local_key:
                        return RecoveryResult(
                            success=True,
                            message=f"Local key refreshed successfully for device {device_id}.",
                            recovered_data={
                                "device": device,
                                "local_key": device.local_key,
                            },
                            retry_recommended=True,
                        )
                    else:
                        return RecoveryResult(
                            success=False,
                            message=f"Device {device_id} found but no local key available.",
                            retry_recommended=False,
                        )

            # Device not found in discovery
            return RecoveryResult(
                success=False,
                message=f"Device {device_id} not found during local key refresh.",
                retry_recommended=False,
            )

        except Exception as e:
            logger.error(f"Local key refresh failed: {e}")
            return RecoveryResult(
                success=False,
                message=f"Local key refresh failed: {str(e)}. Please re-discover the device.",
                retry_recommended=True,
            )

    def _attempt_encryption_recovery(
        self, device_id: str, context: Dict[str, Any]
    ) -> RecoveryResult:
        """Attempt to recover from encryption errors."""
        logger.debug(f"Attempting encryption recovery for device {device_id}")

        # Try different protocol versions
        return RecoveryResult(
            success=False,
            message="Encryption error. Try using a different protocol version.",
            retry_recommended=True,
        )

    def _attempt_network_scan_recovery(
        self, device_id: str, context: Dict[str, Any]
    ) -> RecoveryResult:
        """Attempt to recover from network scan failures."""
        logger.debug(f"Attempting network scan recovery for device {device_id}")

        # Extended network scan or different scan method
        return RecoveryResult(
            success=False,
            message="Network scan failed. Try scanning a different network range.",
            retry_recommended=True,
        )

    def _attempt_ip_discovery_fallback(
        self, device_id: str, context: Dict[str, Any]
    ) -> RecoveryResult:
        """Attempt IP discovery fallback methods."""
        logger.debug(f"Attempting IP discovery fallback for device {device_id}")

        # Try cloud API for IP discovery
        return RecoveryResult(
            success=False,
            message="IP discovery failed. Try using cloud API fallback.",
            retry_recommended=True,
            fallback_used=True,
        )


class DPSMappingRecovery(BaseRecoveryHandler):
    """Recovery handler for DPS mapping errors."""

    def __init__(self, retry_manager: Optional[RetryManager] = None):
        super().__init__(retry_manager)
        self.fallback_mappings = {}

    def can_handle(self, error: Exception) -> bool:
        """Check if this handler can handle DPS mapping errors."""
        return isinstance(error, DPSMappingError)

    def get_priority(self) -> int:
        """DPS mapping recovery has medium priority."""
        return 30

    def recover(self, error: Exception, context: Dict[str, Any]) -> RecoveryResult:
        """Recover from DPS mapping errors."""
        self.recovery_attempts += 1
        self.last_recovery_time = time.time()

        logger.info(
            f"Attempting DPS mapping recovery (attempt {self.recovery_attempts})"
        )

        if isinstance(error, UnknownDeviceError):
            return self._recover_unknown_device_error(error, context)
        elif isinstance(error, CapabilityMismatchError):
            return self._recover_capability_mismatch_error(error, context)
        else:
            return self._recover_generic_mapping_error(error, context)

    def _recover_unknown_device_error(
        self, error: UnknownDeviceError, context: Dict[str, Any]
    ) -> RecoveryResult:
        """Recover from unknown device errors."""
        logger.debug("Recovering from unknown device error")

        device_info = error.device_info
        if not device_info:
            return RecoveryResult(
                success=False,
                message="No device information available for mapping recovery.",
                retry_recommended=False,
            )

        # Try to create generic mapping based on available DPS
        fallback_mapping = self._create_fallback_mapping(
            error.available_dps, device_info
        )

        if fallback_mapping:
            return RecoveryResult(
                success=True,
                message="Created fallback device mapping using heuristics.",
                recovered_data={"mapping": fallback_mapping},
                fallback_used=True,
            )

        return RecoveryResult(
            success=False,
            message="Unable to create device mapping. Manual configuration required.",
            retry_recommended=False,
        )

    def _recover_capability_mismatch_error(
        self, error: CapabilityMismatchError, context: Dict[str, Any]
    ) -> RecoveryResult:
        """Recover from capability mismatch errors."""
        logger.debug("Recovering from capability mismatch error")

        # Create adjusted mapping with available capabilities
        adjusted_mapping = self._create_adjusted_mapping(
            error.available_dps,
            error.expected_dps,
            error.missing_capabilities,
            error.unexpected_capabilities,
        )

        if adjusted_mapping:
            return RecoveryResult(
                success=True,
                message="Adjusted device mapping to match available capabilities.",
                recovered_data={"mapping": adjusted_mapping},
                fallback_used=True,
            )

        return RecoveryResult(
            success=False,
            message="Unable to adjust device mapping. Some features may not work.",
            retry_recommended=False,
        )

    def _recover_generic_mapping_error(
        self, error: DPSMappingError, context: Dict[str, Any]
    ) -> RecoveryResult:
        """Recover from generic mapping errors."""
        logger.debug("Recovering from generic mapping error")

        # Try reprobing device capabilities
        if error.available_dps:
            fallback_mapping = self._create_fallback_mapping(error.available_dps, {})
            if fallback_mapping:
                return RecoveryResult(
                    success=True,
                    message="Reprobed device capabilities and created fallback mapping.",
                    recovered_data={"mapping": fallback_mapping},
                    fallback_used=True,
                )

        return RecoveryResult(
            success=False,
            message="DPS mapping failed. Try reprobing device capabilities.",
            retry_recommended=True,
        )

    def _create_fallback_mapping(
        self, available_dps: List[int], device_info: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Create fallback mapping based on available DPS."""
        logger.debug(f"Creating fallback mapping for DPS: {available_dps}")

        if not available_dps:
            return None

        # Basic heuristic mappings
        mapping = {}

        # DPS 1 is almost always the main switch
        if 1 in available_dps:
            mapping["switch"] = 1

        # DPS 2 is often a secondary switch or mode
        if 2 in available_dps:
            mapping["mode"] = 2

        # DPS 3 is often brightness for lights
        if 3 in available_dps:
            mapping["brightness"] = 3

        # DPS 4 is often temperature or timer
        if 4 in available_dps:
            mapping["temperature"] = 4

        # DPS 5 is often color for RGB lights
        if 5 in available_dps:
            mapping["color"] = 5

        return mapping if mapping else None

    def _create_adjusted_mapping(
        self,
        available_dps: List[int],
        expected_dps: List[int],
        missing_capabilities: List[str],
        unexpected_capabilities: List[str],
    ) -> Optional[Dict[str, Any]]:
        """Create adjusted mapping based on capability mismatch."""
        logger.debug("Creating adjusted mapping for capability mismatch")

        # Start with basic fallback mapping
        mapping = self._create_fallback_mapping(available_dps, {})

        if not mapping:
            return None

        # Remove mappings for missing capabilities
        for capability in missing_capabilities:
            if capability in mapping:
                del mapping[capability]

        # Add basic mappings for unexpected capabilities
        for capability in unexpected_capabilities:
            if capability not in mapping:
                # Try to find a reasonable DPS for this capability
                for dps in available_dps:
                    if dps not in mapping.values():
                        mapping[capability] = dps
                        break

        return mapping


class ProtocolRecovery(BaseRecoveryHandler):
    """Recovery handler for protocol errors."""

    def __init__(self, retry_manager: Optional[RetryManager] = None):
        super().__init__(retry_manager)
        self.protocol_version_cache = {}

    def can_handle(self, error: Exception) -> bool:
        """Check if this handler can handle protocol errors."""
        return isinstance(error, ProtocolError)

    def get_priority(self) -> int:
        """Protocol recovery has medium priority."""
        return 40

    def recover(self, error: Exception, context: Dict[str, Any]) -> RecoveryResult:
        """Recover from protocol errors."""
        self.recovery_attempts += 1
        self.last_recovery_time = time.time()

        logger.info(f"Attempting protocol recovery (attempt {self.recovery_attempts})")

        if isinstance(error, VersionDetectionError):
            return self._recover_version_detection_error(error, context)
        elif isinstance(error, CommandError):
            return self._recover_command_error(error, context)
        else:
            return self._recover_generic_protocol_error(error, context)

    def _recover_version_detection_error(
        self, error: VersionDetectionError, context: Dict[str, Any]
    ) -> RecoveryResult:
        """Recover from version detection errors."""
        logger.debug("Recovering from version detection error")

        # Try common protocol versions
        common_versions = ["3.3", "3.1", "3.4", "3.2"]
        attempted_versions = error.attempted_versions or []

        for version in common_versions:
            if version not in attempted_versions:
                return RecoveryResult(
                    success=False,
                    message=f"Try protocol version {version}.",
                    recovered_data={"suggested_version": version},
                    retry_recommended=True,
                )

        return RecoveryResult(
            success=False,
            message="Unable to detect protocol version. Try manual configuration.",
            retry_recommended=False,
        )

    def _recover_command_error(
        self, error: CommandError, context: Dict[str, Any]
    ) -> RecoveryResult:
        """Recover from command errors."""
        logger.debug("Recovering from command error")

        # Check if it's a DPS format issue
        if "dps" in error.message.lower():
            return RecoveryResult(
                success=False,
                message="Command format error. Try adjusting DPS values.",
                retry_recommended=True,
            )

        # Check if it's a protocol version issue
        if "version" in error.message.lower():
            return RecoveryResult(
                success=False,
                message="Protocol version mismatch. Try different protocol version.",
                retry_recommended=True,
            )

        return RecoveryResult(
            success=False,
            message="Command execution failed. Check device compatibility.",
            retry_recommended=False,
        )

    def _recover_generic_protocol_error(
        self, error: ProtocolError, context: Dict[str, Any]
    ) -> RecoveryResult:
        """Recover from generic protocol errors."""
        logger.debug("Recovering from generic protocol error")

        return RecoveryResult(
            success=False,
            message="Protocol error. Try different protocol version or device reboot.",
            retry_recommended=True,
        )


class NetworkRecovery(BaseRecoveryHandler):
    """Recovery handler for network errors."""

    def __init__(self, retry_manager: Optional[RetryManager] = None):
        super().__init__(retry_manager)
        self.connectivity_cache = {}

    def can_handle(self, error: Exception) -> bool:
        """Check if this handler can handle network errors."""
        return isinstance(error, NetworkError)

    def get_priority(self) -> int:
        """Network recovery has low priority (handled by retry logic)."""
        return 60

    def recover(self, error: Exception, context: Dict[str, Any]) -> RecoveryResult:
        """Recover from network errors."""
        self.recovery_attempts += 1
        self.last_recovery_time = time.time()

        logger.info(f"Attempting network recovery (attempt {self.recovery_attempts})")

        if isinstance(error, ConnectivityError):
            return self._recover_connectivity_error(error, context)
        elif isinstance(error, DNSError):
            return self._recover_dns_error(error, context)
        elif isinstance(error, TimeoutError):
            return self._recover_timeout_error(error, context)
        else:
            return self._recover_generic_network_error(error, context)

    def _recover_connectivity_error(
        self, error: ConnectivityError, context: Dict[str, Any]
    ) -> RecoveryResult:
        """Recover from connectivity errors."""
        logger.debug("Recovering from connectivity error")

        return RecoveryResult(
            success=False,
            message="Network connectivity issue. Please check your internet connection.",
            retry_recommended=True,
        )

    def _recover_dns_error(
        self, error: DNSError, context: Dict[str, Any]
    ) -> RecoveryResult:
        """Recover from DNS errors."""
        logger.debug("Recovering from DNS error")

        return RecoveryResult(
            success=False,
            message="DNS resolution failed. Please check your DNS settings.",
            retry_recommended=True,
        )

    def _recover_timeout_error(
        self, error: TimeoutError, context: Dict[str, Any]
    ) -> RecoveryResult:
        """Recover from timeout errors."""
        logger.debug("Recovering from timeout error")

        return RecoveryResult(
            success=False,
            message="Operation timed out. Please try again or check network speed.",
            retry_recommended=True,
        )

    def _recover_generic_network_error(
        self, error: NetworkError, context: Dict[str, Any]
    ) -> RecoveryResult:
        """Recover from generic network errors."""
        logger.debug("Recovering from generic network error")

        return RecoveryResult(
            success=False,
            message="Network error occurred. Please check your connection and try again.",
            retry_recommended=True,
        )


class RecoveryCoordinator:
    """
    Coordinates all recovery handlers and provides a unified recovery interface.
    """

    def __init__(self, retry_manager: Optional[RetryManager] = None):
        self.retry_manager = retry_manager or RetryManager()
        self.handlers: List[BaseRecoveryHandler] = []
        self.recovery_stats = {
            "total_attempts": 0,
            "successful_recoveries": 0,
            "failed_recoveries": 0,
            "fallback_used": 0,
        }

        # Register default handlers
        self._register_default_handlers()

    def _register_default_handlers(self):
        """Register all default recovery handlers."""
        self.handlers = [
            AuthenticationRecovery(self.retry_manager),
            DeviceConnectionRecovery(self.retry_manager),
            DPSMappingRecovery(self.retry_manager),
            ProtocolRecovery(self.retry_manager),
            NetworkRecovery(self.retry_manager),
        ]

        # Sort handlers by priority
        self.handlers.sort(key=lambda h: h.get_priority())

    def add_handler(self, handler: BaseRecoveryHandler):
        """Add a custom recovery handler."""
        self.handlers.append(handler)
        self.handlers.sort(key=lambda h: h.get_priority())

    def recover(
        self, error: Exception, context: Optional[Dict[str, Any]] = None
    ) -> RecoveryResult:
        """
        Attempt to recover from an error using appropriate handlers.

        Args:
            error: The error to recover from
            context: Additional context for recovery

        Returns:
            RecoveryResult indicating success or failure
        """
        context = context or {}
        self.recovery_stats["total_attempts"] += 1

        logger.info(f"Attempting recovery for error: {type(error).__name__}: {error}")

        # Find appropriate handler
        handler = None
        for h in self.handlers:
            if h.can_handle(error):
                handler = h
                break

        if not handler:
            logger.warning(f"No handler found for error type: {type(error).__name__}")
            self.recovery_stats["failed_recoveries"] += 1
            return RecoveryResult(
                success=False,
                message=f"No recovery handler available for {type(error).__name__}",
                retry_recommended=False,
            )

        # Attempt recovery
        try:
            result = handler.recover(error, context)

            # Update statistics
            if result.success:
                self.recovery_stats["successful_recoveries"] += 1
            else:
                self.recovery_stats["failed_recoveries"] += 1

            if result.fallback_used:
                self.recovery_stats["fallback_used"] += 1

            logger.info(
                f"Recovery {'succeeded' if result.success else 'failed'}: {result.message}"
            )
            return result

        except Exception as recovery_error:
            logger.error(f"Recovery handler failed: {recovery_error}")
            self.recovery_stats["failed_recoveries"] += 1
            return RecoveryResult(
                success=False,
                message=f"Recovery handler failed: {recovery_error}",
                retry_recommended=False,
            )

    def get_recovery_stats(self) -> Dict[str, Any]:
        """Get recovery statistics."""
        return {
            **self.recovery_stats,
            "success_rate": (
                self.recovery_stats["successful_recoveries"]
                / max(self.recovery_stats["total_attempts"], 1)
            ),
            "handler_count": len(self.handlers),
            "handlers": [
                {
                    "name": type(handler).__name__,
                    "priority": handler.get_priority(),
                    "recovery_attempts": handler.recovery_attempts,
                    "last_recovery_time": handler.last_recovery_time,
                }
                for handler in self.handlers
            ],
        }

    def reset_stats(self):
        """Reset recovery statistics."""
        self.recovery_stats = {
            "total_attempts": 0,
            "successful_recoveries": 0,
            "failed_recoveries": 0,
            "fallback_used": 0,
        }

        # Reset handler stats
        for handler in self.handlers:
            handler.reset_recovery_state()


# Global recovery coordinator instance
default_recovery_coordinator = RecoveryCoordinator()
