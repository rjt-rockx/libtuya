"""libtuya: control Tuya devices from Python, locally, without a developer account.

    from libtuya import Tuya

    tuya = Tuya()                       # uses the login saved by `tuya login`
    lamp = tuya.device("Living room")
    lamp.turn_on()
    lamp.entity("light").turn_on(brightness=128, kelvin=3000)
    print(lamp.refresh())               # {"switch_led": True, "bright_value_v2": 500, ...}

See the README for the full picture.
"""

from importlib.metadata import PackageNotFoundError, version

from .client import Tuya
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
    "Tuya",
    "TuyaError",
    "Unmapped",
]
