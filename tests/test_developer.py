"""The developer-account login: records, what may use the LAN, failures, and the whole path.

Tuya's servers are replaced at the HTTP level (fake_openapi), so TinyTuya's Cloud class
runs for real; on the LAN the real TinyTuya client talks to a fake device.
"""

import json

import fake_openapi as canned
import pytest
import requests
from conftest import fake
from fake_openapi import BULB_ID, LIST, PLUG_ID, SESSION, about, ok, prop, refused, row
from fake_openapi import values as v

from libtuya import CloudError, Device, Light, Tuya, TuyaError
from libtuya.developer import DeveloperCloud
from libtuya.dpmap import DpMap
from libtuya.lan import LanAddress

SECRET = SESSION["access_secret"]
TOKEN = "GET /v1.0/token"
SPEC, MODEL = about(PLUG_ID)
MODEL_TEXT = canned.ROUTES[MODEL]["result"]["model"]
BASE = dict.fromkeys([1, 2, 4, 5, 6], "default")  # the plug's own datapoints, all mapped
HUE = {"min": 0, "max": 360}


@pytest.fixture
def cloud(monkeypatch) -> canned.FakeTuyaCloud:
    return canned.FakeTuyaCloud(dict(canned.ROUTES)).install(monkeypatch)


def conversions(record) -> dict[int, str]:
    return {dp_id: item["value_convert"] for dp_id, item in record["local_strategy"].items()}


def test_records(cloud, tuya):
    # The same product, its colour given as an object.
    as_object = {"code": "colour_data_v2", "value": {"h": 0, "s": 1000, "v": 1000}}
    hall = canned.BULB | {"id": "bf00000000000000hall", "name": "Hall", "status": [as_object]}
    cloud.routes[LIST] = ok([canned.BULB, canned.PLUG, hall])
    bulb, plug, hall = DeveloperCloud(SESSION).devices()
    # Nothing for the second bulb.
    assert cloud.paths() == [TOKEN, LIST, *about(BULB_ID), SPEC, MODEL]
    assert hall["status"] == {"colour_data_v2": '{"h":0,"s":1000,"v":1000}'}
    # Not the scene (dp 25), Json in the cloud and text on the device: its conversion is unknown.
    expected = dict.fromkeys([20, 21, 22, 23, 26], "default") | {24: "dj_v2_color_alg"}
    assert conversions(bulb) == expected
    assert conversions(plug) == BASE
    assert list(plug["function"]) == ["switch", "countdown_1"]
    # The plug's countdown has a functions row only.
    assert plug["local_strategy"][2]["config_item"]["statusFormat"] == '{"countdown_1": "$"}'

    dp_map = DpMap(json.loads(json.dumps(bulb["local_strategy"])))  # as read from devices.json
    colour = dp_map.decode({"24": "007803e801f4"})
    assert colour == {"colour_data_v2": '{"h": 120, "s": 1000, "v": 500}'}
    raw = dp_map.encode([{"code": "colour_data_v2", "value": colour["colour_data_v2"]}])
    assert raw == {"24": "007803e801f4"}
    sensors = Device(tuya, plug)
    assert sensors.entity("sensor.cur_power").value == 12.7
    assert sensors.entity("sensor.cur_voltage").value == 229.8


def dp7(code, kind, values_, device_kind, value=None, **type_spec):
    """The plug with a dp 7 as its specification, its thing model and its status give it."""
    rows = [*canned.PLUG_SPEC["status"], row(7, code, kind, values_)]
    status = [*canned.PLUG["status"], {"code": code, "value": value}]
    properties = [*canned.PLUG_PROPERTIES, prop(7, code, type=device_kind, **type_spec)]
    return {
        SPEC: ok(canned.PLUG_SPEC | {"status": rows}),
        MODEL: ok(canned.model(*properties)),
        LIST: ok([canned.PLUG | {"status": status}]),
    }


PERCENT = v(min=0, max=100, scale=0, step=1)
V1_COLOUR = v(h=HUE, s={"min": 0, "max": 255})
TEXT_IDS = [p | {"abilityId": str(p["abilityId"])} for p in canned.PLUG_PROPERTIES]
STATUS = canned.PLUG_SPEC["status"]
UNREADABLE = [*STATUS[:2], row(5, "cur_power", "Integer", v(min=0, max=99)), STATUS[3]]
NO_DP_ID = {"code": "cur_power", "type": "Integer", "values": v(min=0, max=99999, scale=1, step=1)}
ON_THE_LAN = {  # routes -> how the plug's datapoints are then mapped
    "renamed enumeration": (
        dp7("relay_status", "Enum", v(range=["0", "1"]), "enum", range=["off", "on"]),
        BASE,
    ),
    "rescaled integer": (dp7("bright_value", "Integer", PERCENT, "value", min=25, max=255), BASE),
    "text": (dp7("cycle_time", "String", "{}", "string"), BASE),
    "colour without a range": (dp7("colour_data", "Json", "{}", "string"), BASE),
    "colour without saturation": (dp7("colour_data", "Json", v(h=HUE, v=HUE), "string"), BASE),
    "v1 colour": (dp7("colour_data", "Json", V1_COLOUR, "string"), BASE | {7: "dj_v1_hsv_alg"}),
    "colour as hex text": (
        dp7("colour_data", "String", "{}", "string", value="00f003e803e8"),
        BASE | {7: "default"},
    ),
    "thing model refused": ({MODEL: refused(2009, "not support this device")}, {}),
    "thing model as an object": ({MODEL: ok({"model": json.loads(MODEL_TEXT)})}, BASE),
    "abilityId as text": ({MODEL: ok(canned.model(*TEXT_IDS))}, BASE),
    "an unreadable row": (  # an Integer without scale and step: dropped
        {SPEC: ok(canned.PLUG_SPEC | {"status": UNREADABLE})},
        dict.fromkeys([1, 2, 4, 6], "default"),
    ),
    "a row of the code without a dp id": (  # still sent to dp 5 by its code
        {SPEC: ok(canned.PLUG_SPEC | {"functions": [*canned.PLUG_SPEC["functions"], NO_DP_ID]})},
        dict.fromkeys([1, 2, 4, 6], "default"),
    ),
}


