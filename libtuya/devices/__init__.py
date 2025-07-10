"""
libtuya Device Integration System

This package provides the Device Factory Pattern that seamlessly integrates cloud discovery
with local control using TinyTuya, device intelligence, and DPS mapping.

Main Components:
- DeviceFactory: Creates appropriate TinyTuya device instances
- IntelligentDevice: Base wrapper combining cloud + local control
- Specialized device types: IntelligentLight, IntelligentSwitch, etc.
- Device discovery and setup utilities

Usage:
    from libtuya.devices import DeviceManager
    from libtuya.auth import TuyaAuthenticator
    from libtuya.intelligence import DeviceIntelligence
    from libtuya.dps import DPSMapper

    # Initialize components
    auth = TuyaAuthenticator()
    # ... authenticate ...
    device_manager = DeviceManager(auth)

    # Discover and create devices
    devices = device_manager.discover_and_create_all()

    # Use high-level controls
    for device in devices:
        device.turn_on()
"""

import logging
import dataclasses
from typing import Dict, List, Optional, Any, Union, Type

# Import main classes
from .factory import DeviceFactory, create_device_from_info, get_supported_categories
from .intelligent_device import (
    IntelligentDevice,
    DeviceCapability,
    DeviceStatus,
    create_intelligent_device,
)
from .device_types import (
    IntelligentLight,
    IntelligentSwitch,
    IntelligentClimate,
    IntelligentCover,
    create_specialized_device,
)

# Import dependencies
from ..auth.models import DeviceInfo
from ..intelligence import DeviceIntelligence
from ..dps import DPSMapper

logger = logging.getLogger(__name__)

# Version information
__version__ = "0.2.0"
__author__ = "libtuya"
__description__ = (
    "Device Factory Pattern for libtuya - seamless Tuya device integration"
)


