"""
Specialized Device Type Classes for libtuya.

This module provides specialized device classes that extend IntelligentDevice
with device-specific methods and proper value scaling for common device types.
"""

import logging
from typing import Dict, List, Optional, Any, Union, Tuple
from abc import ABC, abstractmethod

from .intelligent_device import IntelligentDevice, DeviceCapability, DeviceStatus
from ..auth.models import DeviceInfo
from ..intelligence import DeviceIntelligence
from ..dps import DPSMapper

logger = logging.getLogger(__name__)


class IntelligentLight(IntelligentDevice):
    """
    Intelligent light device with advanced lighting control capabilities.

    Supports brightness, color, color temperature, and scene control for all
    types of smart lights including bulbs, strips, and ceiling lights.
    """

    def __init__(
        self,
        device_info: DeviceInfo,
        intelligence: DeviceIntelligence,
        dps_mapper: DPSMapper,
        **kwargs,
    ):
        """Initialize intelligent light device."""
        super().__init__(device_info, intelligence, dps_mapper, **kwargs)

        # Light-specific capability mappings
        self.brightness_capabilities = [
            "bright_value",
            "bright_value_v2",
            "bright_value_1",
        ]
        self.color_capabilities = ["colour_data", "colour_data_v2", "colour_data_hsv"]
        self.color_temp_capabilities = ["temp_value", "temp_value_v2"]
        self.switch_capabilities = ["switch_led", "switch", "switch_1"]
        self.mode_capabilities = ["work_mode", "mode", "scene"]

        # Light state tracking
        self._last_brightness = None
        self._last_color = None
        self._last_color_temp = None
        self._supported_modes = None

    @property
    def is_on(self) -> bool:
        """Check if light is currently on."""
        for switch_cap in self.switch_capabilities:
            if switch_cap in self.dps_mappings:
                return bool(self.get_capability(switch_cap))
        return False

    @property
    def brightness(self) -> Optional[int]:
        """Get current brightness as percentage (0-100)."""
        for brightness_cap in self.brightness_capabilities:
            if brightness_cap in self.dps_mappings:
                raw_value = self.get_capability(brightness_cap)
                if raw_value is not None:
                    return self._scale_brightness_to_percentage(
                        brightness_cap, raw_value
                    )
        return None

    @property
    def color_rgb(self) -> Optional[Tuple[int, int, int]]:
        """Get current color as RGB tuple."""
        for color_cap in self.color_capabilities:
            if color_cap in self.dps_mappings:
                raw_value = self.get_capability(color_cap)
                if raw_value is not None:
                    return self._parse_color_value(color_cap, raw_value)
        return None

    @property
    def color_temperature(self) -> Optional[int]:
        """Get current color temperature in Kelvin."""
        for temp_cap in self.color_temp_capabilities:
            if temp_cap in self.dps_mappings:
                raw_value = self.get_capability(temp_cap)
                if raw_value is not None:
                    return self._scale_color_temperature(temp_cap, raw_value)
        return None

    @property
    def supported_features(self) -> Dict[str, bool]:
        """Get supported light features."""
        return {
            "brightness": any(
                cap in self.dps_mappings for cap in self.brightness_capabilities
            ),
            "color": any(cap in self.dps_mappings for cap in self.color_capabilities),
            "color_temperature": any(
                cap in self.dps_mappings for cap in self.color_temp_capabilities
            ),
            "modes": any(cap in self.dps_mappings for cap in self.mode_capabilities),
            "switch": any(cap in self.dps_mappings for cap in self.switch_capabilities),
        }

    def set_brightness(
        self, brightness: int, transition_time: Optional[int] = None
    ) -> bool:
        """
        Set brightness with optional transition time.

        Args:
            brightness: Brightness percentage (0-100)
            transition_time: Transition time in milliseconds (if supported)

        Returns:
            True if successful, False otherwise
        """
        if not (0 <= brightness <= 100):
            raise ValueError("Brightness must be between 0 and 100")

        success = self.set_brightness_percentage(brightness)
        if success:
            self._last_brightness = brightness

        return success

    def set_color_hsv(self, h: int, s: int, v: int) -> bool:
        """
        Set color using HSV values.

        Args:
            h: Hue (0-360)
            s: Saturation (0-100)
            v: Value/Brightness (0-100)

        Returns:
            True if successful, False otherwise
        """
        if not (0 <= h <= 360 and 0 <= s <= 100 and 0 <= v <= 100):
            raise ValueError("HSV values out of range")

        # Convert HSV to RGB first
        import colorsys

        r, g, b = colorsys.hsv_to_rgb(h / 360.0, s / 100.0, v / 100.0)
        r, g, b = int(r * 255), int(g * 255), int(b * 255)

        success = self.set_color_rgb(r, g, b)
        if success:
            self._last_color = (r, g, b)

        return success

    def set_color_hex(self, hex_color: str) -> bool:
        """
        Set color using hex string.

        Args:
            hex_color: Hex color string (e.g., "#FF0000" or "FF0000")

        Returns:
            True if successful, False otherwise
        """
        # Remove # if present
        hex_color = hex_color.lstrip("#")

        if len(hex_color) != 6:
            raise ValueError("Hex color must be 6 characters")

        try:
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)

            return self.set_color_rgb(r, g, b)
        except ValueError:
            raise ValueError("Invalid hex color format")

    def set_scene(self, scene_name: str) -> bool:
        """
        Set light to a predefined scene.

        Args:
            scene_name: Scene name (e.g., "read", "relax", "bright")

        Returns:
            True if successful, False otherwise
        """
        # Map scene names to device values
        scene_mappings = {
            "white": "white",
            "colour": "colour",
            "scene": "scene",
            "music": "music",
            "read": "read",
            "relax": "relax",
            "bright": "bright",
            "night": "night",
            "warm": "warm",
            "cold": "cold",
        }

        scene_value = scene_mappings.get(scene_name.lower(), scene_name)

        # Try to set scene via work mode
        for mode_cap in self.mode_capabilities:
            if mode_cap in self.dps_mappings:
                return self.set_capability(mode_cap, scene_value)

        logger.warning(f"Scene capability not found for light {self.device_info.id}")
        return False

    async def pulse_light(self, duration: int = 3, brightness: int = 100) -> bool:
        """
        Pulse the light for a specified duration.

        Args:
            duration: Pulse duration in seconds
            brightness: Maximum brightness during pulse

        Returns:
            True if successful, False otherwise
        """
        import asyncio

        original_brightness = self.brightness
        original_state = self.is_on

        try:
            # Turn on and set brightness
            if not self.turn_on():
                return False

            if not self.set_brightness(brightness):
                return False

            # Wait for pulse duration (non-blocking)
            await asyncio.sleep(duration)

            # Restore original state
            if original_state:
                if original_brightness is not None:
                    self.set_brightness(original_brightness)
            else:
                self.turn_off()

            return True

        except Exception as e:
            logger.error(f"Light pulse failed: {e}")
            return False

    def _scale_brightness_to_percentage(self, capability: str, raw_value: Any) -> int:
        """Convert raw brightness value to percentage."""
        try:
            mapping_info = self.dps_mappings.get(capability)
            if mapping_info:
                # Use HA intelligence for proper inverse scaling
                try:
                    percentage = self.intelligence.scale_value(
                        dpcode=capability,
                        value=raw_value,
                        device_category=self.device_info.category,
                        output_range=(0, 100),  # Output is percentage
                        scaling_type="brightness",
                        inverse=True,  # Convert from device value to percentage
                    )
                    return int(percentage)
                except Exception as e:
                    logger.warning(f"HA inverse scaling failed for {capability}: {e}")
                    # Fall back to manual scaling
                    if mapping_info.scaling_info:
                        min_val = mapping_info.scaling_info.get("min", 10)
                        max_val = mapping_info.scaling_info.get("max", 1000)
                        return int((raw_value - min_val) / (max_val - min_val) * 100)

            # Default scaling (10-1000 range)
            return int((raw_value - 10) / 990 * 100)
        except Exception:
            return int(raw_value) if isinstance(raw_value, (int, float)) else 0

    def _parse_color_value(
        self, capability: str, raw_value: Any
    ) -> Optional[Tuple[int, int, int]]:
        """Parse raw color value to RGB tuple."""
        try:
            if isinstance(raw_value, str):
                if raw_value.startswith("#"):
                    # Hex format
                    hex_color = raw_value[1:]
                    r = int(hex_color[0:2], 16)
                    g = int(hex_color[2:4], 16)
                    b = int(hex_color[4:6], 16)
                    return (r, g, b)
                elif "hsv" in capability.lower():
                    # HSV format parsing would go here
                    # This is a simplified example
                    return None

            # If it's a dict with h, s, v values
            elif isinstance(raw_value, dict):
                if all(key in raw_value for key in ["h", "s", "v"]):
                    import colorsys

                    h, s, v = raw_value["h"], raw_value["s"], raw_value["v"]
                    r, g, b = colorsys.hsv_to_rgb(h / 360.0, s / 100.0, v / 100.0)
                    return (int(r * 255), int(g * 255), int(b * 255))

            return None
        except Exception:
            return None

    def _scale_color_temperature(self, capability: str, raw_value: Any) -> int:
        """Scale raw color temperature value to Kelvin."""
        try:
            # Most devices use Kelvin directly
            return int(raw_value)
        except Exception:
            return 3000  # Default warm white


