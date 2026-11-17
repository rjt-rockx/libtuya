"""Alarms.

Follows ``TuyaAlarmEntity`` in Home Assistant's
``homeassistant/components/tuya/alarm_control_panel.py`` (Apache-2.0), and its
generic alarm entity (``homeassistant/components/alarm_control_panel``) for
the state and its attributes.
"""

from __future__ import annotations

from typing import Any

from ..errors import TuyaError
from .base import Entity


class AlarmControlPanel(Entity):
    """An alarm that can be armed and disarmed.

    No action takes a code: these alarms do not ask for one.
    """

    @property
    def alarm_state(self) -> str | None:
        """Whether the alarm is armed, and how; None if unknown.

        One of "disarmed", "armed_home", "armed_away" and "triggered". An
        armed alarm is "triggered" while a sensor has set it off, but not for
        a sensor's low-battery warning.
        """
        state = self.wrappers["state"].read_device_status(self.device.info)
        return str(state) if state else None

    @property
    def changed_by(self) -> str | None:
        """What raised the alarm, in the device's words; None while nothing has.

        Usually the name of the sensor that set it off, or a low-battery warning.
        """
        wrapper = self.wrappers.get("changed_by")
        return None if wrapper is None else wrapper.read_device_status(self.device.info)

    def summary(self) -> dict[str, Any]:
        """Home Assistant's state (`alarm_state`) and attributes for this entity."""
        return {"state": self.alarm_state, "changed_by": self.changed_by}

    def writable(self, attribute: str) -> bool:
        """Whether `set` can change an attribute: only ``action``, as `disarm` and the others do."""
        return attribute == "action" and super().writable(attribute)

    def state(self) -> dict[str, Any]:
        """As `Entity.state`, without ``action``, which is only set."""
        values = super().state()
        values.pop("action", None)
        return values

    def describe(self) -> dict[str, dict[str, Any]]:
        """As `Entity.describe`, without the device's raw modes as the options of ``state``."""
        described = super().describe()
        described["state"].pop("options", None)
        return described

    def _act(self, action: str) -> None:
        """Put the alarm in one of the modes it has."""
        if action not in self.wrappers["action"].options:
            raise TuyaError(f"{self.device.name} cannot {action.replace('_', ' ')}")
        self.set(action=action)

    def disarm(self) -> None:
        """Disarm the alarm."""
        self._act("disarm")

    def arm_home(self) -> None:
        """Arm the alarm for while someone is at home."""
        self._act("arm_home")

    def arm_away(self) -> None:
        """Arm the alarm for while nobody is at home."""
        self._act("arm_away")

    def trigger(self) -> None:
        """Set the alarm off."""
        self._act("trigger")
