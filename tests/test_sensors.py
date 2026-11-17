"""Sensors and binary sensors read as Home Assistant's do; they have nothing to write.

The cases are those of Home Assistant's own tests of the same devices
(tests/components/tuya/test_sensor.py and test_binary_sensor.py).
"""

from datetime import UTC, datetime, timedelta

import pytest

from libtuya import TuyaError
from libtuya.entities import _tables
from libtuya.entities.sensor import _UNITS


def test_a_reading_comes_in_the_unit_home_assistant_shows(make_device):
    current = make_device("znjdq_au6dqazvkxqnpaak").entity("sensor.cur_current")
    assert (current.value, current.unit) == (0.258, "A")
    assert current.state() == {"sensor": 258.0}  # the device reports mA
    # An inverter that reports kW where Home Assistant shows W.
    total = make_device("znnbq_0kllybtbzftaee7y").entity("sensor.power_total")
    assert (total.value, total.unit) == (19060.0, "W")
    total.device.status["power_total"] = 1005  # 1.005 kW
    assert total.value == 1005  # not 1004.9999999999999
    # A device that names no unit has the one Home Assistant gives the sensor.
    assert make_device("mcs_7jIGJAymiH8OsFFb").entity("sensor.battery").unit == "%"


def test_a_temperature_follows_the_unit_the_device_is_set_to(make_device):
    heat_pump = make_device("znrb_gpzittzfnzhduquz")
    outside = heat_pump.entity("sensor.temp_around")  # its datapoint names no unit
    assert (outside.value, outside.unit) == (14.0, "°C")
    heat_pump.status["temp_unit_convert"] = "f"
    assert (outside.value, outside.unit) == (14.0, "°F")
    assert make_device("bh_dft4ebatvon3ha5s").entity("sensor.temp_current").unit == "°C"  # "℃"


def test_increments_add_up_once_pushes_are_followed(make_device):
    socket = make_device("cz_guitoc9iylae4axs")
    energy = socket.entity("sensor.add_ele")
    assert (energy.value, energy.summary()) == (None, {"state": 0})  # Home Assistant starts at 0
    socket._apply_report([{"code": "add_ele", "value": 200}])
    socket._apply_report([{"code": "add_ele", "value": 300}, {"code": "switch_1", "value": True}])
    socket._apply_report([{"code": "switch_1", "value": False}])
    assert (energy.summary(), energy.unit) == ({"state": pytest.approx(0.5)}, "kWh")


def test_a_countdown_reads_as_the_time_it_ends(make_device):
    towel_rack = make_device("mjj_sbcafqr6tykxq4bm")
    countdown = towel_rack.entity("sensor.countdown_left")
    assert countdown.summary() == {"state": None}  # nothing is counting down
    towel_rack._apply_report([{"code": "countdown_left", "value": 90}])  # minutes
    ends = countdown.value
    assert abs(ends - datetime.now(UTC) - timedelta(minutes=90)) < timedelta(seconds=5)
    assert countdown.summary() == {"state": ends.isoformat(timespec="seconds")}


def test_each_fault_bit_is_a_binary_sensor(make_device):
    dehumidifier = make_device("cs_zibqa9dutqyaxym2")
    faults = [dehumidifier.entity(f"binary_sensor.{key}") for key in ("tankfull", "defrost", "wet")]
    for fault, expected in ((0, [False] * 3), (0x2, [False, True, False]), (0x83, [True] * 3)):
        dehumidifier.status["fault"] = fault
        assert [sensor.is_on for sensor in faults] == expected


def test_a_binary_sensor_is_on_for_the_value_home_assistant_names(make_device):
    motion = make_device("pir_3amxzozho9xp4mkh").entity("binary_sensor.pir")
    assert (motion.is_on, motion.summary()) == (True, {"state": "on"})  # the device says "pir"
    motion.device.status["pir"] = "none"
    assert (motion.is_on, motion.summary()) == (False, {"state": "off"})
    with pytest.raises(TuyaError, match="cannot be switched"):
        motion.turn_on()


def test_every_unit_home_assistant_names_is_known():
    """`_UNITS` is written by hand; a re-sync that names another unit must add it."""
    named = {
        description[field]["$ha"]
        for descriptions in _tables()["platforms"]["sensor"].values()
        for description in descriptions
        for field in ("native_unit_of_measurement", "suggested_unit_of_measurement")
        if field in description
    }
    assert named == set(_UNITS)