class IntelligentSwitch(IntelligentDevice):
    """
    Intelligent switch device with multi-channel support and power monitoring.

    Supports single and multi-channel switches, smart plugs, and power monitoring.
    """

    def __init__(
        self,
        device_info: DeviceInfo,
        intelligence: DeviceIntelligence,
        dps_mapper: DPSMapper,
        **kwargs,
    ):
        """Initialize intelligent switch device."""
        super().__init__(device_info, intelligence, dps_mapper, **kwargs)

        # Switch-specific capability mappings
        self.switch_capabilities = [
            "switch",
            "switch_1",
            "switch_2",
            "switch_3",
            "switch_4",
        ]
        self.power_capabilities = ["cur_power", "power", "add_ele"]
        self.voltage_capabilities = ["cur_voltage", "voltage"]
        self.current_capabilities = ["cur_current", "current"]

        # Detect number of channels
        self.channel_count = self._detect_channel_count()

    @property
    def is_on(self) -> bool:
        """Check if main switch is on."""
        return bool(self.get_capability("switch"))

    @property
    def power_consumption(self) -> Optional[float]:
        """Get current power consumption in watts."""
        for power_cap in self.power_capabilities:
            if power_cap in self.dps_mappings:
                raw_value = self.get_capability(power_cap)
                if raw_value is not None:
                    return self._scale_power_value(power_cap, raw_value)
        return None

    @property
    def voltage(self) -> Optional[float]:
        """Get current voltage."""
        for voltage_cap in self.voltage_capabilities:
            if voltage_cap in self.dps_mappings:
                raw_value = self.get_capability(voltage_cap)
                if raw_value is not None:
                    return self._scale_voltage_value(voltage_cap, raw_value)
        return None

    @property
    def current(self) -> Optional[float]:
        """Get current amperage."""
        for current_cap in self.current_capabilities:
            if current_cap in self.dps_mappings:
                raw_value = self.get_capability(current_cap)
                if raw_value is not None:
                    return self._scale_current_value(current_cap, raw_value)
        return None

    @property
    def channel_states(self) -> Dict[int, bool]:
        """Get state of all channels."""
        states = {}
        for i in range(1, self.channel_count + 1):
            if i == 1:
                cap_name = "switch"
            else:
                cap_name = f"switch_{i}"

            if cap_name in self.dps_mappings:
                states[i] = bool(self.get_capability(cap_name))

        return states

    def turn_on_channel(self, channel: int = 1) -> bool:
        """
        Turn on a specific channel.

        Args:
            channel: Channel number (1-based)

        Returns:
            True if successful, False otherwise
        """
        if not (1 <= channel <= self.channel_count):
            raise ValueError(f"Channel must be between 1 and {self.channel_count}")

        if channel == 1:
            cap_name = "switch"
        else:
            cap_name = f"switch_{channel}"

        if cap_name in self.dps_mappings:
            return self.set_capability(cap_name, True)

        logger.warning(f"Channel {channel} not found on switch {self.device_info.id}")
        return False

    def turn_off_channel(self, channel: int = 1) -> bool:
        """
        Turn off a specific channel.

        Args:
            channel: Channel number (1-based)

        Returns:
            True if successful, False otherwise
        """
        if not (1 <= channel <= self.channel_count):
            raise ValueError(f"Channel must be between 1 and {self.channel_count}")

        if channel == 1:
            cap_name = "switch"
        else:
            cap_name = f"switch_{channel}"

        if cap_name in self.dps_mappings:
            return self.set_capability(cap_name, False)

        logger.warning(f"Channel {channel} not found on switch {self.device_info.id}")
        return False

    def toggle_channel(self, channel: int = 1) -> bool:
        """
        Toggle a specific channel.

        Args:
            channel: Channel number (1-based)

        Returns:
            True if successful, False otherwise
        """
        current_state = self.channel_states.get(channel, False)
        if current_state:
            return self.turn_off_channel(channel)
        else:
            return self.turn_on_channel(channel)

    def turn_on_all_channels(self) -> bool:
        """
        Turn on all channels.

        Returns:
            True if all successful, False otherwise
        """
        success = True
        for channel in range(1, self.channel_count + 1):
            if not self.turn_on_channel(channel):
                success = False
        return success

    def turn_off_all_channels(self) -> bool:
        """
        Turn off all channels.

        Returns:
            True if all successful, False otherwise
        """
        success = True
        for channel in range(1, self.channel_count + 1):
            if not self.turn_off_channel(channel):
                success = False
        return success

    def get_power_stats(self) -> Dict[str, Any]:
        """Get comprehensive power statistics."""
        return {
            "power_watts": self.power_consumption,
            "voltage_volts": self.voltage,
            "current_amps": self.current,
            "supported_monitoring": {
                "power": any(
                    cap in self.dps_mappings for cap in self.power_capabilities
                ),
                "voltage": any(
                    cap in self.dps_mappings for cap in self.voltage_capabilities
                ),
                "current": any(
                    cap in self.dps_mappings for cap in self.current_capabilities
                ),
            },
        }

    def _detect_channel_count(self) -> int:
        """Detect number of switch channels."""
        count = 0
        for cap in self.switch_capabilities:
            if cap in self.dps_mappings:
                count += 1
        return max(1, count)

    def _scale_power_value(self, capability: str, raw_value: Any) -> float:
        """Scale raw power value to watts."""
        try:
            # Most devices report power in watts, but some use 0.1W units
            mapping_info = self.dps_mappings.get(capability)
            if mapping_info and mapping_info.scaling_info:
                scale_factor = mapping_info.scaling_info.get("scale", 1.0)
                return float(raw_value) * scale_factor
            else:
                return float(raw_value)
        except Exception:
            return 0.0

    def _scale_voltage_value(self, capability: str, raw_value: Any) -> float:
        """Scale raw voltage value to volts."""
        try:
            # Most devices report voltage in volts, but some use 0.1V units
            mapping_info = self.dps_mappings.get(capability)
            if mapping_info and mapping_info.scaling_info:
                scale_factor = mapping_info.scaling_info.get("scale", 1.0)
                return float(raw_value) * scale_factor
            else:
                return float(raw_value)
        except Exception:
            return 0.0

    def _scale_current_value(self, capability: str, raw_value: Any) -> float:
        """Scale raw current value to amps."""
        try:
            # Most devices report current in mA, convert to A
            mapping_info = self.dps_mappings.get(capability)
            if mapping_info and mapping_info.scaling_info:
                scale_factor = mapping_info.scaling_info.get("scale", 0.001)
                return float(raw_value) * scale_factor
            else:
                return float(raw_value) * 0.001  # Default mA to A conversion
        except Exception:
            return 0.0


