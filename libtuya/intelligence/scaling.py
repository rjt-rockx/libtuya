"""
Value scaling and conversion logic for Tuya devices.

This module contains the scaling and conversion logic extracted from Home Assistant's
Tuya integration for handling device value transformations.
"""

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Unit conversion constants
TEMPERATURE_UNITS = {
    "celsius": ["°C", "C", "celsius"],
    "fahrenheit": ["°F", "F", "fahrenheit"],
    "kelvin": ["K", "kelvin"],
}

ELECTRICAL_UNITS = {
    "voltage": ["V", "volt", "volts"],
    "current": ["A", "amp", "amps", "ampere", "amperes"],
    "power": ["W", "watt", "watts"],
    "energy": ["kWh", "kwh", "Wh", "wh"],
}

PERCENTAGE_UNITS = ["%", "percent", "percentage"]

# Common DPCode patterns for value type detection
DPCODE_PATTERNS = {
    "temperature": [
        "temp",
        "temperature",
        "current_temp",
        "set_temp",
        "temp_set",
        "temp_current",
    ],
    "brightness": ["bright", "brightness", "bright_value", "work_power"],
    "electrical": [
        "voltage",
        "electriccurrent",
        "electricity",
        "energy",
    ],  # Removed 'current' and 'power' to avoid conflicts
    "humidity": ["humidity", "humidity_value", "relative_humidity"],
    "battery": ["battery", "battery_percentage", "va_battery"],
    "color": ["colour", "color", "colour_data", "color_data", "hsv", "rgb"],
}


@dataclass
class IntegerTypeData:
    """
    Handles scaling for integer values with temperature special case logic.

    This class provides robust value scaling based on Home Assistant's IntegerTypeData
    implementation, with special handling for temperature values that have scale=0
    and step!=1 (the Tuya temperature scaling edge case).

    The special case handles devices that report temperature values that need to be
    divided by 10 when scale=0 and step!=1, as documented in Tuya's developer docs.
    """

    dpcode: str
    min_value: int
    max_value: int
    scale: int = 0
    step: int = 1
    unit: Optional[str] = None
    type_info: Optional[str] = None

    @property
    def is_temperature(self) -> bool:
        """
        Detect if this data represents temperature values.

        Returns:
            True if this appears to be temperature data
        """
        if self.unit:
            temp_units = [
                "°C",
                "°F",
                "C",
                "F",
                "K",
                "celsius",
                "fahrenheit",
                "kelvin",
            ]
            return any(unit.lower() in self.unit.lower() for unit in temp_units)

        # Check dpcode patterns
        temp_dpcodes = ["temp", "temperature", "current_temp", "set_temp"]
        return any(pattern in self.dpcode.lower() for pattern in temp_dpcodes)

    @property
    def uses_temperature_special_case(self) -> bool:
        """
        Check if this data uses the temperature special case logic.

        Returns:
            True if scale=0 and step!=1 (temperature special case)
        """
        return self.scale == 0 and self.step != 1

    def scale_value(self, value: Union[int, float]) -> float:
        """
        Scale a raw device value to the proper range.

        Implements Home Assistant's scaling logic including special case for
        temperature values with scale=0 and step!=1.

        Args:
            value: Raw device value

        Returns:
            Scaled value

        Raises:
            ValueError: If value is None
        """
        if value is None:
            raise ValueError("Cannot scale None value")

        # Home Assistant special case for temperature values
        # https://developer.tuya.com/en/docs/iot/shift-temperature-scale-follow-the-setting-of-app-account-center?id=Ka9qo7so58efq#title-7-Round%20values
        if self.scale == 0 and self.step != 1:
            # Temperature values with scale=0 but step!=1 need to be divided by 10
            value = value / 10

        return value / (10**self.scale)

    def scale_value_back(self, value: Union[int, float]) -> int:
        """
        Scale a value back to device range.

        Implements the inverse of scale_value(), including handling of the
        temperature special case where scale=0 and step!=1.

        Args:
            value: Scaled value

        Returns:
            Raw device value

        Raises:
            ValueError: If value is None
        """
        if value is None:
            raise ValueError("Cannot scale back None value")

        # Apply inverse of temperature special case logic
        if self.scale == 0 and self.step != 1:
            # Temperature values with scale=0 but step!=1 need to be multiplied by 10
            # before applying standard scaling
            value = value * 10

        return int(round(value * (10**self.scale)))

    def remap_value_to(
        self,
        value: Union[int, float],
        to_min: Union[int, float],
        to_max: Union[int, float],
    ) -> Union[int, float]:
        """
        Remap value from device range to target range.

        Args:
            value: Device value
            to_min: Target minimum
            to_max: Target maximum

        Returns:
            Remapped value
        """
        return remap_value(value, self.min_value, self.max_value, to_min, to_max)

    def remap_value_from(
        self,
        value: Union[int, float],
        from_min: Union[int, float],
        from_max: Union[int, float],
    ) -> Union[int, float]:
        """
        Remap value from target range to device range.

        Args:
            value: Target value
            from_min: Source minimum
            from_max: Source maximum

        Returns:
            Device value
        """
        return remap_value(value, from_min, from_max, self.min_value, self.max_value)


