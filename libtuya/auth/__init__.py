"""
Tuya Authentication System for libtuya.

This package provides a complete authentication system for the Tuya Cloud API
using QR code authentication and automatic device discovery with local keys.

Key Components:
- TuyaAuthenticator: Main authentication interface
- QRAuthenticator: QR code authentication flow
- DeviceManager: Device discovery and management
- AuthSession: Token management
- DeviceInfo: Device information wrapper

Example Usage:
    from libtuya.auth import TuyaAuthenticator

    authenticator = TuyaAuthenticator()

    # QR code authentication
    qr_code = authenticator.start_qr_auth("user_code_123")
    print(f"Scan this QR code with Smart Life app: {qr_code}")

    # Wait for authentication
    session = authenticator.wait_for_auth(timeout=60)

    # Get devices with local keys
    devices = authenticator.get_devices_with_keys()
    for device in devices:
        print(f"Device: {device.name}, Local Key: {device.local_key}")
"""

import logging
import uuid
from typing import List, Optional, Dict, Any, Callable
from datetime import datetime

from .models import (
    AuthSession,
    DeviceInfo,
    QRCodeData,
    DeviceDiscoveryResult,
    AuthenticationError,
)
from .qr_auth import QRAuthenticator
from .manager import DeviceManager

logger = logging.getLogger(__name__)