@pytest.mark.parametrize(("routes", "expected"), ON_THE_LAN.values(), ids=ON_THE_LAN.keys())
def test_only_what_the_thing_model_confirms_uses_the_lan(cloud, tuya, routes, expected):
    cloud.routes |= routes
    plug = DeveloperCloud(SESSION).devices()[-1]
    assert conversions(plug) == expected
    assert Device(tuya, plug).entities  # the rest of the device still works, through the cloud


@pytest.mark.parametrize(
    ("routes", "message", "requests_made"),
    [
        ({TOKEN: refused(1004, "sign invalid")}, "sign invalid.*the Access Secret", 1),
        ({TOKEN: refused(1013, "request time is invalid")}, "clock is wrong", 1),
        ({TOKEN: b"<html>502 Bad Gateway</html>"}, "unexpected response", 1),
        ({LIST: refused(1106, "permission deny")}, r"deny \(1106\).*linked to the project", 2),
        # TinyTuya renews the token and asks again, once.
        ({LIST: refused(1010, "token invalid")}, "keeps rejecting the project's token", 4),
        # The second product's specification: refused for the whole project.
        ({SPEC: refused(28841002, "No permissions")}, r"\(28841002\).*trial has expired", 5),
        ({LIST: requests.ConnectionError(SECRET)}, r"cannot reach .* \(ConnectionError\)", 2),
    ],
)
def test_failures(cloud, tuya, routes, message, requests_made):
    cloud.routes |= routes
    tuya._write("session.json", SESSION)
    with pytest.raises(TuyaError, match=message) as raised:
        tuya.devices()
    assert SECRET not in str(raised.value)
    assert len(cloud.calls) == requests_made


@pytest.mark.parametrize("session", [SESSION | {"uid": ""}, SESSION | {"region": "AY"}, []])
def test_an_unusable_session_is_no_login(cloud, tuya, session):
    tuya._write("session.json", session)
    assert not tuya.logged_in
    with pytest.raises(TuyaError, match="not logged in") as raised:
        tuya.devices()
    assert SECRET not in str(raised.value)
    assert cloud.calls == []


def test_a_token_called_expired_is_replaced(cloud):
    cloud.routes[LIST] = [refused(1010, "token is expired"), ok([canned.PLUG])]
    developer = DeveloperCloud(SESSION)
    with pytest.raises(CloudError, match=r"token is expired \(1010\)"):
        developer.devices()
    developer.devices()
    assert cloud.paths()[:4] == [TOKEN, LIST, TOKEN, LIST]


def test_from_login_to_the_lan(cloud, tuya, make_device):
    dps = {"20": False, "21": "white", "22": 500, "23": 1000, "24": "000003e803e8"}
    with fake(BULB_ID, "3.4", dps) as on_the_wire:
        address = LanAddress("127.0.0.1", "3.4", on_the_wire.port)
        make_device(BULB_ID, address)  # a device list saved under an earlier login
        tuya._save()
        with pytest.raises(CloudError, match="unknown region 'ay'"):
            tuya.login_developer(SESSION["access_id"], SECRET, "AY", uid=canned.UID)
        assert cloud.calls == []
        tuya.login_developer(SESSION["access_id"], SECRET, "EU", device_id=PLUG_ID)
        assert json.loads((tuya.home / "session.json").read_text()) == SESSION
        # The list is this login's, and the bulb keeps the address saved with the earlier one.
        assert [device.address for device in tuya.devices()] == [address, None]

        asked = len(cloud.calls)
        again = Tuya(tuya.home)
        bulb, _ = again.devices()
        bulb.entity("light", Light).turn_on(hs_color=(120, 100), brightness=128)
        assert (on_the_wire.dps["21"], on_the_wire.dps["24"]) == ("colour", "007803e801f6")
        assert len(cloud.calls) == asked  # neither the list nor the colour needed the cloud

        bulb.set_raw(scene_data_v2='{"scene_num":2,"scene_units":[]}')  # no LAN mapping
        scene = {"code": "scene_data_v2", "value": {"scene_num": 2, "scene_units": []}}
        path = f"/v1.0/iot-03/devices/{BULB_ID}/commands"
        assert cloud.calls[-1] == ("POST", path, {"commands": [scene]})
    for unavailable in (again.scenes, lambda: again.subscribe(print), bulb.stream_url):
        with pytest.raises(CloudError, match="not available with a developer account"):
            unavailable()
    again.logout()
    assert not (tuya.home / "session.json").exists()
