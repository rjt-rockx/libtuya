"""
libtuya DPS Discovery and Mapping System

This module provides intelligent DPS (Data Point) discovery and mapping for Tuya devices,
combining Home Assistant device intelligence with TinyTuya's local control capabilities.

The system automatically:
- Discovers available DPS indices using TinyTuya's detect_available_dps()
- Maps device capabilities to DPS indices using bulletproof heuristics
- Provides bidirectional capability ↔ DPS mapping
- Handles device quirks and edge cases
- Caches mappings for improved performance
- Supports all 60+ device categories from Home Assistant

Main Classes:
- DPSMapper: Primary interface for DPS discovery and mapping
- DeviceInfo: Device information container
- DPSMappingInfo: Information about a specific DPS mapping
- DPSDiscoveryEngine: Core discovery engine
- DPSMappingRules: Heuristic rules for DPS mapping

Usage:
    from libtuya.dps import DPSMapper, DeviceInfo

    # Create mapper
    mapper = DPSMapper()

    # Define device info
    device_info = DeviceInfo(
        device_id="bf1234567890abcdef",
        category="dj",  # Light category
        name="Living Room Light"
    )

    # Discover DPS mapping
    mappings = mapper.discover_dps_mapping(
        device_info=device_info,
        expected_capabilities=["switch_led", "bright_value", "colour_data"],
        tinytuya_device=tinytuya_device
    )

    # Use mappings
    switch_dps = mapper.get_dps_for_capability(device_info.device_id, "switch_led")
    brightness_dps = mapper.get_dps_for_capability(device_info.device_id, "bright_value")

    # Validate mappings
    validation = mapper.validate_mapping(device_info.device_id)
    print(f"Mapping is valid: {validation['valid']}, Score: {validation['score']}")
"""

from .mapper import DPSMapper, DeviceInfo, DPSMappingInfo, DPSMappingCache
from .discovery import (
    DPSDiscoveryEngine,
    DPSDiscoveryResult,
    DPSMatch,
    DiscoveryError,
    DiscoveryTimeout,
    DeviceUnreachable,
)
from .mapping_rules import DPSMappingRules, DPSConfidence, DPSMapping

# Version info
__version__ = "0.1.0"
__author__ = "libtuya"
__description__ = "Intelligent DPS discovery and mapping for Tuya devices"

# Export main classes
__all__ = [
    # Main interface
    "DPSMapper",
    "DeviceInfo",
    "DPSMappingInfo",
    # Discovery engine
    "DPSDiscoveryEngine",
    "DPSDiscoveryResult",
    "DPSMatch",
    # Mapping rules
    "DPSMappingRules",
    "DPSConfidence",
    "DPSMapping",
    # Cache
    "DPSMappingCache",
    # Exceptions
    "DiscoveryError",
    "DiscoveryTimeout",
    "DeviceUnreachable",
    # Utilities
    "create_device_info",
    "validate_device_category",
    "get_supported_categories",
]


# Convenience functions
def create_device_info(device_id: str, category: str, **kwargs) -> DeviceInfo:
    """
    Create a DeviceInfo object with validation

    Args:
        device_id: Unique device identifier
        category: Device category (e.g., "dj" for lights)
        **kwargs: Additional device info fields

    Returns:
        DeviceInfo object

    Raises:
        ValueError: If device_id or category is invalid
    """
    return DeviceInfo(device_id=device_id, category=category, **kwargs)


def validate_device_category(category: str) -> bool:
    """
    Validate if a device category is supported

    Args:
        category: Device category to validate

    Returns:
        True if category is supported, False otherwise
    """
    return category in DPSMappingRules.get_supported_categories()


def get_supported_categories() -> list:
    """
    Get list of all supported device categories

    Returns:
        List of supported category strings
    """
    return DPSMappingRules.get_supported_categories()


def create_mapper(enable_cache: bool = True, **kwargs) -> DPSMapper:
    """
    Create a DPSMapper with recommended settings

    Args:
        enable_cache: Whether to enable mapping cache
        **kwargs: Additional mapper options

    Returns:
        Configured DPSMapper instance
    """
    return DPSMapper(enable_cache=enable_cache, **kwargs)


