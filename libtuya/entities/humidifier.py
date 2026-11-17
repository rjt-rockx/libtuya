"""Humidifiers and dehumidifiers.

Follows ``TuyaHumidifierEntity`` in Home Assistant's
``homeassistant/components/tuya/humidifier.py`` (Apache-2.0), and its generic
humidifier entity (``homeassistant/components/humidifier``) for the state and
its attributes.
"""

from __future__ import annotations

from typing import Any

from .base import Entity


class Humidifier(Entity):
    """A humidifier or dehumidifier; `device_class` says which.

    Humidity is relative, in percent. `turn_on()` and `turn_off()` use the
    device's switch. The methods raise TuyaError for what the device lacks and
    ValueError for a value it does not take.
    """

    def _read(self, attribute: str) -> Any:
        """An attribute's value; None if the device lacks it or does not report it."""
        wrapper = self.wrappers.get(attribute)
        return None if wrapper is None else wrapper.read_device_status(self.device.info)

    @property
    def device_class(self) -> str | None:
        """Which way the device works: "humidifier" adds moisture, "dehumidifier" removes it."""
        member: str = self.description.get("device_class", {}).get("$ha", "")
        return member.rpartition(".")[2].lower() or None

    @property
    def is_on(self) -> bool | None:
        """Whether the device is switched on; None if unknown."""
        return self._read("switch")

    @property
    def current_humidity(self) -> int | None:
        """The humidity the device measures."""
        return self._read("current_humidity")

    @property
    def target_humidity(self) -> int | None:
        """The humidity the device is set to reach."""
        return self._read("target_humidity")

    @property
    def min_humidity(self) -> int:
        """Lowest target humidity; 0 if the device has no such setting."""
        wrapper = self.wrappers.get("target_humidity")
        return round(wrapper.min_value) if wrapper else 0

    @property
    def max_humidity(self) -> int:
        """Highest target humidity; 100 if the device has no such setting."""
        wrapper = self.wrappers.get("target_humidity")
        return round(wrapper.max_value) if wrapper else 100

    @property
    def mode(self) -> str | None:
        """The active mode, one of `available_modes`; None if unknown."""
        return self._read("mode")

    @property
    def available_modes(self) -> list[str]:
        """The device's modes, under its own names; empty if it has none."""
        return list(getattr(self.wrappers.get("mode"), "options", ()))

    def summary(self) -> dict[str, Any]:
        """Home Assistant's state ("on" or "off") and attributes for this entity."""
        shown: dict[str, Any] = {
            "state": {True: "on", False: "off"}.get(self.is_on),
            "min_humidity": self.min_humidity,
            "max_humidity": self.max_humidity,
        }
        if (current := self.current_humidity) is not None:
            shown["current_humidity"] = current
        if (target := self.target_humidity) is not None:
            shown["humidity"] = target
        if "mode" in self.wrappers:
            shown |= {"mode": self.mode, "available_modes": self.available_modes}
        return shown

    def set_humidity(self, humidity: int) -> None:
        """Set the humidity to reach, from `min_humidity` to `max_humidity`."""
        self.set(target_humidity=humidity)

    def set_mode(self, mode: str) -> None:
        """Change to one of `available_modes`."""
        self.set(mode=mode)
