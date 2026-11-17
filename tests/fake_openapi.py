"""A stand-in for Tuya's OpenAPI at the HTTP level, with canned replies for a bulb and a plug.

It replaces `requests` inside TinyTuya's Cloud module, so TinyTuya's real signing, token
handling and error dictionaries run on top of it, as in TinyTuya's own tests.

Where the canned data comes from:

- The bulb's specification rows, dp ids and status are those of Home Assistant's fixture
  dj_k3okx0w3bsgmindp (a real dump), and it has that fixture's name as its id, so that
  `conftest.fake` can stand in for it on the LAN. Its thing model follows a real reply
  for another bulb of the same layout.
- The plug is TinyTuya's published example mapping (WP1 socket); its countdown is in
  `functions` only, as the order of that mapping shows. Its thing model is inferred.
- Envelopes, ids, keys and times are made up.
"""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlsplit

import requests
from conftest import local_key

TOKEN = {"success": True, "t": 1700000000000, "result": {"access_token": "T1", "expire_time": 7200}}


class FakeTuyaCloud:
    """Answers each request from `routes`: {"GET /path": reply or list of replies}.

    A list is consumed one reply per request, its last entry then repeating. Bytes are
    sent as they are (a gateway's error page); an exception is raised (no network).
    Requests are recorded in `calls` as (method, path, parsed body).
    """

    Request = requests.Request  # TinyTuya builds query strings with it

    def __init__(self, routes: dict[str, Any]) -> None:
        self.routes = {"GET /v1.0/token": TOKEN} | routes
        self.calls: list[tuple[str, str, Any]] = []

    def install(self, monkeypatch) -> FakeTuyaCloud:
        monkeypatch.setattr(sys.modules["tinytuya.Cloud"], "requests", self)
        return self

    def get(self, url: str, headers: dict[str, str]) -> Any:
        return self.request("GET", url, headers=headers)

    def request(self, method: str, url: str, headers: dict[str, str], data: Any = None) -> Any:
        assert headers["sign"] and headers["client_id"] == SESSION["access_id"]
        path = urlsplit(url).path
        self.calls.append((method, path, json.loads(data) if data else None))
        reply = self.routes.get(f"{method} {path}", refused(1108, "uri path invalid"))
        if isinstance(reply, list):
            reply = reply.pop(0) if len(reply) > 1 else reply[0]
        if isinstance(reply, Exception):
            raise reply
        content = reply if isinstance(reply, bytes) else json.dumps(reply).encode()
        return SimpleNamespace(status_code=200, content=content, text=content.decode())

    def paths(self) -> list[str]:
        return [f"{method} {path}" for method, path, _ in self.calls]


def about(device_id: str) -> list[str]:
    """The requests for a device's specification and thing model, as `paths()` lists them."""
    return [
        f"GET /v1.1/devices/{device_id}/specifications",
        f"GET /v2.0/cloud/thing/{device_id}/model",
    ]


def ok(result: Any) -> dict[str, Any]:
    return {"success": True, "t": 1700000000000, "tid": "0123456789abcdef", "result": result}


def refused(code: int, msg: str) -> dict[str, Any]:
    return {"success": False, "code": code, "msg": msg, "t": 1700000000000, "tid": "0123"}


def values(**fields: Any) -> str:
    return json.dumps(fields, separators=(",", ":"))


def row(dp_id: int, code: str, type_: str, values_: str = "{}") -> dict[str, Any]:
    return {"code": code, "dp_id": dp_id, "type": type_, "values": values_}


def prop(dp_id: int, code: str, **type_spec: Any) -> dict[str, Any]:
    return {"abilityId": dp_id, "code": code, "accessMode": "rw", "typeSpec": type_spec}


def model(*properties: dict[str, Any]) -> dict[str, Any]:
    """The result of GET /v2.0/cloud/thing/{id}/model: the model comes as JSON text."""
    services = [{"code": "", "name": "", "properties": list(properties)}]
    return {"model": json.dumps({"modelId": "000004abcd", "services": services})}


UID = "eu1700000000000aBcDe"
SESSION = {
    "kind": "developer",
    "region": "eu",
    "access_id": "abcdefghijklmnop1234",
    "access_secret": "0123456789abcdef0123456789abcdef",
    "uid": UID,
}
BULB_ID, PLUG_ID = "dj_k3okx0w3bsgmindp", "01234567890abcdef012"
LIST = f"GET /v1.0/users/{UID}/devices"

