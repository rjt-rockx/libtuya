"""A Tuya device: status and control, over the LAN first and the cloud second."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import cached_property
from typing import TYPE_CHECKING, Any, overload

from .cloud import Record, load_device
from .dpmap import DpMap
from .entities import Entity, apply_quirks, build_entities
from .errors import LanError, TuyaError, Unmapped
from .lan import Connection, LanAddress

if TYPE_CHECKING:
    from .client import Tuya

# Where turn_on()/turn_off() look for the thing to switch, in order.
_POWER_PLATFORMS = ("light", "switch", "fan", "climate", "humidifier", "siren", "valve")
# TinyTuya errors after which a write may or may not have reached the device.
_UNCONFIRMED = {"902", "904"}


class Device:
    """One device of the account.

    `info` is the device as tuya-device-sharing-sdk models it. `status` holds
    its state by DP code, in the cloud's terms, and is what entities read;
    until the first `refresh()` it is what the cloud knew when the device list
    was fetched. `refresh()` updates it and `send()` changes the device; both
    use the LAN when the device is reachable there and fall back to the cloud
    otherwise. `transport` says which one served the last call.

    A write is confirmed by the device's acknowledgement only: `status` then
    shows what was sent, and `refresh()` shows what the device made of it.
    """

    def __init__(self, client: Tuya, record: Record, address: LanAddress | None = None) -> None:
        self._client = client
        self.record = record  # as the cloud sent it; this is what gets cached
        self.info = load_device(record)  # the SDK object the device logic works on
        apply_quirks(self.info)
        self.address = address
        self.dp_map = DpMap(self.info.local_strategy)
        self.transport: str | None = None
        self._connection: Connection | None = None
        self._connection_lock = threading.Lock()
        self._holders = 0  # `connected()` blocks open, nested or in other threads
        self._may_relocate = True

    @property
    def id(self) -> str:
        return self.info.id

    @property
    def name(self) -> str:
        return self.info.name

    @property
    def category(self) -> str:
        return self.info.category

    @property
    def product_name(self) -> str:
        return getattr(self.info, "product_name", None) or ""

    @property
    def local_key(self) -> str:
        """Key for LAN traffic; empty for devices the cloud gives none for, such as some hubs."""
        return getattr(self.info, "local_key", None) or ""

    @property
    def online(self) -> bool:
        """Whether the cloud last reported the device as connected to it."""
        return bool(getattr(self.info, "online", True))

    @property
    def status(self) -> dict[str, Any]:
        return self.info.status

    def __repr__(self) -> str:
        return f"<Device {self.name!r} {self.category} {self.id}>"

    # -- entities ---------------------------------------------------------

    @cached_property
    def entities(self) -> list[Entity]:
        return build_entities(self)

    @overload
    def entity(self, ref: str) -> Entity: ...
    @overload
    def entity[E: Entity](self, ref: str, kind: type[E]) -> E: ...
    def entity(self, ref: str, kind: type[Entity] = Entity) -> Entity:
        """Find an entity by id (``light.switch_led``), key, platform or name.

        With `kind` (``device.entity("light", Light)``) it must be of that
        class, which also tells a type checker what comes back.
        """
        found = self._find_entity(ref)
        if not isinstance(found, kind):
            raise TuyaError(
                f"{found.id} of {self.name} is a {type(found).__name__}, not a {kind.__name__}"
            )
        return found

    def _find_entity(self, ref: str) -> Entity:
        ref_lower = ref.lower()
        for matches in (
            lambda e: e.id == ref,
            lambda e: ref in (e.key, e.platform),
            lambda e: (e.name or "").lower() == ref_lower,
        ):
            found = [entity for entity in self.entities if matches(entity)]
            if len(found) == 1:
                return found[0]
            if found:
                raise TuyaError(
                    f"{ref!r} matches several entities: {', '.join(e.id for e in found)}"
                )
        raise TuyaError(
            f"{self.name} has no entity {ref!r}; it has {', '.join(e.id for e in self.entities)}"
        )

    @property
    def power(self) -> Entity:
        """The entity that turns the device on and off.

        Raises TuyaError if there is none, or no obvious one (a fan with a
        light, a multi-gang switch); pick one with `entity()` then.
        """
        candidates = [
            entity
            for platform in _POWER_PLATFORMS
            for entity in self.entities
            if entity.platform == platform
            and entity.on_off
            and "entity_category" not in entity.description
        ]
        # The entity that carries the device's own name is the device, if there is just one.
        candidates = [entity for entity in candidates if entity.name is None] or candidates
        if len(candidates) == 1:
            return candidates[0]
        if candidates:
            raise TuyaError(
                f"{self.name} has several switches, pick one: {', '.join(e.id for e in candidates)}"
            )
        raise TuyaError(f"{self.name} has nothing to switch on or off")

    def turn_on(self) -> None:
        self.power.turn_on()

    def turn_off(self) -> None:
        self.power.turn_off()

    def toggle(self) -> None:
        power = self.power
        with self.connected():
            self.refresh()
            power.turn_off() if power.value else power.turn_on()

    # -- transport --------------------------------------------------------

    def refresh(self) -> dict[str, Any]:
        """Read the device's current status."""
        try:
            dps = self._over_lan(lambda connection: connection.status())
            if not dps:
                raise LanError(f"{self.name} answered without any status")
        except LanError as err:
            self._client._cloud_refresh(self, reason=err)
            self.transport = "cloud"
        else:
            self.status.update(self.dp_map.decode(dps))
            self.transport = "lan"
        return self.status

    def send(self, commands: list[dict[str, Any]]) -> None:
        """Send commands, each ``{"code": ..., "value": ...}`` in cloud terms."""
        if not commands:
            return
        try:
            dps = self.dp_map.encode(commands)
            reported = self._over_lan(lambda connection: connection.set(dps), write=True)
        except (LanError, Unmapped) as err:
            if isinstance(err, LanError) and err.code in _UNCONFIRMED:
                # Sending it again through the cloud could run it twice, which
                # matters for one-shot commands such as "feed now".
                raise LanError(
                    f"{self.name} did not acknowledge the command; it may or may not have "
                    f"been carried out ({err})",
                    err.code,
                ) from err
            self._client._cloud_send(self, commands, reason=err)
            self.status.update({command["code"]: command["value"] for command in commands})
            self.transport = "cloud"
        else:
            self.status.update(self.dp_map.decode({**dps, **reported}))
            self.transport = "lan"

    def set_raw(self, values: dict[str, Any] | None = None, /, **codes: Any) -> None:
        """Write DP codes directly, e.g. ``device.set_raw(switch_1=True, countdown_1=60)``.

        Values are the cloud's own, unscaled and unchecked; entities take
        friendly units and validate.
        """
        self.send(
            [{"code": code, "value": value} for code, value in {**(values or {}), **codes}.items()]
        )

    @contextmanager
    def connected(self) -> Iterator[None]:
        """Keep one LAN connection open for several calls in a row.

        Without it every call connects anew, which is gentle on a device's
        single connection slot but, done in quick succession, has been reported
        to make some devices stop answering. For a sub-device it is its
        gateway's connection that is held, shared with the gateway's other
        sub-devices: most gateways accept only one.
        """
        gateway = self._client.gateway_of(self)
        if gateway is not None:
            with gateway.connected():
                yield
            return
        with self._connection_lock:
            self._holders += 1
            if self._holders == 1:  # an outer block's connection is shared, not replaced
                address = self.address
                opened = self._try_connect(persist=True)
                self._keep(opened, address)
                if opened is not None and opened is not self._connection:
                    opened.close()  # built for an address the device has left
        try:
            yield
        finally:
            with self._connection_lock:
                self._holders -= 1
                held = self._connection if not self._holders else None
                if not self._holders:
                    self._connection = None
            if held is not None:
                held.close()

    def watch(self) -> Iterator[dict[str, Any]]:
        """Yield the device's status over the LAN, then each change, forever.

        The first item is the full current status by DP code; after that only
        what changed, as the device pushes it (the status is also re-read every
        30 seconds, and differences found then are yielded too). Holds a
        connection open, which most devices allow only one of. Raises LanError
        when the connection is lost; start again to resume.
        """
        self._require_map()
        connection = self._connect(persist=True)
        first = True
        try:
            for dps, pushed in connection.updates():
                decoded = self.dp_map.decode(dps)
                if pushed or first:
                    changed = decoded
                else:  # a status this side asked for
                    changed = {c: v for c, v in decoded.items() if self.status.get(c) != v}
                first = False
                self.status.update(decoded)
                if pushed:  # as opposed to a status this side asked for
                    now = time.monotonic_ns()
                    for entity in self.entities:
                        entity._note_push(dict.fromkeys(changed, now))
                if changed:
                    yield changed
        finally:
            connection.close()

    def stream_url(self, kind: str = "rtsp") -> str:
        """A short-lived URL for a camera's live stream, from the cloud.

        `kind` is rtsp, hls, flv or rtmp.
        """
        return self._client._ask_cloud(lambda cloud: cloud.stream_url(self.id, kind))

    def _require_map(self) -> None:
        if not self.dp_map:
            raise LanError(f"the cloud gave no datapoint map for {self.name}")

    def _connect(self, persist: bool = False, key: str = "") -> Connection:
        """A new connection to this device, through its gateway if it is a sub-device.

        `key` stands in for a gateway that has no key of its own.
        """
        dp_ids = self.dp_map.dp_ids
        gateway = self._client.gateway_of(self)
        if gateway is None:
            if not (self.local_key or key):
                raise LanError(f"the cloud gave no local key for {self.name}")
            return Connection(
                self.id,
                self.local_key or key,
                self.address,
                dp_ids,
                persist=persist,
                timeout=self._client.timeout,
            )
        parent = (
            gateway._connect(persist=True, key=self.local_key)
            if persist
            else gateway._lan_connection(key=self.local_key)
        )
        cid = getattr(self.info, "node_id", None) or getattr(self.info, "uuid", None)
        return Connection(self.id, "", None, dp_ids, cid=cid, parent=parent)

    def _try_connect(self, persist: bool) -> Connection | None:
        try:
            return self._connect(persist)
        except LanError:
            return None

    def _lan_connection(self, key: str = "") -> Connection:
        with self._connection_lock:
            if self._connection is not None:
                return self._connection
            # A sub-device (no address of its own) is cheap to set up each
            # time, and that way follows its gateway to a new address.
            address = self.address
            connection = self._connect(key=key)
            if address is not None:
                self._keep(connection, address)
            return connection

    def _keep(self, connection: Connection | None, address: LanAddress | None) -> None:
        """Hold a connection built for `address`, unless the device moved meanwhile.

        A move does not take the connection lock (see `_drop_connection`), so it
        can happen while a connection is being built for the old address.
        """
        if connection is not None and self.address == address:
            self._connection = connection

    def _over_lan(
        self, call: Callable[[Connection], dict[str, Any]], write: bool = False
    ) -> dict[str, Any]:
        self._require_map()
        try:
            result = call(self._lan_connection())
        except LanError as err:
            # Whatever went wrong on the connection, the device may simply have
            # a new IP address (and another device its old one): look once.
            # Not after a write that may have arrived: it would run twice.
            if err.code is None or not self._may_relocate:
                raise
            if write and err.code in _UNCONFIRMED:
                raise
            self._may_relocate = False
            if not self._client._relocate(self):
                raise
            # A connection still held here (a sub-device's, through its gateway) leads
            # to the old address.
            self._drop_connection()
            result = call(self._lan_connection())
        self._may_relocate = True
        return result

    def _moved(self, address: LanAddress | None) -> None:
        """Record a new LAN address."""
        self.address = address
        self._drop_connection()

    def _drop_connection(self) -> None:
        # Not under the connection lock: the client calls this holding its own lock,
        # and a device call holds the connection lock while it waits for the client's.
        stale, self._connection = self._connection, None
        if stale is not None:
            stale.close()

    def _merge_cloud(self, current: dict[str, Any]) -> None:
        """Take over `online` and `status` as the cloud just reported them."""
        fresh = load_device({**self.record, **current})
        apply_quirks(fresh)  # quirks correct some status values too
        self.info.online = fresh.online
        self.status.update(fresh.status)

    def _apply_report(self, items: Any) -> dict[str, Any]:
        """Apply a status report pushed through the cloud; returns what changed, by DP code."""
        changed: dict[str, Any] = {}
        timestamps: dict[str, int] = {}
        for item in items:
            if "value" not in item:
                continue
            if "dpId" in item:  # by datapoint id, raw, as on the LAN
                decoded = self.dp_map.decode({item["dpId"]: item["value"]})
            elif "code" in item:
                decoded = {item["code"]: item["value"]}
            else:
                continue
            changed |= decoded
            # The cloud stamps each report; the same report can arrive twice.
            timestamps |= dict.fromkeys(decoded, item.get("t") or time.monotonic_ns())
        self.status.update(changed)
        for entity in self.entities:
            entity._note_push(timestamps)
        return changed
