"""Cameras.

Follows ``TuyaCameraEntity`` in Home Assistant's
``homeassistant/components/tuya/camera.py`` (Apache-2.0), and its generic
camera entity (``homeassistant/components/camera``) for the state and its
attributes.
"""

from __future__ import annotations

from typing import Any

from .base import Entity


class Camera(Entity):
    """A camera: its live stream, whether it is recording, and its motion detection."""

    def _on(self, attribute: str) -> bool:
        """An on/off attribute's value; False if the camera lacks it or does not report it."""
        wrapper = self.wrappers.get(attribute)
        return bool(wrapper and wrapper.read_device_status(self.device.info))

    @property
    def is_recording(self) -> bool:
        """Whether the camera is recording; False if it does not say."""
        return self._on("recording_status")

    @property
    def motion_detection_enabled(self) -> bool:
        """Whether motion detection is switched on; False if the camera does not say."""
        return self._on("motion_detection_switch")

    def summary(self) -> dict[str, Any]:
        """Home Assistant's state ("recording" or "idle") and attributes for this entity."""
        shown: dict[str, Any] = {"state": "recording" if self.is_recording else "idle"}
        if self.motion_detection_enabled:
            shown["motion_detection"] = True
        return shown

    def stream_source(self) -> str:
        """A short-lived RTSP URL for the live stream, from the cloud.

        `Device.stream_url` offers the other kinds of stream.
        """
        return self.device.stream_url()

    def enable_motion_detection(self) -> None:
        """Switch motion detection on."""
        self.set(motion_detection_switch=True)

    def disable_motion_detection(self) -> None:
        """Switch motion detection off."""
        self.set(motion_detection_switch=False)
