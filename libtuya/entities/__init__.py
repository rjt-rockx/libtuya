"""Entities: the lights, switches, sensors ... that make up a device.

One class per kind, named after Home Assistant's platforms and behaving like
Home Assistant's entities do. `Entity` is what they share.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .alarm_control_panel import AlarmControlPanel
from .base import Entity, _name, _tables, apply_quirks, definitions
from .binary_sensor import BinarySensor
from .button import Button
from .camera import Camera
from .climate import Climate
from .cover import Cover
from .event import Event
from .fan import Fan
from .humidifier import Humidifier
from .light import Light
from .number import Number
from .select import Select
from .sensor import Sensor
from .siren import Siren
from .switch import Switch
from .vacuum import Vacuum
from .valve import Valve

if TYPE_CHECKING:
    from ..device import Device

# Home Assistant platform -> the class for its entities.
CLASSES: dict[str, type[Entity]] = {
    "alarm_control_panel": AlarmControlPanel,
    "binary_sensor": BinarySensor,
    "button": Button,
    "camera": Camera,
    "climate": Climate,
    "cover": Cover,
    "event": Event,
    "fan": Fan,
    "humidifier": Humidifier,
    "light": Light,
    "number": Number,
    "select": Select,
    "sensor": Sensor,
    "siren": Siren,
    "switch": Switch,
    "vacuum": Vacuum,
    "valve": Valve,
}


def build_entities(device: Device) -> list[Entity]:
    """Create a device's entities, leaving out those with nothing to read or write."""
    names = _tables()["names"]
    entities = [
        CLASSES[platform](
            device, platform, description, _name(platform, description, names), definition
        )
        for platform, description, definition in definitions(device.info)
    ]
    # Home Assistant gives every camera an entity, even with nothing to read.
    return [entity for entity in entities if entity.wrappers or entity.platform == "camera"]


__all__ = [
    "CLASSES",
    "AlarmControlPanel",
    "BinarySensor",
    "Button",
    "Camera",
    "Climate",
    "Cover",
    "Entity",
    "Event",
    "Fan",
    "Humidifier",
    "Light",
    "Number",
    "Select",
    "Sensor",
    "Siren",
    "Switch",
    "Vacuum",
    "Valve",
    "apply_quirks",
    "build_entities",
    "definitions",
]
