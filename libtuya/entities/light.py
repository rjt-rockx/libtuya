"""Lights.

Follows ``TuyaLightEntity`` in Home Assistant's
``homeassistant/components/tuya/light.py``. What `Light.summary` shows and
what `Light.turn_on` accepts follow Home Assistant's light platform
(``homeassistant/components/light``), with the colour conversions of
``homeassistant/util/color.py`` (all Apache-2.0).
"""

from __future__ import annotations

import colorsys
import math
from typing import Any

from tuya_device_handlers.device_wrapper.light import ColorTempWrapper

from ..errors import TuyaError
from .base import Entity, on_off_state

_LACKING = {
    "hs": "adjustable colour",
    "color_temp": "adjustable colour temperature",
    "white": "plain white mode",
}


def _hs_to_rgb(hue: float, saturation: float) -> tuple[int, int, int]:
    """Red, green and blue (0-255) of a colour at full brightness."""
    red, green, blue = colorsys.hsv_to_rgb(hue / 360, saturation / 100, 1)
    return round(red * 255), round(green * 255), round(blue * 255)


def _rgb_to_xy(red: int, green: int, blue: int) -> tuple[float, float]:
    """CIE xy chromaticity of a colour (wide gamut, D65)."""
    if not red + green + blue:
        return 0.0, 0.0
    r, g, b = (
        ((c / 255 + 0.055) / 1.055) ** 2.4 if c / 255 > 0.04045 else c / 255 / 12.92
        for c in (red, green, blue)
    )
    x = r * 0.664511 + g * 0.154324 + b * 0.162028
    y = r * 0.283881 + g * 0.668433 + b * 0.047685
    z = r * 0.000088 + g * 0.072310 + b * 0.986039
    return round(x / (x + y + z), 3), round(y / (x + y + z), 3)


def _kelvin_to_hs(kelvin: float) -> tuple[float, float]:
    """Hue and saturation of a white of the given temperature (T. Helland's approximation)."""
    t = min(max(kelvin, 1000), 40000) / 100
    red = 255 if t <= 66 else 329.698727446 * (t - 60) ** -0.1332047592
    green = (
        99.4708025861 * math.log(t) - 161.1195681661
        if t <= 66
        else 288.1221695283 * (t - 60) ** -0.0755148492
    )
    blue = 255 if t >= 66 else 0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.0447927307
    hue, saturation, _ = colorsys.rgb_to_hsv(
        *(min(max(c, 0), 255) / 255 for c in (red, green, blue))
    )
    return round(hue * 360, 3), round(saturation * 100, 3)


