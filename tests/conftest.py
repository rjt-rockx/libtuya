"""Shared test helpers.

Devices come from Home Assistant's fixture corpus (real device dumps, vendored
under third_party/), served by a fake LAN device that the real TinyTuya client
talks to.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from fake_device import FakeTuyaDevice

from libtuya import Tuya
from libtuya import client as client_module
from libtuya.device import Device
from libtuya.lan import LanAddress

FIXTURES = (
    Path(__file__).parent.parent / "third_party/home-assistant-core/tests/components/tuya/fixtures"
)


def local_key(name: str) -> str:
    """Every device has its own 16-character key, as real ones do."""
    return hashlib.md5(name.encode()).hexdigest()[:16]


def fixture_names() -> list[str]:
    return sorted(path.stem for path in FIXTURES.glob("*.json"))


def record(name: str, **overrides: Any) -> dict[str, Any]:
    """Turn a Home Assistant device dump into a record as libtuya caches them."""
    dump = json.loads((FIXTURES / f"{name}.json").read_text())

    def describe(code: str, item: dict[str, Any]) -> dict[str, Any]:
        values = item["value"]
        return {
            "code": code,
            "type": item["type"],
            "values": values if isinstance(values, str) else json.dumps(values),
            "report_type": item.get("report_type"),
        }

    function = {code: describe(code, item) for code, item in dump["function"].items()}
    status_range = {code: describe(code, item) for code, item in dump["status_range"].items()}
    json_codes = {
        code
        for spec in (function, status_range)
        for code, item in spec.items()
        if item["type"] == "Json"
    }
    status = {}
    for code, value in dump["status"].items():
        if value == "**REDACTED**":
            value = ""
        elif code in json_codes and not isinstance(value, str):
            value = json.dumps(value)  # the cloud delivers Json datapoints as text
        status[code] = value
    return {
        "id": name,
        "name": dump["name"],
        "category": dump["category"],
        "product_id": dump["product_id"],
        "product_name": dump["product_name"],
        "online": dump["online"],
        "sub": bool(dump.get("sub")),
        "uuid": name,
        "local_key": local_key(name),
        "function": function,
        "status_range": status_range,
        "status": status,
        "local_strategy": dump.get("local_strategy") or {},
    } | overrides


@pytest.fixture(autouse=True)
def no_real_discovery(monkeypatch) -> None:
    """Tests never listen on the real network; by default nothing is found."""
    monkeypatch.setattr(client_module, "discover", lambda keys, timeout=0: {})


@pytest.fixture
def tuya(tmp_path: Path) -> Tuya:
    """A client with an empty home directory and no login."""
    return Tuya(tmp_path)


@pytest.fixture
def make_device(tuya: Tuya):
    def make(name: str, address: LanAddress | None = None, **overrides: Any) -> Device:
        device = Device(tuya, record(name, **overrides), address)
        tuya._devices = [*(tuya._devices or []), device]
        return device

    return make


def fake(name: str, version: str = "3.4", dps: dict[str, Any] | None = None, **kwargs: Any):
    """A fake LAN device standing in for the fixture device `name`."""
    return FakeTuyaDevice(name, local_key(name), version, dps, **kwargs)
