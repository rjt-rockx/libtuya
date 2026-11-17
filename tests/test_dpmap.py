"""LAN datapoints to cloud codes and back, using datapoint maps of real devices."""

import json

import pytest
from conftest import record
from tuya_sharing import strategy

from libtuya.dpmap import _ENCODERS, DpMap
from libtuya.errors import Unmapped

BULB = DpMap(record("dj_k3okx0w3bsgmindp")["local_strategy"])


def test_decode_names_and_converts_raw_datapoints():
    raw = {"20": True, "21": "colour", "22": 500, "24": "007803e801f4", "99": "unknown dp"}
    assert BULB.decode(raw) == {
        "switch_led": True,
        "work_mode": "colour",
        "bright_value_v2": 500,
        "colour_data_v2": '{"h": 120, "s": 1000, "v": 500}',
    }


def test_values_the_device_did_not_report_are_not_made_up():
    """The SDK reads these as the first value of the range (tuya-device-sharing-sdk#86)."""

    def datapoint(code: str, convert: str, values: list[str], mapping: dict) -> dict:
        config = {"statusFormat": json.dumps({code: "$"}), "valueType": "Enum"}
        config |= {"valueDesc": json.dumps({"range": values}), "enumMappingMap": mapping}
        return {"value_convert": convert, "status_code": code, "config_item": config}

    names = {"1": {"value": "alarm"}, "2": {"value": "normal"}}
    smoke = datapoint("smoke_sensor_status", "enum", ["alarm", "normal"], names)
    battery = datapoint("battery_state", "default", ["low", "middle", "high"], {})
    smoke_alarm = DpMap({1: smoke, 14: battery})  # product dehj5gbayszxesma
    assert smoke_alarm.decode({"1": "23"}) == {}  # not a value the cloud lists
    assert smoke_alarm.decode({"1": "", "14": ""}) == smoke_alarm.decode({"1": None}) == {}
    expected = {"smoke_sensor_status": "normal", "battery_state": "high"}
    assert smoke_alarm.decode({"1": "2", "14": "high"}) == expected


def test_encode_is_the_inverse_of_decode():
    commands = [
        {"code": "switch_led", "value": False},
        {"code": "bright_value_v2", "value": 10},
        {"code": "colour_data_v2", "value": '{"h": 120, "s": 1000, "v": 500}'},
    ]
    dps = BULB.encode(commands)
    assert dps == {"20": False, "22": 10, "24": "007803e801f4"}
    assert BULB.decode(dps) == {command["code"]: command["value"] for command in commands}


def test_old_style_colour_matches_the_sdk_decoder():
    """Version 1 bulbs pack colour as RRGGBBHHHHSSVV; check against the SDK's reading of it."""
    raw = _ENCODERS["dj_v1_hsv_alg"]({"h": 120, "s": 255, "v": 128}, {})
    assert raw == "0080000078ff80"
    config = {"statusFormat": '{"colour_data": "$"}'}
    _, value = strategy.convert("dj_v1_hsv_alg", (None, raw), config)
    assert json.loads(value) == {"h": 120, "s": 255, "v": 128}


def test_what_the_lan_cannot_express_is_refused():
    with pytest.raises(Unmapped, match="no datapoint"):
        BULB.encode([{"code": "not_a_code", "value": 1}])
    with pytest.raises(Unmapped, match="read-only on the LAN"):
        BULB.encode([{"code": "scene_data_v2", "value": "{}"}])

    # An enumeration: several raw values stand for one cloud value, so it
    # reads locally but is written through the cloud.
    relay = DpMap(record("tdq_1ctrc5jx88mtdh9w")["local_strategy"])
    assert relay.decode({"38": "memory"}) == {"relay_status": "2"}
    with pytest.raises(Unmapped):
        relay.encode([{"code": "relay_status", "value": "2"}])


def test_a_datapoint_reported_and_commanded_under_different_codes():
    breaker = DpMap(record("dlq_fygozcnralhwbauo")["local_strategy"])
    assert breaker.dp_id("energy_reset") == breaker.dp_id("clear_energy") == 12