class TuyaAuthenticator:
    """
    Main authentication interface for Tuya Cloud API.

    This class provides a unified interface for QR code authentication,
    device discovery, and session management. It combines the QRAuthenticator
    and DeviceManager to provide a complete authentication solution.
    """

    def __init__(
        self,
        endpoint: str = "https://apigw.iotbing.com",
        token_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        """
        Initialize Tuya authenticator.

        Args:
            endpoint: API endpoint URL
            token_callback: Optional callback for token updates
        """
        self.endpoint = endpoint
        self.token_callback = token_callback

        # Initialize components
        self.qr_authenticator = QRAuthenticator(endpoint)
        self.device_manager: Optional[DeviceManager] = None
        self._current_session: Optional[AuthSession] = None
        self._last_qr_data: Optional[QRCodeData] = None
        self._last_user_code: Optional[str] = None

        logger.info("TuyaAuthenticator initialized")

    def start_qr_auth(self, user_code: Optional[str] = None) -> str:
        """
        Start QR code authentication flow.

        Args:
            user_code: Optional user code. If None, generates unique code.

        Returns:
            QR code string for display

        Raises:
            AuthenticationError: If QR code generation fails
        """
        logger.info("Starting QR code authentication")

        # Generate user code if not provided
        if user_code is None:
            user_code = str(uuid.uuid4())
        
        # Store user code for later use
        self._last_user_code = user_code

        # Generate QR code
        qr_data = self.qr_authenticator.generate_qr_code(user_code)
        self._last_qr_data = qr_data

        # Return formatted QR code for display
        return self.qr_authenticator.format_qr_for_display(qr_data)

    def wait_for_auth(self, timeout: int = 300, poll_interval: int = 2) -> AuthSession:
        """
        Wait for user to complete authentication.

        Args:
            timeout: Maximum time to wait in seconds
            poll_interval: Time between polling attempts in seconds

        Returns:
            AuthSession with authentication tokens

        Raises:
            AuthenticationError: If authentication fails or times out
        """
        if not self._last_qr_data:
            raise AuthenticationError(
                "No QR code generated. Call start_qr_auth() first.", "NO_QR_CODE"
            )

        # Use stored user code
        user_code = self._last_user_code or str(uuid.uuid4())

        # Wait for authentication
        session = self.qr_authenticator.wait_for_authentication(
            self._last_qr_data, user_code, timeout, poll_interval
        )

        # Store session and initialize device manager
        self._current_session = session
        self._initialize_device_manager()

        return session

    def authenticate_with_qr(
        self,
        user_code: Optional[str] = None,
        timeout: int = 300,
        poll_interval: int = 2,
    ) -> AuthSession:
        """
        Complete QR code authentication flow in one call.

        Args:
            user_code: Optional user code. If None, generates unique code.
            timeout: Maximum time to wait for authentication
            poll_interval: Time between polling attempts

        Returns:
            AuthSession with authentication tokens

        Raises:
            AuthenticationError: If authentication fails
        """
        logger.info("Starting complete QR code authentication flow")

        # Generate user code if not provided
        if user_code is None:
            user_code = str(uuid.uuid4())

        # Complete authentication flow
        qr_data, session = self.qr_authenticator.authenticate_with_qr(
            user_code, timeout, poll_interval
        )

        # Store session and QR data
        self._current_session = session
        self._last_qr_data = qr_data

        # Initialize device manager
        self._initialize_device_manager()

        logger.info("QR code authentication completed successfully")
        return session

    def _initialize_device_manager(self):
        """Initialize device manager with current session."""
        if self._current_session:
            self.device_manager = DeviceManager(
                session=self._current_session,
                endpoint=self.endpoint,
                token_callback=self.token_callback,
            )
            logger.info("Device manager initialized")

    def get_devices_with_keys(self, force_refresh: bool = False) -> List[DeviceInfo]:
        """
        Get all devices that have local keys.

        Args:
            force_refresh: Force refresh device cache

        Returns:
            List of DeviceInfo objects with local keys

        Raises:
            AuthenticationError: If not authenticated or discovery fails
        """
        if not self.device_manager:
            raise AuthenticationError(
                "Not authenticated. Call authenticate_with_qr() first.",
                "NOT_AUTHENTICATED",
            )

        # Discover devices
        result = self.device_manager.discover_devices(force_refresh)

        # Return devices with local keys
        return result.devices_with_local_keys

    def get_all_devices(self, force_refresh: bool = False) -> DeviceDiscoveryResult:
        """
        Get all discovered devices.

        Args:
            force_refresh: Force refresh device cache

        Returns:
            DeviceDiscoveryResult with all discovered devices

        Raises:
            AuthenticationError: If not authenticated or discovery fails
        """
        if not self.device_manager:
            raise AuthenticationError(
                "Not authenticated. Call authenticate_with_qr() first.",
                "NOT_AUTHENTICATED",
            )

        return self.device_manager.discover_devices(force_refresh)

    def get_device(self, device_id: str) -> Optional[DeviceInfo]:
        """
        Get a specific device by ID.

        Args:
            device_id: Device identifier

        Returns:
            DeviceInfo if found, None otherwise
        """
        if not self.device_manager:
            return None

        return self.device_manager.get_device(device_id)

    def get_online_devices(self) -> List[DeviceInfo]:
        """
        Get all online devices.

        Returns:
            List of online DeviceInfo objects
        """
        if not self.device_manager:
            return []

        return self.device_manager.get_online_devices()

    def get_controllable_devices(self) -> List[DeviceInfo]:
        """
        Get devices that can be controlled locally.

        Returns:
            List of DeviceInfo objects that can be controlled locally
        """
        if not self.device_manager:
            return []

        return self.device_manager.get_controllable_devices()

    def get_devices_by_category(self, category: str) -> List[DeviceInfo]:
        """
        Get devices by category.

        Args:
            category: Device category

        Returns:
            List of DeviceInfo objects in the category
        """
        if not self.device_manager:
            return []

        return self.device_manager.get_devices_by_category(category)

    def send_command(self, device_id: str, commands: List[Dict[str, Any]]) -> bool:
        """
        Send commands to a device via cloud API.

        Args:
            device_id: Device identifier
            commands: List of command dictionaries with 'code' and 'value'

        Returns:
            True if successful, False otherwise
        """
        if not self.device_manager:
            return False

        return self.device_manager.send_command(device_id, commands)

    def start_real_time_updates(
        self,
        device_callback: Optional[Callable[[DeviceInfo], None]] = None,
        add_callback: Optional[Callable[[DeviceInfo], None]] = None,
        remove_callback: Optional[Callable[[str], None]] = None,
    ):
        """
        Start real-time device updates.

        Args:
            device_callback: Callback for device updates
            add_callback: Callback for device additions
            remove_callback: Callback for device removals
        """
        if self.device_manager:
            self.device_manager.start_real_time_updates(
                device_callback, add_callback, remove_callback
            )

    def stop_real_time_updates(self):
        """Stop real-time device updates."""
        if self.device_manager:
            self.device_manager.stop_real_time_updates()

    def get_session(self) -> Optional[AuthSession]:
        """Get current authentication session."""
        return self._current_session

    def get_session_info(self) -> Dict[str, Any]:
        """
        Get current session information.

        Returns:
            Dictionary with session details
        """
        if not self._current_session:
            return {"authenticated": False}

        info = {"authenticated": True}

        if self.device_manager:
            info.update(self.device_manager.get_session_info())
        else:
            info.update(
                {
                    "uid": self._current_session.uid,
                    "client_id": self._current_session.client_id,
                    "expires_in_minutes": self._current_session.expires_in_minutes,
                    "is_expired": self._current_session.is_expired,
                }
            )

        return info

    def is_authenticated(self) -> bool:
        """Check if currently authenticated."""
        return (
            self._current_session is not None and not self._current_session.is_expired
        )

    def restore_session(self, session: AuthSession) -> bool:
        """
        Restore authentication session.

        Args:
            session: Previously saved AuthSession

        Returns:
            True if session restored successfully
        """
        try:
            if session.is_expired:
                logger.warning("Attempting to restore expired session")
                return False

            self._current_session = session
            self._initialize_device_manager()

            # Test session by discovering devices
            result = self.device_manager.discover_devices()

            logger.info(
                f"Session restored successfully with {len(result.devices)} devices"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to restore session: {e}")
            self._current_session = None
            self.device_manager = None
            return False

    def close(self):
        """Clean up resources."""
        self.stop_real_time_updates()
        if self.device_manager:
            self.device_manager.close()
        self._current_session = None
        self.device_manager = None
        logger.info("TuyaAuthenticator closed")


# Export main classes and functions
__all__ = [
    "TuyaAuthenticator",
    "QRAuthenticator",
    "DeviceManager",
    "AuthSession",
    "DeviceInfo",
    "QRCodeData",
    "DeviceDiscoveryResult",
    "AuthenticationError",
]
