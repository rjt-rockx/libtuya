"""
Device discovery and management using tuya-device-sharing-sdk.

This module provides the CloudDeviceManager class that handles device discovery,
token management, and real-time device updates using the Tuya Cloud API.
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from ..concurrency import (
    ThreadSafeCache,
    ThreadSafeMixin,
)
from .models import (
    AuthenticationError,
    AuthSession,
    DeviceDiscoveryResult,
    DeviceInfo,
)

logger = logging.getLogger(__name__)


class TokenListener:
    """
    Token update listener for handling token refresh events.

    This class implements the SharingTokenListener interface to handle
    automatic token updates and persistence.
    """

    def __init__(
        self,
        session: AuthSession,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        """
        Initialize token listener.

        Args:
            session: AuthSession to update with new token information
            callback: Optional callback function for token updates
        """
        self.session = session
        self.callback = callback
        self._last_update: Optional[datetime] = None

    def update_token(self, token_info: Dict[str, Any]):
        """
        Handle token update from the SDK.

        Args:
            token_info: Updated token information
        """
        logger.info("Token updated")
        self._last_update = datetime.now()

        # Update session with new token information
        if "access_token" in token_info:
            self.session.access_token = token_info["access_token"]
        if "refresh_token" in token_info:
            self.session.refresh_token = token_info["refresh_token"]
        if "expire_time" in token_info:
            self.session.expire_time = token_info["expire_time"]
        if "uid" in token_info:
            self.session.uid = token_info["uid"]
        if "t" in token_info:
            self.session.t = token_info["t"]

        logger.info(f"Session updated - expires in {self.session.expires_in_minutes} minutes")

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


class CloudDeviceManager(ThreadSafeMixin):
    """
    Thread-safe manager for device discovery and real-time updates using Tuya Cloud API.

    This class wraps the tuya-device-sharing-sdk Manager to provide device
    discovery, token management, and real-time device updates with full thread safety.

    Thread Safety:
    - Device cache operations are thread-safe
    - Discovery operations are atomic
    - Token refresh operations are protected
    - Multiple threads can safely discover devices concurrently
    """

    def __init__(
        self,
        session: AuthSession,
        endpoint: str = "https://apigw.iotbing.com",
        terminal_id: Optional[str] = None,
        token_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        """
        Initialize thread-safe device manager.

        Args:
            session: Authenticated session
            endpoint: API endpoint URL
            terminal_id: Unique terminal identifier
            token_callback: Optional callback for token updates
        """
        super().__init__()  # Initialize ThreadSafeMixin

        self.session = session
        self.endpoint = endpoint
        self.terminal_id = terminal_id or str(uuid.uuid4())

        # Initialize components
        self.token_listener = TokenListener(session, token_callback)
        self.device_listener: Optional[DeviceListener] = None
        self.manager = None

        # Thread-safe device cache
        self._device_cache = ThreadSafeCache[DeviceInfo](default_ttl=300.0, max_entries=1000)
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
        Discover devices with local keys (thread-safe).

        Args:
            force_refresh: Force refresh even if recently discovered

        Returns:
            DeviceDiscoveryResult with discovered devices

        Raises:
            AuthenticationError: If device discovery fails
        """
        # Check if we need to refresh (with read lock)
        if not force_refresh:
            with self._read_lock():
                if self._last_discovery:
                    time_since_last = (datetime.now() - self._last_discovery).total_seconds()
                    if time_since_last < 30:  # Don't refresh more than once per 30 seconds
                        logger.debug("Using cached device discovery results")
                        devices = []
                        for device_id in self._device_cache._cache.keys():
                            device = self._device_cache.get(device_id)
                            if device:
                                devices.append(device)
                        return DeviceDiscoveryResult(
                            devices=devices,
                            total_count=len(devices),
                            discovery_time=self._last_discovery,
                        )

        logger.info("Discovering devices...")
        errors: List[str] = []

        try:
            # Refresh token if needed before discovery
            if not self.refresh_token_if_needed():
                raise AuthenticationError(
                    "Token refresh failed - cannot discover devices",
                    "TOKEN_REFRESH_FAILED",
                )

            # Update device cache
            if self.manager is None:
                raise AuthenticationError(
                    "Device manager not initialized", "MANAGER_NOT_INITIALIZED"
                )
            self.manager.update_device_cache()

            # Convert devices to DeviceInfo objects
            devices = []
            for device_id, customer_device in self.manager.device_map.items():
                try:
                    device_info = DeviceInfo.from_customer_device(customer_device)
                    devices.append(device_info)
                    # Use thread-safe cache
                    self._device_cache.set(device_id, device_info)
                except Exception as e:
                    error_msg = f"Error processing device {device_id}: {str(e)}"
                    logger.warning(error_msg)
                    errors.append(error_msg)

            # Update discovery time with write lock
            with self._write_lock():
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
            # Log once at this level and raise structured exception
            logger.debug(f"Device discovery failed: {e}")
            raise AuthenticationError(
                f"Device discovery failed: {str(e)}",
                "DISCOVERY_ERROR",
                {"exception": str(e)},
            )

    def get_device(self, device_id: str) -> Optional[DeviceInfo]:
        """
        Get a specific device by ID (thread-safe).

        Args:
            device_id: Device identifier

        Returns:
            DeviceInfo if found, None otherwise
        """
        return self._device_cache.get(device_id)

    def get_devices_with_local_keys(self) -> List[DeviceInfo]:
        """
        Get all devices that have local keys (thread-safe).

        Returns:
            List of DeviceInfo objects with local keys
        """
        devices = []
        # Get all devices from thread-safe cache
        for device_id in list(self._device_cache._cache.keys()):
            device = self._device_cache.get(device_id)
            if device and device.has_local_key:
                devices.append(device)
        return devices

    def get_online_devices(self) -> List[DeviceInfo]:
        """
        Get all online devices.

        Returns:
            List of online DeviceInfo objects
        """
        devices = []
        for device_id in list(self._device_cache._cache.keys()):
            device = self._device_cache.get(device_id)
            if device and device.online:
                devices.append(device)
        return devices

    def get_controllable_devices(self) -> List[DeviceInfo]:
        """
        Get devices that can be controlled locally.

        Returns:
            List of DeviceInfo objects that can be controlled locally
        """
        devices = []
        for device_id in list(self._device_cache._cache.keys()):
            device = self._device_cache.get(device_id)
            if device and device.can_control_locally:
                devices.append(device)
        return devices

    def get_devices_by_category(self, category: str) -> List[DeviceInfo]:
        """
        Get devices by category.

        Args:
            category: Device category

        Returns:
            List of DeviceInfo objects in the category
        """
        devices = []
        for device_id in list(self._device_cache._cache.keys()):
            device = self._device_cache.get(device_id)
            if device and device.category == category:
                devices.append(device)
        return devices

    def get_device_status_fast(self, device_id: str) -> Optional[DeviceInfo]:
        """
        Get single device status using optimized API call.

        This is much faster than discover_devices() for getting one device.

        Args:
            device_id: Device identifier

        Returns:
            Updated DeviceInfo with latest status, or None if failed
        """
        import time

        start_time = time.time()

        try:
            # Refresh token if needed before API call
            token_start = time.time()
            if not self.refresh_token_if_needed():
                logger.error("Token refresh failed - cannot get device status")
                return None
            token_time = time.time() - token_start
            logger.debug(f"Token refresh took {token_time:.3f}s")

            logger.debug(f"Getting fast status for device {device_id}")

            if self.manager is None:
                logger.error("Device manager not initialized")
                return None

            # Use optimized single device query
            api_start = time.time()
            devices = self.manager.device_repository.query_devices_by_ids([device_id])
            api_time = time.time() - api_start
            logger.debug(f"API call took {api_time:.3f}s")

            if devices:
                conversion_start = time.time()
                device = devices[0]

                # Debug raw DPS data
                logger.debug(f"Raw device data for {device_id}:")
                logger.debug(f"  device.status: {device.status}")
                logger.debug(f"  device.function: {device.function}")
                logger.debug(f"  device.status_range: {device.status_range}")
                logger.debug(f"  device.local_strategy: {device.local_strategy}")
                logger.debug(f"  device.online: {device.online}")

                device_info = DeviceInfo.from_customer_device(device)
                conversion_time = time.time() - conversion_start
                logger.debug(f"Device conversion took {conversion_time:.3f}s")

                # Update our cache
                self._device_cache.set(device_id, device_info)

                total_time = time.time() - start_time
                logger.debug(f"Fast status completed in {total_time:.3f}s total")
                return device_info
            else:
                logger.warning(f"Device {device_id} not found in fast status query")
                return None

        except Exception as e:
            logger.error(f"Fast device status failed for {device_id}: {e}")
            return None

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
            # Refresh token if needed before sending commands
            if not self.refresh_token_if_needed():
                logger.error("Token refresh failed - cannot send commands")
                return False

            logger.info(f"Sending commands to device {device_id}: {commands}")
            if self.manager is None:
                logger.error("Device manager not initialized")
                return False
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
            if self.manager is None:
                raise AuthenticationError(
                    "Device manager not initialized", "MANAGER_NOT_INITIALIZED"
                )
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
            if self.device_listener and self.manager:
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
            # Check if token is expired
            was_expired = self.session.is_expired

            if was_expired:
                logger.info("Token is expired, attempting refresh")

            # Always try to refresh if needed - the SDK will handle the logic
            if self.manager is None:
                raise AuthenticationError(
                    "Device manager not initialized", "MANAGER_NOT_INITIALIZED"
                )
            self.manager.customer_api.refresh_access_token_if_need()

            # If the token was expired but now works, it means it was refreshed
            if was_expired and not self.session.is_expired:
                logger.info("Token successfully refreshed")

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
            "last_discovery": (self._last_discovery.isoformat() if self._last_discovery else None),
            "device_count": len(self._device_cache._cache),
            "devices_with_keys": len(self.get_devices_with_local_keys()),
            "online_devices": len(self.get_online_devices()),
        }

    def close(self):
        """Clean up resources."""
        self.stop_real_time_updates()
        self._device_cache.clear()
        logger.info("Device manager closed")
