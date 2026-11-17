"""Sensors.

Follows ``TuyaSensorEntity`` in Home Assistant's
``homeassistant/components/tuya/sensor.py`` (Apache-2.0).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from tuya_device_handlers.const import CELSIUS_ALIASES, FAHRENHEIT_ALIASES
from tuya_device_handlers.device_wrapper.common import DPCodeEnumWrapper
from tuya_device_handlers.device_wrapper.sensor import DeltaIntegerWrapper
from tuya_device_handlers.helpers.homeassistant import TuyaUnitOfTemperature

from .base import Entity

# Home Assistant's unit constants that its sensor descriptions name.
_UNITS = {
    "UnitOfDensity.MICROGRAMS_PER_CUBIC_METER": "μg/m³",
    "UnitOfElectricCurrent.AMPERE": "A",
    "UnitOfElectricPotential.VOLT": "V",
    "UnitOfEnergy.KILO_WATT_HOUR": "kWh",
    "UnitOfPower.WATT": "W",
    "UnitOfRatio.PARTS_PER_MILLION": "ppm",
    "UnitOfRatio.PERCENTAGE": "%",
    "UnitOfTime.MINUTES": "min",
}
# Metric prefixes as powers of ten. The unit Home Assistant shows a reading in
# differs from the device's by one of these, if at all (A for mA, kW for W).
_PREFIXES = {"": 0, "k": 3, "m": -3}


def _power(unit: str, shown: str) -> int | None:
    """Power of ten that takes a value in `unit` to `shown`; None if no prefix relates them."""
    for prefix, power in _PREFIXES.items():
        if unit == prefix + shown:
            return power
        if shown == prefix + unit:
            return -power
    return None


class Sensor(Entity):
    """A reading: power, a temperature, a battery level, or a status such as "charging".

    `value` and `unit` are what Home Assistant shows, which for some sensors is
    a larger or smaller unit than the device reports in (A for mA). `state()`
    and `describe()` keep the device's own figures. Home Assistant's choice of
    unit system does not come into it: a device set to °F reads in °F.
    """

    @property
    def value(self) -> float | str | datetime | None:
        """The reading: a number in `unit`, one of `options`, or the time a countdown ends.

        None if unknown. A sensor that reports increments rather than totals
        reads None until the device's pushes are followed (see `Device.watch`),
        then their sum.
        """
        return self._converted(self.state()["sensor"])

    @property
    def unit(self) -> str | None:
        """The unit of `value`, such as "W"; None or "" for a reading without one.

        Spelled as the device spells it ("kW·h", "lux"), except for °C, °F and
        a unit Home Assistant converts the reading to.
        """
        return self._shown()[0]

    @property
    def options(self) -> list[str] | None:
        """The values a status sensor can take; None for any other sensor."""
        wrapper = self.wrappers["sensor"]
        if "device_class" not in self.description and isinstance(wrapper, DPCodeEnumWrapper):
            return wrapper.options
        return None

    def summary(self) -> dict[str, Any]:
        """Home Assistant's state for the sensor and, for a status sensor, its ``options``.

        A sensor that reports increments shows 0 until its pushes are followed,
        as Home Assistant's does from the moment it starts, while `value` stays
        None. The unit is not included; see `unit`.
        """
        value = self.value
        wrapper = self.wrappers["sensor"]
        if value is None and isinstance(wrapper, DeltaIntegerWrapper):
            value = self._converted(wrapper.read_device_status(self.device.info))
        if isinstance(value, datetime):
            value = value.isoformat(timespec="seconds")
        summary: dict[str, Any] = {"state": value}
        if (options := self.options) is not None:
            summary["options"] = options
        return summary

    def _converted(self, reading: Any) -> Any:
        """A reading in the device's unit, given in `unit`."""
        _, power = self._shown()
        if power and isinstance(reading, (int, float)):
            # Moving the decimal point: float arithmetic makes 1.005 kW 1004.9999999999999 W.
            return float(Decimal(str(reading)).scaleb(power))
        return reading

    def _described(self, field: str) -> str | None:
        """The unit Home Assistant's description of this sensor gives in `field`, if any."""
        marker = self.description.get(field)
        return _UNITS[marker["$ha"]] if marker else None

    def _native_unit(self) -> str | None:
        """The unit the device reports in, named Home Assistant's way where libtuya can tell.

        That is for temperatures and for devices that name no unit; the rest of
        ``_validate_device_class_unit`` needs Home Assistant's tables of units.
        """
        unit = self.wrappers["sensor"].native_unit
        if self.description.get("device_class") == {"$ha": "SensorDeviceClass.TEMPERATURE"}:
            # The datapoint's own unit, or failing that the device's Celsius/Fahrenheit setting.
            spelling = (unit or self.device.status.get("temp_unit_convert") or "").lower()
            if spelling in CELSIUS_ALIASES:
                return TuyaUnitOfTemperature.CELSIUS.value
            if spelling in FAHRENHEIT_ALIASES:
                return TuyaUnitOfTemperature.FAHRENHEIT.value
        if not unit and "device_class" in self.description:
            return self._described("native_unit_of_measurement") or unit
        return unit

    def _shown(self) -> tuple[str | None, int]:
        """The unit Home Assistant shows the sensor in, and the power of ten that gets there."""
        native = self._native_unit()
        suggested = (
            self._described("suggested_unit_of_measurement")
            or self.wrappers["sensor"].suggested_unit
        )
        power = _power(native or "", suggested) if suggested else None
        return (native, 0) if power is None else (suggested, power)