# --- GET /v1.0/users/{uid}/devices: the parts libtuya reads, and some it does not -------
_ITEM = {"uid": UID, "sub": False, "owner_id": "12345678", "online": True, "ip": "203.0.113.7"}
BULB = _ITEM | {
    "id": BULB_ID, "name": "Living room", "local_key": local_key(BULB_ID), "category": "dj",
    "product_id": "k3okx0w3bsgmindp", "product_name": "Smart Bulb", "uuid": "a1b2c3d4e5f60718",
    "status": [
        {"code": "switch_led", "value": True},
        {"code": "work_mode", "value": "white"},
        {"code": "bright_value_v2", "value": 1000},
        {"code": "temp_value_v2", "value": 1000},
        {"code": "colour_data_v2", "value": '{"h":0,"s":1000,"v":1000}'},
        {"code": "scene_data_v2", "value": '{"scene_num":1,"scene_units":[]}'},
        {"code": "countdown_1", "value": 0},
    ],
}  # fmt: skip
PLUG = _ITEM | {
    "id": PLUG_ID, "name": "Smart Plug", "local_key": "abcdef0123456789", "category": "cz",
    "product_id": "iXfg9AQVUPhlfyGw", "product_name": "WP1-Smart Socket", "uuid": PLUG_ID,
    "status": [
        {"code": "switch", "value": True},
        {"code": "countdown_1", "value": 0},
        {"code": "cur_current", "value": 55},
        {"code": "cur_power", "value": 127},
        {"code": "cur_voltage", "value": 2298},
    ],
}  # fmt: skip

# --- GET /v1.1/devices/{id}/specifications ---------------------------------------------
HSV_V2 = values(
    h={"min": 0, "scale": 0, "unit": "", "max": 360, "step": 1},
    s={"min": 0, "scale": 0, "unit": "", "max": 1000, "step": 1},
    v={"min": 0, "scale": 0, "unit": "", "max": 1000, "step": 1},
)
_BULB_ROWS = [
    row(20, "switch_led", "Boolean"),
    row(21, "work_mode", "Enum", values(range=["white", "colour", "scene", "music"])),
    row(22, "bright_value_v2", "Integer", values(min=10, max=1000, scale=0, step=1)),
    row(23, "temp_value_v2", "Integer", values(min=0, max=1000, scale=0, step=1)),
    row(24, "colour_data_v2", "Json", HSV_V2),
    row(25, "scene_data_v2", "Json", values(scene_num={"min": 1, "scale": 0, "max": 8, "step": 1})),
    row(26, "countdown_1", "Integer", values(unit="s", min=0, max=86400, scale=0, step=1)),
]
BULB_SPEC = {"category": "dj", "functions": _BULB_ROWS, "status": _BULB_ROWS}
_PLUG_SWITCH = row(1, "switch", "Boolean")
PLUG_SPEC = {
    "category": "cz",
    "functions": [
        _PLUG_SWITCH,
        row(2, "countdown_1", "Integer", values(unit="s", min=0, max=86400, scale=0, step=1)),
    ],
    "status": [
        _PLUG_SWITCH,
        row(4, "cur_current", "Integer", values(unit="mA", min=0, max=30000, scale=0, step=1)),
        row(5, "cur_power", "Integer", values(unit="W", min=0, max=50000, scale=1, step=1)),
        row(6, "cur_voltage", "Integer", values(unit="V", min=0, max=5000, scale=1, step=1)),
    ],
}

# --- GET /v2.0/cloud/thing/{id}/model: the device's own datapoints ----------------------
BULB_MODEL = model(
    prop(20, "switch_led", type="bool"),
    prop(21, "work_mode", type="enum", range=["white", "colour", "scene", "music"]),
    prop(22, "bright_value", type="value", min=10, max=1000, scale=0, step=1, unit=""),
    prop(23, "temp_value", type="value", min=0, max=1000, scale=0, step=1, unit=""),
    prop(24, "colour_data", type="string", maxlen=255),
    prop(25, "scene_data", type="string", maxlen=255),
    prop(26, "countdown", type="value", min=0, max=86400, scale=0, step=1, unit="s"),
    prop(27, "music_data", type="string", maxlen=255),
    prop(28, "control_data", type="string", maxlen=255),
)
PLUG_PROPERTIES = [
    prop(1, "switch_1", type="bool"),
    prop(2, "countdown_1", type="value", min=0, max=86400, scale=0, step=1, unit="s"),
    prop(4, "cur_current", type="value", min=0, max=30000, scale=0, step=1, unit="mA"),
    prop(5, "cur_power", type="value", min=0, max=50000, scale=1, step=1, unit="W"),
    prop(6, "cur_voltage", type="value", min=0, max=5000, scale=1, step=1, unit="V"),
]

ROUTES = {
    LIST: ok([BULB, PLUG]),
    f"GET /v1.0/devices/{PLUG_ID}": ok(PLUG),
    f"GET /v1.1/devices/{BULB_ID}/specifications": ok(BULB_SPEC),
    f"GET /v1.1/devices/{PLUG_ID}/specifications": ok(PLUG_SPEC),
    f"GET /v2.0/cloud/thing/{BULB_ID}/model": ok(BULB_MODEL),
    f"GET /v2.0/cloud/thing/{PLUG_ID}/model": ok(model(*PLUG_PROPERTIES)),
    f"POST /v1.0/iot-03/devices/{BULB_ID}/commands": ok(True),
}