class DeviceManager:
    """
    Main device management interface for libtuya.

    This class provides a unified interface for discovering, creating, and managing
    intelligent Tuya devices with automatic capability detection and mapping.
    """

    def __init__(
        self,
        auth_manager=None,
        intelligence: Optional[DeviceIntelligence] = None,
        dps_mapper: Optional[DPSMapper] = None,
        device_factory: Optional[DeviceFactory] = None,
    ):
        """
        Initialize the device manager.

        Args:
            auth_manager: Authentication manager instance (optional)
            intelligence: Device intelligence instance (creates default if None)
            dps_mapper: DPS mapper instance (creates default if None)
            device_factory: Device factory instance (creates default if None)
        """
        self.auth_manager = auth_manager
        self.intelligence = intelligence or DeviceIntelligence()
        self.dps_mapper = dps_mapper or DPSMapper()
        self.device_factory = device_factory or DeviceFactory()

        # Active devices registry
        self.active_devices: Dict[str, IntelligentDevice] = {}

        logger.info("DeviceManager initialized")

    def discover_devices(self) -> List[DeviceInfo]:
        """
        Discover available devices using the auth manager.

        Returns:
            List of discovered devices

        Raises:
            RuntimeError: If no auth manager is configured
        """
        if not self.auth_manager:
            raise RuntimeError("Auth manager not configured")

        try:
            # Assuming get_devices_with_keys() returns the list of DeviceInfo
            devices = self.auth_manager.get_devices_with_keys()
            logger.info(f"Discovered {len(devices)} devices")
            return devices
        except Exception as e:
            logger.error(f"Device discovery failed: {e}")
            raise

    def create_devices(
        self, device_info: DeviceInfo, use_specialized_type: bool = True, **kwargs
    ) -> List[IntelligentDevice]:
        """
        Create one or more intelligent devices from a single device information object.
        Handles multi-entity devices by creating a device instance for each entity.

        Args:
            device_info: Device information from discovery
            use_specialized_type: Create specialized device type (Light, Switch, etc.)
            **kwargs: Additional arguments for device creation

        Returns:
            A list of IntelligentDevice instances
        """
        try:
            # Validate device info
            validation = self.device_factory.validate_device_info(device_info)
            if not validation["valid"]:
                logger.warning(
                    f"Device validation failed for {device_info.id}: {validation['errors']}"
                )

            # Check for multi-entity devices
            is_multi = self.intelligence.quirks_manager.is_multi_entity_device(
                device_info.category
            )

            if not is_multi:
                # Standard single-entity device
                device = create_specialized_device(
                    device_info=device_info,
                    intelligence=self.intelligence,
                    dps_mapper=self.dps_mapper,
                    auth_manager=self.auth_manager,
                    device_factory=self.device_factory,
                )
                self.active_devices[device.id] = device
                logger.debug(f"Created device: {device.name} ({device.category})")
                return [device]

            # --- Multi-entity device handling ---
            created_devices = []
            entity_mappings = (
                self.intelligence.quirks_manager.get_multi_entity_mappings(
                    device_info.category
                )
            )

            logger.info(
                f"Device {device_info.id} is multi-entity. Creating {len(entity_mappings)} sub-devices."
            )

            # Create one shared TinyTuya device instance
            shared_tinytuya_device = self.device_factory.create_device(
                device_info,
                persist_connection=True,  # Persistent connection is required for multi-entity
            )

            for i, entity_map in enumerate(entity_mappings):
                # Create a unique ID and name for the sub-device
                entity_id = f"{device_info.id}_{entity_map.key}"
                entity_name = (
                    f"{device_info.name} - {entity_map.key.replace('_', ' ').title()}"
                )

                # Create a copy of the device info for the entity
                entity_device_info = dataclasses.replace(
                    device_info, id=entity_id, name=entity_name
                )

                # Determine the capabilities for this specific entity
                entity_capabilities = [entity_map.key]
                if entity_map.brightness_dpcode:
                    entity_capabilities.append(entity_map.brightness_dpcode)
                if entity_map.additional_dpcodes:
                    entity_capabilities.extend(entity_map.additional_dpcodes)

                # Create the specialized or intelligent device instance
                device = create_specialized_device(
                    device_info=entity_device_info,
                    intelligence=self.intelligence,
                    dps_mapper=self.dps_mapper,
                    auth_manager=self.auth_manager,
                    device_factory=self.device_factory,
                    tinytuya_device_instance=shared_tinytuya_device,
                    entity_capabilities=entity_capabilities,
                )

                self.active_devices[device.id] = device
                created_devices.append(device)
                logger.debug(f"Created sub-device: {device.name} ({device.category})")

            return created_devices

        except Exception as e:
            logger.error(f"Device creation failed for {device_info.id}: {e}")
            raise

    def get_device(self, device_id: str) -> Optional[IntelligentDevice]:
        """
        Get an active device by ID.

        Args:
            device_id: Device ID

        Returns:
            IntelligentDevice instance or None
        """
        return self.active_devices.get(device_id)

    def get_devices_by_category(self, category: str) -> List[IntelligentDevice]:
        """
        Get all active devices of a specific category.

        Args:
            category: Device category

        Returns:
            List of matching devices
        """
        return [
            device
            for device in self.active_devices.values()
            if device.device_info.category == category
        ]

    def get_devices_by_type(
        self, device_type: Type[IntelligentDevice]
    ) -> List[IntelligentDevice]:
        """
        Get all active devices of a specific type.

        Args:
            device_type: Device type class

        Returns:
            List of matching devices
        """
        return [
            device
            for device in self.active_devices.values()
            if isinstance(device, device_type)
        ]

    def get_lights(self) -> List[IntelligentLight]:
        """Get all light devices."""
        return self.get_devices_by_type(IntelligentLight)

    def get_switches(self) -> List[IntelligentSwitch]:
        """Get all switch devices."""
        return self.get_devices_by_type(IntelligentSwitch)

    def get_climate_devices(self) -> List[IntelligentClimate]:
        """Get all climate devices."""
        return self.get_devices_by_type(IntelligentClimate)

    def get_covers(self) -> List[IntelligentCover]:
        """Get all cover devices."""
        return self.get_devices_by_type(IntelligentCover)

    def close_device(self, device_id: str):
        """
        Close and remove a device.

        Args:
            device_id: Device ID to close
        """
        device = self.active_devices.get(device_id)
        if device:
            device.close()
            del self.active_devices[device_id]
            logger.info(f"Closed device {device_id}")

    def close_all_devices(self):
        """Close all active devices."""
        for device_id in list(self.active_devices.keys()):
            self.close_device(device_id)
        logger.info("All devices closed")

    def get_device_stats(self) -> Dict[str, Any]:
        """Get statistics about active devices."""
        stats = {
            "total_devices": len(self.active_devices),
            "devices_by_category": {},
            "devices_by_type": {},
            "online_devices": 0,
            "offline_devices": 0,
        }

        for device in self.active_devices.values():
            category = device.device_info.category
            stats["devices_by_category"][category] = (
                stats["devices_by_category"].get(category, 0) + 1
            )

            device_type = type(device).__name__
            stats["devices_by_type"][device_type] = (
                stats["devices_by_type"].get(device_type, 0) + 1
            )

            if device.is_online:
                stats["online_devices"] += 1
            else:
                stats["offline_devices"] += 1

        return stats

    def discover_and_create_all(
        self, use_specialized_types: bool = True
    ) -> List[IntelligentDevice]:
        """
        Discover all devices and create intelligent device instances.

        Args:
            use_specialized_types: Create specialized device types

        Returns:
            List of all created IntelligentDevice instances (including sub-devices)
        """
        devices_info = self.discover_devices()
        all_created_devices = []

        for device_info in devices_info:
            try:
                created = self.create_devices(device_info, use_specialized_types)
                all_created_devices.extend(created)
            except Exception as e:
                logger.error(f"Failed to create device(s) for {device_info.id}: {e}")

        logger.info(
            f"Created {len(all_created_devices)} device instances from {len(devices_info)} physical devices"
        )
        return all_created_devices

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close_all_devices()


__all__ = [
    "DeviceManager",
    "IntelligentDevice",
    "DeviceFactory",
    "DeviceCapability",
    "DeviceStatus",
    "IntelligentLight",
    "IntelligentSwitch",
    "IntelligentClimate",
    "IntelligentCover",
    "create_intelligent_device",
    "create_specialized_device",
    "create_device_from_info",
    "get_supported_categories",
    "DeviceInfo",
]

logging.getLogger(__name__).addHandler(logging.NullHandler())
logger.info(f"libtuya.devices module loaded (version {__version__})")
