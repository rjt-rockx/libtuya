"""
DeviceStatusCache - Handles device status retrieval and caching.

This module provides the DeviceStatusCache class that manages device status
retrieval with multiple fallback strategies and intelligent caching.
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from libtuya.auth.models import DeviceInfo

from .models import DeviceCapability, DeviceStatus

logger = logging.getLogger(__name__)


class DeviceStatusCache:
    """
    Manages device status retrieval and caching with fallback strategies.

    This class handles:
    - Status caching with configurable timeouts
    - Multiple fallback strategies (hybrid, cloud-only, local-only)
    - Error tracking and recovery
    - Cache invalidation and management
    """

    def __init__(self, device_info: DeviceInfo, cache_timeout_seconds: int = 30):
        """
        Initialize status cache manager.

        Args:
            device_info: Device information from cloud discovery
            cache_timeout_seconds: How long to cache status data
        """
        self.device_info = device_info
        self.cache_timeout = timedelta(seconds=cache_timeout_seconds)

        # Status tracking
        self.last_status_update: Optional[datetime] = None
        self.cached_status: Optional[DeviceStatus] = None

        # Status retrieval strategies (set by orchestrator)
        self._hybrid_strategy: Optional[Callable[[], DeviceStatus]] = None
        self._cloud_strategy: Optional[Callable[[], DeviceStatus]] = None
        self._local_strategy: Optional[Callable[[], DeviceStatus]] = None

    def set_status_strategies(
        self,
        hybrid_strategy: Callable[[], DeviceStatus],
        cloud_strategy: Callable[[], DeviceStatus],
        local_strategy: Callable[[], DeviceStatus],
    ):
        """
        Set the status retrieval strategy functions.

        Args:
            hybrid_strategy: Function to get hybrid status (local + cloud)
            cloud_strategy: Function to get cloud-only status
            local_strategy: Function to get local-only status
        """
        self._hybrid_strategy = hybrid_strategy
        self._cloud_strategy = cloud_strategy
        self._local_strategy = local_strategy

    def get_status(self, force_refresh: bool = False) -> DeviceStatus:
        """
        Get device status with caching.

        Args:
            force_refresh: Force refresh ignoring cache

        Returns:
            DeviceStatus object with current device state
        """
        # Check cache first unless forcing refresh
        if not force_refresh and self._is_cache_valid():
            logger.debug(f"Returning cached status for {self.device_info.id}")
            if self.cached_status is not None:
                return self.cached_status

        # Get fresh status with fallback strategies
        status = self.get_status_with_fallback_strategies()

        # Update cache
        self.cached_status = status
        self.last_status_update = datetime.now()

        return status

    def get_status_with_fallback_strategies(self, max_attempts: int = 3) -> DeviceStatus:
        """
        Get device status with comprehensive fallback strategies for different failure scenarios.

        This method implements multiple fallback strategies:
        1. Standard hybrid status retrieval
        2. Cloud-only status retrieval
        3. Local-only status retrieval
        4. Cached status with error reporting

        Args:
            max_attempts: Maximum number of attempts with different strategies

        Returns:
            DeviceStatus object with current state
        """
        logger.debug(
            f"Getting status with fallback strategies for {self.device_info.id} (max_attempts: {max_attempts})"
        )

        strategies = [
            ("hybrid", self._hybrid_strategy),
            ("cloud_only", self._cloud_strategy),
            ("local_only", self._local_strategy),
        ]

        # Filter out None strategies
        strategies = [(name, func) for name, func in strategies if func is not None]

        last_error = None
        for attempt in range(max_attempts):
            for strategy_name, strategy_func in strategies:
                try:
                    logger.debug(
                        f"Attempting {strategy_name} status retrieval for {self.device_info.id} (attempt {attempt + 1})"
                    )
                    status = strategy_func()

                    if status and (status.online or status.capabilities):
                        logger.info(
                            f"Status retrieved successfully using {strategy_name} for {self.device_info.id}"
                        )
                        return status
                    else:
                        logger.warning(
                            f"{strategy_name} returned empty status for {self.device_info.id}"
                        )

                except Exception as e:
                    logger.warning(
                        f"{strategy_name} status retrieval failed for {self.device_info.id}: {e}"
                    )
                    last_error = e
                    continue

            # Brief delay between attempts
            if attempt < max_attempts - 1:
                time.sleep(1)

        # All strategies failed - return cached status if available
        if self.cached_status:
            logger.warning(
                f"All status retrieval strategies failed for {self.device_info.id}, returning cached status"
            )
            self.cached_status.errors.append(f"All retrieval strategies failed: {last_error}")
            return self.cached_status

        # Final fallback - return error status
        logger.error(f"All status retrieval strategies failed for {self.device_info.id}")
        return DeviceStatus(
            online=False,
            last_update=datetime.now(),
            capabilities={},
            raw_dps={},
            errors=[f"All status retrieval strategies failed: {last_error}"],
        )

    def _is_cache_valid(self) -> bool:
        """
        Check if the current cached status is still valid.

        Returns:
            True if cache is valid, False otherwise
        """
        if not self.cached_status or not self.last_status_update:
            return False

        time_since_update = datetime.now() - self.last_status_update
        return time_since_update < self.cache_timeout

    def clear_cache(self):
        """
        Clear the status cache to force fresh status retrieval.

        This method clears cached status data, forcing the next get_status()
        call to retrieve fresh data from the device or cloud.
        """
        logger.debug(f"Clearing status cache for {self.device_info.id}")
        self.cached_status = None
        self.last_status_update = None

    def get_cache_info(self) -> Dict[str, Any]:
        """
        Get information about the current cache state.

        Returns:
            Dictionary with cache status and timing information
        """
        cache_age_seconds = None
        if self.last_status_update:
            cache_age_seconds = (datetime.now() - self.last_status_update).total_seconds()

        return {
            "device_id": self.device_info.id,
            "has_cached_status": self.cached_status is not None,
            "cache_valid": self._is_cache_valid(),
            "last_update": (
                self.last_status_update.isoformat() if self.last_status_update else None
            ),
            "cache_age_seconds": cache_age_seconds,
            "cache_timeout_seconds": self.cache_timeout.total_seconds(),
            "cached_online": (self.cached_status.online if self.cached_status else None),
            "cached_capabilities_count": (
                len(self.cached_status.capabilities) if self.cached_status else 0
            ),
            "cached_errors_count": (len(self.cached_status.errors) if self.cached_status else 0),
        }

    def update_cache_timeout(self, timeout_seconds: int):
        """
        Update the cache timeout duration.

        Args:
            timeout_seconds: New cache timeout in seconds
        """
        self.cache_timeout = timedelta(seconds=timeout_seconds)
        logger.debug(
            f"Updated cache timeout to {timeout_seconds} seconds for {self.device_info.id}"
        )

    def force_cache_update(self, status: DeviceStatus):
        """
        Force update the cache with a specific status.

        Args:
            status: DeviceStatus to cache
        """
        self.cached_status = status
        self.last_status_update = datetime.now()
        logger.debug(f"Force updated cache for {self.device_info.id}")
