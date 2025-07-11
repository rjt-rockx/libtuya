"""
DPS Mapping Rules for libtuya

This module provides bulletproof DPS mapping heuristics based on Home Assistant's
device intelligence and TinyTuya patterns. It handles mapping from device categories
and capabilities to actual DPS indices.

Key principles:
- DPS 1 = switch (almost universal)
- DPS 3 = brightness (lights)
- DPS 5 = color (RGB lights)
- DPS 4 = color_temp (white lights)
- Device category-specific mappings for all 60+ categories
- Fallback logic for unknown devices
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

from .capability_patterns import (
    CapabilityConfidence,
    EnhancedCapabilityPatterns,
    normalize_capability_name,
)


class DPSConfidence(Enum):
    """Confidence levels for DPS mappings"""

    HIGH = 0.9  # Very confident, based on strong heuristics
    MEDIUM = 0.6  # Moderately confident, based on category patterns
    LOW = 0.3  # Low confidence, fallback heuristics
    UNKNOWN = 0.0  # No confidence, pure guess


@dataclass
class DPSMapping:
    """Represents a DPS mapping with confidence score"""

    dps: int
    capability: str
    confidence: DPSConfidence
    reason: str
    fallback: bool = False


class DPSMappingRules:
    """
    Core DPS mapping rules engine based on Home Assistant intelligence
    """

    # Universal DPS mappings (highest confidence)
    UNIVERSAL_MAPPINGS = {
        1: ("switch", DPSConfidence.HIGH, "DPS 1 is switch in 99% of devices"),
        20: (
            "switch",
            DPSConfidence.MEDIUM,
            "DPS 20 is alternate switch pattern",
        ),
    }

    # Category-specific DPS mapping patterns
    CATEGORY_MAPPINGS = {
        # Lights - most common and well-understood
        "dj": {  # Standard lights
            1: ("switch_led", DPSConfidence.HIGH, "Standard light switch"),
            2: (
                "work_mode",
                DPSConfidence.HIGH,
                "Light mode (white/color/scene)",
            ),
            3: ("bright_value", DPSConfidence.HIGH, "Brightness control"),
            4: ("temp_value", DPSConfidence.HIGH, "Color temperature"),
            5: ("colour_data", DPSConfidence.HIGH, "RGB color data"),
            6: ("switch_1", DPSConfidence.MEDIUM, "Additional switch channel"),
            7: (
                "bright_value_1",
                DPSConfidence.MEDIUM,
                "Additional brightness channel",
            ),
            # DPS 100+ range for advanced light features
            101: ("switch_2", DPSConfidence.HIGH, "Secondary light switch"),
            102: ("work_mode_2", DPSConfidence.HIGH, "Secondary light mode"),
            103: ("temp_current", DPSConfidence.MEDIUM, "Temperature sensor"),
            104: ("switch_3", DPSConfidence.MEDIUM, "Tertiary light switch"),
            105: (
                "bright_value_2",
                DPSConfidence.MEDIUM,
                "Secondary brightness",
            ),
        },
        "dc": {  # String lights
            1: ("switch_led", DPSConfidence.HIGH, "String light switch"),
            2: ("work_mode", DPSConfidence.HIGH, "String light mode"),
            3: ("bright_value", DPSConfidence.HIGH, "String light brightness"),
            4: ("temp_value", DPSConfidence.HIGH, "String light color temp"),
            5: ("colour_data", DPSConfidence.HIGH, "String light color"),
        },
        "dd": {  # Strip lights
            1: ("switch_led", DPSConfidence.HIGH, "Strip light switch"),
            2: ("work_mode", DPSConfidence.HIGH, "Strip light mode"),
            3: ("bright_value", DPSConfidence.HIGH, "Strip light brightness"),
            4: ("temp_value", DPSConfidence.HIGH, "Strip light color temp"),
            5: ("colour_data", DPSConfidence.HIGH, "Strip light color"),
        },
        "dsd": {  # Filament lights
            1: ("switch_led", DPSConfidence.HIGH, "Filament light switch"),
            2: ("work_mode", DPSConfidence.MEDIUM, "Filament light mode"),
            3: (
                "bright_value",
                DPSConfidence.HIGH,
                "Filament light brightness",
            ),
        },
        "xdd": {  # Ceiling lights
            1: ("switch_led", DPSConfidence.HIGH, "Ceiling light switch"),
            2: ("work_mode", DPSConfidence.HIGH, "Ceiling light mode"),
            3: (
                "bright_value",
                DPSConfidence.HIGH,
                "Ceiling light brightness",
            ),
            4: ("temp_value", DPSConfidence.HIGH, "Ceiling light color temp"),
            5: ("colour_data", DPSConfidence.HIGH, "Ceiling light color"),
            6: (
                "switch_night_light",
                DPSConfidence.MEDIUM,
                "Night light switch",
            ),
        },
        "tgkg": {  # Dimmer switches
            1: ("switch_led_1", DPSConfidence.HIGH, "Dimmer switch channel 1"),
            2: (
                "bright_value_1",
                DPSConfidence.HIGH,
                "Dimmer brightness channel 1",
            ),
            3: (
                "brightness_max_1",
                DPSConfidence.MEDIUM,
                "Dimmer max brightness 1",
            ),
            4: (
                "brightness_min_1",
                DPSConfidence.MEDIUM,
                "Dimmer min brightness 1",
            ),
            5: ("switch_led_2", DPSConfidence.HIGH, "Dimmer switch channel 2"),
            6: (
                "bright_value_2",
                DPSConfidence.HIGH,
                "Dimmer brightness channel 2",
            ),
            7: (
                "brightness_max_2",
                DPSConfidence.MEDIUM,
                "Dimmer max brightness 2",
            ),
            8: (
                "brightness_min_2",
                DPSConfidence.MEDIUM,
                "Dimmer min brightness 2",
            ),
            9: ("switch_led_3", DPSConfidence.HIGH, "Dimmer switch channel 3"),
            10: (
                "bright_value_3",
                DPSConfidence.HIGH,
                "Dimmer brightness channel 3",
            ),
            11: (
                "brightness_max_3",
                DPSConfidence.MEDIUM,
                "Dimmer max brightness 3",
            ),
            12: (
                "brightness_min_3",
                DPSConfidence.MEDIUM,
                "Dimmer min brightness 3",
            ),
        },
        "tgq": {  # Dimmers
            1: ("switch_led", DPSConfidence.HIGH, "Dimmer switch"),
            2: ("bright_value", DPSConfidence.HIGH, "Dimmer brightness"),
            3: (
                "brightness_max_1",
                DPSConfidence.MEDIUM,
                "Dimmer max brightness",
            ),
            4: (
                "brightness_min_1",
                DPSConfidence.MEDIUM,
                "Dimmer min brightness",
            ),
            5: ("switch_led_1", DPSConfidence.HIGH, "Dimmer switch channel 1"),
            6: (
                "bright_value_1",
                DPSConfidence.HIGH,
                "Dimmer brightness channel 1",
            ),
            7: ("switch_led_2", DPSConfidence.HIGH, "Dimmer switch channel 2"),
            8: (
                "bright_value_2",
                DPSConfidence.HIGH,
                "Dimmer brightness channel 2",
            ),
        },
        # Switches and plugs
        "kg": {  # Standard switches
            1: ("switch", DPSConfidence.HIGH, "Standard switch"),
            2: ("switch_1", DPSConfidence.HIGH, "Switch channel 1"),
            3: ("switch_2", DPSConfidence.HIGH, "Switch channel 2"),
            4: ("switch_3", DPSConfidence.HIGH, "Switch channel 3"),
            5: ("switch_4", DPSConfidence.HIGH, "Switch channel 4"),
            6: ("switch_5", DPSConfidence.HIGH, "Switch channel 5"),
            7: ("switch_6", DPSConfidence.HIGH, "Switch channel 6"),
            8: ("switch_7", DPSConfidence.HIGH, "Switch channel 7"),
            9: ("switch_8", DPSConfidence.HIGH, "Switch channel 8"),
            10: ("child_lock", DPSConfidence.MEDIUM, "Child lock"),
            # DPS 100+ range for advanced switch features
            101: ("switch_9", DPSConfidence.HIGH, "Extended switch channel 9"),
            102: ("work_mode", DPSConfidence.HIGH, "Switch operation mode"),
            103: (
                "temp_current",
                DPSConfidence.MEDIUM,
                "Temperature monitoring",
            ),
            104: (
                "switch_10",
                DPSConfidence.MEDIUM,
                "Extended switch channel 10",
            ),
            105: (
                "power_memory",
                DPSConfidence.MEDIUM,
                "Power memory setting",
            ),
        },
        "pc": {  # Power sockets
            1: ("switch", DPSConfidence.HIGH, "Socket main switch"),
            2: ("switch_1", DPSConfidence.HIGH, "Socket channel 1"),
            3: ("switch_2", DPSConfidence.HIGH, "Socket channel 2"),
            4: ("switch_3", DPSConfidence.HIGH, "Socket channel 3"),
            5: ("switch_4", DPSConfidence.HIGH, "Socket channel 4"),
            6: ("switch_5", DPSConfidence.HIGH, "Socket channel 5"),
            7: ("switch_6", DPSConfidence.HIGH, "Socket channel 6"),
            8: ("switch_usb1", DPSConfidence.MEDIUM, "USB port 1"),
            9: ("switch_usb2", DPSConfidence.MEDIUM, "USB port 2"),
            10: ("child_lock", DPSConfidence.MEDIUM, "Child lock"),
        },
        "tdq": {  # IoT switches
            1: ("switch_1", DPSConfidence.HIGH, "IoT switch channel 1"),
            2: ("switch_2", DPSConfidence.HIGH, "IoT switch channel 2"),
            3: ("switch_3", DPSConfidence.HIGH, "IoT switch channel 3"),
            4: ("switch_4", DPSConfidence.HIGH, "IoT switch channel 4"),
            5: ("child_lock", DPSConfidence.MEDIUM, "Child lock"),
        },
        # Fans
        "fs": {  # Fans
            1: ("switch", DPSConfidence.HIGH, "Fan power switch"),
            2: ("fan_speed", DPSConfidence.HIGH, "Fan speed"),
            3: ("fan_direction", DPSConfidence.HIGH, "Fan direction"),
            4: ("light", DPSConfidence.HIGH, "Fan light"),
            5: ("work_mode", DPSConfidence.MEDIUM, "Fan mode"),
            6: ("bright_value", DPSConfidence.MEDIUM, "Fan light brightness"),
            7: ("temp_value", DPSConfidence.LOW, "Fan light color temp"),
            8: ("switch_led", DPSConfidence.MEDIUM, "Fan light switch"),
            9: (
                "bright_value_1",
                DPSConfidence.LOW,
                "Fan light brightness alt",
            ),
            10: ("anion", DPSConfidence.LOW, "Fan anion"),
            11: ("humidifier", DPSConfidence.LOW, "Fan humidifier"),
            12: ("oxygen", DPSConfidence.LOW, "Fan oxygen"),
            13: ("fan_cool", DPSConfidence.LOW, "Fan cooling"),
            14: ("fan_beep", DPSConfidence.LOW, "Fan beep"),
            15: ("child_lock", DPSConfidence.LOW, "Fan child lock"),
        },
        "fsd": {  # Ceiling fan lights
            1: ("switch_led", DPSConfidence.HIGH, "Ceiling fan light switch"),
            2: ("work_mode", DPSConfidence.HIGH, "Ceiling fan light mode"),
            3: (
                "bright_value",
                DPSConfidence.HIGH,
                "Ceiling fan light brightness",
            ),
            4: (
                "temp_value",
                DPSConfidence.HIGH,
                "Ceiling fan light color temp",
            ),
            5: ("colour_data", DPSConfidence.HIGH, "Ceiling fan light color"),
            6: ("light", DPSConfidence.HIGH, "Ceiling fan light"),
        },
        # Covers
        "cl": {  # Curtains
            1: ("control", DPSConfidence.HIGH, "Curtain control"),
            2: ("percent_control", DPSConfidence.HIGH, "Curtain position"),
            3: ("work_mode", DPSConfidence.MEDIUM, "Curtain mode"),
            4: ("control_back", DPSConfidence.MEDIUM, "Curtain reverse"),
            5: (
                "opposite",
                DPSConfidence.MEDIUM,
                "Curtain opposite direction",
            ),
        },
        # Climate devices
        "kt": {  # Air conditioners
            1: ("switch", DPSConfidence.HIGH, "AC power"),
            2: ("temp_set", DPSConfidence.HIGH, "AC temperature set"),
            3: ("temp_current", DPSConfidence.HIGH, "AC current temperature"),
            4: ("mode", DPSConfidence.HIGH, "AC mode"),
            5: ("fan_speed", DPSConfidence.HIGH, "AC fan speed"),
            6: ("anion", DPSConfidence.MEDIUM, "AC anion"),
            7: ("lock", DPSConfidence.MEDIUM, "AC lock"),
            8: ("light", DPSConfidence.LOW, "AC light"),
            # DPS 100+ range for advanced climate features
            101: ("switch_2", DPSConfidence.MEDIUM, "Secondary AC zone"),
            102: ("work_mode_2", DPSConfidence.HIGH, "Advanced mode control"),
            103: (
                "temp_current_2",
                DPSConfidence.HIGH,
                "Secondary temperature sensor",
            ),
            105: ("fan_speed_2", DPSConfidence.MEDIUM, "Secondary fan speed"),
            107: ("humidity_current", DPSConfidence.HIGH, "Humidity sensor"),
        },
        "qn": {  # Heaters
            1: ("switch", DPSConfidence.HIGH, "Heater power"),
            2: ("temp_set", DPSConfidence.HIGH, "Heater temperature set"),
            3: (
                "temp_current",
                DPSConfidence.HIGH,
                "Heater current temperature",
            ),
            4: ("mode", DPSConfidence.HIGH, "Heater mode"),
            5: ("anion", DPSConfidence.MEDIUM, "Heater anion"),
            6: ("lock", DPSConfidence.MEDIUM, "Heater lock"),
            7: ("light", DPSConfidence.LOW, "Heater light"),
        },
        "wk": {  # Thermostats
            1: ("switch", DPSConfidence.HIGH, "Thermostat power"),
            2: ("temp_set", DPSConfidence.HIGH, "Thermostat temperature set"),
            3: (
                "temp_current",
                DPSConfidence.HIGH,
                "Thermostat current temperature",
            ),
            4: ("mode", DPSConfidence.HIGH, "Thermostat mode"),
            5: ("child_lock", DPSConfidence.MEDIUM, "Thermostat child lock"),
        },
        "wkf": {  # Radiator valves
            1: ("switch", DPSConfidence.HIGH, "Valve power"),
            2: ("temp_set", DPSConfidence.HIGH, "Valve temperature set"),
            3: (
                "temp_current",
                DPSConfidence.HIGH,
                "Valve current temperature",
            ),
            4: ("mode", DPSConfidence.HIGH, "Valve mode"),
            5: ("child_lock", DPSConfidence.MEDIUM, "Valve child lock"),
            6: ("window_check", DPSConfidence.MEDIUM, "Valve window check"),
        },
        # Cameras
        "sp": {  # Smart cameras
            1: ("switch", DPSConfidence.HIGH, "Camera power"),
            2: ("floodlight_switch", DPSConfidence.HIGH, "Camera floodlight"),
            3: (
                "floodlight_lightness",
                DPSConfidence.HIGH,
                "Camera floodlight brightness",
            ),
            4: ("basic_indicator", DPSConfidence.HIGH, "Camera indicator"),
            5: (
                "wireless_batterylock",
                DPSConfidence.MEDIUM,
                "Camera battery lock",
            ),
            6: (
                "cry_detection_switch",
                DPSConfidence.MEDIUM,
                "Camera cry detection",
            ),
            7: (
                "decibel_switch",
                DPSConfidence.MEDIUM,
                "Camera decibel detection",
            ),
            8: ("record_switch", DPSConfidence.MEDIUM, "Camera record switch"),
            9: ("motion_record", DPSConfidence.MEDIUM, "Camera motion record"),
            10: ("basic_private", DPSConfidence.MEDIUM, "Camera privacy"),
            11: ("basic_flip", DPSConfidence.MEDIUM, "Camera flip"),
            12: ("basic_osd", DPSConfidence.MEDIUM, "Camera OSD"),
            13: ("basic_wdr", DPSConfidence.MEDIUM, "Camera WDR"),
            14: (
                "motion_tracking",
                DPSConfidence.MEDIUM,
                "Camera motion tracking",
            ),
            15: (
                "motion_switch",
                DPSConfidence.MEDIUM,
                "Camera motion switch",
            ),
        },
        # Humidifiers
        "jsq": {  # Humidifiers
            1: ("switch", DPSConfidence.HIGH, "Humidifier power"),
            2: ("humidity_set", DPSConfidence.HIGH, "Humidifier humidity set"),
            3: (
                "humidity_current",
                DPSConfidence.HIGH,
                "Humidifier current humidity",
            ),
            4: ("mode", DPSConfidence.HIGH, "Humidifier mode"),
            5: ("switch_led", DPSConfidence.MEDIUM, "Humidifier light"),
            6: ("work_mode", DPSConfidence.MEDIUM, "Humidifier work mode"),
            7: (
                "bright_value",
                DPSConfidence.MEDIUM,
                "Humidifier light brightness",
            ),
            8: (
                "colour_data_hsv",
                DPSConfidence.MEDIUM,
                "Humidifier light color",
            ),
            9: ("switch_sound", DPSConfidence.LOW, "Humidifier sound"),
            10: ("sleep", DPSConfidence.LOW, "Humidifier sleep"),
            11: (
                "sterilization",
                DPSConfidence.LOW,
                "Humidifier sterilization",
            ),
        },
        # Air purifiers
        "kj": {  # Air purifiers
            1: ("switch", DPSConfidence.HIGH, "Air purifier power"),
            2: ("fan_speed", DPSConfidence.HIGH, "Air purifier fan speed"),
            3: ("mode", DPSConfidence.HIGH, "Air purifier mode"),
            4: ("air_quality", DPSConfidence.HIGH, "Air purifier air quality"),
            5: ("anion", DPSConfidence.MEDIUM, "Air purifier anion"),
            6: (
                "filter_reset",
                DPSConfidence.MEDIUM,
                "Air purifier filter reset",
            ),
            7: ("lock", DPSConfidence.MEDIUM, "Air purifier lock"),
            8: ("wet", DPSConfidence.MEDIUM, "Air purifier wet"),
            9: ("uv", DPSConfidence.MEDIUM, "Air purifier UV"),
            10: ("light", DPSConfidence.LOW, "Air purifier light"),
        },
    }

    # Duplicate category mappings from HA
    DUPLICATE_MAPPINGS = {
        "cz": "kg",  # Power socket acts like switch
        "pc": "kg",  # Another power socket variant
        "dghsxj": "sp",  # Camera variant
        "tdq": "tgq",  # Dimmer variant
    }

    # Extended DPS patterns for advanced devices (DPS 100+ range)
    # Based on analysis of 1119 devices showing critical high-frequency patterns
    EXTENDED_DPS_PATTERNS = {
        101: (
            "switch_2",
            DPSConfidence.HIGH,
            "DPS 101 secondary switch (503 devices, 45%)",
        ),
        102: (
            "work_mode_2",
            DPSConfidence.HIGH,
            "DPS 102 secondary mode/preset (404 devices, 36%)",
        ),
        103: (
            "temp_current_2",
            DPSConfidence.MEDIUM,
            "DPS 103 sensor data/temperature (398 devices, 35%)",
        ),
        104: (
            "switch_3",
            DPSConfidence.MEDIUM,
            "DPS 104 tertiary switch (370 devices, 33%)",
        ),
        105: (
            "bright_value_2",
            DPSConfidence.MEDIUM,
            "DPS 105 secondary brightness (315 devices, 28%)",
        ),
        107: (
            "humidity_current",
            DPSConfidence.MEDIUM,
            "DPS 107 humidity sensor (231 devices, 21%)",
        ),
        108: (
            "switch_4",
            DPSConfidence.MEDIUM,
            "DPS 108 quaternary switch (244 devices, 22%)",
        ),
        109: (
            "temp_set_2",
            DPSConfidence.LOW,
            "DPS 109 secondary temperature set (231 devices, 21%)",
        ),
        110: (
            "mode_2",
            DPSConfidence.LOW,
            "DPS 110 alternate mode (223 devices, 20%)",
        ),
        111: (
            "fan_speed_2",
            DPSConfidence.LOW,
            "DPS 111 secondary fan speed (194 devices, 17%)",
        ),
        112: (
            "bright_value_3",
            DPSConfidence.LOW,
            "DPS 112 tertiary brightness (148 devices, 13%)",
        ),
    }

    # Fallback DPS patterns for unknown devices
    FALLBACK_PATTERNS = {
        1: ("switch", DPSConfidence.HIGH, "DPS 1 universal switch"),
        2: ("mode", DPSConfidence.MEDIUM, "DPS 2 common mode"),
        3: ("brightness", DPSConfidence.MEDIUM, "DPS 3 common brightness"),
        4: ("color_temp", DPSConfidence.MEDIUM, "DPS 4 common color temp"),
        5: ("color", DPSConfidence.MEDIUM, "DPS 5 common color"),
        6: ("switch_1", DPSConfidence.LOW, "DPS 6 alt switch"),
        7: ("brightness_1", DPSConfidence.LOW, "DPS 7 alt brightness"),
        8: ("switch_2", DPSConfidence.LOW, "DPS 8 alt switch 2"),
        9: ("brightness_2", DPSConfidence.LOW, "DPS 9 alt brightness 2"),
        10: ("child_lock", DPSConfidence.LOW, "DPS 10 common child lock"),
        20: ("switch", DPSConfidence.MEDIUM, "DPS 20 alternate switch"),
        21: ("mode", DPSConfidence.LOW, "DPS 21 alternate mode"),
        22: ("brightness", DPSConfidence.LOW, "DPS 22 alternate brightness"),
        23: ("color_temp", DPSConfidence.LOW, "DPS 23 alternate color temp"),
        24: ("color", DPSConfidence.LOW, "DPS 24 alternate color"),
        25: (
            "switch_night_light",
            DPSConfidence.LOW,
            "DPS 25 night light switch",
        ),
        26: ("timer", DPSConfidence.LOW, "DPS 26 timer control"),
        27: ("countdown", DPSConfidence.LOW, "DPS 27 countdown timer"),
        28: ("delay", DPSConfidence.LOW, "DPS 28 delay control"),
        29: ("schedule", DPSConfidence.LOW, "DPS 29 schedule control"),
        30: ("power_memory", DPSConfidence.LOW, "DPS 30 power memory"),
        31: ("backlight", DPSConfidence.LOW, "DPS 31 backlight control"),
    }

    # Common DPS ranges to probe
    DPS_RANGES = [
        range(1, 12),  # 1-11: Most common range
        range(20, 32),  # 20-31: Secondary range
        range(100, 112),  # 100-111: Extended range
    ]

    @classmethod
    def get_mappings_for_category(cls, category: str) -> Dict[int, Tuple[str, DPSConfidence, str]]:
        """Get DPS mappings for a specific device category"""
        # Handle duplicate mappings
        if category in cls.DUPLICATE_MAPPINGS:
            category = cls.DUPLICATE_MAPPINGS[category]

        # Return category-specific mappings or empty dict
        return cls.CATEGORY_MAPPINGS.get(category, {})

    @classmethod
    def get_universal_mappings(
        cls,
    ) -> Dict[int, Tuple[str, DPSConfidence, str]]:
        """Get universal DPS mappings that apply to all devices"""
        return cls.UNIVERSAL_MAPPINGS.copy()

    @classmethod
    def get_extended_mappings(
        cls,
    ) -> Dict[int, Tuple[str, DPSConfidence, str]]:
        """Get extended DPS mappings for DPS 100+ range"""
        return cls.EXTENDED_DPS_PATTERNS.copy()

    @classmethod
    def get_fallback_mappings(
        cls,
    ) -> Dict[int, Tuple[str, DPSConfidence, str]]:
        """Get fallback DPS mappings for unknown devices"""
        return cls.FALLBACK_PATTERNS.copy()

    @classmethod
    def predict_dps_for_capability(
        cls, capability: str, category: str = None
    ) -> List[Tuple[int, DPSConfidence, str]]:
        """
        Predict possible DPS indices for a given capability using enhanced patterns

        Args:
            capability: The capability name (e.g., "switch_led", "bright_value")
            category: Optional device category for better prediction

        Returns:
            List of tuples (dps_index, confidence, reason) - ordered by confidence
        """
        predictions = []

        # ENHANCED: Try data-driven capability patterns first (highest priority)
        normalized_capability = normalize_capability_name(capability)
        enhanced_predictions = EnhancedCapabilityPatterns.predict_dps_for_capability(
            normalized_capability, category
        )

        # Convert enhanced predictions to legacy format
        for dps, enh_conf, reason in enhanced_predictions:
            # Map enhanced confidence to legacy confidence
            if enh_conf.value >= 0.85:
                legacy_conf = DPSConfidence.HIGH
            elif enh_conf.value >= 0.60:
                legacy_conf = DPSConfidence.MEDIUM
            else:
                legacy_conf = DPSConfidence.LOW

            predictions.append((dps, legacy_conf, f"Enhanced: {reason}"))

        # Check category-specific mappings (legacy support)
        if category:
            category_mappings = cls.get_mappings_for_category(category)
            for dps, (cap, conf, reason) in category_mappings.items():
                if cap == capability:
                    # Avoid duplicates from enhanced patterns
                    if not any(p[0] == dps for p in predictions):
                        predictions.append((dps, conf, f"Category {category}: {reason}"))

        # Check universal mappings (legacy support)
        universal_mappings = cls.get_universal_mappings()
        for dps, (cap, conf, reason) in universal_mappings.items():
            if cap == capability:
                # Avoid duplicates from enhanced patterns
                if not any(p[0] == dps for p in predictions):
                    predictions.append((dps, conf, f"Universal: {reason}"))

        # Check extended mappings (DPS 100+ range)
        extended_mappings = cls.get_extended_mappings()
        for dps, (cap, conf, reason) in extended_mappings.items():
            if cap == capability:
                # Avoid duplicates from enhanced patterns
                if not any(p[0] == dps for p in predictions):
                    predictions.append((dps, conf, f"Extended: {reason}"))

        # Check fallback mappings (lowest priority)
        fallback_mappings = cls.get_fallback_mappings()
        for dps, (cap, conf, reason) in fallback_mappings.items():
            if cap == capability:
                # Avoid duplicates from enhanced patterns
                if not any(p[0] == dps for p in predictions):
                    predictions.append((dps, DPSConfidence.LOW, f"Fallback: {reason}"))

        # Sort by confidence (highest first)
        predictions.sort(key=lambda x: x[1].value, reverse=True)
        return predictions

    @classmethod
    def get_capability_for_dps(
        cls, dps: int, category: str = None
    ) -> Optional[Tuple[str, DPSConfidence, str]]:
        """
        Get the most likely capability for a given DPS index

        Args:
            dps: DPS index
            category: Optional device category for better prediction

        Returns:
            Tuple of (capability, confidence, reason) or None
        """
        # Check category-specific mappings first
        if category:
            category_mappings = cls.get_mappings_for_category(category)
            if dps in category_mappings:
                cap, conf, reason = category_mappings[dps]
                return (cap, conf, f"Category {category}: {reason}")

        # Check universal mappings
        universal_mappings = cls.get_universal_mappings()
        if dps in universal_mappings:
            cap, conf, reason = universal_mappings[dps]
            return (cap, conf, f"Universal: {reason}")

        # Check extended mappings (DPS 100+ range)
        extended_mappings = cls.get_extended_mappings()
        if dps in extended_mappings:
            cap, conf, reason = extended_mappings[dps]
            return (cap, conf, f"Extended: {reason}")

        # Check fallback mappings
        fallback_mappings = cls.get_fallback_mappings()
        if dps in fallback_mappings:
            cap, conf, reason = fallback_mappings[dps]
            return (cap, DPSConfidence.LOW, f"Fallback: {reason}")

        return None

    @classmethod
    def get_common_dps_ranges(cls) -> List[range]:
        """Get common DPS ranges to probe during discovery"""
        return cls.DPS_RANGES.copy()

    @classmethod
    def is_switch_dps(cls, dps: int) -> bool:
        """Check if a DPS index is likely a switch"""
        return (
            dps in [1, 20]
            or dps in range(2, 10)  # Common switch patterns
            or dps in [101, 104, 108]  # Extended switch patterns
        )

    @classmethod
    def is_brightness_dps(cls, dps: int) -> bool:
        """Check if a DPS index is likely brightness"""
        return (
            dps in [3, 22]
            or dps in [7, 9]  # Common brightness patterns
            or dps in [105, 112]  # Extended brightness patterns
        )

    @classmethod
    def is_color_dps(cls, dps: int) -> bool:
        """Check if a DPS index is likely color"""
        return dps in [5, 24]  # Common color patterns

    @classmethod
    def get_supported_categories(cls) -> List[str]:
        """Get list of all supported device categories"""
        return list(cls.CATEGORY_MAPPINGS.keys()) + list(cls.DUPLICATE_MAPPINGS.keys())

    @classmethod
    def predict_capability_with_fallback_chain(
        cls, capability: str, category: str = None
    ) -> List[Tuple[int, DPSConfidence, str, float]]:
        """
        Enhanced capability prediction using intelligent fallback chains

        Args:
            capability: The capability name
            category: Optional device category

        Returns:
            List of (dps, confidence, reason, statistical_probability) tuples
        """
        # Get enhanced patterns with statistical data
        normalized_capability = normalize_capability_name(capability)
        pattern = EnhancedCapabilityPatterns.get_capability_pattern(normalized_capability)

        if not pattern:
            # Fall back to legacy prediction
            legacy_predictions = cls.predict_dps_for_capability(capability, category)
            return [(dps, conf, reason, 0.0) for dps, conf, reason in legacy_predictions]

        enhanced_predictions = []
        total_devices = pattern.total_analyzed_devices

        for fallback in pattern.fallback_chain:
            # Calculate statistical probability based on device count
            statistical_prob = fallback.device_count / total_devices if total_devices > 0 else 0.0

            # Map enhanced confidence to legacy confidence
            if fallback.confidence.value >= 0.85:
                legacy_conf = DPSConfidence.HIGH
            elif fallback.confidence.value >= 0.60:
                legacy_conf = DPSConfidence.MEDIUM
            else:
                legacy_conf = DPSConfidence.LOW

            reason = (
                f"Fallback chain: {fallback.analysis_note} (probability: {statistical_prob:.2%})"
            )
            enhanced_predictions.append((fallback.dps, legacy_conf, reason, statistical_prob))

        return enhanced_predictions

    @classmethod
    def validate_enhanced_mapping_accuracy(cls) -> Dict[str, float]:
        """
        Validate enhanced mapping accuracy against known patterns

        Returns:
            Dictionary with accuracy metrics for each capability
        """
        # Test patterns based on mission briefing data
        test_patterns = {
            "switch": [1, 101, 104],  # Should prioritize 1, then 101, then 104
            "brightness": [
                22,
                3,
                2,
            ],  # Should prioritize 22 over 3 (key correction)
            "temperature": [2, 16, 4],  # Should prioritize 2
            "preset_mode": [2, 4, 3],  # Close competition between 2 and 4
            "speed": [3, 4, 62],  # DPS 3 primary for speed
        }

        accuracy_results = {}

        for capability, expected_dps_list in test_patterns.items():
            predictions = cls.predict_capability_with_fallback_chain(capability)
            predicted_dps = [pred[0] for pred in predictions[:3]]  # Top 3 predictions

            # Calculate accuracy - how many expected DPS are in top 3 predictions
            correct_predictions = sum(1 for dps in expected_dps_list if dps in predicted_dps)
            accuracy = correct_predictions / len(expected_dps_list) if expected_dps_list else 0.0

            # Calculate order accuracy - bonus if order matches expectations
            order_bonus = 0.0
            if predicted_dps and expected_dps_list:
                if predicted_dps[0] == expected_dps_list[0]:  # Primary DPS correct
                    order_bonus += 0.3
                if len(predicted_dps) > 1 and len(expected_dps_list) > 1:
                    if predicted_dps[1] == expected_dps_list[1]:  # Secondary DPS correct
                        order_bonus += 0.2

            final_accuracy = min(1.0, accuracy + order_bonus)
            accuracy_results[capability] = final_accuracy

        return accuracy_results