@dataclass
class EnumTypeData:
    """
    Handles enum values.

    Equivalent to Home Assistant's EnumTypeData class.
    """

    dpcode: str
    range_values: List[str]

    def is_valid_value(self, value: Union[str, int, float]) -> bool:
        """
        Check if a value is valid for this enum.

        Args:
            value: Value to check (string, int, or float)

        Returns:
            True if valid, False otherwise
        """
        if value is None:
            return False

        # Convert to string for comparison
        str_value = str(value)
        return str_value in self.range_values

    def get_valid_values(self) -> List[str]:
        """
        Get all valid values for this enum.

        Returns:
            List of valid values
        """
        return self.range_values.copy()

    def validate_and_convert(self, value: Union[str, int, float]) -> str:
        """
        Validate a value and convert it to proper enum format.

        Args:
            value: Value to validate and convert

        Returns:
            Validated enum value as string

        Raises:
            ValueError: If value is not valid for this enum
        """
        if not self.is_valid_value(value):
            raise ValueError(
                f"Invalid enum value '{value}' for {self.dpcode}. "
                f"Valid values: {', '.join(self.range_values)}"
            )
        return str(value)

    def get_fallback_value(self) -> str:
        """
        Get a fallback value for this enum (first valid value).

        Returns:
            First valid enum value

        Raises:
            ValueError: If no valid values are available
        """
        if not self.range_values:
            raise ValueError(f"No valid values available for enum {self.dpcode}")
        return self.range_values[0]


@dataclass
class ColorTypeData:
    """
    Handles color value scaling.

    Equivalent to Home Assistant's color type data structures.
    """

    h_min: int
    h_max: int
    s_min: int
    s_max: int
    v_min: int
    v_max: int
    h_scale: int = 0
    s_scale: int = 0
    v_scale: int = 0
    h_step: int = 1
    s_step: int = 1
    v_step: int = 1


def remap_value(
    value: Union[int, float],
    from_min: Union[int, float] = 0,
    from_max: Union[int, float] = 255,
    to_min: Union[int, float] = 0,
    to_max: Union[int, float] = 255,
    reverse: bool = False,
) -> Union[int, float]:
    """
    Core remapping function from Home Assistant's util.py.

    Enhanced with robust edge case handling and validation.

    Args:
        value: Value to remap
        from_min: Source minimum value
        from_max: Source maximum value
        to_min: Target minimum value
        to_max: Target maximum value
        reverse: Whether to reverse the mapping (for covers/blinds: 0=open, 100=closed)

    Returns:
        Remapped value

    Raises:
        ValueError: If ranges are invalid or value is None
    """
    if value is None:
        raise ValueError("Cannot remap None value")

    # Validate source range
    if from_min == from_max:
        raise ValueError(f"Invalid source range: min ({from_min}) equals max ({from_max})")

    # If target range is a single point, return that point
    if to_min == to_max:
        return to_min

    # Apply reverse mapping for covers/blinds (0=open, 100=closed)
    if reverse:
        value = from_max - value + from_min

    # Clamp input value to source range to handle out-of-bounds values gracefully
    value = max(from_min, min(value, from_max))

    # Calculate remapped value with improved precision
    source_range = from_max - from_min
    target_range = to_max - to_min
    normalized = (value - from_min) / source_range

    return normalized * target_range + to_min


