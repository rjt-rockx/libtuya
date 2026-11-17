"""Switches.

Follows ``TuyaSwitchEntity`` in Home Assistant's
``homeassistant/components/tuya/switch.py`` (Apache-2.0).
"""

from __future__ import annotations

from typing import Any

from .base import Entity, on_off_state


class Switch(Entity):
    """Something that is on or off: a socket, a relay, a child lock.

    `turn_on()` and `turn_off()` switch it.
    """

    @property
    def is_on(self) -> bool | None:
        """Whether it is on; None if unknown."""
        return self.wrappers["switch"].read_device_status(self.device.info)

    def summary(self) -> dict[str, Any]:
        """Home Assistant's state ("on" or "off") for this entity."""
        return {"state": on_off_state(self.is_on)}
