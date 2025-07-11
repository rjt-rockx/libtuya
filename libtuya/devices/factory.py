"""
Device Factory Pattern for libtuya.

This module provides the DeviceFactory class that creates appropriate TinyTuya device
instances based on device category and capabilities, handling all 60+ device categories
from Home Assistant's Tuya integration.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Type, Union

# Import TinyTuya device classes
try:
    import tinytuya
    from tinytuya import BulbDevice, CoverDevice, Device, OutletDevice

    TINYTUYA_AVAILABLE = True
except ImportError:
    # Mock classes for testing without TinyTuya
    class Device:
        def __init__(self, *args, **kwargs):
            pass

    class BulbDevice(Device):
        pass

    class OutletDevice(Device):
        pass

    class CoverDevice(Device):
        pass

    TINYTUYA_AVAILABLE = False
    logging.warning("TinyTuya not available, using mock classes")

# Import libtuya components
from ..auth.models import DeviceInfo
from ..intelligence.quirks import quirks_manager

logger = logging.getLogger(__name__)


@dataclass
class DeviceClassMapping:
    """Mapping configuration for device categories to TinyTuya classes."""

    tinytuya_class: Type[Device]
    capabilities: list
    typical_dps: dict
    description: str


class DeviceFactory:
    """
    Factory class for creating TinyTuya device instances based on Tuya device categories.

    This factory maps Home Assistant's device categories to appropriate TinyTuya device
    classes and handles initialization with auto-discovered local keys.
    """

    # Device category to TinyTuya class mappings
    DEVICE_MAPPINGS: Dict[str, DeviceClassMapping] = {
        # Light categories -> BulbDevice
        "dj": DeviceClassMapping(
            tinytuya_class=BulbDevice,
            capabilities=[
                "switch_led",
                "bright_value",
                "colour_data",
                "temp_value",
            ],
            typical_dps={
                1: "switch",
                3: "brightness",
                5: "color",
                4: "color_temp",
            },
            description="Smart Light/Bulb",
        ),
        "dc": DeviceClassMapping(
            tinytuya_class=BulbDevice,
            capabilities=["switch_led", "bright_value", "colour_data"],
            typical_dps={1: "switch", 3: "brightness", 5: "color"},
            description="String Lights",
        ),
        "dd": DeviceClassMapping(
            tinytuya_class=BulbDevice,
            capabilities=["switch_led", "bright_value", "colour_data"],
            typical_dps={1: "switch", 3: "brightness", 5: "color"},
            description="Strip Lights",
        ),
        "dsd": DeviceClassMapping(
            tinytuya_class=BulbDevice,
            capabilities=["switch_led", "bright_value"],
            typical_dps={1: "switch", 3: "brightness"},
            description="Filament Light",
        ),
        "xdd": DeviceClassMapping(
            tinytuya_class=BulbDevice,
            capabilities=["switch_led", "bright_value", "colour_data"],
            typical_dps={1: "switch", 3: "brightness", 5: "color"},
            description="Ceiling Light",
        ),
        "tgkg": DeviceClassMapping(
            tinytuya_class=BulbDevice,
            capabilities=["switch_led", "bright_value"],
            typical_dps={1: "switch", 3: "brightness"},
            description="Dimmer Switch",
        ),
        "tgq": DeviceClassMapping(
            tinytuya_class=BulbDevice,
            capabilities=["switch_led", "bright_value"],
            typical_dps={1: "switch", 3: "brightness"},
            description="Dimmer",
        ),
        # Switch categories -> OutletDevice
        "kg": DeviceClassMapping(
            tinytuya_class=OutletDevice,
            capabilities=["switch", "switch_1", "switch_2"],
            typical_dps={1: "switch", 2: "switch_1", 3: "switch_2"},
            description="Switch",
        ),
        "pc": DeviceClassMapping(
            tinytuya_class=OutletDevice,
            capabilities=["switch", "cur_power", "cur_voltage", "cur_current"],
            typical_dps={
                1: "switch",
                18: "power",
                19: "voltage",
                20: "current",
            },
            description="Power Socket",
        ),
        "cz": DeviceClassMapping(
            tinytuya_class=OutletDevice,
            capabilities=["switch", "cur_power"],
            typical_dps={1: "switch", 18: "power"},
            description="Socket",
        ),
        "tdq": DeviceClassMapping(
            tinytuya_class=OutletDevice,
            capabilities=["switch"],
            typical_dps={1: "switch"},
            description="IoT Switch",
        ),
        # Cover categories -> CoverDevice
        "cl": DeviceClassMapping(
            tinytuya_class=CoverDevice,
            capabilities=["control", "percent_control"],
            typical_dps={1: "control", 2: "percent_control"},
            description="Curtain",
        ),
        # Climate categories -> Device (generic)
        "kt": DeviceClassMapping(
            tinytuya_class=Device,
            capabilities=["switch", "temp_set", "temp_current", "mode"],
            typical_dps={
                1: "switch",
                2: "temp_set",
                3: "temp_current",
                4: "mode",
            },
            description="Air Conditioner",
        ),
        "qn": DeviceClassMapping(
            tinytuya_class=Device,
            capabilities=["switch", "temp_set", "temp_current"],
            typical_dps={1: "switch", 2: "temp_set", 3: "temp_current"},
            description="Heater",
        ),
        "wk": DeviceClassMapping(
            tinytuya_class=Device,
            capabilities=["switch", "temp_set", "temp_current", "mode"],
            typical_dps={
                1: "switch",
                2: "temp_set",
                3: "temp_current",
                4: "mode",
            },
            description="Thermostat",
        ),
        "wkf": DeviceClassMapping(
            tinytuya_class=Device,
            capabilities=["switch", "temp_set", "temp_current"],
            typical_dps={1: "switch", 2: "temp_set", 3: "temp_current"},
            description="Radiator Valve",
        ),
        # Fan categories -> Device (generic)
        "fs": DeviceClassMapping(
            tinytuya_class=Device,
            capabilities=["switch", "fan_speed", "fan_direction"],
            typical_dps={1: "switch", 2: "fan_speed", 3: "fan_direction"},
            description="Fan",
        ),
        "fsd": DeviceClassMapping(
            tinytuya_class=Device,
            capabilities=["switch", "fan_speed", "bright_value"],
            typical_dps={1: "switch", 2: "fan_speed", 3: "brightness"},
            description="Ceiling Fan Light",
        ),
        # Sensor categories -> Device (generic)
        "sp": DeviceClassMapping(
            tinytuya_class=Device,
            capabilities=["switch", "record_switch"],
            typical_dps={1: "switch", 2: "record_switch"},
            description="Smart Camera",
        ),
        "pir": DeviceClassMapping(
            tinytuya_class=Device,
            capabilities=["pir", "battery_percentage"],
            typical_dps={1: "pir", 4: "battery_percentage"},
            description="PIR Sensor",
        ),
        "mcs": DeviceClassMapping(
            tinytuya_class=Device,
            capabilities=["doorcontact_state", "battery_percentage"],
            typical_dps={1: "doorcontact_state", 4: "battery_percentage"},
            description="Door/Window Sensor",
        ),
        "ms": DeviceClassMapping(
            tinytuya_class=Device,
            capabilities=["switch", "sensitivity"],
            typical_dps={1: "switch", 2: "sensitivity"},
            description="Motion Sensor",
        ),
        # Appliance categories -> Device (generic)
        "jsq": DeviceClassMapping(
            tinytuya_class=Device,
            capabilities=["switch", "humidity_set", "humidity_current"],
            typical_dps={
                1: "switch",
                2: "humidity_set",
                3: "humidity_current",
            },
            description="Humidifier",
        ),
        "kj": DeviceClassMapping(
            tinytuya_class=Device,
            capabilities=["switch", "filter_life", "air_quality"],
            typical_dps={1: "switch", 2: "filter_life", 3: "air_quality"},
            description="Air Purifier",
        ),
        "cs": DeviceClassMapping(
            tinytuya_class=Device,
            capabilities=["switch", "humidity_set", "humidity_current"],
            typical_dps={
                1: "switch",
                2: "humidity_set",
                3: "humidity_current",
            },
            description="Dehumidifier",
        ),
        # Additional categories from HA
        "zndb": DeviceClassMapping(
            tinytuya_class=Device,
            capabilities=["switch"],
            typical_dps={1: "switch"},
            description="Smart Lock",
        ),
        "wsdcg": DeviceClassMapping(
            tinytuya_class=Device,
            capabilities=["temp_current", "humidity_value"],
            typical_dps={1: "temp_current", 2: "humidity_value"},
            description="Temperature/Humidity Sensor",
        ),
        "ldcg": DeviceClassMapping(
            tinytuya_class=Device,
            capabilities=["bright_value", "temp_current"],
            typical_dps={1: "bright_value", 2: "temp_current"},
            description="Light Sensor",
        ),
        "rqbj": DeviceClassMapping(
            tinytuya_class=Device,
            capabilities=["gas_sensor_value"],
            typical_dps={1: "gas_sensor_value"},
            description="Gas Detector",
        ),
        "ywbj": DeviceClassMapping(
            tinytuya_class=Device,
            capabilities=["smoke_sensor_value"],
            typical_dps={1: "smoke_sensor_value"},
            description="Smoke Detector",
        ),
        "sj": DeviceClassMapping(
            tinytuya_class=Device,
            capabilities=["water_sensor"],
            typical_dps={1: "water_sensor"},
            description="Water Sensor",
        ),
        "sg": DeviceClassMapping(
            tinytuya_class=Device,
            capabilities=["switch", "fan_speed", "water_pump"],
            typical_dps={1: "switch", 2: "fan_speed", 3: "water_pump"},
            description="Plant Monitor",
        ),
        "xxj": DeviceClassMapping(
            tinytuya_class=Device,
            capabilities=["switch", "mode"],
            typical_dps={1: "switch", 2: "mode"},
            description="Washing Machine",
        ),
        "bx": DeviceClassMapping(
            tinytuya_class=Device,
            capabilities=["switch", "mode"],
            typical_dps={1: "switch", 2: "mode"},
            description="Refrigerator",
        ),
    }

    def __init__(
        self,
        enable_auto_discovery: bool = True,
        default_timeout: int = 5,
        default_version: float = 3.3,
    ):
        """
        Initialize the device factory.

        Args:
            enable_auto_discovery: Enable IP auto-discovery for devices
            default_timeout: Default connection timeout in seconds
            default_version: Default Tuya protocol version
        """
        self.enable_auto_discovery = enable_auto_discovery
        self.default_timeout = default_timeout
        self.default_version = default_version

        # Cache for created devices
        self._device_cache: Dict[str, Device] = {}

        logger.info(f"DeviceFactory initialized with TinyTuya available: {TINYTUYA_AVAILABLE}")

    def create_device(
        self,
        device_info: DeviceInfo,
        persist_connection: bool = False,
        custom_version: Optional[float] = None,
    ) -> Device:
        """
        Create a TinyTuya device instance from DeviceInfo.

        Args:
            device_info: Device information from cloud discovery
            persist_connection: Keep connection open between commands
            custom_version: Override default protocol version

        Returns:
            TinyTuya device instance

        Raises:
            ValueError: If device category is not supported
            RuntimeError: If device creation fails
        """
        # Check cache first
        if device_info.id in self._device_cache:
            logger.debug(f"Returning cached device for {device_info.id}")
            return self._device_cache[device_info.id]

        # Get device mapping
        mapping = self.get_device_mapping(device_info.category)
        if not mapping:
            logger.debug(
                f"Unknown device category '{device_info.category}', using generic Device class"
            )
            mapping = DeviceClassMapping(
                tinytuya_class=Device,
                capabilities=[],
                typical_dps={},
                description=f"Unknown Device ({device_info.category})",
            )

        # Determine IP address
        ip_address = device_info.ip if device_info.ip else "Auto"
        if self.enable_auto_discovery and ip_address == "Auto":
            logger.info(f"Using auto-discovery for device {device_info.id}")

        # Determine protocol version
        version = custom_version if custom_version else self.default_version

        # Create device initialization parameters
        device_params = {
            "dev_id": device_info.id,
            "address": ip_address,
            "local_key": device_info.local_key,
            "version": version,
            "persist": persist_connection,
            "connection_timeout": self.default_timeout,
        }

        # Create device instance
        try:
            device = mapping.tinytuya_class(**device_params)

            # Store additional info on device for later use
            device._libtuya_device_info = device_info
            device._libtuya_mapping = mapping

            # Cache the device
            self._device_cache[device_info.id] = device

            logger.debug(f"Created {mapping.description} device for {device_info.name}")
            return device

        except Exception as e:
            logger.error(f"Failed to create device {device_info.id}: {e}")
            raise RuntimeError(f"Device creation failed: {e}")

    def get_device_mapping(self, category: str) -> Optional[DeviceClassMapping]:
        """
        Get device mapping configuration for a category.

        Args:
            category: Device category ID

        Returns:
            DeviceClassMapping or None if not found
        """
        return self.DEVICE_MAPPINGS.get(category)

    def get_supported_categories(self) -> list:
        """
        Get list of all supported device categories.

        Returns:
            List of supported category strings
        """
        return list(self.DEVICE_MAPPINGS.keys())

    def get_category_info(self, category: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a device category.

        Args:
            category: Device category ID

        Returns:
            Dictionary with category information
        """
        mapping = self.get_device_mapping(category)
        if not mapping:
            return None

        return {
            "category": category,
            "description": mapping.description,
            "tinytuya_class": mapping.tinytuya_class.__name__,
            "capabilities": mapping.capabilities,
            "typical_dps": mapping.typical_dps,
            "is_light": issubclass(mapping.tinytuya_class, BulbDevice),
            "is_switch": issubclass(mapping.tinytuya_class, OutletDevice),
            "is_cover": issubclass(mapping.tinytuya_class, CoverDevice),
            "is_generic": mapping.tinytuya_class == Device,
        }

    def detect_device_category(self, available_capabilities: list) -> list:
        """
        Suggest device categories based on available capabilities.

        Args:
            available_capabilities: List of available device capabilities

        Returns:
            List of suggested categories sorted by relevance
        """
        suggestions = []
        capability_set = set(available_capabilities)

        for category, mapping in self.DEVICE_MAPPINGS.items():
            mapping_capabilities = set(mapping.capabilities)
            # Calculate match score based on intersection
            match_score = len(capability_set & mapping_capabilities)
            if match_score > 0:
                suggestions.append((category, match_score, mapping.description))

        # Sort by match score descending
        suggestions.sort(key=lambda x: x[1], reverse=True)

        # Return just the category IDs
        return [category for category, score, desc in suggestions]

    def clear_cache(self):
        """Clear the device cache."""
        self._device_cache.clear()
        logger.info("Device cache cleared")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get statistics about the device cache."""
        return {
            "cached_devices": len(self._device_cache),
            "device_ids": list(self._device_cache.keys()),
            "total_categories": len(self.DEVICE_MAPPINGS),
        }

    def detect_multi_entity_device(self, device_info: DeviceInfo) -> Dict[str, Any]:
        """
        Detect if a device is a multi-entity device and determine entity structure.

        Args:
            device_info: Device information from cloud discovery

        Returns:
            Dictionary containing multi-entity detection results
        """
        detection_result = {
            "is_multi_entity": False,
            "entity_count": 1,
            "entity_definitions": [],
            "pattern_info": None,
            "confidence": 0.0,
        }

        # Try to get available DPS from device status
        available_dps = []
        if device_info.status and isinstance(device_info.status, dict):
            # Extract DPS indices from status
            for key in device_info.status.keys():
                try:
                    dps = int(key)
                    available_dps.append(dps)
                except ValueError:
                    continue

        # If no DPS available from status, try common patterns for the category
        if not available_dps:
            mapping = self.get_device_mapping(device_info.category)
            if mapping and mapping.typical_dps:
                available_dps = list(mapping.typical_dps.keys())

        # Detect multi-entity patterns using quirks manager
        if available_dps:
            pattern_detection = quirks_manager.detect_multi_entity_pattern(
                available_dps, device_info.category
            )

            if pattern_detection and pattern_detection.get("confidence", 0) >= 0.6:
                detection_result.update(
                    {
                        "is_multi_entity": True,
                        "entity_count": pattern_detection.get("entity_count_estimate", 1),
                        "pattern_info": pattern_detection,
                        "confidence": pattern_detection.get("confidence", 0),
                    }
                )

                # Generate entity definitions based on detected patterns
                detection_result["entity_definitions"] = self._generate_entity_definitions(
                    pattern_detection, device_info, available_dps
                )

        # Check legacy multi-entity devices from quirks
        if not detection_result["is_multi_entity"]:
            legacy_entities = quirks_manager.get_multi_entity_mappings(device_info.category)
            if legacy_entities:
                detection_result.update(
                    {
                        "is_multi_entity": True,
                        "entity_count": len(legacy_entities),
                        "entity_definitions": [
                            {
                                "entity_id": f"{device_info.id}_{i}",
                                "name": f"{device_info.name} {entity.key}",
                                "type": entity.entity_type,
                                "primary_capability": entity.key,
                                "brightness_capability": entity.brightness_dpcode,
                                "category": "primary",
                            }
                            for i, entity in enumerate(legacy_entities)
                        ],
                        "confidence": 0.8,
                    }
                )

        return detection_result

    def _generate_entity_definitions(
        self,
        pattern_detection: Dict[str, Any],
        device_info: DeviceInfo,
        available_dps: List[int],
    ) -> List[Dict[str, Any]]:
        """
        Generate entity definitions based on detected patterns.

        Args:
            pattern_detection: Result from pattern detection
            device_info: Original device info
            available_dps: Available DPS indices

        Returns:
            List of entity definitions
        """
        entity_definitions = []

        for pattern in pattern_detection.get("detected_patterns", []):
            pattern_type = pattern.get("pattern_type")

            if pattern_type == "multi_gang_switch":
                # Create switch entities
                switch_dps = pattern.get("switch_dps", [])
                for i, switch_dps_idx in enumerate(switch_dps):
                    entity_definitions.append(
                        {
                            "entity_id": f"{device_info.id}_switch_{i + 1}",
                            "name": f"{device_info.name} Switch {i + 1}",
                            "type": "switch",
                            "primary_capability": "switch",
                            "dps_index": switch_dps_idx,
                            "category": "primary",
                        }
                    )

                # Create timer entities if present
                timer_dps = pattern.get("timer_dps", [])
                for i, timer_dps_idx in enumerate(timer_dps):
                    if timer_dps_idx in available_dps:
                        entity_definitions.append(
                            {
                                "entity_id": f"{device_info.id}_timer_{i + 1}",
                                "name": f"{device_info.name} Timer {i + 1}",
                                "type": "number",
                                "primary_capability": "timer",
                                "dps_index": timer_dps_idx,
                                "category": "config",
                            }
                        )

            elif pattern_type == "energy_monitoring":
                # Create energy monitoring entities
                matched_dps = pattern.get("matched_dps", [])
                subtype = pattern.get("subtype", "single_phase")

                if subtype == "single_phase":
                    for dps in matched_dps:
                        capability = self._map_energy_dps_to_capability(dps)
                        if capability:
                            entity_definitions.append(
                                {
                                    "entity_id": f"{device_info.id}_{capability}",
                                    "name": f"{device_info.name} {capability.title()}",
                                    "type": "sensor",
                                    "primary_capability": capability,
                                    "dps_index": dps,
                                    "category": "primary",
                                }
                            )
                elif subtype == "three_phase":
                    # Group by phases
                    phase_mapping = {
                        103: ("voltage", "A"),
                        104: ("current", "A"),
                        105: ("power", "A"),
                        109: ("energy", "A"),
                        113: ("voltage", "B"),
                        114: ("current", "B"),
                        115: ("power", "B"),
                        119: ("energy", "B"),
                        123: ("voltage", "C"),
                        124: ("current", "C"),
                        125: ("power", "C"),
                        129: ("energy", "C"),
                    }

                    for dps in matched_dps:
                        if dps in phase_mapping:
                            capability, phase = phase_mapping[dps]
                            entity_definitions.append(
                                {
                                    "entity_id": f"{device_info.id}_{capability}_phase_{phase.lower()}",
                                    "name": f"{device_info.name} {capability.title()} Phase {phase}",
                                    "type": "sensor",
                                    "primary_capability": f"{capability}_phase_{phase.lower()}",
                                    "dps_index": dps,
                                    "category": "primary",
                                }
                            )

            elif pattern_type == "fan_light_combo":
                # Create light entity
                light_dps = pattern.get("light_dps", [])
                if light_dps:
                    entity_definitions.append(
                        {
                            "entity_id": f"{device_info.id}_light",
                            "name": f"{device_info.name} Light",
                            "type": "light",
                            "primary_capability": "switch_led",
                            "dps_indices": light_dps,
                            "category": "primary",
                        }
                    )

                # Create fan entity
                fan_dps = pattern.get("fan_dps", [])
                if fan_dps:
                    entity_definitions.append(
                        {
                            "entity_id": f"{device_info.id}_fan",
                            "name": f"{device_info.name} Fan",
                            "type": "fan",
                            "primary_capability": "switch",
                            "dps_indices": fan_dps,
                            "category": "primary",
                        }
                    )

            elif pattern_type == "complex_lighting":
                # Create main light entity with advanced features
                lighting_dps = pattern.get("lighting_dps", [])
                entity_definitions.append(
                    {
                        "entity_id": f"{device_info.id}_light",
                        "name": f"{device_info.name} Advanced Light",
                        "type": "light",
                        "primary_capability": "switch_led",
                        "dps_indices": lighting_dps,
                        "category": "primary",
                        "features": [
                            "brightness",
                            "color",
                            "effects",
                            "scenes",
                        ],
                    }
                )

        return entity_definitions

    def _map_energy_dps_to_capability(self, dps: int) -> Optional[str]:
        """Map energy monitoring DPS to capability name."""
        energy_mapping = {
            103: "voltage",
            104: "current",
            105: "power",
            109: "total_energy",
            110: "power_factor",
        }
        return energy_mapping.get(dps)

    def validate_device_info(self, device_info: DeviceInfo) -> Dict[str, Any]:
        """
        Validate device information before creating device.

        Args:
            device_info: Device information to validate

        Returns:
            Validation results
        """
        errors = []
        warnings = []

        # Check required fields
        if not device_info.id:
            errors.append("Device ID is required")

        if not device_info.local_key:
            errors.append("Local key is required")

        if not device_info.category:
            errors.append("Device category is required")

        # Check category support
        mapping = self.get_device_mapping(device_info.category)
        if not mapping:
            # Unknown category is common and not an error - just log at debug level
            logger.debug(
                f"Unknown device category '{device_info.category}', will use generic Device class"
            )

        # Check connectivity
        if not device_info.online:
            warnings.append("Device is reported as offline")

        if not device_info.ip:
            warnings.append("No IP address available, will use auto-discovery")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "category_supported": mapping is not None,
            "category_info": (self.get_category_info(device_info.category) if mapping else None),
        }


# Global factory instance
device_factory = DeviceFactory()


def create_device_from_info(device_info: DeviceInfo, **kwargs) -> Device:
    """
    Convenience function to create a device from DeviceInfo.

    Args:
        device_info: Device information from cloud discovery
        **kwargs: Additional arguments for device creation

    Returns:
        TinyTuya device instance
    """
    return device_factory.create_device(device_info, **kwargs)


def get_supported_categories() -> list:
    """
    Get list of all supported device categories.

    Returns:
        List of supported category strings
    """
    return device_factory.get_supported_categories()


def detect_category_from_capabilities(capabilities: list) -> list:
    """
    Detect device category from available capabilities.

    Args:
        capabilities: List of available device capabilities

    Returns:
        List of suggested categories
    """
    return device_factory.detect_device_category(capabilities)