class ValueScalingManager:
    """
    Manages value scaling and conversion for Tuya devices.
    """

    def __init__(self):
        """Initialize the value scaling manager."""
        self._scaling_data = None
        self._integer_types = {}
        self._enum_types = {}
        self._color_types = {}
        self._load_data()

    def _load_data(self) -> None:
        """Load and cache scaling data from JSON file."""
        intelligence_dir = Path(__file__).parent / "data"
        scaling_file = intelligence_dir / "scaling_rules.json"

        with open(scaling_file, "r") as f:
            self._scaling_data = json.load(f)

        # Initialize color type data
        self._initialize_color_types()

    def _initialize_color_types(self) -> None:
        """Initialize color type data structures."""
        color_data = self._scaling_data.get("color_scaling", {}) if self._scaling_data else {}

        # DEFAULT_COLOR_TYPE_DATA
        if "DEFAULT_COLOR_TYPE_DATA" in color_data:
            default_color = color_data["DEFAULT_COLOR_TYPE_DATA"]
            self._color_types["default"] = ColorTypeData(
                h_min=default_color["h_type"]["min"],
                h_max=default_color["h_type"]["max"],
                s_min=default_color["s_type"]["min"],
                s_max=default_color["s_type"]["max"],
                v_min=default_color["v_type"]["min"],
                v_max=default_color["v_type"]["max"],
                h_scale=default_color["h_type"]["scale"],
                s_scale=default_color["s_type"]["scale"],
                v_scale=default_color["v_type"]["scale"],
            )

        # DEFAULT_COLOR_TYPE_DATA_V2
        if "DEFAULT_COLOR_TYPE_DATA_V2" in color_data:
            default_color_v2 = color_data["DEFAULT_COLOR_TYPE_DATA_V2"]
            self._color_types["default_v2"] = ColorTypeData(
                h_min=default_color_v2["h_type"]["min"],
                h_max=default_color_v2["h_type"]["max"],
                s_min=default_color_v2["s_type"]["min"],
                s_max=default_color_v2["s_type"]["max"],
                v_min=default_color_v2["v_type"]["min"],
                v_max=default_color_v2["v_type"]["max"],
                h_scale=default_color_v2["h_type"]["scale"],
                s_scale=default_color_v2["s_type"]["scale"],
                v_scale=default_color_v2["v_type"]["scale"],
            )

    def create_integer_type(
        self,
        dpcode: str,
        min_val: int,
        max_val: int,
        scale: int = 0,
        step: int = 1,
        unit: Optional[str] = None,
    ) -> IntegerTypeData:
        """
        Create an IntegerTypeData instance.

        Args:
            dpcode: DPCode this applies to
            min_val: Minimum value
            max_val: Maximum value
            scale: Scale factor (power of 10)
            step: Step size
            unit: Unit of measurement

        Returns:
            IntegerTypeData instance
        """
        return IntegerTypeData(
            dpcode=dpcode,
            min_value=min_val,
            max_value=max_val,
            scale=scale,
            step=step,
            unit=unit,
        )

    def create_enum_type(self, dpcode: str, range_values: List[str]) -> EnumTypeData:
        """
        Create an EnumTypeData instance.

        Args:
            dpcode: DPCode this applies to
            range_values: List of valid enum values

        Returns:
            EnumTypeData instance
        """
        return EnumTypeData(dpcode=dpcode, range_values=range_values)

    def scale_brightness(
        self,
        value: Union[int, float],
        device_min: int = 10,
        device_max: int = 1000,
        target_min: int = 0,
        target_max: int = 255,
    ) -> int:
        """
        Scale brightness value between device and target ranges.

        Args:
            value: Brightness value to scale
            device_min: Device minimum brightness
            device_max: Device maximum brightness
            target_min: Target minimum brightness
            target_max: Target maximum brightness

        Returns:
            Scaled brightness value
        """
        return round(remap_value(value, device_min, device_max, target_min, target_max))

    def scale_color_temp(
        self,
        value: Union[int, float],
        device_min: int = 1000,
        device_max: int = 10000,
        use_mireds: bool = True,
    ) -> Union[int, float]:
        """
        Scale color temperature value.

        Args:
            value: Color temperature value
            device_min: Device minimum color temperature
            device_max: Device maximum color temperature
            use_mireds: Whether to convert to mireds

        Returns:
            Scaled color temperature value
        """
        if use_mireds:
            # Convert Kelvin to mireds: mireds = 1000000 / kelvin
            return round(1000000 / value)
        else:
            return round(remap_value(value, device_min, device_max, 1000, 10000))

    def convert_hsv_to_rgb(self, h: float, s: float, v: float) -> Tuple[int, int, int]:
        """
        Convert HSV color values to RGB.

        Args:
            h: Hue (0-360)
            s: Saturation (0-100)
            v: Value/Brightness (0-100)

        Returns:
            RGB tuple (r, g, b) with values 0-255
        """
        # Normalize to 0-1 range
        h = h / 360.0
        s = s / 100.0
        v = v / 100.0

        if s == 0:
            r = g = b = v
        else:
            i = int(h * 6.0)
            f = (h * 6.0) - i
            p = v * (1.0 - s)
            q = v * (1.0 - s * f)
            t = v * (1.0 - s * (1.0 - f))

            i = i % 6

            if i == 0:
                r, g, b = v, t, p
            elif i == 1:
                r, g, b = q, v, p
            elif i == 2:
                r, g, b = p, v, t
            elif i == 3:
                r, g, b = p, q, v
            elif i == 4:
                r, g, b = t, p, v
            elif i == 5:
                r, g, b = v, p, q

        return (int(r * 255), int(g * 255), int(b * 255))

    def convert_rgb_to_hsv(self, r: int, g: int, b: int) -> Tuple[float, float, float]:
        """
        Convert RGB color values to HSV.

        Args:
            r: Red (0-255)
            g: Green (0-255)
            b: Blue (0-255)

        Returns:
            HSV tuple (h, s, v) with h in 0-360, s and v in 0-100
        """
        # Normalize to 0-1 range
        r = r / 255.0
        g = g / 255.0
        b = b / 255.0

        max_val = max(r, g, b)
        min_val = min(r, g, b)
        diff = max_val - min_val

        # Value (brightness)
        v = max_val * 100

        # Saturation
        if max_val == 0:
            s = 0
        else:
            s = (diff / max_val) * 100

        # Hue
        if diff == 0:
            h = 0
        elif max_val == r:
            h = (60 * ((g - b) / diff) + 360) % 360
        elif max_val == g:
            h = (60 * ((b - r) / diff) + 120) % 360
        elif max_val == b:
            h = (60 * ((r - g) / diff) + 240) % 360

        return (h, s, v)

    def scale_color_hsv(
        self, h: float, s: float, v: float, color_type: str = "default"
    ) -> Tuple[int, int, int]:
        """
        Scale HSV color values according to device color type.

        Args:
            h: Hue value
            s: Saturation value
            v: Value/brightness value
            color_type: Color type ("default" or "default_v2")

        Returns:
            Scaled HSV tuple
        """
        if color_type not in self._color_types:
            color_type = "default"

        color_data = self._color_types[color_type]

        # Scale hue to device range
        h_scaled = round(remap_value(h, 0, 360, color_data.h_min, color_data.h_max))

        # Scale saturation to device range
        s_scaled = round(remap_value(s, 0, 100, color_data.s_min, color_data.s_max))

        # Scale value to device range
        v_scaled = round(remap_value(v, 0, 100, color_data.v_min, color_data.v_max))

        return (h_scaled, s_scaled, v_scaled)

    def get_common_brightness_ranges(self) -> Dict[str, Dict[str, int]]:
        """
        Get common brightness ranges for different device types.

        Returns:
            Dictionary of brightness ranges
        """
        return {
            "10_to_1000": {"min": 10, "max": 1000, "scale": 0},
            "25_to_255": {"min": 25, "max": 255, "scale": 0},
            "1_to_100": {"min": 1, "max": 100, "scale": 0},
            "0_to_255": {"min": 0, "max": 255, "scale": 0},
        }

    def get_common_color_temp_ranges(self) -> Dict[str, Dict[str, int]]:
        """
        Get common color temperature ranges for different device types.

        Returns:
            Dictionary of color temperature ranges
        """
        return {
            "cold_to_warm": {"min": 1000, "max": 10000},
            "mireds_range": {"min": 100, "max": 1000},
            "kelvin_range": {"min": 1000, "max": 10000},
        }

    def to_percentage(
        self,
        value: Union[int, float],
        device_min: int,
        device_max: int,
        clamp: bool = True,
    ) -> float:
        """
        Convert device value to percentage (0-100%).

        Args:
            value: Device value to convert
            device_min: Device minimum value
            device_max: Device maximum value
            clamp: Whether to clamp result to 0-100 range

        Returns:
            Percentage value (0-100)
        """
        percentage = remap_value(value, device_min, device_max, 0, 100)

        if clamp:
            return max(0, min(100, percentage))
        return percentage

    def from_percentage(
        self,
        percentage: Union[int, float],
        device_min: int,
        device_max: int,
        clamp: bool = True,
    ) -> int:
        """
        Convert percentage (0-100%) to device value.

        Args:
            percentage: Percentage value (0-100)
            device_min: Device minimum value
            device_max: Device maximum value
            clamp: Whether to clamp input percentage to 0-100 range

        Returns:
            Device value
        """
        if clamp:
            percentage = max(0, min(100, percentage))

        device_value = remap_value(percentage, 0, 100, device_min, device_max)
        return int(round(device_value))

    def validate_color_value(self, color_data: str) -> bool:
        """
        Validate color data format.

        Args:
            color_data: Color data string

        Returns:
            True if valid, False otherwise
        """
        try:
            # Try to parse as hex color
            if color_data.startswith("#") and len(color_data) == 7:
                int(color_data[1:], 16)
                return True

            # Try to parse as HSV format
            if color_data.startswith("hsv(") and color_data.endswith(")"):
                values = color_data[4:-1].split(",")
                if len(values) == 3:
                    h, s, v = [float(val.strip()) for val in values]
                    return 0 <= h <= 360 and 0 <= s <= 100 and 0 <= v <= 100

            return False
        except (ValueError, IndexError):
            return False


