"""
DPCode definitions and management for Tuya devices.

This module contains all 316 DPCode definitions extracted from Home Assistant's
Tuya integration, providing type-safe access to device capabilities.
"""

import json
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


def _load_dpcodes() -> Dict[str, str]:
    """Load DPCodes from the extracted JSON file."""
    intelligence_dir = Path(__file__).parent / "data"
    dpcodes_file = intelligence_dir / "dpcodes.json"

    with open(dpcodes_file, "r") as f:
        data = json.load(f)

    return data["dpcodes"]


class DPCode(str, Enum):
    """
    Enumeration of all Tuya DPCode values.

    These are the standardized data point codes used by Tuya devices
    to identify specific capabilities and functions.
    """

    # Initialize enum values from JSON
    _dpcodes_data = _load_dpcodes()

    # Air quality and sensors
    AIR_QUALITY = _dpcodes_data["AIR_QUALITY"]
    AIR_QUALITY_INDEX = _dpcodes_data["AIR_QUALITY_INDEX"]

    # Alarms
    ALARM_SWITCH = _dpcodes_data["ALARM_SWITCH"]
    ALARM_TIME = _dpcodes_data["ALARM_TIME"]
    ALARM_VOLUME = _dpcodes_data["ALARM_VOLUME"]
    ALARM_MESSAGE = _dpcodes_data["ALARM_MESSAGE"]
    ALARM_MSG = _dpcodes_data["ALARM_MSG"]

    # Motion and positioning
    ANGLE_HORIZONTAL = _dpcodes_data["ANGLE_HORIZONTAL"]
    ANGLE_VERTICAL = _dpcodes_data["ANGLE_VERTICAL"]
    ANION = _dpcodes_data["ANION"]
    ARM_DOWN_PERCENT = _dpcodes_data["ARM_DOWN_PERCENT"]
    ARM_UP_PERCENT = _dpcodes_data["ARM_UP_PERCENT"]

    # Basic device settings
    BASIC_ANTI_FLICKER = _dpcodes_data["BASIC_ANTI_FLICKER"]
    BASIC_DEVICE_VOLUME = _dpcodes_data["BASIC_DEVICE_VOLUME"]
    BASIC_FLIP = _dpcodes_data["BASIC_FLIP"]
    BASIC_INDICATOR = _dpcodes_data["BASIC_INDICATOR"]
    BASIC_NIGHTVISION = _dpcodes_data["BASIC_NIGHTVISION"]
    BASIC_OSD = _dpcodes_data["BASIC_OSD"]
    BASIC_PRIVATE = _dpcodes_data["BASIC_PRIVATE"]
    BASIC_WDR = _dpcodes_data["BASIC_WDR"]

    # Battery
    BATTERY = _dpcodes_data["BATTERY"]
    BATTERY_PERCENTAGE = _dpcodes_data["BATTERY_PERCENTAGE"]
    BATTERY_STATE = _dpcodes_data["BATTERY_STATE"]
    BATTERY_VALUE = _dpcodes_data["BATTERY_VALUE"]

    # Brightness control
    BRIGHT_CONTROLLER = _dpcodes_data["BRIGHT_CONTROLLER"]
    BRIGHT_STATE = _dpcodes_data["BRIGHT_STATE"]
    BRIGHT_VALUE = _dpcodes_data["BRIGHT_VALUE"]
    BRIGHT_VALUE_1 = _dpcodes_data["BRIGHT_VALUE_1"]
    BRIGHT_VALUE_2 = _dpcodes_data["BRIGHT_VALUE_2"]
    BRIGHT_VALUE_3 = _dpcodes_data["BRIGHT_VALUE_3"]
    BRIGHT_VALUE_V2 = _dpcodes_data["BRIGHT_VALUE_V2"]
    BRIGHTNESS_MAX_1 = _dpcodes_data["BRIGHTNESS_MAX_1"]
    BRIGHTNESS_MAX_2 = _dpcodes_data["BRIGHTNESS_MAX_2"]
    BRIGHTNESS_MAX_3 = _dpcodes_data["BRIGHTNESS_MAX_3"]
    BRIGHTNESS_MIN_1 = _dpcodes_data["BRIGHTNESS_MIN_1"]
    BRIGHTNESS_MIN_2 = _dpcodes_data["BRIGHTNESS_MIN_2"]
    BRIGHTNESS_MIN_3 = _dpcodes_data["BRIGHTNESS_MIN_3"]

    # Temperature and climate
    C_F = _dpcodes_data["C_F"]

    # Gas sensors
    CH2O_STATE = _dpcodes_data["CH2O_STATE"]
    CH2O_VALUE = _dpcodes_data["CH2O_VALUE"]
    CH4_SENSOR_STATE = _dpcodes_data["CH4_SENSOR_STATE"]
    CH4_SENSOR_VALUE = _dpcodes_data["CH4_SENSOR_VALUE"]

    # Safety and locks
    CHILD_LOCK = _dpcodes_data["CHILD_LOCK"]
    CISTERN = _dpcodes_data["CISTERN"]

    # Cleaning devices
    CLEAN_AREA = _dpcodes_data["CLEAN_AREA"]


