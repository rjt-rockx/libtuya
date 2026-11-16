"""The generic entity, and how a device's entities are found.

A Tuya device is a bag of datapoints. Which of them form "a light with
brightness and colour" depends on the device category, and how their values
are scaled depends on the product. Home Assistant has worked both out:

- its Tuya integration lists, per category, the DP codes behind each entity
  (extracted into ``data/ha_tuya.json`` by ``scripts/gen_ha_tables.py``);
- ``tuya-device-handlers`` turns such a list into wrappers that read and write
  values in friendly units, and patches products that misreport themselves.

This module joins the two, so a device here has the same entities, with the
same values, as it would in Home Assistant.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
from collections.abc import Callable, Iterator
from functools import cache
from importlib import resources
from typing import TYPE_CHECKING, Any

from tuya_device_handlers import TUYA_QUIRKS_REGISTRY
from tuya_device_handlers.device_wrapper import DeviceWrapper
from tuya_device_handlers.device_wrapper.common import DPCodeIntegerWrapper
from tuya_device_handlers.device_wrapper.exception import SetValueOutOfRangeError
from tuya_device_handlers.device_wrapper.light import ColorDataWrapper, ColorTempWrapper
from tuya_device_handlers.device_wrapper.sensor import DeltaIntegerWrapper
from tuya_device_handlers.devices import register_tuya_quirks
from tuya_device_handlers.helpers.homeassistant import TuyaUnitOfTemperature
from tuya_sharing import CustomerDevice

from ..errors import TuyaError

if TYPE_CHECKING:
    from ..device import Device

_UNSET: Any = object()
_READ_ONLY_PLATFORMS = {"binary_sensor", "event", "sensor"}
# What the handlers call the on/off attribute: most platforms, sirens, valves.
_ON_OFF = ("switch", "siren", "control")


@cache
def _tables() -> dict[str, Any]:
    register_tuya_quirks()  # imports the per-product fixes shipped with the handlers
    text = resources.files("libtuya").joinpath("data/ha_tuya.json").read_text(encoding="utf-8")
    return json.loads(text, object_hook=_resolve)


def _resolve(node: dict[str, Any]) -> Any:
    """Turn a ``$ref`` marker back into the handlers object it names."""
    if (ref := node.get("$ref")) is None:
        return node
    module, _, path = ref.partition(":")
    target: Any = importlib.import_module(module)
    for name in path.split("."):
        target = getattr(target, name)
    return target


def _codes(value: Any) -> Any:
    """DP code alternatives are tuples upstream; JSON made them lists."""
    return tuple(value) if isinstance(value, list) else value


def _present(description: dict[str, Any], **names: str) -> dict[str, Any]:
    """Keyword arguments for the description fields that are set."""
    return {
        keyword: _codes(description[field])
        for keyword, field in names.items()
        if field in description
    }


def _definition(platform: str, device: CustomerDevice, d: dict[str, Any]) -> Any:
    """Build the handlers' definition for one description.

    Mirrors the `get_default_definition(...)` call in each Home Assistant
    platform's `async_discover_device`.
    """
    module = importlib.import_module(f"tuya_device_handlers.definition.{platform}")
    build: Callable[..., Any] = module.get_default_definition
    key = d["key"]
    match platform:
        case "alarm_control_panel" | "camera" | "fan" | "vacuum":
            return build(device)
        case "climate":
            return build(device, TuyaUnitOfTemperature.CELSIUS)
        case "binary_sensor":
            on_value = d.get("on_value", True)
            return build(
                device,
                _codes(d.get("dpcode")) or key,
                d.get("bitmap_key"),
                set(on_value) if isinstance(on_value, list) else on_value,
            )
        case "sensor":
            return build(device, _codes(d.get("dpcode")) or key, _codes(d.get("wrapper_class")))
        case "event":
            return build(device, key, *_present(d, wrapper_class="wrapper_class").values())
        case "cover":
            return build(
                device,
                instruction_dpcode=key,
                **_present(
                    d,
                    current_position_dpcode="current_position",
                    current_state_dpcode="current_state",
                    current_state_wrapper="current_state_wrapper",
                    instruction_wrapper="instruction_wrapper",
                    set_position_dpcode="set_position",
                ),
            )
        case "humidifier":
            return build(
                device,
                switch_dpcode=_codes(d.get("dpcode")) or key,
                **_present(
                    d, current_humidity_dpcode="current_humidity", humidity_dpcode="humidity"
                ),
            )
        case "light":
            return build(
                device,
                switch_dpcode=key,
                **_present(
                    d,
                    brightness_dpcode="brightness",
                    brightness_max_dpcode="brightness_max",
                    brightness_min_dpcode="brightness_min",
                    color_data_dpcode="color_data",
                    color_mode_dpcode="color_mode",
                    color_temp_dpcode="color_temp",
                    fallback_color_data_mode="fallback_color_data_mode",
                ),
            )
        case _:  # button, number, select, siren, switch, valve
            return build(device, key)


def _name(platform: str, d: dict[str, Any], names: dict[str, dict[str, str]]) -> str | None:
    """English entity name; None for the entity that *is* the device."""
    if "name" in d:
        return d["name"]
    if key := d.get("translation_key"):
        text = names.get(platform, {}).get(key, "")
        if not text or text.startswith("[%"):  # a reference into Home Assistant's own strings
            text = key.replace("_", " ").capitalize()
        return text.format(**d.get("translation_placeholders", {}))
    if device_class := d.get("device_class", {}).get("$ha"):
        return device_class.rpartition(".")[2].replace("_", " ").capitalize()
    return None


def _limits(wrapper: DeviceWrapper[Any]) -> dict[str, Any]:
    """The range of values an attribute takes, in the units its values are given in."""
    if isinstance(wrapper, ColorTempWrapper):
        return {"min": wrapper.min_kelvin, "max": wrapper.max_kelvin, "unit": "K"}
    # Brightness, percentages and fan speeds are remapped from the device's own range.
    if remap := getattr(wrapper, "_remap_helper", None):
        return {"min": remap.target_min, "max": remap.target_max}
    if isinstance(wrapper, DPCodeIntegerWrapper):
        return {"min": wrapper.min_value, "max": wrapper.max_value, "step": wrapper.value_step}
    return {}


class Entity:
    """One controllable or readable feature of a device.

    An entity has named attributes: a switch has one (``switch``), a light up
    to five (``switch``, ``brightness``, ``color_temp``, ``color_data``,
    ``color_mode``). `describe()` lists them with their units and limits.
    Values use Home Assistant's conventions: brightness 0-255, colour
    temperature in kelvin, colour as (hue 0-360, saturation 0-100, value
    0-255), positions and humidity in percent.

    `name` is None for the entity that is the device itself (the light of a
    bulb), otherwise an English label such as "Child lock". `wrappers` holds
    the tuya-device-handlers objects behind the attributes.
    """

    def __init__(
        self,
        device: Device,
        platform: str,
        description: dict[str, Any],
        name: str | None,
        definition: Any,
    ) -> None:
        self.device = device
        self.platform = platform
        self.key: str = description["key"]
        self.name = name
        self.description = description
        self.definition = definition
        self.wrappers: dict[str, DeviceWrapper[Any]] = {
            field.name.removesuffix("_wrapper"): wrapper
            for field in dataclasses.fields(definition)
            if isinstance(wrapper := getattr(definition, field.name), DeviceWrapper)
        }
        self._pushed = False

    @property
    def id(self) -> str:
        """Identifier unique within the device, e.g. ``light.switch_led``."""
        return f"{self.platform}.{self.key}" if self.key else self.platform

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.id} of {self.device.name!r}>"

    def writable(self, attribute: str) -> bool:
        """Whether an attribute can be set (best effort, from the device's spec)."""
        if self.platform in _READ_ONLY_PLATFORMS:
            return False
        code = getattr(self.wrappers[attribute], "dpcode", None)
        return code is None or code in self.device.info.function

    def state(self) -> dict[str, Any]:
        """Value of every attribute, as of the device's last `refresh()` or write."""
        values = {}
        for attribute, wrapper in self.wrappers.items():
            if isinstance(wrapper, DeltaIntegerWrapper) and not self._pushed:
                # The device reports increments, which only add up to a total
                # while its pushes are being followed (see Device.watch).
                values[attribute] = None
                continue
            try:
                values[attribute] = wrapper.read_device_status(self.device.info)
            except NotImplementedError:  # write-only, e.g. a button
                continue
        return values

    def summary(self) -> dict[str, Any]:
        """What Home Assistant would show for this entity: its ``state`` and attributes.

        The classes for each kind of entity use Home Assistant's own names and
        values here ("on", ``brightness``, ``current_temperature`` ...). This
        generic one only knows the entity's `value`.
        """
        return {"state": self.value}

    def describe(self) -> dict[str, dict[str, Any]]:
        """Each attribute with its value and, where known, unit, limits and choices.

        Keys per attribute: ``value``, ``writable``, and any of ``unit``,
        ``min``, ``max``, ``step``, ``options``.
        """
        state = self.state()
        described = {}
        for attribute, wrapper in self.wrappers.items():
            details = {"value": state.get(attribute), "writable": self.writable(attribute)}
            if unit := getattr(wrapper, "native_unit", None):
                details["unit"] = unit
            details |= _limits(wrapper)
            if options := getattr(wrapper, "options", None):
                details["options"] = [str(option) for option in options]
            described[attribute] = details
        return described

    @property
    def on_off(self) -> str | None:
        """Name of the attribute that switches the entity on and off, if it has one."""
        return next((name for name in _ON_OFF if name in self.wrappers), None)

    @property
    def value(self) -> Any:
        """The on/off state if the entity has one, else its only attribute.

        None for an entity with several attributes and no on/off (a cover);
        use `state()` there.
        """
        state = self.state()
        if self.on_off or len(state) != 1:
            return state.get(self.on_off)
        return next(iter(state.values()))

    def commands(self, value: Any = _UNSET, /, **attributes: Any) -> list[dict[str, Any]]:
        """Cloud commands that would apply the given attribute values.

        Raises TuyaError for an unknown or read-only attribute and ValueError
        for a value the device does not accept.
        """
        if value is not _UNSET:
            if len(self.wrappers) != 1:
                raise TuyaError(
                    f"{self.id} has several attributes; name one of {list(self.wrappers)}"
                )
            attributes = {next(iter(self.wrappers)): value}
        commands: list[dict[str, Any]] = []
        for attribute, new in attributes.items():
            if attribute not in self.wrappers:
                raise TuyaError(
                    f"{self.id} has no attribute {attribute!r}; it has {list(self.wrappers)}"
                )
            wrapper = self.wrappers[attribute]
            if not self.writable(attribute):
                raise TuyaError(f"{self.id}.{attribute} is read-only")
            # The wrappers check numbers against the device's range, but not these two.
            options = getattr(wrapper, "options", None)
            if isinstance(new, str) and options and new not in options:
                raise ValueError(f"{self.id}.{attribute} must be one of {[*map(str, options)]}")
            if isinstance(wrapper, ColorDataWrapper):
                hue, saturation, brightness = new
                if not (0 <= hue <= 360 and 0 <= saturation <= 100 and 0 <= brightness <= 255):
                    raise ValueError(
                        f"{self.id}.{attribute} is (hue 0-360, saturation 0-100, value 0-255)"
                    )
            try:
                commands += wrapper.get_update_commands(self.device.info, new)
            except NotImplementedError:
                raise TuyaError(f"{self.id}.{attribute} is read-only") from None
            except SetValueOutOfRangeError:
                limits = self.describe()[attribute]
                allowed = f"{limits.get('min')} to {limits.get('max')}" if "max" in limits else ""
                raise ValueError(
                    f"{self.id}.{attribute}={new!r} is out of range {allowed}".rstrip()
                ) from None
            except Exception as err:
                # The wrappers assume a value of the right type and fail in
                # assorted ways (TypeError, StopIteration, ...) on any other.
                raise ValueError(f"{self.id}.{attribute} does not accept {new!r}") from err
        return commands

    def set(self, value: Any = _UNSET, /, **attributes: Any) -> None:
        """Set attributes: ``switch.set(True)`` or ``cover.set(set_position=40)``.

        Each attribute is written as given; nothing else is changed to make it
        take effect (see `Light.turn_on` for lights).
        """
        self.device.send(self.commands(value, **attributes))

    def turn_on(self) -> None:
        self._switch(True)

    def turn_off(self) -> None:
        self._switch(False)

    def _switch(self, on: bool) -> None:
        if self.on_off is None:
            raise TuyaError(f"{self.id} cannot be switched on or off")
        self.set(**{self.on_off: on})

    def _note_push(self, codes: list[str], timestamp: int) -> None:
        """Tell wrappers that keep a running value about a report pushed by the device."""
        self._pushed = True
        for wrapper in self.wrappers.values():
            wrapper.skip_update(self.device.info, codes, dict.fromkeys(codes, timestamp))


def apply_quirks(info: CustomerDevice) -> None:
    """Patch a device the cloud describes wrongly. Call once per device."""
    _tables()
    TUYA_QUIRKS_REGISTRY.initialise_device_quirk(info)


def definitions(info: CustomerDevice) -> Iterator[tuple[str, dict[str, Any], Any]]:
    """Every (platform, description, definition) Home Assistant would use for a device."""
    for platform, categories in _tables()["platforms"].items():
        for description in categories.get(info.category, ()):
            if definition := _definition(platform, info, description):
                yield platform, description, definition