# Common scaling presets
BRIGHTNESS_PRESETS = {
    "lights_10_1000": IntegerTypeData("bright_value", 10, 1000, 0, 1),
    "lights_25_255": IntegerTypeData("bright_value", 25, 255, 0, 1),
    "lights_1_100": IntegerTypeData("bright_value", 1, 100, 0, 1),
    "dimmer_0_255": IntegerTypeData("bright_value", 0, 255, 0, 1),
}

COLOR_TEMP_PRESETS = {
    "warm_cool_1000_10000": IntegerTypeData("temp_value", 1000, 10000, 0, 1, "K"),
    "mireds_100_1000": IntegerTypeData("temp_value", 100, 1000, 0, 1, "mireds"),
}


# Utility functions for common percentage conversions
def brightness_to_percentage(
    brightness: Union[int, float], device_min: int = 10, device_max: int = 1000
) -> float:
    """
    Convert device brightness to percentage.

    Args:
        brightness: Device brightness value
        device_min: Device minimum brightness (default: 10)
        device_max: Device maximum brightness (default: 1000)

    Returns:
        Brightness as percentage (0-100)

    Example:
        >>> brightness_to_percentage(800, 10, 1000)
        78.8
    """
    return remap_value(brightness, device_min, device_max, 0, 100)


