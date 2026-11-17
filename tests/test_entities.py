"""Entities are checked against Home Assistant itself.

The vendored tree holds dumps of real devices and the snapshots of the entities
Home Assistant creates for them, so "libtuya sees a device the way Home
Assistant does" is a testable statement.
"""

import importlib.util
import json
import re
import tomllib
from pathlib import Path

import pytest
from conftest import FIXTURES, fixture_names, record

from libtuya import Light, TuyaError
from libtuya.cloud import load_device
from libtuya.entities import _tables, definitions

ROOT = Path(__file__).parent.parent
SNAPSHOTS = FIXTURES.parent / "snapshots"
ENTRY = re.compile(
    r"^# name: test_platform_setup_and_discovery\[.*?-entry\]$.*?'unique_id': 'tuya\.(.*?)'",
    re.MULTILINE | re.DOTALL,
)


def test_same_entities_as_home_assistant():
    """Every fixture device gets exactly the entities in Home Assistant's snapshots."""
    built: dict[str, set[str]] = {platform: set() for platform in _tables()["platforms"]}
    for name in fixture_names():
        # Home Assistant's snapshot test runs without product quirks, and uses
        # the reversed fixture name as the device id.
        info = load_device(record(name, id=name.replace("_", "")[::-1]))
        for platform, description, _ in definitions(info):
            built[platform].add(info.id + description["key"])

    for platform, ours in built.items():
        theirs = set(ENTRY.findall((SNAPSHOTS / f"test_{platform}.ambr").read_text()))
        assert ours == theirs, platform


def test_every_device_can_be_read(make_device):
    """With quirks applied, as in real use, every entity of every fixture reads."""
    for name in fixture_names():
        for entity in make_device(name).entities:
            entity.state()


def test_generated_data_is_current():
    """ha_tuya.json matches the vendored source, and the pins match its manifest."""
    spec = importlib.util.spec_from_file_location("gen", ROOT / "scripts/gen_ha_tables.py")
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    assert generator.build() == json.loads(generator.OUT.read_text())

    dependencies = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["dependencies"]
    assert set(generator.build()["requirements"]) <= set(dependencies)


def test_light_attributes_use_friendly_units(make_device):
    light = make_device("dj_k3okx0w3bsgmindp").entity("light")
    assert isinstance(light, Light)
    assert light.name is None  # the main entity carries the device's name
    assert light.state() == {
        "switch": True,
        "brightness": 255,  # raw 1000 of 10..1000
        "color_temp": 6500,  # raw 1000 of 0..1000, in kelvin
        "color_data": (0.0, 100.0, 255.0),  # raw h 0, s 1000, v 1000
        "color_mode": "white",
    }
    assert light.commands(brightness=128) == [{"code": "bright_value_v2", "value": 507}]


def test_on_and_off_for_every_kind_of_device(make_device):
    valve = make_device("ggq_7ytb3h8u").power
    assert (valve.id, valve.on_off) == ("valve.switch", "control")
    assert valve.commands(control=True) == [{"code": "switch", "value": True}]
    assert make_device("sgbj_ulv4nnue7gqp0rjk").power.on_off == "siren"
    # A fan with a light is two things; neither is silently preferred.
    with pytest.raises(TuyaError, match="several switches"):
        _ = make_device("fs_g0ewlb1vmwqljzji").power
    with pytest.raises(TuyaError, match="nothing to switch"):
        _ = make_device("cl_zah67ekd").power


def test_entities_describe_themselves(make_device):
    device = make_device("znjdq_au6dqazvkxqnpaak")
    assert device.entity("sensor.cur_power").describe() == {
        "sensor": {
            "value": 14.3,
            "writable": False,
            "unit": "W",
            "min": 0.0,
            "max": 26000.0,
            "step": 0.1,
        }
    }
    mode = device.entity("select.light_mode").describe()["select"]
    assert (mode["value"], mode["writable"], mode["options"]) == (
        "relay",
        True,
        ["relay", "pos", "none", "on"],
    )


def test_a_light_refuses_what_it_cannot_do(make_device):
    dimmer = make_device("dj_bSXSSFArVKtc4DyC").entity("light")
    with pytest.raises(TuyaError, match="no adjustable colour"):
        dimmer.turn_on(hs_color=(0, 100))
    bulb = make_device("dj_k3okx0w3bsgmindp").entity("light")
    with pytest.raises(ValueError, match="hue 0-360"):
        bulb.set(color_data=(400, 150, 999))
    with pytest.raises(ValueError, match="out of range 0 to 255"):
        bulb.set(brightness=999)
    with pytest.raises(ValueError, match="does not accept"):
        bulb.set(brightness="high")


def test_bad_requests_are_explained(make_device):
    device = make_device("znjdq_au6dqazvkxqnpaak")
    with pytest.raises(TuyaError, match="read-only"):
        device.entity("sensor.cur_power").set(5)
    with pytest.raises(TuyaError, match="no attribute"):
        device.entity("switch.switch_1").set(colour="red")
    with pytest.raises(TuyaError, match="has no entity"):
        device.entity("nope")
    with pytest.raises(TuyaError, match="nothing to set"):
        device.entity("switch.switch_1").set()
    with pytest.raises(TuyaError, match="is a Switch, not a Light"):
        device.entity("switch.switch_1", Light)
