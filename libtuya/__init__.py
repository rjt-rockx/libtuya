"""libtuya: control Tuya devices from Python, locally, without Home Assistant.

    from libtuya import Tuya

    tuya = Tuya()                       # uses the saved login
    lamp = tuya.device("Living room")
    lamp.turn_on()

See the README for the full picture.
"""

from importlib.metadata import PackageNotFoundError, version

from .client import Tuya
from .cloud import Scene
from .device import Device
from .entities import Entity, Light
from .errors import CloudError, DeviceNotFound, LanError, NotLoggedIn, TuyaError, Unmapped
from .lan import LanAddress

try:
    __version__ = version("libtuya")
except PackageNotFoundError:  # running from a source tree that is not installed
    __version__ = "0+unknown"

__all__ = [
    "CloudError",
    "Device",
    "DeviceNotFound",
    "Entity",
    "LanAddress",
    "LanError",
    "Light",
    "NotLoggedIn",
    "Scene",
    "Tuya",
    "TuyaError",
    "Unmapped",
]