class IntelligentClimate(IntelligentDevice):
    """
    Intelligent climate device for thermostats, heaters, and air conditioners.

    Supports temperature control, mode switching, and humidity monitoring.
    """

    def __init__(
        self,
        device_info: DeviceInfo,
        intelligence: DeviceIntelligence,
        dps_mapper: DPSMapper,
        **kwargs,
    ):
        """Initialize intelligent climate device."""
        super().__init__(device_info, intelligence, dps_mapper, **kwargs)

        # Climate-specific capability mappings
        self.temperature_capabilities = ["temp_set", "temp_current", "temp_value"]
        self.humidity_capabilities = [
            "humidity_set",
            "humidity_current",
            "humidity_value",
        ]
        self.mode_capabilities = ["mode", "work_mode", "fan_mode"]
        self.switch_capabilities = ["switch", "power"]

        # Common climate modes
        self.supported_modes = ["auto", "cool", "heat", "dry", "fan_only", "off"]

    @property
    def current_temperature(self) -> Optional[float]:
        """Get current temperature."""
        for temp_cap in self.temperature_capabilities:
            if "current" in temp_cap and temp_cap in self.dps_mappings:
                raw_value = self.get_capability(temp_cap)
                if raw_value is not None:
                    return self._scale_temperature_value(temp_cap, raw_value)
        return None

    @property
    def target_temperature(self) -> Optional[float]:
        """Get target temperature."""
        for temp_cap in self.temperature_capabilities:
            if "set" in temp_cap and temp_cap in self.dps_mappings:
                raw_value = self.get_capability(temp_cap)
                if raw_value is not None:
                    return self._scale_temperature_value(temp_cap, raw_value)
        return None

    @property
    def current_humidity(self) -> Optional[float]:
        """Get current humidity percentage."""
        for humidity_cap in self.humidity_capabilities:
            if "current" in humidity_cap and humidity_cap in self.dps_mappings:
                raw_value = self.get_capability(humidity_cap)
                if raw_value is not None:
                    return float(raw_value)
        return None

    @property
    def target_humidity(self) -> Optional[float]:
        """Get target humidity percentage."""
        for humidity_cap in self.humidity_capabilities:
            if "set" in humidity_cap and humidity_cap in self.dps_mappings:
                raw_value = self.get_capability(humidity_cap)
                if raw_value is not None:
                    return float(raw_value)
        return None

    @property
    def current_mode(self) -> Optional[str]:
        """Get current climate mode."""
        for mode_cap in self.mode_capabilities:
            if mode_cap in self.dps_mappings:
                raw_value = self.get_capability(mode_cap)
                if raw_value is not None:
                    return str(raw_value)
        return None

    def set_temperature(self, temperature: float) -> bool:
        """
        Set target temperature.

        Args:
            temperature: Target temperature in Celsius

        Returns:
            True if successful, False otherwise
        """
        for temp_cap in self.temperature_capabilities:
            if "set" in temp_cap and temp_cap in self.dps_mappings:
                # Scale temperature if needed
                scaled_temp = self._scale_temperature_for_device(temp_cap, temperature)
                return self.set_capability(temp_cap, scaled_temp)

        logger.warning(
            f"Temperature set capability not found for climate {self.device_info.id}"
        )
        return False

    def set_humidity(self, humidity: float) -> bool:
        """
        Set target humidity.

        Args:
            humidity: Target humidity percentage (0-100)

        Returns:
            True if successful, False otherwise
        """
        if not (0 <= humidity <= 100):
            raise ValueError("Humidity must be between 0 and 100")

        for humidity_cap in self.humidity_capabilities:
            if "set" in humidity_cap and humidity_cap in self.dps_mappings:
                return self.set_capability(humidity_cap, int(humidity))

        logger.warning(
            f"Humidity set capability not found for climate {self.device_info.id}"
        )
        return False

    def set_mode(self, mode: str) -> bool:
        """
        Set climate mode.

        Args:
            mode: Mode name (e.g., "auto", "cool", "heat", "dry", "fan_only")

        Returns:
            True if successful, False otherwise
        """
        for mode_cap in self.mode_capabilities:
            if mode_cap in self.dps_mappings:
                return self.set_capability(mode_cap, mode)

        logger.warning(f"Mode capability not found for climate {self.device_info.id}")
        return False

    def _scale_temperature_value(self, capability: str, raw_value: Any) -> float:
        """Scale raw temperature value to Celsius."""
        try:
            # Most devices use Celsius, but some use Fahrenheit or scaled values
            mapping_info = self.dps_mappings.get(capability)
            if mapping_info and mapping_info.scaling_info:
                scale_factor = mapping_info.scaling_info.get("scale", 1.0)
                offset = mapping_info.scaling_info.get("offset", 0.0)
                return float(raw_value) * scale_factor + offset
            else:
                return float(raw_value)
        except Exception:
            return 0.0

    def _scale_temperature_for_device(self, capability: str, temperature: float) -> Any:
        """Scale temperature for device storage."""
        try:
            mapping_info = self.dps_mappings.get(capability)
            if mapping_info and mapping_info.scaling_info:
                scale_factor = mapping_info.scaling_info.get("scale", 1.0)
                offset = mapping_info.scaling_info.get("offset", 0.0)
                return int((temperature - offset) / scale_factor)
            else:
                return int(temperature)
        except Exception:
            return int(temperature)


