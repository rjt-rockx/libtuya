"""
Device discovery and management using tuya-device-sharing-sdk.

This module provides the DeviceManager class that handles device discovery,
token management, and real-time device updates using the Tuya Cloud API.
"""

import time
import uuid
import logging
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime

from .models import AuthSession, DeviceInfo, DeviceDiscoveryResult, AuthenticationError

logger = logging.getLogger(__name__)


class TokenListener:
    """
    Token update listener for handling token refresh events.

    This class implements the SharingTokenListener interface to handle
    automatic token updates and persistence.
    """

    def __init__(self, callback: Optional[Callable[[Dict[str, Any]], None]] = None):
        """
        Initialize token listener.

        Args:
            callback: Optional callback function for token updates
        """
        self.callback = callback
        self._last_update = None

    def update_token(self, token_info: Dict[str, Any]):
        """
        Handle token update from the SDK.

        Args:
            token_info: Updated token information
        """
        logger.info("Token updated")
        self._last_update = datetime.now()

        if self.callback:
            try:
                self.callback(token_info)
            except Exception as e:
                logger.error(f"Error in token update callback: {e}")

    @property
    def last_update(self) -> Optional[datetime]:
        """Get the last token update time."""
        return self._last_update


class DeviceListener:
    """
    Device update listener for handling real-time device changes.

    This class implements the SharingDeviceListener interface to handle
    device additions, updates, and removals.
    """

    def __init__(
        self,
        device_callback: Optional[Callable[[DeviceInfo], None]] = None,
        add_callback: Optional[Callable[[DeviceInfo], None]] = None,
        remove_callback: Optional[Callable[[str], None]] = None,
    ):
        """
        Initialize device listener.

        Args:
            device_callback: Callback for device updates
            add_callback: Callback for device additions
            remove_callback: Callback for device removals
        """
        self.device_callback = device_callback
        self.add_callback = add_callback
        self.remove_callback = remove_callback

    def update_device(self, device):
        """Handle device update."""
        if self.device_callback:
            try:
                device_info = DeviceInfo.from_customer_device(device)
                self.device_callback(device_info)
            except Exception as e:
                logger.error(f"Error in device update callback: {e}")

    def add_device(self, device):
        """Handle device addition."""
        if self.add_callback:
            try:
                device_info = DeviceInfo.from_customer_device(device)
                self.add_callback(device_info)
            except Exception as e:
                logger.error(f"Error in device add callback: {e}")

    def remove_device(self, device_id: str):
        """Handle device removal."""
        if self.remove_callback:
            try:
                self.remove_callback(device_id)
            except Exception as e:
                logger.error(f"Error in device remove callback: {e}")


