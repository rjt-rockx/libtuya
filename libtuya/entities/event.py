"""Events.

Follows ``TuyaEventEntity`` in Home Assistant's
``homeassistant/components/tuya/event.py`` (Apache-2.0), and its generic event
entity (``homeassistant/components/event``) for the attributes.
"""

from __future__ import annotations

from typing import Any

from .base import Entity


class Event(Entity):
    """Something that happens: a doorbell ring, a scene button press.

    What can be read is the last event the device reported, and a second,
    identical one reads the same. `Tuya.subscribe` tells them apart: the
    changes it passes on include this entity's `key` each time the event is
    reported.
    """

    def _last(self) -> tuple[str | None, dict[str, Any]]:
        """Type and attributes of the last event the device reported."""
        event = self.wrappers["event"].read_device_status(self.device.info)
        return (event[0], event[1] or {}) if event else (None, {})

    @property
    def event_types(self) -> list[str]:
        """The kinds of event there are, such as "click" and "double_click"."""
        return list(self.wrappers["event"].options)

    @property
    def event_type(self) -> str | None:
        """Kind of the last event, one of `event_types`; None if there has been none."""
        return self._last()[0]

    @property
    def event_attributes(self) -> dict[str, Any]:
        """What came with the last event, such as a doorbell's ``message``; often nothing."""
        return self._last()[1]

    def summary(self) -> dict[str, Any]:
        """Home Assistant's attributes for this entity.

        Its state there is the time it received the last event, which the
        device does not report, so there is no ``state`` here.
        """
        return {
            "event_type": self.event_type,
            "event_types": self.event_types,
            **self.event_attributes,
        }
