"""Buttons.

Follows ``TuyaButtonEntity`` in Home Assistant's
``homeassistant/components/tuya/button.py`` (Apache-2.0).
"""

from __future__ import annotations

from typing import Any

from .base import Entity


class Button(Entity):
    """Something that can be pressed, with no state of its own: "Restart", "Reset filter"."""

    def press(self) -> None:
        """Press the button."""
        self.set(button=True)

    def summary(self) -> dict[str, Any]:
        """Home Assistant's state for this entity, which is always unknown here.

        Home Assistant shows when it last pressed the button itself; the
        device keeps no such record.
        """
        return {"state": None}
