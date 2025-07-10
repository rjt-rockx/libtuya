"""
Value scaling and conversion logic for Tuya devices.

This module contains the scaling and conversion logic extracted from Home Assistant's
Tuya integration for handling device value transformations.
"""

import json
import math
from typing import Dict, List, Optional, Union, Any, Tuple
from pathlib import Path
from dataclasses import dataclass


@dataclass
class IntegerTypeData:
    """
    Handles scaling for integer values.

    Equivalent to Home Assistant's IntegerTypeData class.
    """

    dpcode: str
    min_value: int
    max_value: int
    scale: int = 0
    step: int = 1
    unit: Optional[str] = None
    type_info: Optional[str] = None

    def scale_value(self, value: Union[int, float]) -> float:
        """
        Scale a raw device value to the proper range.

        Args:
            value: Raw device value

        Returns:
            Scaled value
        """
        return value / (10**self.scale)

    def scale_value_back(self, value: Union[int, float]) -> int:
        """
        Scale a value back to device range.

        Args:
            value: Scaled value

        Returns:
            Raw device value
        """
        return int(value * (10**self.scale))

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

    def is_valid_value(self, value: str) -> bool:
        """
        Check if a value is valid for this enum.

        Args:
            value: Value to check

        Returns:
            True if valid, False otherwise
        """
        return value in self.range_values

    def get_valid_values(self) -> List[str]:
        """
        Get all valid values for this enum.

        Returns:
            List of valid values
        """
        return self.range_values.copy()


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

    Args:
        value: Value to remap
        from_min: Source minimum value
        from_max: Source maximum value
        to_min: Target minimum value
        to_max: Target maximum value
        reverse: Whether to reverse the mapping

    Returns:
        Remapped value
    """
    if reverse:
        value = from_max - value + from_min

    return ((value - from_min) / (from_max - from_min)) * (to_max - to_min) + to_min


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
        intelligence_dir = Path(__file__).parent.parent.parent / "intelligence"
        scaling_file = intelligence_dir / "scaling_rules.json"

        with open(scaling_file, "r") as f:
            self._scaling_data = json.load(f)

        # Initialize color type data
        self._initialize_color_types()

    def _initialize_color_types(self) -> None:
        """Initialize color type data structures."""
        color_data = self._scaling_data.get("color_scaling", {})

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

# Default instance for easy access
scaling_manager = ValueScalingManager()
