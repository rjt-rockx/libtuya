"""Thermostats, heaters and air conditioners.

Follows ``TuyaClimateEntity`` in Home Assistant's
``homeassistant/components/tuya/climate.py`` (Apache-2.0), and its generic
climate entity for how the state and its attributes are derived.
"""

from __future__ import annotations

from typing import Any

from tuya_device_handlers.const import CELSIUS_ALIASES, FAHRENHEIT_ALIASES
from tuya_device_handlers.helpers.homeassistant import TuyaUnitOfTemperature

from ..errors import TuyaError
from .base import Entity

_CELSIUS = TuyaUnitOfTemperature.CELSIUS
_FAHRENHEIT = TuyaUnitOfTemperature.FAHRENHEIT


def _convert(value: float, source: str | None, target: str | None) -> float:
    """A temperature in `target` units; unchanged if either unit is unknown."""
    if source is None or target is None or source == target:
        return value
    return (value - 32) / 1.8 if target == _CELSIUS else value * 1.8 + 32


def _shown(temperature: float | None) -> float | None:
    """A temperature as Home Assistant displays it: to a tenth of a degree."""
    return None if temperature is None else round(temperature, 1)


class Climate(Entity):
    """A thermostat, heater or air conditioner.

    Temperatures, their limits and their step are in `temperature_unit`,
    whichever unit the device itself works in. Modes are plain strings: "off",
    "heat", "cool", "heat_cool", "auto", "dry" and "fan_only" for the HVAC
    mode, the device's own names for presets and fan speeds. `turn_on()` and
    `turn_off()` use the device's switch and leave its mode alone.
    """

    def _options(self, attribute: str) -> list[str]:
        """An attribute's choices as plain strings; none if the device lacks it."""
        wrapper = self.wrappers.get(attribute)
        return [str(option) for option in wrapper.options] if wrapper else []

    def _unit_of(self, attribute: str) -> str | None:
        """The unit a temperature attribute is in on the device, as far as it says."""
        wrapper = self.wrappers.get(attribute)
        if wrapper is None:
            return None
        if not wrapper.native_unit:  # then the device's own unit setting decides
            setting = self.device.status.get("temp_unit_convert")
            return {"c": _CELSIUS, "f": _FAHRENHEIT}.get(str(setting))
        unit = wrapper.native_unit.lower()
        if unit in CELSIUS_ALIASES:
            return _CELSIUS
        return _FAHRENHEIT if unit in FAHRENHEIT_ALIASES else None

    def _temperature(self, attribute: str) -> float | None:
        """A temperature attribute's value in `temperature_unit`."""
        value = self._read(attribute)
        if value is None:
            return None
        return _convert(value, self._unit_of(attribute), self.temperature_unit)

    @property
    def _switch_only_mode(self) -> str:
        """The one mode this kind of device is in when it only says that it is on."""
        return self.description["switch_only_hvac_mode"]["$ha"].rpartition(".")[2].lower()

    @property
    def temperature_unit(self) -> str:
        """Unit of the temperatures here: "°C", also for a device that works in Fahrenheit."""
        return str(self.definition.temperature_unit)

    @property
    def current_temperature(self) -> float | None:
        """The temperature the device measures."""
        return self._temperature("current_temperature")

    @property
    def target_temperature(self) -> float | None:
        """The temperature the device is set to reach."""
        return self._temperature("set_temperature")

    @property
    def min_temp(self) -> float:
        """Lowest target temperature the device takes; 7 °C if it gives none."""
        wrapper = self.wrappers.get("set_temperature")
        if wrapper is None:
            return _convert(7, _CELSIUS, self.temperature_unit)
        return _convert(wrapper.min_value, self._unit_of("set_temperature"), self.temperature_unit)

    @property
    def max_temp(self) -> float:
        """Highest target temperature the device takes; 35 °C if it gives none."""
        wrapper = self.wrappers.get("set_temperature")
        if wrapper is None:
            return _convert(35, _CELSIUS, self.temperature_unit)
        return _convert(wrapper.max_value, self._unit_of("set_temperature"), self.temperature_unit)

    @property
    def target_temperature_step(self) -> float:
        """Smallest change of the target temperature the device takes."""
        wrapper = self.wrappers.get("set_temperature")
        if wrapper is None:
            return 1.0
        fahrenheit = self._unit_of("set_temperature") == _FAHRENHEIT
        return wrapper.value_step / 1.8 if fahrenheit else wrapper.value_step

    @property
    def current_humidity(self) -> int | None:
        """The relative humidity the device measures, in percent."""
        return self._read("current_humidity")

    @property
    def target_humidity(self) -> int | None:
        """The relative humidity the device is set to reach, in percent."""
        return self._read("target_humidity")

    @property
    def min_humidity(self) -> int:
        """Lowest target humidity, in percent; 30 if the device has no such setting."""
        wrapper = self.wrappers.get("target_humidity")
        return round(wrapper.min_value) if wrapper else 30

    @property
    def max_humidity(self) -> int:
        """Highest target humidity, in percent; 99 if the device has no such setting."""
        wrapper = self.wrappers.get("target_humidity")
        return round(wrapper.max_value) if wrapper else 99

    @property
    def hvac_mode(self) -> str | None:
        """What the device is doing: "off", "heat", "cool" ...; None if it does not say.

        A device that is on in one of its presets, or has no modes at all, is
        in the one mode its kind of device has ("heat" for a heater).
        """
        switch = self._read("switch")
        if switch is False:
            return "off"
        if "hvac_mode" not in self.wrappers:
            return self._switch_only_mode if switch else None
        if mode := self._read("hvac_mode"):
            return str(mode)
        return self._switch_only_mode if self.preset_mode is not None else None

    @property
    def hvac_modes(self) -> list[str]:
        """Home Assistant's modes for the device, "off" first; empty for a device without any.

        "off" is listed even for a device that cannot be switched off, where
        `set_hvac_mode("off")` raises TuyaError.
        """
        modes: list[str] = []
        if "hvac_mode" in self.wrappers:
            modes = ["off", *(mode for mode in self._options("hvac_mode") if mode != "off")]
        elif "switch" in self.wrappers:
            modes = ["off", self._switch_only_mode]
        if self.preset_modes and self._switch_only_mode not in modes:
            modes.append(self._switch_only_mode)
        return modes

    @property
    def preset_mode(self) -> str | None:
        """The active preset, one of `preset_modes`; None while the device is in none."""
        return self._read("preset")

    @property
    def preset_modes(self) -> list[str]:
        """The device's modes that are not HVAC modes, such as "eco" or "holiday"."""
        return self._options("preset")

    @property
    def fan_mode(self) -> str | None:
        """The fan speed, one of `fan_modes`."""
        return self._read("fan_mode")

    @property
    def fan_modes(self) -> list[str]:
        """The fan speeds the device has, under its own names."""
        return self._options("fan_mode")

    @property
    def swing_mode(self) -> str | None:
        """How the louvres move: "off", "on", "horizontal", "vertical" or "both"."""
        mode = self._read("swing")
        return str(mode) if mode else None

    @property
    def swing_modes(self) -> list[str]:
        """The swing modes `set_swing_mode` takes."""
        return self._options("swing")

    def summary(self) -> dict[str, Any]:
        """Home Assistant's state (the HVAC mode) and attributes for this entity."""
        shown: dict[str, Any] = {
            "state": self.hvac_mode,
            "hvac_modes": self.hvac_modes,
            "min_temp": _shown(self.min_temp),
            "max_temp": _shown(self.max_temp),
            "target_temp_step": self.target_temperature_step,
            "current_temperature": _shown(self.current_temperature),
            "temperature_unit": self.temperature_unit,
        }
        if "set_temperature" in self.wrappers:
            shown["temperature"] = _shown(self.target_temperature)
        if (humidity := self.current_humidity) is not None:
            shown["current_humidity"] = humidity
        if "target_humidity" in self.wrappers:
            shown |= {
                "humidity": self.target_humidity,
                "min_humidity": self.min_humidity,
                "max_humidity": self.max_humidity,
            }
        if "fan_mode" in self.wrappers:
            shown |= {"fan_mode": self.fan_mode, "fan_modes": self.fan_modes}
        if self.preset_modes:
            shown |= {"preset_mode": self.preset_mode, "preset_modes": self.preset_modes}
        if "swing" in self.wrappers:
            shown |= {"swing_mode": self.swing_mode, "swing_modes": self.swing_modes}
        return shown

    def _check_mode(self, kind: str, mode: str, modes: list[str]) -> None:
        """Refuse a mode the device does not offer, as Home Assistant's services do."""
        if not modes:
            raise TuyaError(f"{self.device.name} has no {kind} modes")
        if mode not in modes:
            raise ValueError(f"{self.id}: {kind} mode must be one of {modes}, not {mode!r}")

    def set_hvac_mode(self, hvac_mode: str) -> None:
        """Change to one of `hvac_modes`: "off" switches the device off, any other also on."""
        self._check_mode("HVAC", hvac_mode, self.hvac_modes)
        setting: dict[str, Any] = {}
        if "switch" in self.wrappers:
            setting["switch"] = hvac_mode != "off"
        if hvac_mode in self._options("hvac_mode"):
            setting["hvac_mode"] = hvac_mode
        elif hvac_mode == self._switch_only_mode:
            if self.preset_modes and self.preset_mode is None:
                # The device is in a mode of its own such as "off"; a preset takes it out of that.
                setting["preset"] = self.preset_modes[0]
        elif not setting:
            raise TuyaError(f"{self.device.name} has neither a switch nor a mode for {hvac_mode!r}")
        self.set(**setting)

    def set_preset_mode(self, preset_mode: str) -> None:
        """Activate one of `preset_modes`."""
        self._check_mode("preset", preset_mode, self.preset_modes)
        self.set(preset=preset_mode)

    def set_fan_mode(self, fan_mode: str) -> None:
        """Set the fan speed to one of `fan_modes`."""
        self._check_mode("fan", fan_mode, self.fan_modes)
        self.set(fan_mode=fan_mode)

    def set_swing_mode(self, swing_mode: str) -> None:
        """Set how the louvres move, to one of `swing_modes`."""
        self._check_mode("swing", swing_mode, self.swing_modes)
        self.set(swing=swing_mode)

    def set_temperature(self, temperature: float) -> None:
        """Set the target temperature, in `temperature_unit`, from `min_temp` to `max_temp`."""
        if "set_temperature" not in self.wrappers:
            raise TuyaError(f"{self.device.name} has no target temperature")
        low, high = self.min_temp, self.max_temp
        number = isinstance(temperature, (int, float)) and not isinstance(temperature, bool)
        if not (number and low <= temperature <= high):
            raise ValueError(
                f"{self.id}: temperature must be a number from {low} to {high}, not {temperature!r}"
            )
        unit = self._unit_of("set_temperature")
        self.set(set_temperature=_convert(temperature, self.temperature_unit, unit))

    def set_humidity(self, humidity: int) -> None:
        """Set the target humidity, in percent."""
        self.set(target_humidity=humidity)
