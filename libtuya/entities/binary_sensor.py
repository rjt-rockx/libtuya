"""Binary sensors.

Follows ``TuyaBinarySensorEntity`` in Home Assistant's
``homeassistant/components/tuya/binary_sensor.py`` (Apache-2.0).
"""

from __future__ import annotations

from typing import Any

from .base import Entity, on_off_state


class BinarySensor(Entity):
    """A sensor that is on or off: motion, an open door, a leak, a fault."""

    @property
    def is_on(self) -> bool | None:
        """Whether the sensor detects what it watches for; None if the device has not said yet."""
        return self.wrappers["binary_sensor"].read_device_status(self.device.info)

    def summary(self) -> dict[str, Any]:
        return {"state": on_off_state(self.is_on)}
