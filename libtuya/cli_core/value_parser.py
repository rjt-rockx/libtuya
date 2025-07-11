"""
Value Parser - Input parsing and validation

This module handles parsing and validation of user input values for device control.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


class ValueParser:
    """Parses and validates user input values."""

    def parse_temperature_input(self, value: str) -> Tuple[float, str]:
        """
        Parse temperature input with various formats.

        Args:
            value: Temperature string like "22.5", "22.5°C", "22.5F", etc.

        Returns:
            Tuple of (temperature_value, unit)

        Raises:
            ValueError: If the input format is invalid
        """
        if not value:
            raise ValueError("Temperature value cannot be empty")

        value = value.strip()

        # Check for Fahrenheit indicators
        if value.endswith("°F") or value.endswith("F"):
            unit = "F"
            temp_str = value.replace("°F", "").replace("F", "").strip()
        elif value.endswith("°C") or value.endswith("C"):
            unit = "C"
            temp_str = value.replace("°C", "").replace("C", "").strip()
        else:
            # Default to Celsius for plain numbers
            unit = "C"
            temp_str = value

        try:
            temp_value = float(temp_str)
        except ValueError:
            raise ValueError(
                f"Invalid temperature value: '{value}'. Expected format: '22.5', '22.5°C', '72°F', etc."
            )

        return temp_value, unit

    def parse_brightness_input(self, value: str) -> int:
        """
        Parse brightness input with percentage support.

        Args:
            value: Brightness string like "75", "75%", "bright 75", etc.

        Returns:
            Brightness value as integer (0-100)

        Raises:
            ValueError: If the input format is invalid
        """
        if not value:
            raise ValueError("Brightness value cannot be empty")

        value = value.strip().lower()

        # Handle "bright 75" format
        if value.startswith("bright "):
            value = value[7:].strip()

        # Remove percentage symbol
        if value.endswith("%"):
            value = value[:-1].strip()

        try:
            brightness = int(float(value))
        except ValueError:
            raise ValueError(
                f"Invalid brightness value: '{value}'. Expected format: '75', '75%', 'bright 75', etc."
            )

        if brightness < 0 or brightness > 100:
            raise ValueError(f"Brightness must be between 0 and 100, got {brightness}")

        return brightness

    def parse_generic_input_with_units(
        self, value: str, allowed_units: Optional[List[str]] = None
    ) -> Tuple[Union[int, float], Optional[str]]:
        """
        Parse generic input that may contain units.

        Args:
            value: Input string like "75%", "22.5°C", "100", etc.
            allowed_units: Optional list of allowed unit suffixes

        Returns:
            Tuple of (numeric_value, unit)

        Raises:
            ValueError: If the input format is invalid
        """
        if not value:
            raise ValueError("Value cannot be empty")

        value = value.strip()

        # Common unit patterns
        unit_patterns = ["%", "°C", "°F", "C", "F", "V", "A", "W", "Hz"]
        if allowed_units:
            unit_patterns = allowed_units

        detected_unit = None
        numeric_part = value

        # Check for unit suffix
        for unit in unit_patterns:
            if value.endswith(unit):
                detected_unit = unit
                numeric_part = value[: -len(unit)].strip()
                break

        try:
            # Try integer first, then float
            if "." in numeric_part:
                numeric_value = float(numeric_part)
            else:
                numeric_value = int(numeric_part)
        except ValueError:
            raise ValueError(
                f"Invalid numeric value: '{value}'. Expected a number optionally followed by a unit."
            )

        return numeric_value, detected_unit

    def validate_input_format(self, value: str, action: str) -> Tuple[bool, Optional[str]]:
        """
        Validate input format for different action types.

        Args:
            value: Input value to validate
            action: Action type (brightness, temperature, color, etc.)

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not value:
            return False, f"{action} value cannot be empty"

        value = value.strip()

        try:
            if action.lower() in ["brightness", "bright", "level"]:
                self.parse_brightness_input(value)
            elif action.lower() in [
                "temperature",
                "temp",
                "target_temperature",
            ]:
                self.parse_temperature_input(value)
            elif action.lower() in ["color", "colour"]:
                # Basic color validation - hex codes, rgb, or named colors
                if not (value.startswith("#") or value.startswith("rgb") or value.isalpha()):
                    return (
                        False,
                        f"Invalid color format: '{value}'. Use hex (#FF0000), rgb(255,0,0), or color names.",
                    )
            # Add more action-specific validations as needed

            return True, None

        except ValueError as e:
            return False, str(e)

    def extract_device_metadata(self, capability: Any) -> Dict[str, Any]:
        """
        Extract device metadata from capability for reverse translation.

        Args:
            capability: Device capability object with scaling information

        Returns:
            Dictionary with min, max, scale, step values for reverse translation
        """
        metadata = {}

        if hasattr(capability, "scaling_info") and capability.scaling_info:
            # Extract from scaling_info if available
            scaling = capability.scaling_info
            metadata["min"] = scaling.get("min_value", 0)
            metadata["max"] = scaling.get("max_value", 1000)
            metadata["scale"] = scaling.get("scale", 1)
            metadata["step"] = scaling.get("step", 1)
        else:
            # Try to extract from individual attributes
            metadata["min"] = getattr(capability, "min_value", 0)
            metadata["max"] = getattr(capability, "max_value", 1000)
            metadata["scale"] = getattr(capability, "scale", 1)
            metadata["step"] = getattr(capability, "step", 1)

        return metadata

    def validate_temperature_range(
        self, temp_value: float, device: Any, unit: str = "C"
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate temperature value against device constraints.

        Args:
            temp_value: Temperature value to validate
            device: Device object with temperature constraints
            unit: Temperature unit ('C' or 'F')

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Get device temperature constraints
            min_temp = getattr(device, "min_temperature", 10.0)
            max_temp = getattr(device, "max_temperature", 30.0)

            # Convert temperature if needed
            if unit == "F":
                # Convert Fahrenheit to Celsius for comparison
                temp_celsius = (temp_value - 32) * 5.0 / 9.0
            else:
                temp_celsius = temp_value

            if temp_celsius < min_temp:
                return (
                    False,
                    f"Temperature {temp_value}°{unit} is below minimum ({min_temp}°C)",
                )
            elif temp_celsius > max_temp:
                return (
                    False,
                    f"Temperature {temp_value}°{unit} is above maximum ({max_temp}°C)",
                )

            return True, None

        except Exception as e:
            logger.warning(f"Could not validate temperature range: {e}")
            return True, None  # Allow if validation fails

    def validate_brightness_range(self, brightness: int, device: Any) -> Tuple[bool, Optional[str]]:
        """
        Validate brightness value against device constraints.

        Args:
            brightness: Brightness value to validate (0-100)
            device: Device object with brightness constraints

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Get device brightness constraints
            min_brightness = getattr(device, "min_brightness", 0)
            max_brightness = getattr(device, "max_brightness", 100)

            if brightness < min_brightness:
                return (
                    False,
                    f"Brightness {brightness}% is below minimum ({min_brightness}%)",
                )
            elif brightness > max_brightness:
                return (
                    False,
                    f"Brightness {brightness}% is above maximum ({max_brightness}%)",
                )

            return True, None

        except Exception as e:
            logger.warning(f"Could not validate brightness range: {e}")
            return True, None  # Allow if validation fails
