"""Robot vacuums.

Follows ``TuyaVacuumEntity`` in Home Assistant's
``homeassistant/components/tuya/vacuum.py`` (Apache-2.0), and its generic
vacuum entity (``homeassistant/components/vacuum``) for the state and its
attributes.
"""

from __future__ import annotations

from typing import Any

from ..errors import TuyaError
from .base import Entity


class Vacuum(Entity):
    """A robot vacuum.

    Models differ in which of `start`, `stop`, `pause`, `return_to_base` and
    `locate` they take: ``describe()["action"]["options"]`` lists them, and
    the others raise TuyaError.
    """

    @property
    def activity(self) -> str | None:
        """What the vacuum is doing; None if it does not say.

        One of "cleaning", "docked", "idle", "paused" and "returning".
        """
        activity = self._read("activity")
        return str(activity) if activity else None

    @property
    def fan_speed(self) -> str | None:
        """The suction the vacuum is set to, one of `fan_speed_list`; None if unknown."""
        return self._read("fan_speed")

    @property
    def fan_speed_list(self) -> list[str]:
        """The suction settings, such as "gentle" and "strong"; empty if there is no choice."""
        return list(getattr(self.wrappers.get("fan_speed"), "options", ()))

    def writable(self, attribute: str) -> bool:
        """Whether `set` can change an attribute; ``activity`` is only read."""
        return attribute != "activity" and super().writable(attribute)

    def summary(self) -> dict[str, Any]:
        """Home Assistant's state (the activity) and attributes for this entity."""
        shown: dict[str, Any] = {"state": self.activity}
        if "fan_speed" in self.wrappers:
            shown |= {"fan_speed": self.fan_speed, "fan_speed_list": self.fan_speed_list}
        return shown

    def _act(self, action: str) -> None:
        """Have the vacuum do one of the things it can be told to."""
        if action not in getattr(self.wrappers.get("action"), "options", ()):
            raise TuyaError(f"{self.device.name} cannot {action.replace('_', ' ')}")
        self.set(action=action)

    def start(self) -> None:
        """Start cleaning."""
        self._act("start")

    def stop(self) -> None:
        """Stop cleaning."""
        self._act("stop")

    def pause(self) -> None:
        """Pause cleaning."""
        self._act("pause")

    def return_to_base(self) -> None:
        """Send the vacuum back to its dock."""
        self._act("return_to_base")

    def locate(self) -> None:
        """Have the vacuum show where it is, usually with a sound."""
        self._act("locate")

    def set_fan_speed(self, fan_speed: str) -> None:
        """Set the suction to one of `fan_speed_list`."""
        self.set(fan_speed=fan_speed)