class DPCodeManager:
    """
    Manages DPCode definitions and provides lookup functionality.
    """

    def __init__(self):
        """Initialize the DPCode manager with cached data."""
        self._dpcodes_data = None
        self._name_to_code = {}
        self._code_to_name = {}
        self._load_data()

    def _load_data(self) -> None:
        """Load and cache DPCode data from JSON file."""
        intelligence_dir = Path(__file__).parent / "data"
        dpcodes_file = intelligence_dir / "dpcodes.json"

        with open(dpcodes_file, "r") as f:
            self._dpcodes_data = json.load(f)

        # Build lookup dictionaries
        dpcodes = self._dpcodes_data["dpcodes"]
        for name, code in dpcodes.items():
            self._name_to_code[name] = code
            self._code_to_name[code] = name

    def get_code_by_name(self, name: str) -> Optional[str]:
        """
        Get DPCode value by constant name.

        Args:
            name: The constant name (e.g., "BRIGHT_VALUE")

        Returns:
            The DPCode value (e.g., "bright_value") or None if not found
        """
        return self._name_to_code.get(name)

    def get_name_by_code(self, code: str) -> Optional[str]:
        """
        Get constant name by DPCode value.

        Args:
            code: The DPCode value (e.g., "bright_value")

        Returns:
            The constant name (e.g., "BRIGHT_VALUE") or None if not found
        """
        return self._code_to_name.get(code)

    def get_all_codes(self) -> List[str]:
        """
        Get all DPCode values.

        Returns:
            List of all DPCode values
        """
        return list(self._code_to_name.keys())

    def get_all_names(self) -> List[str]:
        """
        Get all constant names.

        Returns:
            List of all constant names
        """
        return list(self._name_to_code.keys())

    def search_codes(self, pattern: str) -> List[str]:
        """
        Search for DPCode values matching a pattern.

        Args:
            pattern: Pattern to search for (case-insensitive)

        Returns:
            List of matching DPCode values
        """
        pattern_lower = pattern.lower()
        return [code for code in self._code_to_name.keys() if pattern_lower in code.lower()]

    def search_names(self, pattern: str) -> List[str]:
        """
        Search for constant names matching a pattern.

        Args:
            pattern: Pattern to search for (case-insensitive)

        Returns:
            List of matching constant names
        """
        pattern_lower = pattern.lower()
        return [name for name in self._name_to_code.keys() if pattern_lower in name.lower()]

    def is_valid_code(self, code: str) -> bool:
        """
        Check if a DPCode value is valid.

        Args:
            code: The DPCode value to check

        Returns:
            True if valid, False otherwise
        """
        return code in self._code_to_name

    def is_valid_name(self, name: str) -> bool:
        """
        Check if a constant name is valid.

        Args:
            name: The constant name to check

        Returns:
            True if valid, False otherwise
        """
        return name in self._name_to_code

    def get_total_count(self) -> int:
        """
        Get total number of DPCodes.

        Returns:
            Total count of DPCodes
        """
        return self._dpcodes_data["total_count"]

    def get_category_codes(self, category: str) -> List[str]:
        """
        Get DPCodes commonly used by a device category.

        Args:
            category: Device category (e.g., "dj" for lights)

        Returns:
            List of DPCode values for the category
        """
        # This is a simplified implementation
        # In a full implementation, this would use device mappings
        if category == "dj":  # Lights
            return [
                DPCode.SWITCH_LED,
                DPCode.BRIGHT_VALUE,
                DPCode.BRIGHT_VALUE_V2,
                DPCode.COLOUR_DATA,
                DPCode.COLOUR_DATA_V2,
                DPCode.TEMP_VALUE,
                DPCode.TEMP_VALUE_V2,
                DPCode.WORK_MODE,
            ]
        elif category == "kg":  # Switches
            return [
                DPCode.SWITCH_1,
                DPCode.SWITCH_2,
                DPCode.SWITCH_3,
                DPCode.SWITCH_BACKLIGHT,
            ]
        else:
            return []


# Add remaining DPCodes to the enum by dynamically creating them
def _create_dpcode_enum():
    """Create complete DPCode enum with all 316 values."""
    manager = DPCodeManager()

    # Get all DPCode data
    for name, code in manager._name_to_code.items():
        if not hasattr(DPCode, name):
            setattr(DPCode, name, code)


# Initialize the complete enum
_create_dpcode_enum()


# Default instance for easy access
dpcode_manager = DPCodeManager()
