"""Lights.

Follows ``TuyaLightEntity`` in Home Assistant's
``homeassistant/components/tuya/light.py`` (Apache-2.0).
"""

from __future__ import annotations

from typing import Any

from ..errors import TuyaError
from .base import Entity


class Light(Entity):
    """A light.

    `turn_on` is the way to change brightness, white temperature or colour: it
    also switches the light between its white and colour modes as needed,
    which setting a single attribute with `set` does not.
    """

    @property
    def in_color_mode(self) -> bool:
        """Whether the light currently shows a colour rather than white."""
        if "color_data" not in self.wrappers:
            return False
        mode = self.wrappers.get("color_mode")
        has_white = (
            "brightness" in self.wrappers
            or "color_temp" in self.wrappers
            or (mode is not None and "white" in mode.options)
        )
        if not has_white:
            return True
        return mode is not None and mode.read_device_status(self.device.info) != "white"

    @property
    def brightness(self) -> int | None:
        """Current brightness, 0-255, of whichever mode the light is in.

        `state()["brightness"]` is the white channel's setting alone.
        """
        info = self.device.info
        if self.in_color_mode:
            hsv = self.wrappers["color_data"].read_device_status(info)
            return None if hsv is None else round(hsv[2])
        if "brightness" in self.wrappers:
            return self.wrappers["brightness"].read_device_status(info)
        return None

    def turn_on(
        self,
        *,
        brightness: float | None = None,
        kelvin: int | None = None,
        hs: tuple[float, float] | None = None,
    ) -> None:
        """Turn on, optionally setting brightness (0-255), white temperature or colour.

        Raises TuyaError if the light lacks what is asked for, and ValueError
        for values out of range.
        """
        lacking = [
            what
            for what, asked, needs in (
                ("colour", hs, {"color_data"}),
                ("colour temperature", kelvin, {"color_temp"}),
                ("brightness", brightness, {"brightness", "color_data"}),
            )
            if asked is not None and not needs & self.wrappers.keys()
        ]
        if lacking:
            raise TuyaError(f"{self.device.name} has no adjustable {' or '.join(lacking)}")

        setting: dict[str, Any] = {"switch": True}
        if kelvin is not None:
            setting |= {"color_mode": "white", "color_temp": kelvin}
        colour = self.wrappers.get("color_data")
        # Brightness belongs to the colour while one is showing, and on lights
        # that have no separate white channel.
        dims_colour = kelvin is None and (self.in_color_mode or "brightness" not in self.wrappers)
        if colour and (hs is not None or (brightness is not None and dims_colour)):
            if hs is None:
                hs = (colour.read_device_status(self.device.info) or (0.0, 0.0, 0.0))[:2]
            if brightness is None:
                brightness = self.brightness or 255
            setting |= {"color_mode": "colour", "color_data": (*hs, brightness)}
        elif brightness is not None:
            setting["brightness"] = brightness
        # Lights without a mode datapoint, or without that mode, follow the last value written.
        mode = self.wrappers.get("color_mode")
        if mode is None or setting.get("color_mode") not in mode.options:
            setting.pop("color_mode", None)
        self.device.send(self.commands(**setting))
