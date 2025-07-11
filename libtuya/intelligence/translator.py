"""
Value Translation Engine for libtuya.

This module provides the ValueTranslator class that automatically detects value types
and applies appropriate scaling to convert raw Tuya device values into user-friendly
formats with proper units.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union

from .scaling import (
    DPCODE_PATTERNS,
    ELECTRICAL_UNITS,
    PERCENTAGE_UNITS,
    TEMPERATURE_UNITS,
    ElectricityTypeData,
    EnumTypeData,
    IntegerTypeData,
    battery_to_percentage,
    brightness_to_percentage,
    humidity_to_percentage,
    percentage_to_brightness,
    remap_value,
)

logger = logging.getLogger(__name__)


@dataclass
class TranslatedValue:
    """
    Result of value translation with original and translated data.

    This class provides a structured format for translation results that can be
    easily serialized to JSON and provides both user-friendly and debug information.
    """

    # Translated data
    value: Union[int, float, str, bool]
    unit: Optional[str] = None
    value_type: str = "raw"  # temperature, electrical, percentage, enum, color, raw

    # Original data (for debugging/verbose mode)
    raw_value: Union[int, float, str, bool] = None
    dpcode: Optional[str] = None

    # Translation metadata
    scaling_applied: bool = False
    translation_method: Optional[str] = None
    error_message: Optional[str] = None

    def to_dict(self, include_raw: bool = False) -> Dict[str, Any]:
        """
        Convert to dictionary format suitable for JSON serialization.

        Args:
            include_raw: Whether to include raw value and metadata

        Returns:
            Dictionary representation
        """
        result = {"value": self.value, "type": self.value_type}

        if self.unit:
            result["unit"] = self.unit

        if include_raw:
            result.update(
                {
                    "raw_value": self.raw_value,
                    "dpcode": self.dpcode,
                    "scaling_applied": self.scaling_applied,
                    "translation_method": self.translation_method,
                }
            )

            if self.error_message:
                result["error"] = self.error_message

        return result

    def is_successful(self) -> bool:
        """Check if translation was successful."""
        return self.error_message is None


class ValueTranslator:
    """
    Central translation engine for converting raw Tuya values to user-friendly formats.

    This class combines all the scaling logic from Phase 1 into a unified interface
    that can automatically detect value types and apply appropriate translations.
    """

    def __init__(self):
        """Initialize the value translator."""
        self.logger = logging.getLogger(__name__ + ".ValueTranslator")

    def translate_value(
        self,
        value: Any,
        dpcode: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TranslatedValue:
        """
        Translate a raw device value to user-friendly format.

        Args:
            value: Raw value from device
            dpcode: DPCode identifying the capability
            metadata: Optional device metadata (scale, min, max, etc.)

        Returns:
            TranslatedValue with translated data and metadata
        """
        try:
            # Handle None/empty values
            if value is None:
                return TranslatedValue(
                    value=None,
                    raw_value=value,
                    dpcode=dpcode,
                    error_message="Value is None",
                )

            # Detect value type from DPCode patterns
            value_type = self._detect_value_type(dpcode)

            # Apply appropriate translation based on type
            if value_type == "temperature":
                return self._translate_temperature(value, dpcode, metadata)
            elif value_type == "electrical":
                return self._translate_electrical(value, dpcode, metadata)
            elif value_type == "brightness":
                return self._translate_brightness(value, dpcode, metadata)
            elif value_type == "humidity":
                return self._translate_humidity(value, dpcode, metadata)
            elif value_type == "battery":
                return self._translate_battery(value, dpcode, metadata)
            elif value_type == "color":
                return self._translate_color(value, dpcode, metadata)
            elif value_type == "enum":
                return self._translate_enum(value, dpcode, metadata)
            else:
                # Raw value passthrough
                return TranslatedValue(
                    value=value,
                    raw_value=value,
                    dpcode=dpcode,
                    value_type="raw",
                )

        except Exception as e:
            self.logger.error(f"Translation failed for {dpcode}={value}: {e}")
            return TranslatedValue(
                value=value,
                raw_value=value,
                dpcode=dpcode,
                value_type="raw",
                error_message=str(e),
            )

    def translate_reverse(
        self,
        user_value: Union[str, int, float],
        dpcode: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Translate user-friendly value back to device format.

        Args:
            user_value: User-friendly value (e.g., "22.5°C", "75%")
            dpcode: DPCode identifying the capability
            metadata: Optional device metadata

        Returns:
            Raw device value

        Raises:
            ValueError: If translation fails or value is invalid
        """
        value_type = self._detect_value_type(dpcode)

        if value_type == "temperature":
            return self._reverse_translate_temperature(user_value, dpcode, metadata)
        elif value_type == "brightness":
            return self._reverse_translate_brightness(user_value, dpcode, metadata)
        elif value_type == "humidity":
            return self._reverse_translate_humidity(user_value, dpcode, metadata)
        elif value_type == "battery":
            return self._reverse_translate_battery(user_value, dpcode, metadata)
        else:
            # For other types, assume raw value passthrough
            return user_value

    def _detect_value_type(self, dpcode: str) -> str:
        """
        Detect the value type from DPCode patterns.

        Args:
            dpcode: DPCode string to analyze

        Returns:
            Value type string
        """
        dpcode_lower = dpcode.lower()

        # Check specific patterns first (most specific to least specific)
        # Temperature patterns
        temp_patterns = DPCODE_PATTERNS.get("temperature", [])
        if any(pattern in dpcode_lower for pattern in temp_patterns):
            return "temperature"

        # Brightness patterns
        bright_patterns = DPCODE_PATTERNS.get("brightness", [])
        if any(pattern in dpcode_lower for pattern in bright_patterns):
            return "brightness"

        # Humidity patterns
        humidity_patterns = DPCODE_PATTERNS.get("humidity", [])
        if any(pattern in dpcode_lower for pattern in humidity_patterns):
            return "humidity"

        # Battery patterns
        battery_patterns = DPCODE_PATTERNS.get("battery", [])
        if any(pattern in dpcode_lower for pattern in battery_patterns):
            return "battery"

        # Color patterns
        color_patterns = DPCODE_PATTERNS.get("color", [])
        if any(pattern in dpcode_lower for pattern in color_patterns):
            return "color"

        # Electrical patterns (check after other specific patterns)
        electrical_type = ElectricityTypeData.detect_electrical_dpcode(dpcode)
        if electrical_type:
            return "electrical"

        # Check for common enum patterns
        enum_patterns = ["mode", "state", "status", "level", "type"]
        if any(pattern in dpcode_lower for pattern in enum_patterns):
            return "enum"

        # Default to raw
        return "raw"

    def _translate_temperature(
        self,
        value: Union[int, float],
        dpcode: str,
        metadata: Optional[Dict[str, Any]],
    ) -> TranslatedValue:
        """Translate temperature values with special case handling."""
        try:
            # Create IntegerTypeData from metadata or defaults
            if metadata and all(k in metadata for k in ["min", "max", "scale"]):
                temp_data = IntegerTypeData(
                    dpcode=dpcode,
                    min_value=metadata["min"],
                    max_value=metadata["max"],
                    scale=metadata.get("scale", 0),
                    step=metadata.get("step", 1),
                    unit=metadata.get("unit", "°C"),
                )
            else:
                # Default temperature settings
                temp_data = IntegerTypeData(
                    dpcode=dpcode,
                    min_value=0,
                    max_value=1000,
                    scale=1,  # Most temperature devices use scale=1
                    step=1,
                    unit="°C",
                )

            # Apply temperature scaling
            scaled_value = temp_data.scale_value(value)

            return TranslatedValue(
                value=round(scaled_value, 1),
                unit=temp_data.unit,
                value_type="temperature",
                raw_value=value,
                dpcode=dpcode,
                scaling_applied=True,
                translation_method="temperature_scaling",
            )

        except Exception as e:
            return TranslatedValue(
                value=value,
                raw_value=value,
                dpcode=dpcode,
                value_type="temperature",
                error_message=f"Temperature translation failed: {e}",
            )

    def _translate_electrical(
        self,
        value: Union[str, int, float],
        dpcode: str,
        metadata: Optional[Dict[str, Any]],
    ) -> TranslatedValue:
        """Translate electrical measurements with base64 decoding if needed."""
        try:
            if isinstance(value, str):
                # Attempt base64 decoding
                electrical_data = ElectricityTypeData.decode_electrical_data(value)

                # Determine which measurement to return based on DPCode
                measurement_type = ElectricityTypeData.detect_electrical_dpcode(dpcode)
                elec_type_data = ElectricityTypeData(dpcode)

                if measurement_type and measurement_type in electrical_data:
                    return TranslatedValue(
                        value=round(electrical_data[measurement_type], 3),
                        unit=elec_type_data.get_unit(measurement_type),
                        value_type="electrical",
                        raw_value=value,
                        dpcode=dpcode,
                        scaling_applied=True,
                        translation_method="base64_electrical_decoding",
                    )
                else:
                    # Return voltage as default
                    return TranslatedValue(
                        value=round(electrical_data["voltage"], 3),
                        unit="V",
                        value_type="electrical",
                        raw_value=value,
                        dpcode=dpcode,
                        scaling_applied=True,
                        translation_method="base64_electrical_decoding",
                    )
            else:
                # Numeric electrical value - apply basic scaling
                elec_type_data = ElectricityTypeData(dpcode)
                measurement_type = ElectricityTypeData.detect_electrical_dpcode(dpcode)

                # Apply simple scaling for numeric electrical values
                if measurement_type == "voltage":
                    scaled_value = float(value) / 10.0  # Common voltage scaling
                elif measurement_type == "current":
                    scaled_value = float(value) / 1000.0  # Common current scaling
                elif measurement_type == "power":
                    scaled_value = float(value) / 1000.0  # Common power scaling
                else:
                    scaled_value = float(value)

                return TranslatedValue(
                    value=round(scaled_value, 3),
                    unit=elec_type_data.get_unit(measurement_type),
                    value_type="electrical",
                    raw_value=value,
                    dpcode=dpcode,
                    scaling_applied=True,
                    translation_method="numerical_electrical_scaling",
                )

        except Exception as e:
            return TranslatedValue(
                value=value,
                raw_value=value,
                dpcode=dpcode,
                value_type="electrical",
                error_message=f"Electrical translation failed: {e}",
            )

    def _translate_brightness(
        self,
        value: Union[int, float],
        dpcode: str,
        metadata: Optional[Dict[str, Any]],
    ) -> TranslatedValue:
        """Translate brightness values to percentage."""
        try:
            # Get device range from metadata or use defaults
            if metadata:
                device_min = metadata.get("min", 10)
                device_max = metadata.get("max", 1000)
            else:
                # Common brightness ranges
                device_min = 10
                device_max = 1000

            # Convert to percentage
            percentage = brightness_to_percentage(value, device_min, device_max)

            return TranslatedValue(
                value=round(percentage, 1),
                unit="%",
                value_type="brightness",
                raw_value=value,
                dpcode=dpcode,
                scaling_applied=True,
                translation_method="brightness_percentage_mapping",
            )

        except Exception as e:
            return TranslatedValue(
                value=value,
                raw_value=value,
                dpcode=dpcode,
                value_type="brightness",
                error_message=f"Brightness translation failed: {e}",
            )

    def _translate_humidity(
        self,
        value: Union[int, float],
        dpcode: str,
        metadata: Optional[Dict[str, Any]],
    ) -> TranslatedValue:
        """Translate humidity values to percentage."""
        try:
            percentage = humidity_to_percentage(value)

            return TranslatedValue(
                value=round(percentage, 1),
                unit="%",
                value_type="humidity",
                raw_value=value,
                dpcode=dpcode,
                scaling_applied=True,
                translation_method="humidity_percentage_scaling",
            )

        except Exception as e:
            return TranslatedValue(
                value=value,
                raw_value=value,
                dpcode=dpcode,
                value_type="humidity",
                error_message=f"Humidity translation failed: {e}",
            )

    def _translate_battery(
        self,
        value: Union[int, float],
        dpcode: str,
        metadata: Optional[Dict[str, Any]],
    ) -> TranslatedValue:
        """Translate battery values to percentage."""
        try:
            # Get device range from metadata or use defaults
            if metadata:
                device_min = metadata.get("min", 0)
                device_max = metadata.get("max", 100)
            else:
                device_min = 0
                device_max = 100

            percentage = battery_to_percentage(value, device_min, device_max)

            return TranslatedValue(
                value=round(percentage, 1),
                unit="%",
                value_type="battery",
                raw_value=value,
                dpcode=dpcode,
                scaling_applied=True,
                translation_method="battery_percentage_mapping",
            )

        except Exception as e:
            return TranslatedValue(
                value=value,
                raw_value=value,
                dpcode=dpcode,
                value_type="battery",
                error_message=f"Battery translation failed: {e}",
            )

    def _translate_color(
        self, value: Any, dpcode: str, metadata: Optional[Dict[str, Any]]
    ) -> TranslatedValue:
        """Translate color values (basic implementation)."""
        # For now, pass through color values
        # This can be enhanced later with HSV/RGB conversion
        return TranslatedValue(
            value=value,
            raw_value=value,
            dpcode=dpcode,
            value_type="color",
            translation_method="color_passthrough",
        )

    def _translate_enum(
        self, value: Any, dpcode: str, metadata: Optional[Dict[str, Any]]
    ) -> TranslatedValue:
        """Translate enum values with validation."""
        try:
            # For enum values, validate against range if available
            if metadata and "range" in metadata:
                enum_data = EnumTypeData(dpcode, metadata["range"])
                if enum_data.is_valid_value(value):
                    return TranslatedValue(
                        value=enum_data.validate_and_convert(value),
                        raw_value=value,
                        dpcode=dpcode,
                        value_type="enum",
                        scaling_applied=True,
                        translation_method="enum_validation",
                    )
                else:
                    return TranslatedValue(
                        value=value,
                        raw_value=value,
                        dpcode=dpcode,
                        value_type="enum",
                        error_message=f"Invalid enum value: {value}",
                    )
            else:
                # No validation data available, pass through
                return TranslatedValue(
                    value=value,
                    raw_value=value,
                    dpcode=dpcode,
                    value_type="enum",
                    translation_method="enum_passthrough",
                )

        except Exception as e:
            return TranslatedValue(
                value=value,
                raw_value=value,
                dpcode=dpcode,
                value_type="enum",
                error_message=f"Enum translation failed: {e}",
            )

    def _reverse_translate_temperature(
        self,
        user_value: Union[str, int, float],
        dpcode: str,
        metadata: Optional[Dict[str, Any]],
    ) -> int:
        """Reverse translate temperature values from user format to device format."""
        # Parse user input (handle "22.5°C", "22.5", etc.)
        if isinstance(user_value, str):
            # Remove common temperature units
            clean_value = (
                user_value.replace("°C", "")
                .replace("°F", "")
                .replace("C", "")
                .replace("F", "")
                .strip()
            )
            temp_value = float(clean_value)
        else:
            temp_value = float(user_value)

        # Create IntegerTypeData and apply reverse scaling
        if metadata and all(k in metadata for k in ["min", "max", "scale"]):
            temp_data = IntegerTypeData(
                dpcode=dpcode,
                min_value=metadata["min"],
                max_value=metadata["max"],
                scale=metadata.get("scale", 0),
                step=metadata.get("step", 1),
            )
        else:
            temp_data = IntegerTypeData(dpcode=dpcode, min_value=0, max_value=1000, scale=1, step=1)

        return temp_data.scale_value_back(temp_value)

    def _reverse_translate_brightness(
        self,
        user_value: Union[str, int, float],
        dpcode: str,
        metadata: Optional[Dict[str, Any]],
    ) -> int:
        """Reverse translate brightness from percentage to device format."""
        # Parse percentage input
        if isinstance(user_value, str):
            clean_value = user_value.replace("%", "").strip()
            percentage = float(clean_value)
        else:
            percentage = float(user_value)

        # Get device range
        if metadata:
            device_min = metadata.get("min", 10)
            device_max = metadata.get("max", 1000)
        else:
            device_min = 10
            device_max = 1000

        return percentage_to_brightness(percentage, device_min, device_max)

    def _reverse_translate_humidity(
        self,
        user_value: Union[str, int, float],
        dpcode: str,
        metadata: Optional[Dict[str, Any]],
    ) -> int:
        """Reverse translate humidity from percentage to device format."""
        # Parse percentage input
        if isinstance(user_value, str):
            clean_value = user_value.replace("%", "").strip()
            percentage = float(clean_value)
        else:
            percentage = float(user_value)

        # Simple reverse scaling for humidity (assuming direct percentage)
        return int(round(percentage))

    def _reverse_translate_battery(
        self,
        user_value: Union[str, int, float],
        dpcode: str,
        metadata: Optional[Dict[str, Any]],
    ) -> int:
        """Reverse translate battery from percentage to device format."""
        # Parse percentage input
        if isinstance(user_value, str):
            clean_value = user_value.replace("%", "").strip()
            percentage = float(clean_value)
        else:
            percentage = float(user_value)

        # Get device range
        if metadata:
            device_min = metadata.get("min", 0)
            device_max = metadata.get("max", 100)
        else:
            device_min = 0
            device_max = 100

        # Use remap_value in reverse
        device_value = remap_value(percentage, 0, 100, device_min, device_max)
        return int(round(device_value))


# Default instance for easy access
value_translator = ValueTranslator()
