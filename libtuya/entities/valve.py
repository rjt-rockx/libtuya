"""Valves.

Follows ``TuyaValveEntity`` in Home Assistant's
``homeassistant/components/tuya/valve.py`` (Apache-2.0), and its generic valve
entity for how the state and its attributes are derived.
"""

from __future__ import annotations

from typing import Any

from .base import Entity

_STATES: dict[bool | None, str] = {True: "closed", False: "open"}


class Valve(Entity):
    """A water valve, or one outlet of an irrigation controller."""

    @property
    def is_open(self) -> bool | None:
        """Whether the valve is open; None if the device does not say."""
        return self.wrappers["control"].read_device_status(self.device.info)

    @property
    def is_closed(self) -> bool | None:
        """Whether the valve is closed; None if the device does not say."""
        is_open = self.is_open
        return None if is_open is None else not is_open

    def summary(self) -> dict[str, Any]:
        """Home Assistant's state ("open" or "closed") and attributes for this entity."""
        closed = self.is_closed
        return {"state": _STATES.get(closed), "is_closed": closed}

    def open(self) -> None:
        """Open the valve."""
        self.set(control=True)

    def close(self) -> None:
        """Close the valve."""
        self.set(control=False)
