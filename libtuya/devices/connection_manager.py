"""
ConnectionManager - Handles local/cloud connection management and testing.

This module provides the ConnectionManager class that manages device connections,
tests connectivity, and determines the optimal control method (local vs cloud).
"""

import ipaddress
import logging
import time
from typing import Any, Dict, Optional, Tuple

from libtuya.auth.models import DeviceInfo
from libtuya.recovery.retry_strategies import (
    BackoffStrategy,
    RetryConfig,
    default_retry_manager,
)

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages device connections and determines optimal control methods.

    This class handles:
    - Testing TinyTuya connections with caching
    - Determining local vs cloud control viability
    - Connection method selection with smart caching
    - Connection test result management
    """

    def __init__(self, device_info: DeviceInfo, tinytuya_device=None):
        """
        Initialize connection manager.

        Args:
            device_info: Device information from cloud discovery
            tinytuya_device: Optional TinyTuya device instance
        """
        self.device_info = device_info
        self.tinytuya_device = tinytuya_device

        # Connection testing cache
        self._connection_test_cache: Dict[str, Tuple[bool, float]] = {}
        self._connection_test_cache_timeout = 60.0  # Cache connection test results for 60 seconds

        # Control method selection cache
        self._control_method_cache: Optional[Tuple[str, float]] = None
        self._control_method_cache_timeout = 30.0  # Cache control method for 30 seconds

        # Error tracking
        self.connection_errors = 0
        self.last_error: Optional[str] = None

    def set_tinytuya_device(self, tinytuya_device):
        """
        Set or update the TinyTuya device instance.

        Args:
            tinytuya_device: TinyTuya device instance
        """
        self.tinytuya_device = tinytuya_device
        # Clear caches when device changes
        self.clear_caches()

    def _is_local_ip(self, ip_address: str) -> bool:
        """
        Check if an IP address is local/private.

        Args:
            ip_address: IP address to check

        Returns:
            True if the IP is local/private, False otherwise
        """
        try:
            ip = ipaddress.ip_address(ip_address)
            return ip.is_private
        except ValueError:
            logger.warning(f"Invalid IP address format: {ip_address}")
            return False

    def test_tinytuya_connection(self, use_cache: bool = True) -> bool:
        """
        Test the TinyTuya connection to the device with caching and robust error handling.

        This method attempts a quick status check with retry logic and caches the results
        to avoid repeated overhead. Connection tests are cached for 60 seconds.

        Args:
            use_cache: Whether to use cached connection test results (default: True)

        Returns:
            True if the connection is successful, False otherwise.
        """
        if not self.tinytuya_device:
            logger.debug(f"TinyTuya device not initialized for {self.device_info.id}")
            return False

        # Check cache first if enabled
        if use_cache:
            cache_key = f"connection_test_{self.device_info.id}"
            cached_result = self._connection_test_cache.get(cache_key)
            if cached_result:
                result, timestamp = cached_result
                if time.time() - timestamp < self._connection_test_cache_timeout:
                    logger.debug(
                        f"Using cached connection test result for {self.device_info.id}: {result}"
                    )
                    return result
                else:
                    # Cache expired, remove it
                    del self._connection_test_cache[cache_key]

        connection_successful = False

        try:
            # Create a fast connection test config
            connection_test_config = RetryConfig(
                max_attempts=2,  # Only 2 attempts for quick testing
                base_delay=0.5,  # Start with 0.5 second delay
                max_delay=2.0,  # Maximum 2 seconds delay
                backoff_strategy=BackoffStrategy.EXPONENTIAL,
                timeout=5.0,  # 5 second timeout per attempt
                retryable_exceptions=None,  # Use default retryable exceptions
            )

            logger.debug(f"Testing TinyTuya connection for {self.device_info.id}")

            if self.tinytuya_device is None:
                logger.error("TinyTuya device not initialized")
                return False

            status = default_retry_manager.retry_sync(
                func=lambda: self.tinytuya_device.status(),
                config=connection_test_config,
                operation_name=f"tinytuya_connection_test_{self.device_info.id}",
            )

            # A successful status call usually returns a dict with 'dps' key
            if status and isinstance(status, dict) and "dps" in status:
                logger.debug(f"TinyTuya connection successful for {self.device_info.id}")
                connection_successful = True

                # Reset connection error counter on successful connection
                self.connection_errors = 0

            else:
                logger.warning(
                    f"TinyTuya status check returned unexpected data for {self.device_info.id}: {status}"
                )
                self.connection_errors += 1

        except Exception as e:
            logger.warning(f"TinyTuya connection test failed for {self.device_info.id}: {e}")
            self.connection_errors += 1
            self.last_error = str(e)

        # Cache the result if caching is enabled
        if use_cache:
            cache_key = f"connection_test_{self.device_info.id}"
            self._connection_test_cache[cache_key] = (
                connection_successful,
                time.time(),
            )

            # Clean up old cache entries (simple cleanup)
            current_time = time.time()
            expired_keys = [
                key
                for key, (_, timestamp) in self._connection_test_cache.items()
                if current_time - timestamp > self._connection_test_cache_timeout
            ]
            for key in expired_keys:
                del self._connection_test_cache[key]

        return connection_successful

    def can_use_local_control(self, use_cache: bool = True) -> bool:
        """
        Check if local control is viable for this device with comprehensive validation.

        This method performs multiple checks to determine if local control is possible:
        1. Device must have a local key
        2. Device must be reported as online
        3. Device must have a local IP address
        4. TinyTuya connection must be working

        Args:
            use_cache: Whether to use cached connection test results (default: True)

        Returns:
            True if local control is viable, False otherwise.
        """
        # Check if device has a local key
        if not self.device_info.has_local_key:
            logger.debug(f"Local control not viable for {self.device_info.id}: Missing local key")
            return False

        # Check if the device's local key is valid (not empty)
        if not self.device_info.local_key or len(self.device_info.local_key.strip()) == 0:
            logger.debug(f"Local control not viable for {self.device_info.id}: Empty local key")
            return False

        # Check if device is reported as online by the cloud
        if not self.device_info.online:
            logger.debug(f"Local control not viable for {self.device_info.id}: Device is offline")
            return False

        # Check if the device has an IP address
        if not self.device_info.ip:
            logger.debug(
                f"Local control not viable for {self.device_info.id}: No IP address available"
            )
            return False

        # Check if the device's IP address is local/private
        if not self._is_local_ip(self.device_info.ip):
            logger.debug(
                f"Local control not viable for {self.device_info.id}: Non-local IP ({self.device_info.ip})"
            )
            return False

        # Check if TinyTuya device is initialized
        if not self.tinytuya_device:
            logger.debug(
                f"Local control not viable for {self.device_info.id}: TinyTuya device not initialized"
            )
            return False

        # Test TinyTuya connection
        if not self.test_tinytuya_connection(use_cache=use_cache):
            logger.debug(
                f"Local control not viable for {self.device_info.id}: TinyTuya connection failed"
            )
            return False

        logger.debug(f"Local control is viable for {self.device_info.id}")
        return True

    def determine_control_method(self, use_cache: bool = True, force_refresh: bool = False) -> str:
        """
        Determine the optimal control method for this device with smart caching.

        This method uses intelligent caching to avoid repeated expensive checks while
        still ensuring accuracy. Method selection is cached for 30 seconds.

        Args:
            use_cache: Whether to use cached method selection (default: True)
            force_refresh: Force refresh of method selection ignoring cache (default: False)

        Returns:
            "local" if local control is viable, "cloud" otherwise.
        """
        # Check cache first if enabled and not forcing refresh
        if use_cache and not force_refresh and self._control_method_cache:
            method, timestamp = self._control_method_cache
            if time.time() - timestamp < self._control_method_cache_timeout:
                logger.debug(f"Using cached control method for {self.device_info.id}: {method}")
                return method
            else:
                # Cache expired
                self._control_method_cache = None

        # Determine the control method
        method = "cloud"  # Default to cloud control

        try:
            if self.can_use_local_control(use_cache=use_cache):
                method = "local"
                logger.debug(f"Determined 'local' control for {self.device_info.id}")
            else:
                logger.debug(f"Determined 'cloud' control for {self.device_info.id}")
        except Exception as e:
            logger.warning(
                f"Error determining control method for {self.device_info.id}: {e}. Defaulting to cloud control."
            )
            method = "cloud"
            self.last_error = str(e)

        # Cache the result if caching is enabled
        if use_cache:
            self._control_method_cache = (method, time.time())

        return method

    def clear_caches(self):
        """
        Clear all connection-related caches.

        This method clears both the connection test cache and control method cache,
        forcing fresh evaluation on next access.
        """
        logger.debug(f"Clearing connection caches for {self.device_info.id}")
        self._connection_test_cache.clear()
        self._control_method_cache = None

    def get_connection_info(self) -> Dict[str, Any]:
        """
        Get comprehensive connection information and diagnostics.

        Returns:
            Dictionary with connection status, method selection, and diagnostics
        """
        return {
            "device_id": self.device_info.id,
            "device_name": self.device_info.name,
            "has_local_key": self.device_info.has_local_key,
            "local_key_valid": bool(
                self.device_info.local_key and self.device_info.local_key.strip()
            ),
            "device_online": self.device_info.online,
            "device_ip": self.device_info.ip,
            "ip_is_local": (
                self._is_local_ip(self.device_info.ip) if self.device_info.ip else False
            ),
            "tinytuya_initialized": self.tinytuya_device is not None,
            "can_use_local": self.can_use_local_control(),
            "preferred_method": self.determine_control_method(),
            "connection_errors": self.connection_errors,
            "last_error": self.last_error,
            "cache_entries": len(self._connection_test_cache),
            "cached_method": (
                self._control_method_cache[0] if self._control_method_cache else None
            ),
        }