# Module-level configuration
DEFAULT_DISCOVERY_TIMEOUT = 30.0
DEFAULT_PROBE_DELAY = 0.1
DEFAULT_MAX_RETRIES = 3

# Common device categories for reference
DEVICE_CATEGORIES = {
    # Lights
    "dj": "Light",
    "dc": "String Lights",
    "dd": "Strip Lights",
    "dsd": "Filament Light",
    "xdd": "Ceiling Light",
    "tgkg": "Dimmer Switch",
    "tgq": "Dimmer",
    # Switches
    "kg": "Switch",
    "pc": "Power Socket",
    "tdq": "IoT Switch",
    # Climate
    "kt": "Air Conditioner",
    "qn": "Heater",
    "wk": "Thermostat",
    "wkf": "Radiator Valve",
    # Covers
    "cl": "Curtain",
    # Fans
    "fs": "Fan",
    "fsd": "Ceiling Fan Light",
    # Sensors and Cameras
    "sp": "Smart Camera",
    # Appliances
    "jsq": "Humidifier",
    "kj": "Air Purifier",
    "cs": "Dehumidifier",
}

# Common capabilities for reference
COMMON_CAPABILITIES = {
    # Switch capabilities
    "switch": "Main power switch",
    "switch_led": "LED light switch",
    "switch_1": "Switch channel 1",
    "switch_2": "Switch channel 2",
    # Brightness capabilities
    "bright_value": "Brightness control",
    "bright_value_v2": "Brightness control v2",
    "bright_value_1": "Brightness channel 1",
    # Color capabilities
    "colour_data": "RGB color data",
    "colour_data_v2": "RGB color data v2",
    "colour_data_hsv": "HSV color data",
    # Temperature capabilities
    "temp_value": "Color temperature",
    "temp_value_v2": "Color temperature v2",
    "temp_set": "Temperature setpoint",
    "temp_current": "Current temperature",
    # Mode capabilities
    "work_mode": "Work mode",
    "mode": "General mode",
    # Fan capabilities
    "fan_speed": "Fan speed",
    "fan_direction": "Fan direction",
    # Control capabilities
    "control": "General control",
    "percent_control": "Percentage control",
}

# DPS mapping confidence levels
CONFIDENCE_LEVELS = {
    "HIGH": 0.9,  # Very confident, based on strong heuristics
    "MEDIUM": 0.6,  # Moderately confident, based on category patterns
    "LOW": 0.3,  # Low confidence, fallback heuristics
    "UNKNOWN": 0.0,  # No confidence, pure guess
}

# Default DPS ranges to probe
DEFAULT_DPS_RANGES = [
    range(1, 12),  # 1-11: Most common range
    range(20, 32),  # 20-31: Secondary range
    range(100, 112),  # 100-111: Extended range
]

# Quick reference for common DPS patterns
COMMON_DPS_PATTERNS = {
    1: "switch",  # Almost universal
    2: "mode",  # Common mode control
    3: "brightness",  # Common brightness
    4: "color_temp",  # Common color temperature
    5: "color",  # Common color data
    6: "switch_1",  # Alternative switch
    7: "brightness_1",  # Alternative brightness
    20: "switch",  # Alternative switch pattern
    21: "mode",  # Alternative mode pattern
    22: "brightness",  # Alternative brightness pattern
    23: "color_temp",  # Alternative color temp pattern
    24: "color",  # Alternative color pattern
}

# Error codes for debugging
ERROR_CODES = {
    "DISCOVERY_TIMEOUT": "DPS discovery timed out",
    "DEVICE_UNREACHABLE": "Device is unreachable",
    "NO_DPS_FOUND": "No DPS indices discovered",
    "INVALID_CATEGORY": "Invalid device category",
    "MAPPING_FAILED": "DPS mapping failed",
    "CACHE_ERROR": "Cache operation failed",
    "VALIDATION_FAILED": "Mapping validation failed",
}

# Initialize logging
import logging

logging.getLogger(__name__).addHandler(logging.NullHandler())