class IntelligentCover(IntelligentDevice):
    """
    Intelligent cover device for curtains, blinds, and shades.

    Supports open/close/stop control and position setting.
    """

    def __init__(
        self,
        device_info: DeviceInfo,
        intelligence: DeviceIntelligence,
        dps_mapper: DPSMapper,
        **kwargs,
    ):
        """Initialize intelligent cover device."""
        super().__init__(device_info, intelligence, dps_mapper, **kwargs)

        # Cover-specific capability mappings
        self.control_capabilities = ["control", "mach_operate"]
        self.position_capabilities = ["percent_control", "position"]
        self.mode_capabilities = ["mode", "work_mode"]

        # Cover control commands
        self.control_commands = {
            "open": "open",
            "close": "close",
            "stop": "stop",
            "pause": "pause",
        }

    @property
    def current_position(self) -> Optional[int]:
        """Get current position as percentage (0=closed, 100=open)."""
        for pos_cap in self.position_capabilities:
            if pos_cap in self.dps_mappings:
                raw_value = self.get_capability(pos_cap)
                if raw_value is not None:
                    return int(raw_value)
        return None

    @property
    def is_opening(self) -> bool:
        """Check if cover is currently opening."""
        current_control = self.get_capability("control")
        return current_control == "open" if current_control else False

    @property
    def is_closing(self) -> bool:
        """Check if cover is currently closing."""
        current_control = self.get_capability("control")
        return current_control == "close" if current_control else False

    @property
    def is_stopped(self) -> bool:
        """Check if cover is stopped."""
        current_control = self.get_capability("control")
        return current_control in ["stop", "pause"] if current_control else True

    def open_cover(self) -> bool:
        """
        Open the cover.

        Returns:
            True if successful, False otherwise
        """
        return self._send_control_command("open")

    def close_cover(self) -> bool:
        """
        Close the cover.

        Returns:
            True if successful, False otherwise
        """
        return self._send_control_command("close")

    def stop_cover(self) -> bool:
        """
        Stop the cover movement.

        Returns:
            True if successful, False otherwise
        """
        return self._send_control_command("stop")

    def set_position(self, position: int) -> bool:
        """
        Set cover position.

        Args:
            position: Position percentage (0=closed, 100=open)

        Returns:
            True if successful, False otherwise
        """
        if not (0 <= position <= 100):
            raise ValueError("Position must be between 0 and 100")

        for pos_cap in self.position_capabilities:
            if pos_cap in self.dps_mappings:
                return self.set_capability(pos_cap, position)

        logger.warning(f"Position capability not found for cover {self.device_info.id}")
        return False

    def _send_control_command(self, command: str) -> bool:
        """Send control command to cover."""
        device_command = self.control_commands.get(command, command)

        for control_cap in self.control_capabilities:
            if control_cap in self.dps_mappings:
                return self.set_capability(control_cap, device_command)

        logger.warning(f"Control capability not found for cover {self.device_info.id}")
        return False


