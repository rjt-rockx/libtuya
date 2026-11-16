"""The `tuya` command against a fake device, starting from the on-disk cache as a real run does."""

import json

import pytest
from conftest import fake

from libtuya.cli import main
from libtuya.lan import LanAddress

PLUG = "znjdq_au6dqazvkxqnpaak"
BULB = "dj_k3okx0w3bsgmindp"


@pytest.fixture
def run(tuya, make_device, capsys):
    """Run the CLI with two cached devices; returns (exit status, stdout)."""
    plug_dps = {"1": False, "19": 143, "38": "memory", "41": False}
    bulb_dps = {"20": True, "21": "white", "22": 1000, "23": 0, "24": "000003e803e8"}
    with fake(PLUG, "3.3", plug_dps) as plug, fake(BULB, "3.5", bulb_dps) as bulb:
        make_device(BULB, LanAddress("127.0.0.1", "3.5", bulb.port))
        make_device(PLUG, LanAddress("127.0.0.1", "3.3", plug.port))
        tuya._save()

        def run(*args: str) -> tuple[int, str]:
            status = main(["--home", str(tuya.home), "--local", *args])
            captured = capsys.readouterr()
            run.err = captured.err
            return status, captured.out

        run.plug, run.bulb = plug, bulb
        yield run


def test_control(run):
    status, out = run("control", "breaker", "on", "--json")
    assert status == 0
    assert json.loads(out) == {
        "success": True,
        "device": "Smart Circuit Breaker",
        "action": "on",
        "value": None,
        "transport": "lan",
    }
    assert run.plug.dps["1"] is True

    assert run("control", "1", "brightness", "50")[0] == 0  # by number, as listed
    assert run.bulb.dps["22"] == 505  # half of 10..1000
    assert run("control", "portal", "color", "#00ff00")[0] == 0
    assert (run.bulb.dps["21"], run.bulb.dps["24"]) == ("colour", "007803e803e8")
    assert run("control", "portal", "temperature", "2000")[0] == 0
    assert (run.bulb.dps["21"], run.bulb.dps["23"]) == ("white", 0)


def test_info_and_set(run):
    status, out = run("info", "breaker")
    assert status == 0
    assert "sensor.cur_power" in out and "14.3 W" in out

    assert run("set", "breaker", "switch.child_lock", "on")[0] == 0
    assert run.plug.dps["41"] is True
    assert run("set", "portal", "light", "brightness=255", "color_temp=6500")[0] == 0
    assert (run.bulb.dps["22"], run.bulb.dps["23"]) == (1000, 1000)
    assert run("set", "breaker", "countdown_1", "60", "--raw")[0] == 0
    assert run.plug.dps["9"] == 60


def test_listing_and_errors(run):
    status, out = run("devices")
    assert status == 0
    assert "Smart Circuit Breaker" in out and f"127.0.0.1:{run.plug.port}" in out

    assert run("control", "toaster", "on") == (1, "")
    assert "no device matches" in run.err
    status, out = run("set", "breaker", "sensor.cur_power", "5", "--json")
    assert status == 1 and "read-only" in json.loads(out)["error"]
    assert run("control", "breaker", "brightness", "50")[0] == 1  # a plug is not a light
