"""The entry point: an account, its saved state and its devices."""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import cloud as cloud_api
from .device import Device
from .errors import CloudError, DeviceNotFound, LanError, NotLoggedIn, TuyaError
from .lan import LanAddress, discover, probe_version

_LOGGER = logging.getLogger(__name__)


class Tuya:
    """A Smart Life / Tuya Smart account and its devices.

    State lives in `home` (default ``~/.libtuya``, or ``$LIBTUYA_HOME``):
    ``session.json`` holds the login and ``devices.json`` the device list with
    local keys, datapoint maps and LAN addresses. After the first
    `devices(refresh=True)` the cloud is only contacted when a device cannot
    be reached on the LAN, and not at all with ``cloud_fallback=False``.

    The API is synchronous and blocking; from asyncio, call it through
    ``asyncio.to_thread``.
    """

    def __init__(self, home: str | Path | None = None, *, cloud_fallback: bool = True) -> None:
        self.home = Path(home or os.environ.get("LIBTUYA_HOME") or Path.home() / ".libtuya")
        self.cloud_fallback = cloud_fallback
        self._cloud: cloud_api.Cloud | None = None
        self._devices: list[Device] | None = None

    # -- account ----------------------------------------------------------

    @property
    def logged_in(self) -> bool:
        return "token_info" in self._read("session.json")

    def login(
        self,
        user_code: str,
        show_qr: Callable[[str], None],
        *,
        timeout: float = 180.0,
        interval: float = 2.0,
    ) -> None:
        """Log in by scanning a QR code with the Smart Life or Tuya Smart app.

        `user_code` is shown in the app under Me > Settings > Account and
        Security > User Code. `show_qr` receives the text to display as a QR
        code; this call then waits until it has been scanned and approved.
        """
        token = cloud_api.request_qr(user_code)
        show_qr(cloud_api.QR_PREFIX + token)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if session := cloud_api.poll_login(user_code, token):
                self._write("session.json", session)
                self._cloud = None
                return
            time.sleep(interval)
        raise CloudError("the QR code was not scanned in time")

    def logout(self) -> None:
        """Revoke the login and delete the saved session and device list."""
        if self.logged_in:
            try:
                self.cloud.logout()
            except CloudError as err:
                _LOGGER.debug("Could not revoke the session: %s", err)
        for name in ("session.json", "devices.json"):
            (self.home / name).unlink(missing_ok=True)
        self._cloud = self._devices = None

    @property
    def cloud(self) -> cloud_api.Cloud:
        if self._cloud is None:
            session = self._read("session.json")
            if "token_info" not in session:
                raise NotLoggedIn("not logged in; run `tuya login`")
            self._cloud = cloud_api.Cloud(
                session, lambda updated: self._write("session.json", updated)
            )
        return self._cloud

    # -- devices ----------------------------------------------------------

    def devices(self, refresh: bool = False, scan_timeout: float = 8.0) -> list[Device]:
        """The account's devices.

        Served from the saved list unless `refresh` is set or there is none
        yet; a refresh asks the cloud and then looks for the devices on the LAN.
        """
        if refresh or (self._devices is None and not (self.home / "devices.json").exists()):
            known = {device.id: device.address for device in self._devices or self._load()}
            self._devices = [
                Device(self, record, known.get(record["id"])) for record in self.cloud.devices()
            ]
            try:
                self.scan(scan_timeout)
            except LanError as err:
                _LOGGER.warning("%s", err)
                self._save()
        elif self._devices is None:
            self._devices = self._load()
        return self._devices

    def device(self, ref: str) -> Device:
        """Find a device by id, name, position in `devices()` (from 1) or part of its name."""
        devices = self.devices()
        lowered = ref.lower()
        exact = [d for d in devices if d.id == ref or d.name.lower() == lowered]
        if not exact and ref.isdigit() and 1 <= int(ref) <= len(devices):
            exact = [devices[int(ref) - 1]]
        found = exact or [d for d in devices if lowered in d.name.lower()]
        if len(found) == 1:
            return found[0]
        if not found:
            raise DeviceNotFound(f"no device matches {ref!r}")
        raise DeviceNotFound(f"{ref!r} matches several devices: {', '.join(d.name for d in found)}")

    def scan(self, timeout: float = 8.0) -> dict[str, LanAddress]:
        """Find the devices on the LAN and remember their addresses."""
        devices = self.devices()
        found = discover({d.id: d.info.local_key for d in devices if d.info.local_key}, timeout)
        for device in devices:
            # A device that stayed silent keeps its last known address.
            if device.id in found and found[device.id] != device.address:
                device.moved(found[device.id])
        self._save()
        return found

    def locate(self, device: Device, ip: str, version: str | None = None) -> LanAddress:
        """Set a device's LAN address by hand, for networks where discovery fails.

        Without `version` the protocol versions are tried in turn.
        """
        address = (
            LanAddress(ip, version)
            if version
            else probe_version(device.id, device.info.local_key, ip)
        )
        device.moved(address)
        self._save()
        return address

    # -- used by Device ---------------------------------------------------

    def gateway_of(self, device: Device) -> Device | None:
        """The gateway a sub-device (Zigbee, Bluetooth) is reached through, if it is one.

        The cloud does not link the two, and its `sub` flag is also set on
        gateways. What does tell them apart: a sub-device uses its gateway's
        local key and, unlike the gateway, never shows up on the LAN itself.
        """
        if device.address or not device.info.local_key:
            return None
        gateways = [
            other
            for other in self.devices()
            if other.address and other.info.local_key == device.info.local_key
        ]
        return gateways[0] if len(gateways) == 1 else None

    def relocate(self, device: Device) -> bool:
        """Look for a device that stopped answering; True if it has a new address."""
        target = self.gateway_of(device) or device
        try:
            found = discover({target.id: target.info.local_key}, timeout=6.0).get(target.id)
        except LanError:
            return False
        if found is None or found == target.address:
            return False
        target.moved(found)
        self._save()
        return True

    def cloud_send(self, device: Device, commands: list[dict[str, Any]], reason: TuyaError) -> None:
        self._fall_back(device, reason).send(device.id, commands)

    def cloud_refresh(self, device: Device, reason: TuyaError) -> None:
        fresh = self._fall_back(device, reason).device(device.id)
        if fresh is None:
            raise CloudError(f"the cloud no longer lists {device.name}")
        device.info.online = fresh["online"]
        device.status.update(fresh["status"])

    def _fall_back(self, device: Device, reason: TuyaError) -> cloud_api.Cloud:
        if not self.cloud_fallback:
            raise reason
        _LOGGER.info("%s: %s; using the cloud", device.name, reason)
        try:
            return self.cloud
        except NotLoggedIn:
            raise reason from None

    # -- storage ----------------------------------------------------------

    def _load(self) -> list[Device]:
        saved = self._read("devices.json")
        addresses = {
            dev_id: LanAddress(**address) for dev_id, address in saved.get("lan", {}).items()
        }
        return [
            Device(self, record, addresses.get(record["id"])) for record in saved.get("devices", [])
        ]

    def _save(self) -> None:
        devices = self._devices or []
        self._write(
            "devices.json",
            {
                "devices": [d.record for d in devices],
                "lan": {d.id: vars(d.address) for d in devices if d.address},
            },
        )

    def _read(self, name: str) -> dict[str, Any]:
        try:
            return json.loads((self.home / name).read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _write(self, name: str, data: dict[str, Any]) -> None:
        """Write atomically and privately: these files hold tokens and local keys."""
        self.home.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = self.home / f".{name}.tmp"
        with open(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as file:
            json.dump(data, file, indent=1)
        temporary.replace(self.home / name)
