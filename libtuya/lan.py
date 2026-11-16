"""LAN transport: find devices on the local network and talk to them.

TinyTuya does the protocol work. This module adds what a caller needs around
it: discovery keyed by device id, exceptions instead of error dictionaries,
and one lock per TCP connection (TinyTuya is not thread-safe, and a gateway's
sub-devices all share the gateway's connection).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

import tinytuya
from tinytuya import scanner

from .errors import LanError

# At DEBUG TinyTuya logs local keys and uses a fixed IV for protocol 3.5, so it
# must not inherit a root logger set to DEBUG.
logging.getLogger("tinytuya").setLevel(logging.INFO)

VERSIONS = ("3.1", "3.2", "3.3", "3.4", "3.5")
# Versions to try when only the IP is known, most common first.
PROBE_VERSIONS = ("3.3", "3.4", "3.5", "3.1")
# TinyTuya error codes that mean "nothing answered at this address".
UNREACHABLE = {"901", "905"}
HEARTBEAT_INTERVAL = 10.0
# While watching, how often to ask for the full status in case a push was missed.
FULL_STATUS_INTERVAL = 30.0
# Protocol 3.2 devices are asked for datapoints by id, a few per request
# (requests are limited to 255 bytes), always including dp 1.
DPS_PER_REQUEST = 10


@dataclass(frozen=True)
class LanAddress:
    ip: str
    version: str
    port: int = 6668

    def __str__(self) -> str:
        port = "" if self.port == 6668 else f":{self.port}"
        return f"{self.ip}{port} (protocol {self.version})"


def discover(keys: Mapping[str, str], timeout: float = 8.0) -> dict[str, LanAddress]:
    """Listen for device broadcasts and return the addresses of the wanted ids.

    `keys` maps device id to local key (empty if unknown). Returns as soon as
    every wanted device has been heard, which never happens if one of them is
    switched off, battery powered, on another subnet or a gateway's
    sub-device; then it returns after `timeout` seconds.
    """
    if not keys:
        return {}
    try:
        found = scanner.devices(
            verbose=False,
            poll=False,
            byID=True,
            scantime=timeout,
            wantids=list(keys),
            # Given explicitly so the scanner does not read devices.json from the cwd.
            tuyadevices=[{"id": dev_id, "key": key} for dev_id, key in keys.items()],
        )
    except OSError as err:  # port in use, no network
        raise LanError(f"LAN discovery failed: {err}") from err
    return {
        dev_id: LanAddress(info["ip"], str(info["version"]))
        for dev_id, info in found.items()
        if dev_id in keys and info.get("ip") and info.get("version")
    }


def _error(result: Mapping[str, Any]) -> LanError:
    code = str(result["Err"])
    message = f"{result.get('Error')} (TinyTuya error {code})"
    if code == "914":
        message += "; if the device was re-paired its key has changed, refresh the device list"
    return LanError(message, code)


class Connection:
    """A TinyTuya session with one device, or with a sub-device via its gateway."""

    def __init__(
        self,
        dev_id: str,
        local_key: str,
        address: LanAddress | None,
        dp_ids: Iterable[int] = (),
        *,
        cid: str | None = None,
        parent: Connection | None = None,
        persist: bool = False,
        timeout: float = 5.0,
    ) -> None:
        self._dp_ids = [str(dp_id) for dp_id in dp_ids]
        self._parent = parent
        self._cid = cid
        self._by_id = False
        if parent is not None:
            if parent._by_id:
                # TinyTuya would probe every datapoint range from the constructor.
                raise LanError("sub-devices of a protocol 3.2 gateway are not supported on the LAN")
            self._lock = parent._lock
            with self._lock:  # registers itself on the gateway's TinyTuya object
                self._device = tinytuya.Device(dev_id, cid=cid, parent=parent._device)
            return
        if address is None:
            raise LanError(f"no LAN address known for {dev_id}")
        self._lock = threading.Lock()
        self._by_id = address.version == "3.2"
        self._device = tinytuya.Device(
            dev_id,
            address.ip,
            local_key,
            # 3.2 is 3.3 on the wire; given directly it makes TinyTuya probe the
            # device from the constructor, so it is selected below instead.
            version=3.3 if self._by_id else float(address.version),
            port=address.port,
            persist=persist,
            connection_timeout=timeout,
            connection_retry_limit=1,
            connection_retry_delay=0,
        )
        # TinyTuya can decide from an error reply that a device must be asked
        # for datapoints by id, and from then on "asks" with a command that
        # some devices take as a write of nulls. Only do that for 3.2 devices.
        self._device.disabledetect = True
        if self._by_id:
            self._device.set_dpsUsed({"1": None})
            self._device.set_version(3.2)

    @property
    def _socket_owner(self) -> Any:
        """The TinyTuya object that owns the socket: the gateway's for a sub-device."""
        return (self._parent or self)._device

    def _call(
        self, function: Callable[..., Any], *args: Any, write: bool = False
    ) -> dict[str, Any]:
        """Run a TinyTuya call and return the datapoints it reported, if any."""
        owner = self._socket_owner
        with self._lock:
            # A write returns on the device's acknowledgement and is sent once:
            # by default TinyTuya waits for a status report that some devices
            # never send, and re-sends the command when no reply arrives.
            owner.set_retry(not write)
            owner.set_sendRetryLimit(0 if write else None)
            try:
                result = function(*args)
                rejected = write and owner.cmd_retcode
            finally:
                owner.set_retry(True)
                owner.set_sendRetryLimit(None)
        if result and "Err" in result:
            raise _error(result)
        if rejected:
            raise LanError(f"the device refused the command (code {rejected})")
        result = result or {}
        # A gateway's connection also carries its sub-devices' reports.
        if (result.get("cid") or (result.get("data") or {}).get("cid")) != self._cid:
            return {}
        return dict(result.get("dps") or {})

    def status(self) -> dict[str, Any]:
        """Query the device's datapoints, keyed by dp id as a string."""
        if self._parent is not None or not self._by_id:
            return self._call(self._device.status)
        dps: dict[str, Any] = {}
        wanted = [dp_id for dp_id in self._dp_ids if dp_id != "1"]
        for start in range(0, len(wanted) or 1, DPS_PER_REQUEST):
            chunk = ["1", *wanted[start : start + DPS_PER_REQUEST]]
            self._device.set_dpsUsed(dict.fromkeys(chunk))
            dps |= self._call(self._device.status)
        return dps

    def set(self, dps: Mapping[str, Any]) -> dict[str, Any]:
        """Write datapoints; returns what the device reported by the time it acknowledged."""
        return self._call(self._device.set_multiple_values, dict(dps), write=True)

    def updates(self) -> Iterator[tuple[dict[str, Any], bool]]:
        """Yield datapoints as they come in, forever, with whether the device pushed them.

        Needs `persist=True`. Starts with the full status (not a push) and
        asks for it again now and then, so a push lost to a dropped connection
        is made up for.
        """
        last_heartbeat = last_status = 0.0
        payload_errors = 0
        while True:
            now = time.monotonic()
            if now - last_status >= FULL_STATUS_INTERVAL:
                yield self.status(), False
                last_heartbeat = last_status = time.monotonic()
                continue
            if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                self._call(self._device.heartbeat)
                last_heartbeat = now
            try:
                dps = self._call(self._device.receive)
                payload_errors = 0
            except LanError as err:
                # Protocol 3.4 devices answer an idle read with a payload error,
                # and so does a connection that has just dropped. Let either
                # pass a few times, without spinning on a broken one.
                payload_errors += 1
                if err.code != "904" or payload_errors > 3:
                    raise
                continue
            if dps:
                yield dps, True

    def close(self) -> None:
        with self._lock:
            self._device.close()
            if self._parent is not None:
                self._parent._device.close()


def probe_version(
    dev_id: str, local_key: str, ip: str, version: str | None = None, timeout: float = 5.0
) -> LanAddress:
    """Confirm a device answers at `ip`, finding its protocol version if not given.

    Each version is tried once: repeated failed 3.4/3.5 handshakes can make a
    device refuse connections until it is power-cycled.
    """
    if version is not None and version not in VERSIONS:
        raise ValueError(f"protocol version must be one of {', '.join(VERSIONS)}")
    last: LanError | None = None
    for candidate in (version,) if version else PROBE_VERSIONS:
        connection = Connection(dev_id, local_key, LanAddress(ip, candidate), timeout=timeout)
        try:
            connection.status()
        except LanError as err:
            last = err
            if err.code in UNREACHABLE:
                break
        else:
            return LanAddress(ip, candidate)
        finally:
            connection.close()
    raise LanError(f"{dev_id} did not answer at {ip}: {last}")
