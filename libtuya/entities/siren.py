"""Sirens.

Follows ``TuyaSirenEntity`` in Home Assistant's
``homeassistant/components/tuya/siren.py`` (Apache-2.0).
"""

from __future__ import annotations

from typing import Any

from .base import Entity


class Siren(Entity):
    """A siren, or the one built into a camera or a detector.

    `turn_on` and `turn_off` take no tone, volume or duration: the siren
    sounds as it is set up to.
    """

    @property
    def is_on(self) -> bool | None:
        """Whether the siren is sounding; None if unknown."""
        return self.wrappers["siren"].read_device_status(self.device.info)

    def summary(self) -> dict[str, Any]:
        """Home Assistant's state ("on" or "off") for this entity."""
        return {"state": {True: "on", False: "off"}.get(self.is_on)}