class DeviceManager:
    """
    Manages device discovery and real-time updates using Tuya Cloud API.

    This class wraps the tuya-device-sharing-sdk Manager to provide device
    discovery, token management, and real-time device updates.
    """

    def __init__(
        self,
        session: AuthSession,
        endpoint: str = "https://apigw.iotbing.com",
        terminal_id: Optional[str] = None,
        token_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        """
        Initialize device manager.

        Args:
            session: Authenticated session
            endpoint: API endpoint URL
            terminal_id: Unique terminal identifier
            token_callback: Optional callback for token updates
        """
        self.session = session
        self.endpoint = endpoint
        self.terminal_id = terminal_id or str(uuid.uuid4())

        # Initialize components
        self.token_listener = TokenListener(token_callback)
        self.device_listener = None
        self.manager = None
        self._devices: Dict[str, DeviceInfo] = {}
        self._last_discovery: Optional[datetime] = None

        # Initialize manager
        self._initialize_manager()

    def _initialize_manager(self):
        """Initialize the tuya-device-sharing-sdk Manager."""
        try:
            from tuya_sharing.manager import Manager

            # Convert session to token response format
            token_response = {
                "access_token": self.session.access_token,
                "refresh_token": self.session.refresh_token,
                "uid": self.session.uid,
                "expire_time": self.session.expire_time,
                "t": self.session.t,
            }

            # Use session's terminal_id and endpoint if available
            terminal_id = self.session.terminal_id or self.terminal_id
            endpoint = self.session.endpoint or self.endpoint
            
            self.manager = Manager(
                client_id=self.session.client_id,
                user_code=self.session.user_code,
                terminal_id=terminal_id,
                end_point=endpoint,
                token_response=token_response,
                listener=self.token_listener,
            )

            logger.info("Device manager initialized successfully")

        except ImportError:
            raise AuthenticationError(
                "tuya-device-sharing-sdk not installed. Install with: pip install tuya-device-sharing-sdk",
                "MISSING_DEPENDENCY",
            )
        except Exception as e:
            logger.error(f"Failed to initialize device manager: {e}")
            raise AuthenticationError(
                f"Failed to initialize device manager: {str(e)}",
                "MANAGER_INIT_ERROR",
                {"exception": str(e)},
            )

    def discover_devices(self, force_refresh: bool = False) -> DeviceDiscoveryResult:
        """
        Discover devices with local keys.

        Args:
            force_refresh: Force refresh even if recently discovered

        Returns:
            DeviceDiscoveryResult with discovered devices

        Raises:
            AuthenticationError: If device discovery fails
        """
        # Check if we need to refresh
        if not force_refresh and self._last_discovery:
            time_since_last = (datetime.now() - self._last_discovery).total_seconds()
            if time_since_last < 30:  # Don't refresh more than once per 30 seconds
                logger.debug("Using cached device discovery results")
                return DeviceDiscoveryResult(
                    devices=list(self._devices.values()),
                    total_count=len(self._devices),
                    discovery_time=self._last_discovery,
                )

        logger.info("Discovering devices...")
        errors = []

        try:
            # Update device cache
            self.manager.update_device_cache()

            # Convert devices to DeviceInfo objects
            devices = []
            for device_id, customer_device in self.manager.device_map.items():
                try:
                    device_info = DeviceInfo.from_customer_device(customer_device)
                    devices.append(device_info)
                    self._devices[device_id] = device_info
                except Exception as e:
                    error_msg = f"Error processing device {device_id}: {str(e)}"
                    logger.warning(error_msg)
                    errors.append(error_msg)

            self._last_discovery = datetime.now()

            result = DeviceDiscoveryResult(
                devices=devices,
                total_count=len(devices),
                discovery_time=self._last_discovery,
                errors=errors,
            )

            logger.info(
                f"Discovered {len(devices)} devices ({len(result.devices_with_local_keys)} with local keys)"
            )
            return result

        except Exception as e:
            logger.error(f"Device discovery failed: {e}")
            raise AuthenticationError(
                f"Device discovery failed: {str(e)}",
                "DISCOVERY_ERROR",
                {"exception": str(e)},
            )

    def get_device(self, device_id: str) -> Optional[DeviceInfo]:
        """
        Get a specific device by ID.

        Args:
            device_id: Device identifier

        Returns:
            DeviceInfo if found, None otherwise
        """
        return self._devices.get(device_id)

    def get_devices_with_local_keys(self) -> List[DeviceInfo]:
        """
        Get all devices that have local keys.

        Returns:
            List of DeviceInfo objects with local keys
        """
        return [device for device in self._devices.values() if device.has_local_key]

    def get_online_devices(self) -> List[DeviceInfo]:
        """
        Get all online devices.

        Returns:
            List of online DeviceInfo objects
        """
        return [device for device in self._devices.values() if device.online]

    def get_controllable_devices(self) -> List[DeviceInfo]:
        """
        Get devices that can be controlled locally.

        Returns:
            List of DeviceInfo objects that can be controlled locally
        """
        return [
            device for device in self._devices.values() if device.can_control_locally
        ]

    def get_devices_by_category(self, category: str) -> List[DeviceInfo]:
        """
        Get devices by category.

        Args:
            category: Device category

        Returns:
            List of DeviceInfo objects in the category
        """
        return [
            device for device in self._devices.values() if device.category == category
        ]

    def send_command(self, device_id: str, commands: List[Dict[str, Any]]) -> bool:
        """
        Send commands to a device via cloud API.

        Args:
            device_id: Device identifier
            commands: List of command dictionaries with 'code' and 'value'

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Sending commands to device {device_id}: {commands}")
            result = self.manager.send_commands(device_id, commands)
            logger.info(f"Commands sent successfully: {result}")
            return True
        except Exception as e:
            logger.error(f"Failed to send commands to device {device_id}: {e}")
            return False

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
        try:
            # Create device listener
            self.device_listener = DeviceListener(
                device_callback=device_callback,
                add_callback=add_callback,
                remove_callback=remove_callback,
            )

            # Add listener to manager
            self.manager.add_device_listener(self.device_listener)

            # Start message queue
            self.manager.refresh_mq()

            logger.info("Real-time device updates started")

        except Exception as e:
            logger.error(f"Failed to start real-time updates: {e}")
            raise AuthenticationError(
                f"Failed to start real-time updates: {str(e)}",
                "REALTIME_ERROR",
                {"exception": str(e)},
            )

    def stop_real_time_updates(self):
        """Stop real-time device updates."""
        try:
            if self.device_listener:
                self.manager.remove_device_listener(self.device_listener)
                self.device_listener = None
                logger.info("Real-time device updates stopped")
        except Exception as e:
            logger.error(f"Error stopping real-time updates: {e}")

    def refresh_token_if_needed(self) -> bool:
        """
        Refresh access token if needed.

        Returns:
            True if token was refreshed or is still valid, False if refresh failed
        """
        try:
            if self.session.is_expired:
                logger.info("Token is expired, attempting refresh")
                self.manager.customer_api.refresh_access_token_if_need()
                return True
            return True
        except Exception as e:
            logger.error(f"Token refresh failed: {e}")
            return False

    def get_session_info(self) -> Dict[str, Any]:
        """
        Get current session information.

        Returns:
            Dictionary with session details
        """
        return {
            "uid": self.session.uid,
            "client_id": self.session.client_id,
            "terminal_id": self.terminal_id,
            "expires_in_minutes": self.session.expires_in_minutes,
            "is_expired": self.session.is_expired,
            "last_discovery": (
                self._last_discovery.isoformat() if self._last_discovery else None
            ),
            "device_count": len(self._devices),
            "devices_with_keys": len(self.get_devices_with_local_keys()),
            "online_devices": len(self.get_online_devices()),
        }

    def close(self):
        """Clean up resources."""
        self.stop_real_time_updates()
        self._devices.clear()
        logger.info("Device manager closed")