def percentage_to_brightness(
    percentage: Union[int, float], device_min: int = 10, device_max: int = 1000
) -> int:
    """
    Convert percentage to device brightness.

    Args:
        percentage: Brightness percentage (0-100)
        device_min: Device minimum brightness (default: 10)
        device_max: Device maximum brightness (default: 1000)

    Returns:
        Device brightness value

    Example:
        >>> percentage_to_brightness(78, 10, 1000)
        782
    """
    device_value = remap_value(percentage, 0, 100, device_min, device_max)
    return int(round(device_value))


def humidity_to_percentage(
    humidity: Union[int, float], device_min: int = 0, device_max: int = 100
) -> float:
    """
    Convert device humidity to percentage.

    Args:
        humidity: Device humidity value
        device_min: Device minimum humidity (default: 0)
        device_max: Device maximum humidity (default: 100)

    Returns:
        Humidity as percentage (0-100)
    """
    return remap_value(humidity, device_min, device_max, 0, 100)


def battery_to_percentage(
    battery: Union[int, float], device_min: int = 0, device_max: int = 100
) -> float:
    """
    Convert device battery level to percentage.

    Args:
        battery: Device battery value
        device_min: Device minimum battery (default: 0)
        device_max: Device maximum battery (default: 100)

    Returns:
        Battery as percentage (0-100)
    """
    return remap_value(battery, device_min, device_max, 0, 100)


def cover_position_to_percentage(
    position: Union[int, float],
    device_min: int = 0,
    device_max: int = 100,
    inverted: bool = True,
) -> float:
    """
    Convert device cover position to percentage.

    Args:
        position: Device position value
        device_min: Device minimum position (default: 0)
        device_max: Device maximum position (default: 100)
        inverted: Whether device uses inverted range (0=open, 100=closed)

    Returns:
        Cover position as percentage (0=closed, 100=open)
    """
    return remap_value(position, device_min, device_max, 0, 100, reverse=inverted)


def percentage_to_cover_position(
    percentage: Union[int, float],
    device_min: int = 0,
    device_max: int = 100,
    inverted: bool = True,
) -> int:
    """
    Convert percentage to device cover position.

    Args:
        percentage: Position percentage (0=closed, 100=open)
        device_min: Device minimum position (default: 0)
        device_max: Device maximum position (default: 100)
        inverted: Whether device uses inverted range (0=open, 100=closed)

    Returns:
        Device position value
    """
    device_value = remap_value(percentage, 0, 100, device_min, device_max, reverse=inverted)
    return int(round(device_value))


