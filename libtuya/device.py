"""A Tuya device: status and control, over the LAN first and the cloud second."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from functools import cached_property
from typing import TYPE_CHECKING, Any

from .cloud import Record, load_device
from .dpmap import DpMap
from .entities import Entity, apply_quirks, build_entities
from .errors import LanError, TuyaError, Unmapped
from .lan import UNREACHABLE, Connection, LanAddress

if TYPE_CHECKING:
    from .client import Tuya

# Where turn_on()/turn_off() look for the thing to switch, in order.
_POWER_PLATFORMS = ("light", "switch", "fan", "climate", "humidifier", "siren", "valve")


class Device:
    """One device of the account.

    `info` is the device as tuya-device-sharing-sdk models it. `status` holds
    its state by DP code, in the cloud's terms, and is what entities read.
    `refresh()` updates it and `send()` changes the device; both use the LAN
    when the device is reachable there and fall back to the cloud otherwise.
    `transport` says which one served the last call.
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
    def status(self) -> dict[str, Any]:
        return self.info.status

    def __repr__(self) -> str:
        return f"<Device {self.name!r} {self.category} {self.id}>"

    # -- entities ---------------------------------------------------------

    @cached_property
    def entities(self) -> list[Entity]:
        return build_entities(self)

    def entity(self, ref: str) -> Entity:
        """Find an entity by id (``light.switch_led``), key, platform or name."""
        ref_lower = ref.lower()
        for matches in (
            lambda e: e.id == ref,
            lambda e: e.key == ref,
            lambda e: e.platform == ref,
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
        """The entity that turns the device on and off."""
        candidates = [
            entity
            for platform in _POWER_PLATFORMS
            for entity in self.entities
            if entity.platform == platform
            and "switch" in entity.wrappers
            and "entity_category" not in entity.description
        ]
        main = [entity for entity in candidates if entity.name is None]
        if main:
            return main[0]
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
        self.refresh()
        self.power.set(switch=not self.power.value)

    # -- transport --------------------------------------------------------

    def refresh(self) -> dict[str, Any]:
        """Read the device's current status."""
        try:
            dps = self._over_lan(lambda connection: connection.status())
        except LanError as err:
            self._client.cloud_refresh(self, reason=err)
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
            reported = self._over_lan(lambda connection: connection.set(dps))
        except (LanError, Unmapped) as err:
            self._client.cloud_send(self, commands, reason=err)
            self.status.update({command["code"]: command["value"] for command in commands})
            self.transport = "cloud"
        else:
            # Not every device echoes what it applied, so assume the write
            # took effect and let anything it did report win.
            self.status.update(self.dp_map.decode({**dps, **reported}))
            self.transport = "lan"

    def set(self, values: dict[str, Any] | None = None, /, **codes: Any) -> None:
        """Set raw DP codes, e.g. ``device.set(switch_1=True, countdown_1=60)``.

        Values are the cloud's unscaled ones; use entities for friendly units.
        """
        self.send(
            [{"code": code, "value": value} for code, value in {**(values or {}), **codes}.items()]
        )

    def watch(self) -> Iterator[dict[str, Any]]:
        """Yield status changes pushed by the device over the LAN, forever.

        Holds a connection open, which most devices allow only one of.
        """
        self._require_map()
        connection = self._connect(persist=True)
        try:
            for dps in connection.updates():
                changed = self.dp_map.decode(dps)
                self.status.update(changed)
                for entity in self.entities:
                    entity.pushed(list(changed), time.monotonic_ns())
                if changed:
                    yield changed
        finally:
            connection.close()

    def _require_map(self) -> None:
        if not self.dp_map:
            raise LanError(f"the cloud gave no datapoint map for {self.name}")

    def _connect(self, persist: bool = False) -> Connection:
        """A new connection to this device, through its gateway if it is a sub-device."""
        dp_ids = self.dp_map.dp_ids
        gateway = self._client.gateway_of(self)
        if gateway is None:
            return Connection(self.id, self.info.local_key, self.address, dp_ids, persist=persist)
        parent = gateway._connect(persist=True) if persist else gateway._lan_connection()
        cid = getattr(self.info, "node_id", None) or self.info.uuid
        return Connection(self.id, "", None, dp_ids, cid=cid, parent=parent)

    def _lan_connection(self) -> Connection:
        if self.address is None:  # a sub-device, which follows its gateway, or unreachable
            return self._connect()
        with self._connection_lock:
            if self._connection is None:
                self._connection = self._connect()
            return self._connection

    def _over_lan(self, call: Callable[[Connection], dict[str, Any]]) -> dict[str, Any]:
        self._require_map()
        try:
            result = call(self._lan_connection())
        except LanError as err:
            # The device may have a new IP address: look for it once.
            if err.code not in UNREACHABLE or not self._may_relocate:
                raise
            self._may_relocate = False
            if not self._client.relocate(self):
                raise
            result = call(self._lan_connection())
        self._may_relocate = True
        return result

    def moved(self, address: LanAddress | None) -> None:
        """Record a new LAN address."""
        self.address = address
        self._connection = None
