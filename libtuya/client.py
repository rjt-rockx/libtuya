"""The entry point: an account, its saved state and its devices."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import cloud as cloud_api
from .cloud import Record, Scene
from .device import Device
from .errors import CloudError, DeviceNotFound, LanError, NotLoggedIn, TuyaError
from .lan import LanAddress, discover, probe_version

_LOGGER = logging.getLogger(__name__)


class Tuya:
    """A Smart Life / Tuya Smart account and its devices.

    State lives in `home` (default ``~/.libtuya``, or ``$LIBTUYA_HOME``):
    ``session.json`` holds the login and ``devices.json`` the device list with
    local keys, datapoint maps and LAN addresses. Once the device list has
    been fetched, the cloud is only contacted when a device cannot be reached
    on the LAN (never, with ``cloud_fallback=False``), for scenes, and while
    `subscribe` is active.

    `timeout` is how long to wait for a device on the LAN, in seconds.

    The API is synchronous and blocking; from asyncio, call it through
    ``asyncio.to_thread``. One `Tuya` can be shared between threads.
    """

    def __init__(
        self,
        home: str | Path | None = None,
        *,
        cloud_fallback: bool = True,
        timeout: float = 5.0,
    ) -> None:
        self.home = Path(home or os.environ.get("LIBTUYA_HOME") or Path.home() / ".libtuya")
        self.cloud_fallback = cloud_fallback
        self.timeout = timeout
        self._cloud: cloud_api.Cloud | None = None
        self._devices: list[Device] | None = None
        self._home_ids: list[str] = []
        self._lock = threading.RLock()  # guards the device list

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
        client_id: str = cloud_api.CLIENT_ID,
        schema: str = cloud_api.SCHEMA,
    ) -> None:
        """Log in by scanning a QR code with the Smart Life or Tuya Smart app.

        `user_code` is shown in the app under Me > gear icon > Account and
        Security > User Code. `show_qr` receives the text to display as a QR
        code; this call then waits until it has been scanned and approved.

        `client_id` and `schema` identify the application to Tuya; the
        defaults are Home Assistant's (see docs/login.md).
        """
        attempt = cloud_api.QrLogin(user_code, client_id, schema)
        show_qr(attempt.text)
        deadline = time.monotonic() + timeout
        waiting = "no answer"
        while time.monotonic() < deadline:
            try:
                session, waiting = attempt.poll()
            except CloudError as err:  # a network blip should not end the wait
                session, waiting = None, str(err)
            if session:
                self._write("session.json", session)
                self._cloud = None
                return
            time.sleep(interval)
        raise CloudError(f"the QR code was not scanned and approved in time ({waiting})")

    def logout(self) -> None:
        """Revoke the login and delete the saved session and device list."""
        if self.logged_in:
            try:
                self.cloud.logout()
            except TuyaError as err:
                _LOGGER.warning(
                    "The login was removed here but not revoked at Tuya (%s); it can be "
                    "removed in the app under Me > gear icon > Account and Security",
                    err,
                )
        for name in ("session.json", "devices.json"):
            (self.home / name).unlink(missing_ok=True)
        self._cloud = self._devices = None
        self._home_ids = []

    @property
    def cloud(self) -> cloud_api.Cloud:
        """The account's cloud connection; raises NotLoggedIn without a saved login."""
        with self._lock:
            if self._cloud is None:
                session = self._read("session.json")
                if "token_info" not in session:
                    raise NotLoggedIn("not logged in; run `tuya login`")
                self._cloud = cloud_api.Cloud(
                    session, lambda updated: self._write("session.json", updated)
                )
            return self._cloud

    # -- devices ----------------------------------------------------------

    def devices(
        self, refresh: bool = False, scan_timeout: float = 8.0, *, accept_empty: bool = False
    ) -> list[Device]:
        """The account's devices.

        Served from the saved list unless `refresh` is set or there is none
        yet. A refresh asks the cloud, looks for the devices on the LAN (which
        takes `scan_timeout` seconds unless every device answers sooner) and
        returns new `Device` objects.

        A device the cloud did not fully describe keeps the description saved
        for it, if any; its ``record["incomplete"]`` says what was missing. If
        the cloud lists no devices at all while some are saved, the saved list
        is kept and CloudError raised, unless `accept_empty` is set.
        """
        with self._lock:
            if refresh or not self._known():
                self._fetch(accept_empty)
                try:
                    self.scan(scan_timeout)
                except LanError as err:
                    _LOGGER.warning("%s", err)
                    self._save()
            return self._known()

    def device(self, ref: str | int) -> Device:
        """Find a device by id, name, position in `devices()` (from 1) or part of its name."""
        devices = self.devices()
        ref = str(ref)
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
        """Find the devices on the LAN and remember their addresses.

        Returns the addresses heard this time. A device that stayed silent
        keeps the address it had.
        """
        with self._lock:
            devices = self._known() or self._fetch()
        found = discover({device.id: device.local_key for device in devices}, timeout)
        with self._lock:
            for device in devices:
                if device.id in found and found[device.id] != device.address:
                    device._moved(found[device.id])
            self._save()
        return found

    def locate(self, device: Device, ip: str, version: str | None = None) -> LanAddress:
        """Set a device's LAN address by hand, for networks where discovery fails.

        The device is contacted to confirm the address: with the protocol
        `version` given (e.g. "3.4"), else trying each version in turn.
        Raises LanError if it does not answer.
        """
        address = probe_version(device.id, device.local_key, ip, version, self.timeout)
        device._moved(address)
        self._save()
        return address

    def gateway_of(self, device: Device) -> Device | None:
        """The gateway a sub-device (Zigbee, Bluetooth) is reached through, if it is one.

        The cloud does not link the two, and its `sub` flag is also set on
        gateways. What does tell them apart: a sub-device never shows up on
        the LAN itself, and its local key is the one its gateway answers to.
        The gateway's own record has that same key, or none at all.
        """
        if device.address or not device.local_key:
            return None
        on_lan = [other for other in self.devices() if other.address]
        for gateways in (
            [other for other in on_lan if other.local_key == device.local_key],
            [other for other in on_lan if not other.local_key],
        ):
            if gateways:
                return gateways[0] if len(gateways) == 1 else None
        return None

    # -- cloud features -----------------------------------------------------

    def scenes(self) -> list[Scene]:
        """The tap-to-run scenes defined in the app, fetched from the cloud."""
        return self._ask_cloud(lambda cloud: cloud.scenes(self._homes()))

    def run_scene(self, scene: Scene | str) -> None:
        """Run a scene, given as a `Scene` or by its name or id."""
        if not isinstance(scene, Scene):
            matches = [s for s in self.scenes() if scene in (s.id, s.name)]
            if len(matches) != 1:
                raise TuyaError(f"{len(matches)} scenes are called {scene!r}")
            scene = matches[0]
        self._ask_cloud(lambda cloud: cloud.run_scene(scene))

    def subscribe(self, callback: Callable[[Device, dict[str, Any]], None]) -> Callable[[], None]:
        """Follow every device through the cloud's push channel.

        `callback(device, changed)` is called on a background thread each time
        a device reports: `changed` holds the new status by DP code and is
        empty when only `device.online` changed. `device.status` and its
        entities are up to date by then. Returns a function that ends the
        subscription.

        This works for devices that are not on the LAN too. For one device on
        the LAN, `Device.watch` gets the same without the cloud.
        """
        devices = {device.id: device for device in self.devices()}

        def on_message(message: dict[str, Any]) -> None:
            try:
                data = message.get("data") or {}
                if message.get("protocol") == cloud_api.REPORT:
                    device = devices.get(str(data.get("devId")))
                    if device is None:
                        return
                    changed = device._apply_report(data.get("status") or ())
                    if not changed:
                        return
                elif (kind := data.get("bizCode")) in ("online", "offline"):
                    device = devices.get(str((data.get("bizData") or {}).get("devId")))
                    if device is None:
                        return
                    device.info.online, changed = kind == "online", {}
                else:
                    return
                callback(device, changed)
            except Exception:  # must not take the SDK's network thread down
                _LOGGER.exception("Error while handling a pushed message")

        subscribed = [(d.id, bool(d.record.get("support_local"))) for d in devices.values()]
        homes = self._homes()
        return self._ask_cloud(lambda cloud: cloud.listen(subscribed, homes, on_message))

    # -- for Device ---------------------------------------------------------

    def _relocate(self, device: Device) -> bool:
        """Look for a device that stopped answering; True if it has a new address."""
        target = self.gateway_of(device) or device
        try:
            found = discover({target.id: target.local_key}, timeout=6.0).get(target.id)
        except LanError:
            return False
        if found is None or found == target.address:
            return False
        target._moved(found)
        self._save()
        return True

    def _cloud_send(
        self, device: Device, commands: list[dict[str, Any]], reason: TuyaError
    ) -> None:
        self._fall_back(device, reason, lambda cloud: cloud.send(device.id, commands))

    def _cloud_refresh(self, device: Device, reason: TuyaError) -> None:
        fresh = self._fall_back(device, reason, lambda cloud: cloud.status(device.id))
        if fresh is None:
            raise CloudError(f"the cloud no longer lists {device.name}")
        device._merge_cloud(fresh)

    def _fall_back(self, device: Device, reason: TuyaError, call: Callable[..., Any]) -> Any:
        """Do through the cloud what the LAN could not; `reason` is raised if that is not on."""
        if not self.cloud_fallback:
            raise reason
        _LOGGER.info("%s: %s; using the cloud", device.name, reason)
        try:
            return self._ask_cloud(call)
        except NotLoggedIn:
            if self.logged_in:  # the login has gone stale, which is the news
                raise
            raise reason from None

    def _ask_cloud(self, call: Callable[[cloud_api.Cloud], Any]) -> Any:
        """Run a cloud call, reading the saved login again if it has gone stale.

        Refresh tokens are single-use: when another process sharing this home
        directory has renewed the login, this one's copy stops working.
        """
        try:
            return call(self.cloud)
        except NotLoggedIn:
            with self._lock:
                self._cloud = None
            return call(self.cloud)

    # -- storage ----------------------------------------------------------

    def _known(self) -> list[Device]:
        """The saved devices, read on first use; empty if nothing usable is saved."""
        with self._lock:
            if self._devices is None:
                saved = self._read("devices.json")
                addresses = {
                    dev_id: LanAddress(**address)
                    for dev_id, address in saved.get("lan", {}).items()
                }
                self._home_ids = saved.get("homes", [])
                self._devices = [
                    Device(self, record, addresses.get(record["id"]))
                    for record in saved.get("devices", [])
                ]
            return self._devices

    def _fetch(self, accept_empty: bool = False) -> list[Device]:
        """Replace the device list with the cloud's, keeping what only the saved one has.

        That is the LAN addresses, and descriptions the cloud failed to give this time.
        """
        with self._lock:
            saved = {device.id: device for device in self._known()}
            records = self._ask_cloud(lambda cloud: cloud.devices())
            if saved and not records and not accept_empty:
                # More likely a fault on the cloud's side than every device gone.
                kept = f"kept the {len(saved)} saved ones"
                raise CloudError(f"the Tuya cloud listed no devices; {kept}")
            devices = []
            for record in records:
                old = saved.get(record["id"])
                if old is not None:
                    _keep_description(record, old.record)
                devices.append(Device(self, record, old.address if old else None))
            if saved:
                _log_changes(saved, devices)
            self._devices = devices
            self._home_ids = self._ask_cloud(lambda cloud: cloud.home_ids())
            return self._devices

    def _homes(self) -> list[str]:
        with self._lock:
            self._known()
            if not self._home_ids:
                self._home_ids = self._ask_cloud(lambda cloud: cloud.home_ids())
                self._save()
            return self._home_ids

    def _save(self) -> None:
        with self._lock:
            devices = self._devices or []
            self._write(
                "devices.json",
                {
                    "devices": [d.record for d in devices],
                    "lan": {d.id: vars(d.address) for d in devices if d.address},
                    "homes": self._home_ids,
                },
            )

    def _read(self, name: str) -> dict[str, Any]:
        try:
            return json.loads((self.home / name).read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _write(self, name: str, data: dict[str, Any]) -> None:
        """Write atomically and privately: these files hold tokens and local keys.

        Without taking the lock: renewed tokens are saved from inside a cloud request,
        which another thread holding the lock may be waiting for.
        """
        self.home.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = self.home / f".{name}.{os.getpid()}.{threading.get_ident()}.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        with open(os.open(temporary, flags, 0o600), "w") as file:
            json.dump(data, file, indent=1)
        temporary.replace(self.home / name)


def _keep_description(record: Record, saved: Record) -> None:
    """Take from the saved record what the cloud did not describe this time."""
    for key in ("function", "status_range", "local_strategy"):
        if saved.get(key) and (record.get("incomplete") or not record.get(key)):
            record[key] = saved[key]


def _log_changes(saved: dict[str, Device], devices: list[Device]) -> None:
    """Say which devices a refresh added or dropped, and which have a new local key."""
    listed = {device.id for device in devices}
    for change, names in (
        ("New devices", [d.name for d in devices if d.id not in saved]),
        ("Devices no longer listed", [d.name for d in saved.values() if d.id not in listed]),
        (
            "New local keys",
            [d.name for d in devices if d.id in saved and d.local_key != saved[d.id].local_key],
        ),
    ):
        if names:
            _LOGGER.info("%s: %s", change, ", ".join(names))