@dataclass
class ElectricityTypeData:
    """
    Handles base64-encoded electrical measurements (voltage, current, power).

    This class decodes base64 electrical data from Tuya devices using struct.unpack
    patterns observed in Home Assistant and other Tuya integrations.
    """

    dpcode: str
    unit: Optional[str] = None
    format_type: str = "standard"  # standard, compact, extended

    @staticmethod
    def decode_electrical_data(data: str) -> Dict[str, float]:
        """
        Decode base64 electrical data into voltage, current, and power values.

        Args:
            data: Base64 encoded electrical data string

        Returns:
            Dictionary with 'voltage', 'current', and 'power' values

        Raises:
            ValueError: If data is invalid or cannot be decoded
        """
        import base64
        import struct

        if not data or not isinstance(data, str):
            raise ValueError("Invalid electrical data: empty or non-string input")

        try:
            # Decode base64 data
            raw = base64.b64decode(data)

            if len(raw) < 8:
                raise ValueError(f"Insufficient data length: {len(raw)} bytes, expected at least 8")

            # Standard format: voltage (2 bytes), current (3 bytes), power (3 bytes)
            # Based on Home Assistant's sensor.py pattern
            voltage = struct.unpack(">H", raw[0:2])[0] / 10.0  # 16-bit voltage, divide by 10
            current = (
                struct.unpack(">L", b"\x00" + raw[2:5])[0] / 1000.0
            )  # 24-bit current, divide by 1000
            power = (
                struct.unpack(">L", b"\x00" + raw[5:8])[0] / 1000.0
            )  # 24-bit power, divide by 1000

            return {"voltage": voltage, "current": current, "power": power}

        except (base64.binascii.Error, struct.error) as e:
            raise ValueError(f"Failed to decode electrical data: {e}")
        except Exception as e:
            raise ValueError(f"Unexpected error decoding electrical data: {e}")

    @staticmethod
    def detect_electrical_dpcode(dpcode: str) -> Optional[str]:
        """
        Detect electrical measurement type from DPCode.

        Args:
            dpcode: DPCode string to analyze

        Returns:
            Electrical type ('voltage', 'current', 'power', 'energy') or None
        """
        dpcode_lower = dpcode.lower()

        # Check specific patterns first (more specific matches)
        if "voltage" in dpcode_lower or "volt" in dpcode_lower:
            return "voltage"
        elif "current" in dpcode_lower or "amp" in dpcode_lower:
            return "current"
        elif "power" in dpcode_lower or "watt" in dpcode_lower:
            return "power"
        elif "energy" in dpcode_lower or "kwh" in dpcode_lower:
            return "energy"

        # Check general electrical patterns
        electrical_patterns = DPCODE_PATTERNS.get("electrical", [])
        if any(pattern in dpcode_lower for pattern in electrical_patterns):
            return "electrical"  # Generic electrical measurement

        return None

    def get_unit(self, measurement_type: Optional[str] = None) -> str:
        """
        Get appropriate unit for the measurement type.

        Args:
            measurement_type: Type of electrical measurement

        Returns:
            Unit string (V, A, W, kWh)
        """
        if self.unit:
            return self.unit

        if measurement_type:
            unit_map = {
                "voltage": "V",
                "current": "A",
                "power": "W",
                "energy": "kWh",
            }
            return unit_map.get(measurement_type, "V")

        # Try to detect from dpcode
        detected_type = self.detect_electrical_dpcode(self.dpcode)
        if detected_type:
            return self.get_unit(detected_type)

        return "V"  # Default to voltage


