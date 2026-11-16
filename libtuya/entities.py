"""Entities: the lights, switches, sensors ... that make up a device.

A Tuya device is a bag of datapoints. Which of them form "a light with
brightness and colour" depends on the device category, and how their values
are scaled depends on the product. Home Assistant has worked both out:

- its Tuya integration lists, per category, the DP codes behind each entity
  (extracted into ``data/ha_tuya.json`` by ``scripts/gen_ha_tables.py``);
- ``tuya-device-handlers`` turns such a list into wrappers that read and write
  values in friendly units, and patches products that misreport themselves.

This module joins the two, so a device here has the same entities, with the
same values, as it would in Home Assistant.

``Light.turn_on`` follows ``TuyaLightEntity.async_turn_on`` in Home Assistant's
``homeassistant/components/tuya/light.py`` (Apache-2.0).
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
from tuya_device_handlers.device_wrapper.sensor import DeltaIntegerWrapper
from tuya_device_handlers.devices import register_tuya_quirks
from tuya_device_handlers.helpers.homeassistant import TuyaUnitOfTemperature
from tuya_sharing import CustomerDevice

from .errors import TuyaError

if TYPE_CHECKING:
    from .device import Device

_UNSET: Any = object()
_READ_ONLY_PLATFORMS = {"binary_sensor", "event", "sensor"}


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


class Entity:
    """One controllable or readable feature of a device.

    Its attributes are the handlers' wrappers: a switch has one (``switch``), a
    light up to five (``switch``, ``brightness``, ``color_temp``, ``color_data``,
    ``color_mode``). Values use Home Assistant's conventions: brightness 0-255,
    colour temperature in kelvin, colour as (hue 0-360, saturation 0-100,
    value 0-255), positions and humidity in percent.
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
        """Current value of every attribute, from the device's last known status."""
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

    def pushed(self, codes: list[str], timestamp: int) -> None:
        """Note a report pushed by the device, for wrappers that keep a running value."""
        self._pushed = True
        for wrapper in self.wrappers.values():
            wrapper.skip_update(self.device.info, codes, dict.fromkeys(codes, timestamp))

    @property
    def value(self) -> Any:
        """The switch state if the entity has one, else its only attribute."""
        state = self.state()
        if "switch" in state or len(state) != 1:
            return state.get("switch")
        return next(iter(state.values()))

    def commands(self, value: Any = _UNSET, /, **attributes: Any) -> list[dict[str, Any]]:
        """Cloud commands that would apply the given attribute values.

        Raises ValueError for a value outside the device's range.
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
            # Some wrappers fail obscurely on a choice the device does not offer.
            options = getattr(wrapper, "options", None)
            if isinstance(new, str) and options and new not in options:
                raise ValueError(f"{self.id}.{attribute} must be one of {[*map(str, options)]}")
            try:
                commands += wrapper.get_update_commands(self.device.info, new)
            except NotImplementedError:
                raise TuyaError(f"{self.id}.{attribute} is read-only") from None
        return commands

    def set(self, value: Any = _UNSET, /, **attributes: Any) -> None:
        """Set attributes: ``switch.set(True)`` or ``light.set(switch=True, brightness=128)``."""
        self.device.send(self.commands(value, **attributes))

    def turn_on(self) -> None:
        self.set(switch=True)

    def turn_off(self) -> None:
        self.set(switch=False)


class Light(Entity):
    """A light, with the mode switching colour and white changes need."""

    @property
    def in_color_mode(self) -> bool:
        """Whether the light currently shows a colour rather than white."""
        if "color_data" not in self.wrappers:
            return False
        if "brightness" not in self.wrappers and "color_temp" not in self.wrappers:
            return True
        mode = self.wrappers.get("color_mode")
        return mode is not None and mode.read_device_status(self.device.info) != "white"

    @property
    def brightness(self) -> int | None:
        """Current brightness, 0-255, in whichever mode the light is in."""
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
        """Turn on, optionally setting brightness (0-255), white temperature or colour."""
        wrappers, info = self.wrappers, self.device.info
        commands = wrappers["switch"].get_update_commands(info, True)
        mode = wrappers.get("color_mode")

        if kelvin is not None and "color_temp" in wrappers:
            if mode:
                commands += mode.get_update_commands(info, "white")
            commands += wrappers["color_temp"].get_update_commands(info, kelvin)

        colour = wrappers.get("color_data")
        if colour and (
            hs is not None or (brightness is not None and kelvin is None and self.in_color_mode)
        ):
            if mode:
                commands += mode.get_update_commands(info, "colour")
            if hs is None:
                hs = (colour.read_device_status(info) or (0.0, 0.0, 0.0))[:2]
            if brightness is None:
                brightness = self.brightness or 255
            commands += colour.get_update_commands(info, (*hs, brightness))
        elif brightness is not None and "brightness" in wrappers:
            commands += wrappers["brightness"].get_update_commands(info, brightness)

        self.device.send(commands)


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


def build_entities(device: Device) -> list[Entity]:
    """Create a device's entities, leaving out those with nothing to read or write."""
    names = _tables()["names"]
    entities = [
        (Light if platform == "light" else Entity)(
            device, platform, description, _name(platform, description, names), definition
        )
        for platform, description, definition in definitions(device.info)
    ]
    return [entity for entity in entities if entity.wrappers]
