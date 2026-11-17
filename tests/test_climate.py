"""What thermostats and air conditioners are sent: the commands Home Assistant's own tests
(``tests/components/tuya/test_climate.py``) expect for the same actions on the same devices."""

import json

import pytest
from conftest import record

from libtuya import TuyaError

AIRCON = "kt_5wnlzekkstwcdsvm"  # switch, two fan speeds, temp_set 16..86 in "℃ ℉"
FLOOR = "wk_t94pit6zjbask9qo"  # switch; modes off, auto and manual, the last two being presets


def commands(**values):
    return [{"code": code, "value": value} for code, value in values.items()]


@pytest.fixture
def climate(make_device):
    """Makes a fixture device's climate entity and the list of what it sends, call by call."""

    def make(name, status=(), **overrides):
        device = make_device(name, **overrides)
        device.status.update(status)
        sent = []
        device.send = sent.append
        return device.entity("climate"), sent

    return make


@pytest.mark.parametrize(
    ("name", "action", "arguments", "expected"),
    [
        (AIRCON, "set_temperature", [22.7], commands(temp_set=23)),
        (AIRCON, "set_fan_mode", ["2"], commands(windspeed="2")),
        (AIRCON, "turn_on", [], commands(switch=True)),
        (AIRCON, "turn_off", [], commands(switch=False)),
        ("kt_ibmmirhhq62mmf1g", "set_hvac_mode", ["cool"], commands(switch=True, mode="cold")),
        ("wk_gc1bxoq2hafxpa35", "set_preset_mode", ["holiday"], commands(mode="holiday")),
        ("kt_wxqdp6ecfkd78zzz", "set_swing_mode", ["horizontal"], commands(switch_horizontal=True)),
    ],
)
def test_actions_send_what_home_assistant_sends(climate, name, action, arguments, expected):
    entity, sent = climate(name)
    getattr(entity, action)(*arguments)
    assert sent == [expected]


def test_turning_on_a_thermostat_whose_modes_are_presets(climate):
    # "off" is a mode of the device, not a preset: only choosing a preset gets it out of it.
    entity, sent = climate(FLOOR, {"mode": "off", "switch": True})
    assert (entity.hvac_mode, entity.hvac_modes) == ("off", ["off", "heat_cool"])
    entity.set_hvac_mode("heat_cool")
    # Switched off in a preset: switching on is enough, and keeps the preset.
    entity.device.status.update(mode="manual", switch=False)
    entity.set_hvac_mode("heat_cool")
    assert sent == [commands(switch=True, mode="auto"), commands(switch=True)]


def test_a_device_that_works_in_fahrenheit(climate):
    spec = record(AIRCON)  # on the device: 22 now, set to 23, from 16 to 86 in steps of 1
    for item in (spec["function"]["temp_set"], spec["status_range"]["temp_current"]):
        item["values"] = json.dumps(json.loads(item["values"]) | {"unit": "℉"})
    entity, sent = climate(AIRCON, function=spec["function"], status_range=spec["status_range"])
    keys = ("current_temperature", "temperature", "min_temp", "max_temp", "target_temp_step")
    assert [round(entity.summary()[key], 1) for key in keys] == [-5.6, -5.0, -8.9, 30.0, 0.6]
    entity.set_temperature(25)
    entity.set_temperature(10)  # allowed: the limits are in °C as well
    assert sent == [commands(temp_set=77), commands(temp_set=50)]


def test_a_setpoint_without_a_unit_is_in_the_unit_the_device_is_switched_to(climate):
    entity, sent = climate("wk_B0eP8qYAdpUo4yR9", {"temp_unit_convert": "f"})
    assert entity.summary()["temperature"] == 1.7  # 35.0 on the device
    entity.set_temperature(20)
    assert sent == [commands(temp_set=680)]


def test_what_a_device_cannot_do_is_refused(climate):
    aircon, sent = climate(AIRCON)
    for temperature in (15.6, "22"):  # 15.6 is not rounded up to 16: Home Assistant refuses it too
        with pytest.raises(ValueError, match="a number from 16.0 to 86.0"):
            aircon.set_temperature(temperature)
    with pytest.raises(ValueError, match=r"must be one of \['off', 'cool'\]"):
        aircon.set_hvac_mode("heat")
    with pytest.raises(TuyaError, match="no preset modes"):
        aircon.set_preset_mode("eco")
    with pytest.raises(TuyaError, match="no target temperature"):
        climate("wk_ccpwojhalfxryigz")[0].set_temperature(50)
    valve, valve_sent = climate("wk_cpmgn2cf")  # Home Assistant offers "off", then sends nothing
    with pytest.raises(TuyaError, match="neither a switch nor a mode"):
        valve.set_hvac_mode("off")
    assert sent == valve_sent == []
