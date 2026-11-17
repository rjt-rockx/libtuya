"""Curtains, blinds, shutters and garage doors.

Follows ``TuyaCoverEntity`` in Home Assistant's
``homeassistant/components/tuya/cover.py`` (Apache-2.0), and its generic cover
entity for how the state and its attributes are derived.
"""

from __future__ import annotations

from typing import Any

from ..errors import TuyaError
from .base import Entity

_STATES: dict[bool | None, str] = {True: "closed", False: "open"}


class Cover(Entity):
    """A curtain, blind, shutter or garage door.

    Positions are percentages of fully open: 0 is closed and 100 is open,
    whichever way round the device itself counts. `open` and `close` send a
    cover that takes positions to 100 and 0, and any other the device's own
    open and close instructions.
    """

    @property
    def current_position(self) -> int | None:
        """How far open the cover is, 0 (closed) to 100 (open); None if it does not say.

        A cover that does not report where it is gives the position it was last sent to.
        """
        return self._read("current_position", "set_position")

    @property
    def current_tilt_position(self) -> int | None:
        """How far open the slats are, 0 to 100; None for a cover without tilting slats."""
        return self._read("tilt_position")

    @property
    def is_closed(self) -> bool | None:
        """Whether the cover is closed; None if the device does not say.

        Judged by the position where there is one, else by what the device
        reports as its state.
        """
        if (position := self.current_position) is not None:
            return position == 0
        return self._read("current_state")

    def summary(self) -> dict[str, Any]:
        """Home Assistant's state ("open" or "closed") and attributes for this entity."""
        closed = self.is_closed
        shown: dict[str, Any] = {"state": _STATES.get(closed), "is_closed": closed}
        if (position := self.current_position) is not None:
            shown["current_position"] = position
        if (tilt := self.current_tilt_position) is not None:
            shown["current_tilt_position"] = tilt
        return shown

    def _instruct(self, action: str) -> None:
        """Send the device one of its own instructions: open, close or stop."""
        if action not in getattr(self.wrappers.get("instruction"), "options", ()):
            raise TuyaError(f"{self.id} cannot {action}")
        self.set(instruction=action)

    def open(self) -> None:
        """Open the cover fully."""
        if "set_position" in self.wrappers:
            self.set(set_position=100)
        else:
            self._instruct("open")

    def close(self) -> None:
        """Close the cover fully."""
        if "set_position" in self.wrappers:
            self.set(set_position=0)
        else:
            self._instruct("close")

    def stop(self) -> None:
        """Stop the cover where it is."""
        self._instruct("stop")

    def set_position(self, position: int) -> None:
        """Move the cover to a position, 0 (closed) to 100 (open)."""
        self.set(set_position=position)

    def set_tilt_position(self, tilt_position: int) -> None:
        """Tilt the slats to a position, 0 (closed) to 100 (open)."""
        self.set(tilt_position=tilt_position)
