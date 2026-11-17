"""libtuya: control Tuya devices from Python, locally, without Home Assistant.

    from libtuya import Light, Tuya

    tuya = Tuya()                       # uses the saved login
    lamp = tuya.device("Living room")
    lamp.entity("light", Light).turn_on(brightness=128, color_temp_kelvin=3000)

See the README for the full picture.
"""

from importlib.metadata import PackageNotFoundError, version

from .client import Tuya
from .cloud import Scene
from .device import Device
from .entities import (
    AlarmControlPanel,
    BinarySensor,
    Button,
    Camera,
    Climate,
    Cover,
    Entity,
    Event,
    Fan,
    Humidifier,
    Light,
    Number,
    Select,
    Sensor,
    Siren,
    Switch,
    Vacuum,
    Valve,
)
from .errors import CloudError, DeviceNotFound, LanError, NotLoggedIn, TuyaError, Unmapped
from .lan import LanAddress

try:
    __version__ = version("libtuya")
except PackageNotFoundError:  # running from a source tree that is not installed
    __version__ = "0+unknown"

__all__ = [
    "AlarmControlPanel",
    "BinarySensor",
    "Button",
    "Camera",
    "Climate",
    "CloudError",
    "Cover",
    "Device",
    "DeviceNotFound",
    "Entity",
    "Event",
    "Fan",
    "Humidifier",
    "LanAddress",
    "LanError",
    "Light",
    "NotLoggedIn",
    "Number",
    "Scene",
    "Select",
    "Sensor",
    "Siren",
    "Switch",
    "Tuya",
    "TuyaError",
    "Unmapped",
    "Vacuum",
    "Valve",
]
