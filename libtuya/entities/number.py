"""Numeric settings.

Follows ``TuyaNumberEntity`` in Home Assistant's
``homeassistant/components/tuya/number.py`` (Apache-2.0).
"""

from __future__ import annotations

from typing import Any

from tuya_device_handlers.const import CELSIUS_ALIASES, FAHRENHEIT_ALIASES
from tuya_device_handlers.helpers.homeassistant import TuyaUnitOfTemperature

from .base import Entity

# Home Assistant's device class for temperatures, as the generated tables name it.
_TEMPERATURE = {"$ha": "NumberDeviceClass.TEMPERATURE"}


class Number(Entity):
    """A setting that takes a number: a countdown, a volume, a temperature to keep.

    `set(value)` changes it; a value outside `min` to `max` is a ValueError.
    The value and its limits are in `unit`, not in the device's raw steps.
    """

    @property
    def value(self) -> float | None:
        """The current setting; None if unknown."""
        return self.wrappers["number"].read_device_status(self.device.info)

    @property
    def min(self) -> float:
        """Lowest value the device takes."""
        return self.wrappers["number"].min_value

    @property
    def max(self) -> float:
        """Highest value the device takes."""
        return self.wrappers["number"].max_value

    @property
    def step(self) -> float:
        """Smallest change of the value the device takes."""
        return self.wrappers["number"].value_step

    @property
    def unit(self) -> str | None:
        """The unit of the value as the device names it ("s", "%"); empty or None if it does not.

        A temperature's is "°C" or "°F" however the device spells it, and
        follows the device's own unit setting where it names none.
        """
        unit = self.wrappers["number"].native_unit
        if self.description.get("device_class") != _TEMPERATURE:
            return unit
        spelling = unit.lower() if unit else self.device.status.get("temp_unit_convert")
        if spelling in CELSIUS_ALIASES:
            return TuyaUnitOfTemperature.CELSIUS.value
        if spelling in FAHRENHEIT_ALIASES:
            return TuyaUnitOfTemperature.FAHRENHEIT.value
        return unit

    def summary(self) -> dict[str, Any]:
        """Home Assistant's state (the value) and attributes (the limits and the unit)."""
        shown: dict[str, Any] = {
            "state": self.value,
            "min": self.min,
            "max": self.max,
            "step": self.step,
        }
        if (unit := self.unit) is not None:
            shown["unit_of_measurement"] = unit
        return shown
