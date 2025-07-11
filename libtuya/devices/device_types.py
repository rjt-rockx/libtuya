"""
Specialized Device Type Classes for libtuya.

This module provides specialized device classes that extend IntelligentDevice
with device-specific methods and proper value scaling for common device types.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from ..auth import TuyaAuthenticator
from ..auth.models import DeviceInfo
from ..dps import DPSMapper
from ..dps.capability_patterns import centralized_dps_mapping
from ..intelligence import DeviceIntelligence
from ..intelligence.quirks import centralized_quirks
from ..intelligence.scaling import centralized_scaling
from .intelligent_device import IntelligentDevice

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
        auth_manager: "TuyaAuthenticator",
        **kwargs,
    ):
        """Initialize intelligent light device."""
        super().__init__(device_info, intelligence, dps_mapper, auth_manager, **kwargs)

        # Light-specific capability mappings
        self.brightness_capabilities = [
            "bright_value",
            "bright_value_v2",
            "bright_value_1",
        ]
        self.color_capabilities = [
            "colour_data",
            "colour_data_v2",
            "colour_data_hsv",
        ]
        self.color_temp_capabilities = ["temp_value", "temp_value_v2"]
        self.switch_capabilities = ["switch_led", "switch", "switch_1"]
        self.mode_capabilities = ["work_mode", "mode", "scene"]

        # Light state tracking
        self._last_brightness = None
        self._last_color = None
        self._last_color_temp = None
        self._supported_modes = None

    @property
    def dps_mappings(self):
        """Access DPS mappings through capability translator."""
        return self.capability_translator.dps_mappings

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
                    return self._scale_brightness_to_percentage(brightness_cap, raw_value)
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
            "brightness": any(cap in self.dps_mappings for cap in self.brightness_capabilities),
            "color": any(cap in self.dps_mappings for cap in self.color_capabilities),
            "color_temperature": any(
                cap in self.dps_mappings for cap in self.color_temp_capabilities
            ),
            "modes": any(cap in self.dps_mappings for cap in self.mode_capabilities),
            "switch": any(cap in self.dps_mappings for cap in self.switch_capabilities),
        }

    def set_brightness(self, brightness: int, _transition_time: Optional[int] = None) -> bool:
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
        Set light to a predefined scene using LocalTuya scene intelligence.

        Args:
            scene_name: Scene name (e.g., "Night", "Read", "Meeting", "Soft", "Rainbow")

        Returns:
            True if successful, False otherwise
        """
        # Use the enhanced scene intelligence from the base class
        success = super().set_scene(scene_name)
        if success:
            return True

        # Fallback to simple scene mappings for basic light modes
        scene_mappings = {
            "white": "white",
            "colour": "colour",
            "color": "colour",
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

    def get_available_scenes(self) -> List[str]:
        """
        Get list of scenes available for this light device.

        Returns:
            List of scene names this light supports
        """
        # Get scenes from the enhanced intelligence system
        intelligent_scenes = self.get_supported_scenes()

        # Add basic light mode scenes
        basic_scenes = ["white", "colour", "scene", "music"]

        # Combine and deduplicate
        all_scenes = list(set(intelligent_scenes + basic_scenes))

        logger.debug(f"Light {self.device_info.id} supports {len(all_scenes)} scenes: {all_scenes}")
        return all_scenes

    def set_light_mode(self, mode: str) -> bool:
        """
        Set light mode using intelligent mode mapping.

        Args:
            mode: Light mode ("color", "white", "scene", "music")

        Returns:
            True if successful, False otherwise
        """
        # Use the enhanced mode mapping from the base class
        success = self.set_mode_with_mapping(mode)
        if success:
            return True

        # Fallback to direct mode setting
        for mode_cap in self.mode_capabilities:
            if mode_cap in self.dps_mappings:
                return self.set_capability(mode_cap, mode)

        logger.warning(f"Mode capability not found for light {self.device_info.id}")
        return False

    def get_current_light_mode(self) -> Optional[str]:
        """
        Get current light mode.

        Returns:
            Current mode string or None if not available
        """
        for mode_cap in self.mode_capabilities:
            if mode_cap in self.dps_mappings:
                raw_mode = self.get_capability(mode_cap)
                if raw_mode:
                    return str(raw_mode)
        return None

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
        mapping_info = self.dps_mappings.get(capability)
        mapping_dict = mapping_info.__dict__ if mapping_info else None
        return centralized_scaling.scale_brightness_value(
            raw_value, capability, mapping_dict, (0, 100)
        )

    def _parse_color_value(self, capability: str, raw_value: Any) -> Optional[Tuple[int, int, int]]:
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
        mapping_info = self.dps_mappings.get(capability)
        mapping_dict = mapping_info.__dict__ if mapping_info else None
        return centralized_scaling.scale_color_temperature_value(
            raw_value, capability, mapping_dict
        )


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
        auth_manager: "TuyaAuthenticator",
        **kwargs,
    ):
        """Initialize intelligent switch device."""
        super().__init__(device_info, intelligence, dps_mapper, auth_manager, **kwargs)

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
    def dps_mappings(self):
        """Access DPS mappings through capability translator."""
        return self.capability_translator.dps_mappings

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
                "power": any(cap in self.dps_mappings for cap in self.power_capabilities),
                "voltage": any(cap in self.dps_mappings for cap in self.voltage_capabilities),
                "current": any(cap in self.dps_mappings for cap in self.current_capabilities),
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
        mapping_info = self.dps_mappings.get(capability)
        mapping_dict = mapping_info.__dict__ if mapping_info else None
        return centralized_scaling.scale_electrical_value(
            raw_value, capability, "power", mapping_dict
        )

    def _scale_voltage_value(self, capability: str, raw_value: Any) -> float:
        """Scale raw voltage value to volts."""
        mapping_info = self.dps_mappings.get(capability)
        mapping_dict = mapping_info.__dict__ if mapping_info else None
        return centralized_scaling.scale_electrical_value(
            raw_value, capability, "voltage", mapping_dict
        )

    def _scale_current_value(self, capability: str, raw_value: Any) -> float:
        """Scale raw current value to amps."""
        mapping_info = self.dps_mappings.get(capability)
        mapping_dict = mapping_info.__dict__ if mapping_info else None
        return centralized_scaling.scale_electrical_value(
            raw_value, capability, "current", mapping_dict
        )


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
        auth_manager: "TuyaAuthenticator",
        **kwargs,
    ):
        """Initialize intelligent climate device."""
        super().__init__(device_info, intelligence, dps_mapper, auth_manager, **kwargs)

        # Climate-specific capability mappings
        self.temperature_capabilities = [
            "temp_set",
            "temp_current",
            "temp_value",
        ]
        self.humidity_capabilities = [
            "humidity_set",
            "humidity_current",
            "humidity_value",
        ]
        self.mode_capabilities = ["mode", "work_mode", "fan_mode"]
        self.switch_capabilities = ["switch", "power"]

        # Common climate modes
        self.supported_modes = [
            "auto",
            "cool",
            "heat",
            "dry",
            "fan_only",
            "off",
        ]

    @property
    def dps_mappings(self):
        """Access DPS mappings through capability translator."""
        return self.capability_translator.dps_mappings

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

        logger.warning(f"Temperature set capability not found for climate {self.device_info.id}")
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

        logger.warning(f"Humidity set capability not found for climate {self.device_info.id}")
        return False

    def set_mode(self, mode: str) -> bool:
        """
        Set climate mode using intelligent mode mapping for LocalTuya compatibility.

        Args:
            mode: Mode name (e.g., "manual", "auto", "heat", "cool", "dry", "fan_only")

        Returns:
            True if successful, False otherwise
        """
        # Use the enhanced mode mapping from the base class
        success = self.set_mode_with_mapping(mode)
        if success:
            return True

        # Fallback to direct mode setting
        for mode_cap in self.mode_capabilities:
            if mode_cap in self.dps_mappings:
                return self.set_capability(mode_cap, mode)

        logger.warning(f"Mode capability not found for climate {self.device_info.id}")
        return False

    def get_available_climate_modes(self) -> List[str]:
        """
        Get list of climate modes available for this device.

        Returns:
            List of mode strings this climate device supports
        """
        # Get modes from the enhanced intelligence system
        intelligent_modes = self.get_supported_modes()

        # Add standard climate modes as fallback
        standard_modes = ["auto", "cool", "heat", "dry", "fan_only", "off"]

        # Combine and deduplicate
        all_modes = list(set(intelligent_modes + standard_modes))

        logger.debug(f"Climate {self.device_info.id} supports {len(all_modes)} modes: {all_modes}")
        return all_modes

    def set_hvac_action(self, action: str) -> bool:
        """
        Set HVAC action using LocalTuya action mapping intelligence.

        Args:
            action: Action string ("heating", "cooling", "idle", "off")

        Returns:
            True if successful, False otherwise
        """
        try:
            mode_data = self._load_mode_mappings()
            if not mode_data:
                logger.warning(
                    f"No mode mapping available for HVAC action on {self.device_info.id}"
                )
                return False

            # Get HVAC action patterns
            action_patterns = mode_data.get("hvac_action_sets", {}).get("patterns", {})

            # Try to detect which pattern this device uses
            detected_pattern = self._detect_hvac_action_pattern(action_patterns)

            if not detected_pattern:
                # Default to boolean pattern
                detected_pattern = "true_false_boolean"

            pattern_data = action_patterns.get(detected_pattern, {})
            mappings = pattern_data.get("mappings", {})

            # Map high-level action to device value
            action_mapping = {
                "heating": mappings.get("heating"),
                "cooling": mappings.get("cooling"),
                "idle": mappings.get("idle"),
                "off": mappings.get("idle"),  # Map off to idle
            }

            device_action_value = action_mapping.get(action.lower())
            if device_action_value is None:
                logger.warning(f"Could not map HVAC action '{action}' for {self.device_info.id}")
                return False

            # Find action capability and apply
            action_capability = None
            for capability in self.dps_mappings.keys():
                if "action" in capability.lower():
                    action_capability = capability
                    break

            if action_capability:
                logger.debug(
                    f"Setting HVAC action '{action}' -> '{device_action_value}' via {action_capability}"
                )
                return self.set_capability(action_capability, device_action_value)
            else:
                logger.warning(f"No HVAC action capability found for {self.device_info.id}")
                return False

        except Exception as e:
            logger.error(f"Failed to set HVAC action '{action}' for {self.device_info.id}: {e}")
            return False

    def _detect_hvac_action_pattern(self, action_patterns: Dict[str, Any]) -> Optional[str]:
        """Detect which HVAC action pattern this device uses."""
        try:
            # Get current action value if available
            current_action = None
            for capability in self.dps_mappings.keys():
                if "action" in capability.lower():
                    current_action = self.get_capability(capability)
                    break

            if current_action is None:
                return None

            # Check patterns for matches
            for pattern_name, pattern_data in action_patterns.items():
                mappings = pattern_data.get("mappings", {})
                for action_values in mappings.values():
                    if isinstance(action_values, bool) and action_values == current_action:
                        return pattern_name
                    elif (
                        isinstance(action_values, str)
                        and action_values.lower() == str(current_action).lower()
                    ):
                        return pattern_name

            return None

        except Exception as e:
            logger.error(f"HVAC action pattern detection failed: {e}")
            return None

    def _scale_temperature_value(self, capability: str, raw_value: Any) -> float:
        """Scale raw temperature value to Celsius."""
        mapping_info = self.dps_mappings.get(capability)
        mapping_dict = mapping_info.__dict__ if mapping_info else None
        return centralized_scaling.scale_temperature_value(raw_value, capability, mapping_dict)

    def _scale_temperature_for_device(self, capability: str, temperature: float) -> Any:
        """Scale temperature for device storage."""
        mapping_info = self.dps_mappings.get(capability)
        mapping_dict = mapping_info.__dict__ if mapping_info else None
        return centralized_scaling.scale_temperature_for_device(
            temperature, capability, mapping_dict
        )


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
        auth_manager: "TuyaAuthenticator",
        **kwargs,
    ):
        """Initialize intelligent cover device."""
        super().__init__(device_info, intelligence, dps_mapper, auth_manager, **kwargs)

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
    def dps_mappings(self):
        """Access DPS mappings through capability translator."""
        return self.capability_translator.dps_mappings

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
    auth_manager: "TuyaAuthenticator",
    intelligence: DeviceIntelligence,
    dps_mapper: DPSMapper,
    **kwargs,
) -> IntelligentDevice:
    """
    Create a specialized device type based on device category.

    Args:
        device_info: Device information
        auth_manager: TuyaAuthenticator instance for cloud operations
        intelligence: Device intelligence
        dps_mapper: DPS mapper
        **kwargs: Additional arguments, including tinytuya_device_instance and entity_capabilities for multi-entity

    Returns:
        Specialized IntelligentDevice subclass
    """
    category = device_info.category

    # Light categories
    if category in ["dj", "dc", "dd", "dsd", "xdd", "tgkg", "tgq"]:
        return IntelligentLight(device_info, intelligence, dps_mapper, auth_manager, **kwargs)

    # Switch categories
    elif category in ["kg", "pc", "cz", "tdq"]:
        return IntelligentSwitch(device_info, intelligence, dps_mapper, auth_manager, **kwargs)

    # Climate categories
    elif category in ["kt", "qn", "wk", "wkf", "jsq", "cs"]:
        return IntelligentClimate(device_info, intelligence, dps_mapper, auth_manager, **kwargs)

    # Cover categories
    elif category in ["cl"]:
        return IntelligentCover(device_info, intelligence, dps_mapper, auth_manager, **kwargs)

    # Default to base IntelligentDevice
    else:
        return IntelligentDevice(device_info, intelligence, dps_mapper, auth_manager, **kwargs)