class CentralizedDeviceScaling:
    """
    Centralized scaling interface that eliminates duplication across device classes.

    This interface replaces scattered scaling methods in:
    - device_types.py (_scale_brightness_to_percentage, _scale_color_temperature, etc.)
    - intelligent_device.py (_scale_value)
    - capability_translator.py (scale_value)

    All scaling logic is now centralized here for consistency and maintainability.
    """

    def __init__(self):
        """Initialize centralized scaling."""
        self._scaling_manager = ValueScalingManager()

    def scale_brightness_value(
        self,
        raw_value: Any,
        capability: str = "bright_value",
        mapping_info: Optional[Dict[str, Any]] = None,
        target_range: Tuple[int, int] = (0, 100),
    ) -> int:
        """
        Centralized brightness scaling that replaces device_types._scale_brightness_to_percentage.

        Args:
            raw_value: Raw device brightness value
            capability: Capability name for context
            mapping_info: DPS mapping information with scaling_info
            target_range: Target output range (default 0-100 for percentage)

        Returns:
            Scaled brightness value as integer
        """
        try:
            if mapping_info and mapping_info.get("scaling_info"):
                # Use device-specific scaling info
                scale_info = mapping_info["scaling_info"]
                min_val = scale_info.get("min", 10)
                max_val = scale_info.get("max", 1000)

                # Scale to target range
                scaled = remap_value(
                    raw_value,
                    min_val,
                    max_val,
                    target_range[0],
                    target_range[1],
                )
                return int(max(target_range[0], min(target_range[1], scaled)))
            else:
                # Use intelligence scaling manager
                try:
                    scaled = self._scaling_manager.scale_brightness(
                        raw_value,
                        device_min=10,
                        device_max=1000,
                        target_min=target_range[0],
                        target_max=target_range[1],
                    )
                    return int(scaled)
                except Exception:
                    # Fallback to default brightness scaling (10-1000 range)
                    scaled = remap_value(raw_value, 10, 1000, target_range[0], target_range[1])
                    return int(max(target_range[0], min(target_range[1], scaled)))
        except Exception:
            return int(raw_value) if isinstance(raw_value, (int, float)) else 0

    def scale_color_temperature_value(
        self,
        raw_value: Any,
        capability: str = "temp_value",
        mapping_info: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Centralized color temperature scaling that replaces device_types._scale_color_temperature.

        Args:
            raw_value: Raw device color temperature value
            capability: Capability name for context
            mapping_info: DPS mapping information

        Returns:
            Color temperature in Kelvin
        """
        try:
            # Most devices use Kelvin directly, some need conversion
            if mapping_info and mapping_info.get("scaling_info"):
                scale_info = mapping_info["scaling_info"]
                if scale_info.get("unit") == "mireds":
                    # Convert mireds to Kelvin: K = 1000000 / mireds
                    return int(1000000 / max(1, raw_value))
                elif scale_info.get("scale_factor"):
                    return int(raw_value * scale_info["scale_factor"])

            # Use intelligence scaling manager
            try:
                scaled = self._scaling_manager.scale_color_temp(raw_value, use_mireds=False)
                return int(scaled)
            except Exception:
                # Default: assume Kelvin
                return int(raw_value)
        except Exception:
            return 3000  # Default warm white

    def scale_electrical_value(
        self,
        raw_value: Any,
        capability: str,
        electrical_type: str,  # 'power', 'voltage', 'current'
        mapping_info: Optional[Dict[str, Any]] = None,
    ) -> float:
        """
        Centralized electrical value scaling that replaces device_types._scale_power_value,
        _scale_voltage_value, _scale_current_value.

        Args:
            raw_value: Raw electrical value
            capability: Capability name
            electrical_type: Type of electrical measurement
            mapping_info: DPS mapping information

        Returns:
            Scaled electrical value as float
        """
        try:
            default_scales = {
                "power": 1.0,  # Most devices report watts
                "voltage": 1.0,  # Most devices report volts
                "current": 0.001,  # Most devices report mA, convert to A
            }

            if mapping_info and mapping_info.get("scaling_info"):
                scale_factor = mapping_info["scaling_info"].get(
                    "scale", default_scales.get(electrical_type, 1.0)
                )
            else:
                scale_factor = default_scales.get(electrical_type, 1.0)

            return float(raw_value) * scale_factor
        except Exception:
            return 0.0

    def scale_temperature_value(
        self,
        raw_value: Any,
        capability: str = "temp_current",
        mapping_info: Optional[Dict[str, Any]] = None,
        target_unit: str = "celsius",
    ) -> float:
        """
        Centralized temperature scaling that replaces device_types._scale_temperature_value.

        Args:
            raw_value: Raw temperature value
            capability: Capability name
            mapping_info: DPS mapping information
            target_unit: Target temperature unit

        Returns:
            Scaled temperature value as float
        """
        try:
            if mapping_info and mapping_info.get("scaling_info"):
                scale_info = mapping_info["scaling_info"]
                scale_factor = scale_info.get("scale", 1.0)
                offset = scale_info.get("offset", 0.0)
                result = float(raw_value) * scale_factor + offset

                # Handle unit conversion if needed
                source_unit = scale_info.get("unit", "celsius")
                if source_unit != target_unit:
                    result = self._convert_temperature(result, source_unit, target_unit)

                return result
            else:
                # Use intelligence scaling with temperature special case
                try:
                    # Create IntegerTypeData for temperature scaling
                    temp_data = IntegerTypeData(
                        dpcode=capability,
                        min_value=0,
                        max_value=1000,
                        scale=1,
                        step=1,
                    )
                    return temp_data.scale_value(raw_value)
                except Exception:
                    return float(raw_value)
        except Exception:
            return 0.0

    def scale_temperature_for_device(
        self,
        temperature: float,
        capability: str = "temp_set",
        mapping_info: Optional[Dict[str, Any]] = None,
        source_unit: str = "celsius",
    ) -> Any:
        """
        Centralized temperature scaling for device storage that replaces
        device_types._scale_temperature_for_device.

        Args:
            temperature: Temperature value to scale for device
            capability: Capability name
            mapping_info: DPS mapping information
            source_unit: Source temperature unit

        Returns:
            Device-scaled temperature value
        """
        try:
            if mapping_info and mapping_info.get("scaling_info"):
                scale_info = mapping_info["scaling_info"]

                # Handle unit conversion if needed
                device_unit = scale_info.get("unit", "celsius")
                temp_value = temperature
                if source_unit != device_unit:
                    temp_value = self._convert_temperature(temperature, source_unit, device_unit)

                scale_factor = scale_info.get("scale", 1.0)
                offset = scale_info.get("offset", 0.0)
                return int((temp_value - offset) / scale_factor)
            else:
                # Use intelligence scaling
                try:
                    # Create IntegerTypeData for reverse temperature scaling
                    temp_data = IntegerTypeData(
                        dpcode=capability,
                        min_value=0,
                        max_value=1000,
                        scale=1,
                        step=1,
                    )
                    return temp_data.scale_value_back(temperature)
                except Exception:
                    return int(temperature)
        except Exception:
            return int(temperature)

    def _convert_temperature(self, value: float, from_unit: str, to_unit: str) -> float:
        """Convert temperature between units."""
        if from_unit == to_unit:
            return value

        # Convert to Celsius first
        if from_unit.lower() in ["fahrenheit", "f"]:
            celsius = (value - 32) * 5 / 9
        elif from_unit.lower() in ["kelvin", "k"]:
            celsius = value - 273.15
        else:
            celsius = value  # Assume already Celsius

        # Convert from Celsius to target
        if to_unit.lower() in ["fahrenheit", "f"]:
            return celsius * 9 / 5 + 32
        elif to_unit.lower() in ["kelvin", "k"]:
            return celsius + 273.15
        else:
            return celsius  # Return Celsius

    def scale_any_value(
        self,
        raw_value: Any,
        capability: str,
        mapping_info: Optional[Dict[str, Any]] = None,
        scaling_type: Optional[str] = None,
        target_range: Optional[Tuple[Union[int, float], Union[int, float]]] = None,
        inverse: bool = False,
    ) -> Any:
        """
        Universal scaling method that replaces intelligent_device._scale_value and
        capability_translator.scale_value.

        Args:
            raw_value: Raw value to scale
            capability: Capability name
            mapping_info: DPS mapping information
            scaling_type: Type of scaling to apply (brightness, temperature, etc.)
            target_range: Target output range
            inverse: Whether to scale inverse (device -> user format)

        Returns:
            Scaled value
        """
        try:
            # Auto-detect scaling type if not provided
            if not scaling_type:
                scaling_type = self._detect_scaling_type(capability)

            # Route to specialized scaling methods
            if scaling_type == "brightness":
                if target_range:
                    return self.scale_brightness_value(
                        raw_value, capability, mapping_info, target_range
                    )
                else:
                    return self.scale_brightness_value(raw_value, capability, mapping_info)

            elif scaling_type == "temperature":
                return self.scale_temperature_value(raw_value, capability, mapping_info)

            elif scaling_type == "color_temperature":
                return self.scale_color_temperature_value(raw_value, capability, mapping_info)

            elif scaling_type in ["power", "voltage", "current"]:
                return self.scale_electrical_value(
                    raw_value, capability, scaling_type, mapping_info
                )

            else:
                # Fallback to intelligence system
                try:
                    if scaling_type == "generic" and target_range:
                        # Simple range remapping
                        if mapping_info and mapping_info.get("scaling_info"):
                            scale_info = mapping_info["scaling_info"]
                            min_val = scale_info.get("min", 0)
                            max_val = scale_info.get("max", 100)
                            return remap_value(
                                raw_value,
                                min_val,
                                max_val,
                                target_range[0],
                                target_range[1],
                            )

                    return raw_value
                except Exception:
                    return raw_value
        except Exception:
            # Fallback to original value
            return raw_value

    def _detect_scaling_type(self, capability: str) -> str:
        """Auto-detect scaling type based on capability name."""
        capability_lower = capability.lower()

        for scale_type, patterns in DPCODE_PATTERNS.items():
            if any(pattern in capability_lower for pattern in patterns):
                return scale_type

        # Special cases
        if any(term in capability_lower for term in ["power", "watt"]):
            return "power"
        elif any(term in capability_lower for term in ["voltage", "volt"]):
            return "voltage"
        elif any(term in capability_lower for term in ["current", "amp"]):
            return "current"
        elif "color_temp" in capability_lower or "temp_value" in capability_lower:
            return "color_temperature"

        return "generic"


# Default instances for easy access
scaling_manager = ValueScalingManager()
centralized_scaling = CentralizedDeviceScaling()