# Factory function to create appropriate device type
def create_specialized_device(
    device_info: DeviceInfo,
    intelligence: DeviceIntelligence,
    dps_mapper: DPSMapper,
    **kwargs,
) -> IntelligentDevice:
    """
    Create a specialized device type based on device category.

    Args:
        device_info: Device information
        intelligence: Device intelligence
        dps_mapper: DPS mapper
        **kwargs: Additional arguments, including tinytuya_device_instance and entity_capabilities for multi-entity

    Returns:
        Specialized IntelligentDevice subclass
    """
    category = device_info.category

    # Light categories
    if category in ["dj", "dc", "dd", "dsd", "xdd", "tgkg", "tgq"]:
        return IntelligentLight(device_info, intelligence, dps_mapper, **kwargs)

    # Switch categories
    elif category in ["kg", "pc", "cz", "tdq"]:
        return IntelligentSwitch(device_info, intelligence, dps_mapper, **kwargs)

    # Climate categories
    elif category in ["kt", "qn", "wk", "wkf", "jsq", "cs"]:
        return IntelligentClimate(device_info, intelligence, dps_mapper, **kwargs)

    # Cover categories
    elif category in ["cl"]:
        return IntelligentCover(device_info, intelligence, dps_mapper, **kwargs)

    # Default to base IntelligentDevice
    else:
        return IntelligentDevice(device_info, intelligence, dps_mapper, **kwargs)
