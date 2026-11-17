"""What covers and valves are sent: the commands Home Assistant's own tests
(``tests/components/tuya/test_cover.py``, ``test_valve.py``) expect for the same devices."""

import pytest
from conftest import record

from libtuya import TuyaError

BLIND = "cl_zah67ekd"  # takes a position, which it counts from open (0) to closed (100)
CURTAIN = "cl_n3xgr5pdmpinictg"  # takes open, close and stop only
SHUTTER = "clkg_wltqkykhni0papzj"  # counts its position either way round, by a setting
GARAGE = "ckmkzq_1yyqfw4djv9eii3q"  # a relay to open and close with, a contact for the state
IRRIGATION = "sfkzq_ed7frwissyqrejic"  # eight valves


@pytest.fixture
def entity(make_device):
    """Makes one entity of a fixture device and the list of what it sends, call by call."""

    def make(name, ref="cover", status=(), **overrides):
        device = make_device(name, **overrides)
        device.status.update(status)
        sent = []
        device.send = lambda commands: sent.append([(c["code"], c["value"]) for c in commands])
        return device.entity(ref), sent

    return make


@pytest.mark.parametrize(
    ("name", "ref", "action", "arguments", "expected"),
    [
        (BLIND, "cover", "open", [], [("percent_control", 0)]),
        (BLIND, "cover", "close", [], [("percent_control", 100)]),
        (BLIND, "cover", "set_position", [25], [("percent_control", 75)]),
        (CURTAIN, "cover", "open", [], [("control", "open")]),
        (CURTAIN, "cover", "close", [], [("control", "close")]),
        (CURTAIN, "cover", "stop", [], [("control", "stop")]),
        (GARAGE, "cover", "close", [], [("switch_1", False)]),
        (IRRIGATION, "valve.switch_1", "open", [], [("switch_1", True)]),
        (IRRIGATION, "valve.switch_1", "close", [], [("switch_1", False)]),
    ],
)
def test_actions_send_what_home_assistant_sends(entity, name, ref, action, arguments, expected):
    target, sent = entity(name, ref)
    getattr(target, action)(*arguments)
    assert sent == [expected]


@pytest.mark.parametrize(("setting", "raw", "raw_open"), [("back", 25, 100), ("forward", 75, 0)])
def test_a_shutter_that_counts_either_way_round(entity, setting, raw, raw_open):
    status = {"control_back_mode": setting, "percent_control": raw}
    shutter, sent = entity(SHUTTER, status=status)
    assert (shutter.current_position, shutter.is_closed) == (25, False)
    shutter.set_position(25)
    shutter.open()
    assert sent == [[("percent_control", raw)], [("percent_control", raw_open)]]


def test_closed_is_judged_by_position_before_state(entity):
    blind, _ = entity(BLIND, status={"percent_state": 100, "situation_set": "fully_open"})
    assert blind.summary() == {"state": "closed", "is_closed": True, "current_position": 0}


def test_slats_are_tilted_where_a_cover_has_them(entity):
    function = record(BLIND)["function"]
    function["angle_horizontal"] = function["percent_control"] | {"code": "angle_horizontal"}
    blind, sent = entity(BLIND, status={"angle_horizontal": 30}, function=function)
    assert blind.summary()["current_tilt_position"] == 70
    blind.set_tilt_position(80)
    assert sent == [[("angle_horizontal", 20)]]


def test_what_a_device_cannot_do_is_refused(entity):
    blind, sent = entity(BLIND)
    with pytest.raises(ValueError, match="out of range 0 to 100"):
        blind.set_position(150)
    with pytest.raises(TuyaError, match="no attribute 'tilt_position'"):
        blind.set_tilt_position(50)
    garage, garage_sent = entity(GARAGE)
    with pytest.raises(TuyaError, match="cannot stop"):
        garage.stop()
    assert sent == garage_sent == []
