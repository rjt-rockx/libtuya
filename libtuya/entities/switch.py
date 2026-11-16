"""Switches.

Follows ``TuyaSwitchEntity`` in Home Assistant's
``homeassistant/components/tuya/switch.py`` (Apache-2.0).
"""

from __future__ import annotations

from typing import Any

from .base import Entity


class Switch(Entity):
    """Something that is on or off: a socket, a relay, a child lock."""

    @property
    def is_on(self) -> bool | None:
        return self.wrappers["switch"].read_device_status(self.device.info)

    def summary(self) -> dict[str, Any]:
        return {"state": {True: "on", False: "off"}.get(self.is_on)}
