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

# Versions to try when only the IP is known, most common first.
PROBE_VERSIONS = ("3.3", "3.4", "3.5", "3.1")
# TinyTuya error codes that mean "nothing answered at this address".
UNREACHABLE = {"901", "905"}
HEARTBEAT_INTERVAL = 10.0


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

    `keys` maps device id to local key (needed to read some broadcasts).
    Returns as soon as every wanted device has been heard, else after
    `timeout`. Devices on another subnet or VLAN, battery devices and
    sub-devices of a gateway do not show up.
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
        timeout: float = 3.0,
    ) -> None:
        self._dp_ids = {str(dp_id): None for dp_id in dp_ids}
        self._parent = parent
        if parent is not None:
            self._lock = parent._lock
            self._device = tinytuya.Device(dev_id, cid=cid, parent=parent._device)
            return
        if address is None:
            raise LanError(f"no LAN address known for {dev_id}")
        self._lock = threading.Lock()
        # Protocol 3.2 probes the device from the constructor unless the
        # datapoints to request are already set, so it is applied afterwards.
        version = float(address.version)
        self._device = tinytuya.Device(
            dev_id,
            address.ip,
            local_key,
            version=3.3 if version == 3.2 else version,
            port=address.port,
            persist=persist,
            connection_timeout=timeout,
            connection_retry_limit=1,
            connection_retry_delay=0,
        )
        if version == 3.2:
            self._device.set_dpsUsed(dict(self._dp_ids))
            self._device.set_version(3.2)

    def _call(
        self, function: Callable[..., Any], *args: Any, await_report: bool = True
    ) -> dict[str, Any]:
        """Run a TinyTuya call and return the datapoints it reported, if any."""
        # The socket, and with it this setting, belongs to the gateway for a sub-device.
        owner = (self._parent or self)._device
        with self._lock:
            owner.set_retry(await_report)
            try:
                result = function(*args)
            finally:
                owner.set_retry(True)
        if not result:
            return {}
        if "Err" in result:
            raise LanError(f"{result.get('Error')} (TinyTuya error {result['Err']})", result["Err"])
        return dict(result.get("dps") or {})

    def status(self) -> dict[str, Any]:
        """Query the device's datapoints, keyed by dp id as a string."""
        dps = self._call(self._device.status)
        if (
            self._device.dev_type == "device22"
            and self._dp_ids.keys() - self._device.dps_to_request
        ):
            # Such devices only report the datapoints they are asked for, and
            # TinyTuya asks for dp 1 alone once it has detected one.
            self._device.set_dpsUsed(dict(self._dp_ids))
            dps = self._call(self._device.status)
        return dps

    def set(self, dps: Mapping[str, Any]) -> dict[str, Any]:
        """Write datapoints and return once the device has acknowledged them.

        The status report a device usually sends next is not awaited: a device
        that sends none (some do not when nothing changed) would stall the call
        for the whole timeout. Returns what was reported by then, if anything.
        """
        return self._call(self._device.set_multiple_values, dict(dps), await_report=False)

    def updates(self) -> Iterator[dict[str, Any]]:
        """Yield datapoint changes as the device reports them, forever.

        Needs `persist=True`. Starts with the full status.
        """
        yield self.status()
        last_heartbeat = time.monotonic()
        payload_errors = 0
        while True:
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
                dps = {}
            if dps:
                yield dps
            if time.monotonic() - last_heartbeat >= HEARTBEAT_INTERVAL:
                self._call(self._device.heartbeat)
                last_heartbeat = time.monotonic()

    def close(self) -> None:
        with self._lock:
            self._device.close()
            if self._parent is not None:
                self._parent._device.close()


def probe_version(dev_id: str, local_key: str, ip: str) -> LanAddress:
    """Find the protocol version of a device whose IP was given by hand.

    Each version is tried once: repeated failed 3.4/3.5 handshakes can make a
    device refuse connections until it is power-cycled.
    """
    last: LanError | None = None
    for version in PROBE_VERSIONS:
        connection = Connection(dev_id, local_key, LanAddress(ip, version))
        try:
            connection.status()
        except LanError as err:
            last = err
            if err.code in UNREACHABLE:
                break
        else:
            return LanAddress(ip, version)
        finally:
            connection.close()
    raise LanError(f"{dev_id} did not answer at {ip}: {last}")
