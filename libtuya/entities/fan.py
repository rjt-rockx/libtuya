"""Fans.

Follows ``TuyaFanEntity`` in Home Assistant's
``homeassistant/components/tuya/fan.py`` (Apache-2.0), and its generic fan
entity (``homeassistant/components/fan``) for the state and its attributes.
"""

from __future__ import annotations

from typing import Any

from .base import Entity


class Fan(Entity):
    """A fan, or the fan of an air purifier or dehumidifier.

    Speed is a percentage, 1-100, whether the device counts its speeds or
    names them ("low", "high"): each named speed stands for an equal share,
    so "low" of two is 50 and anything up to 50 selects it. A fraction is cut
    off, as in Home Assistant, so `percentage + percentage_step` is one named
    speed up.

    The methods raise TuyaError for what the fan lacks and ValueError for a
    value it does not take.
    """

    @property
    def is_on(self) -> bool | None:
        """Whether the fan is switched on; None if unknown."""
        return self._read("switch")

    @property
    def percentage(self) -> int | None:
        """The speed the fan is set to, 1-100, also while it is off; None if unknown."""
        return self._read("speed")

    @property
    def speed_count(self) -> int:
        """How many speeds `percentage` distinguishes: the named ones, else 100."""
        named = getattr(self.wrappers.get("speed"), "options", None)
        return len(named) if named else 100

    @property
    def percentage_step(self) -> float:
        """Size of one speed in `percentage`: 50.0 for two named speeds, 1.0 without names."""
        return 100 / self.speed_count

    @property
    def preset_mode(self) -> str | None:
        """The active preset, one of `preset_modes`; None if unknown."""
        return self._read("mode")

    @property
    def preset_modes(self) -> list[str]:
        """The fan's presets, such as "sleep" or "nature"; empty if it has none."""
        return list(getattr(self.wrappers.get("mode"), "options", ()))

    @property
    def oscillating(self) -> bool | None:
        """Whether the fan swings from side to side; None if it cannot or does not say."""
        return self._read("oscillate")

    @property
    def current_direction(self) -> str | None:
        """Which way the fan turns, "forward" or "reverse"; None if it cannot or does not say."""
        direction = self._read("direction")
        return str(direction) if direction else None

    def summary(self) -> dict[str, Any]:
        """Home Assistant's state ("on" or "off") and attributes for this entity."""
        shown: dict[str, Any] = {"state": {True: "on", False: "off"}.get(self.is_on)}
        if "direction" in self.wrappers:
            shown["direction"] = self.current_direction
        if "oscillate" in self.wrappers:
            shown["oscillating"] = self.oscillating
        if "speed" in self.wrappers:
            shown |= {"percentage": self.percentage, "percentage_step": self.percentage_step}
        if "speed" in self.wrappers or "mode" in self.wrappers:
            shown |= {"preset_mode": self.preset_mode, "preset_modes": self.preset_modes or None}
        return shown

    def _speed(self, percentage: float) -> int:
        """A speed without its fraction; refused unless it is a number from 1 to 100."""
        if not (isinstance(percentage, (int, float)) and 1 <= percentage <= 100):
            raise ValueError(
                f"{self.id}: percentage must be a number from 1 to 100, not {percentage!r}"
            )
        return int(percentage)

    def turn_on(self, *, percentage: float | None = None, preset_mode: str | None = None) -> None:
        """Turn on, optionally at a speed (1-100) and in one of `preset_modes`."""
        setting: dict[str, Any] = {"switch": True}
        if percentage is not None:
            setting["speed"] = self._speed(percentage)
        if preset_mode is not None:
            setting["mode"] = preset_mode
        self.set(**setting)

    def set_percentage(self, percentage: float) -> None:
        """Set the speed, 1-100, without turning the fan on; 0 turns it off."""
        if percentage == 0:
            self.turn_off()
        else:
            self.set(speed=self._speed(percentage))

    def set_preset_mode(self, preset_mode: str) -> None:
        """Activate one of `preset_modes`."""
        self.set(mode=preset_mode)

    def oscillate(self, oscillating: bool) -> None:
        """Start or stop swinging from side to side."""
        self.set(oscillate=oscillating)

    def set_direction(self, direction: str) -> None:
        """Make the fan turn "forward" or "reverse"."""
        self.set(direction=direction)
