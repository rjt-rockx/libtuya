"""Settings with a fixed list of choices.

Follows ``TuyaSelectEntity`` in Home Assistant's
``homeassistant/components/tuya/select.py`` (Apache-2.0).
"""

from __future__ import annotations

from typing import Any

from .base import Entity


class Select(Entity):
    """A setting with a fixed list of choices: a mode, a volume level, a motor's direction."""

    @property
    def option(self) -> str | None:
        """The current choice, one of `options`; None if unknown."""
        return self.wrappers["select"].read_device_status(self.device.info)

    @property
    def options(self) -> list[str]:
        """The choices, under the device's own names."""
        return list(self.wrappers["select"].options)

    def select(self, option: str) -> None:
        """Change the setting to one of `options`; anything else is a ValueError."""
        if option not in self.options:
            raise ValueError(f"{self.id} must be one of {self.options}, not {option!r}")
        self.set(option)

    def summary(self) -> dict[str, Any]:
        """Home Assistant's state (the current choice) and ``options`` for this entity."""
        return {"state": self.option, "options": self.options}