class Light(Entity):
    """A light.

    `supported_color_modes` says what it can show and `color_mode` what it is
    showing. `turn_on` is the way to change brightness, white temperature or
    colour: it also switches the light between its white and colour modes as
    needed, which setting a single attribute with `set` does not.
    """

    @property
    def is_on(self) -> bool | None:
        """Whether the light is on; None if unknown."""
        return self._read("switch")

    @property
    def supported_color_modes(self) -> set[str]:
        """What the light can show.

        ``{"onoff"}``, ``{"brightness"}``, or one or two of ``"hs"`` (colour),
        ``"color_temp"`` (white of adjustable temperature) and ``"white"``
        (plain white beside colour).
        """
        modes = {"hs"} if "color_data" in self.wrappers else set()
        mode = self.wrappers.get("color_mode")
        if "color_temp" in self.wrappers:
            modes.add("color_temp")
        elif modes and mode is not None and "white" in mode.options:
            modes.add("white")
        if modes:
            return modes
        return {"brightness"} if "brightness" in self.wrappers else {"onoff"}

    @property
    def color_mode(self) -> str:
        """Which of `supported_color_modes` the light is in (also while it is off)."""
        modes = self.supported_color_modes
        if len(modes) == 1:
            return next(iter(modes))
        # Anything but white (a scene, music) counts as colour.
        if "color_mode" in self.wrappers and self._read("color_mode") != "white":
            return "hs"
        return "color_temp" if "color_temp" in modes else "white"

    @property
    def in_color_mode(self) -> bool:
        """Whether the light currently shows a colour rather than white."""
        return self.color_mode == "hs"

    @property
    def brightness(self) -> int | None:
        """Current brightness, 0-255, of whichever mode the light is in.

        `state()["brightness"]` is the white channel's setting alone.
        """
        if self.in_color_mode:
            hsv = self._read("color_data")
            return None if hsv is None else round(hsv[2])
        return self._read("brightness")

    @property
    def hs_color(self) -> tuple[float, float] | None:
        """The colour last set, as (hue 0-360, saturation 0-100), in any mode."""
        hsv = self._read("color_data")
        return None if hsv is None else (hsv[0], hsv[1])

    @property
    def color_temp_kelvin(self) -> int | None:
        """The white temperature last set, in kelvin, in any mode."""
        return self._read("color_temp")

    @property
    def min_color_temp_kelvin(self) -> int:
        """Warmest white `turn_on(color_temp_kelvin=...)` takes, in kelvin."""
        return getattr(self.wrappers.get("color_temp"), "min_kelvin", ColorTempWrapper.MIN_KELVIN)

    @property
    def max_color_temp_kelvin(self) -> int:
        """Coldest white `turn_on(color_temp_kelvin=...)` takes, in kelvin."""
        return getattr(self.wrappers.get("color_temp"), "max_kelvin", ColorTempWrapper.MAX_KELVIN)

    def summary(self) -> dict[str, Any]:
        """State ("on", "off" or None) and attributes, as Home Assistant shows a light.

        What the light is showing (``color_mode``, ``brightness``,
        ``color_temp_kelvin``, ``hs_color``, ``rgb_color``, ``xy_color``) is
        None while it is off. The colour of a white is that of its temperature.
        """
        on = self.is_on
        modes = self.supported_color_modes
        mode = self.color_mode if on else None
        shown: dict[str, Any] = {
            "state": on_off_state(on),
            "supported_color_modes": sorted(modes),
            "color_mode": mode,
        }
        if modes != {"onoff"}:
            shown["brightness"] = self.brightness if mode else None
        if "color_temp" in modes:
            shown["color_temp_kelvin"] = self.color_temp_kelvin if mode == "color_temp" else None
            shown["min_color_temp_kelvin"] = self.min_color_temp_kelvin
            shown["max_color_temp_kelvin"] = self.max_color_temp_kelvin
        if modes & {"hs", "color_temp"}:
            hs = self.hs_color if mode == "hs" else None
            if mode == "color_temp" and (kelvin := self.color_temp_kelvin):
                hs = _kelvin_to_hs(kelvin)
            rgb = hs and _hs_to_rgb(*hs)
            shown["hs_color"] = hs and (round(hs[0], 3), round(hs[1], 3))
            shown["rgb_color"] = rgb
            shown["xy_color"] = rgb and _rgb_to_xy(*rgb)
        return shown

    def turn_on(
        self,
        *,
        brightness: float | None = None,
        color_temp_kelvin: int | None = None,
        hs_color: tuple[float, float] | None = None,
        white: bool = False,
    ) -> None:
        """Turn on, optionally changing what the light shows.

        `brightness` is 0-255 and dims whatever is showing; 0 turns the light
        off. At most one of: `color_temp_kelvin`, white of that temperature;
        `hs_color`, a colour as (hue 0-360, saturation 0-100); `white=True`,
        the plain white of a colour light without adjustable temperature.

        Raises TuyaError if the light lacks what is asked for, and ValueError
        for a value of the wrong shape or out of range.
        """
        if not isinstance(white, bool):
            raise ValueError("white is True or False; give its level as brightness")
        wanted = {
            "hs": hs_color is not None,
            "color_temp": color_temp_kelvin is not None,
            "white": white,
        }
        asked = [mode for mode, given in wanted.items() if given]
        if len(asked) > 1:
            raise ValueError("give only one of color_temp_kelvin, hs_color and white")
        if asked and asked[0] not in self.supported_color_modes:
            raise TuyaError(f"{self.device.name} has no {_LACKING[asked[0]]}")
        if brightness is not None and not 0 <= brightness <= 255:
            raise ValueError("brightness is 0 to 255")
        if hs_color is not None and not (
            len(hs_color) == 2 and 0 <= hs_color[0] <= 360 and 0 <= hs_color[1] <= 100
        ):
            raise ValueError("hs_color is (hue 0-360, saturation 0-100)")
        if brightness == 0:
            self.turn_off()
            return

        setting: dict[str, Any] = {"switch": True}
        colour: list[dict[str, Any]] = []
        to_white = white or color_temp_kelvin is not None
        if to_white:
            setting["color_mode"] = "white"
        if color_temp_kelvin is not None:
            setting["color_temp"] = color_temp_kelvin
        # Brightness belongs to the colour while one is showing.
        if hs_color is not None or (brightness is not None and not to_white and self.in_color_mode):
            if brightness is None:
                brightness = 255 if self.brightness is None else self.brightness
            setting["color_mode"] = "colour"
            # Not through `commands`, which checks ranges: what is kept of the current
            # colour goes back as read, also from a device that misreports its scale.
            colour = self.wrappers["color_data"].get_update_commands(
                self.device.info, (*(hs_color or self.hs_color or (0, 0)), brightness)
            )
        elif "brightness" in self.wrappers:
            if brightness is None and white:
                brightness = self.brightness  # white takes over the brightness of the colour
            if brightness is not None:
                setting["brightness"] = brightness
        elif brightness is not None:
            what = "white brightness" if "color_data" in self.wrappers else "brightness"
            raise TuyaError(f"{self.device.name} has no adjustable {what}")
        # Lights without a mode datapoint, or without that mode, follow the last value written.
        mode = self.wrappers.get("color_mode")
        if mode is None or setting.get("color_mode") not in mode.options:
            setting.pop("color_mode", None)
        self.device.send(self.commands(**setting) + colour)
