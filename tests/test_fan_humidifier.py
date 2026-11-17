"""What fans and (de)humidifiers are sent, by what Home Assistant's own tests expect of them."""

import pytest

from libtuya import TuyaError

TOWER = "ks_j9fa8ahzac8uvlfl"  # switch, speeds 1..12, three presets, oscillation
CEILING = "fs_g0ewlb1vmwqljzji"  # switch, six named speeds, three presets, direction
DEHUMIDIFIER = "cs_zibqa9dutqyaxym2"  # switch, target humidity 35..70
PRO_BREEZE = "cs_ipmyy4nigpqcnd8q"  # all of its datapoints come from a quirk


def commands(**values):
    return [{"code": code, "value": value} for code, value in values.items()]


@pytest.fixture
def entity(make_device):
    """Makes one entity of a fixture device and the list of what it sends, call by call."""

    def make(name, platform):
        device = make_device(name)
        sent = []
        device.send = sent.append
        return device.entity(platform), sent

    return make


@pytest.mark.parametrize(
    ("name", "platform", "action", "args", "expected"),
    [
        (TOWER, "fan", "oscillate", [False], commands(switch_horizontal=False)),
        (TOWER, "fan", "set_preset_mode", ["sleep"], commands(mode="sleep")),
        (TOWER, "fan", "set_percentage", [0], commands(switch=False)),
        (CEILING, "fan", "set_direction", ["forward"], commands(fan_direction="forward")),
        (CEILING, "fan", "set_percentage", [50], commands(fan_speed="3")),
        (CEILING, "fan", "set_percentage", [50 + 100 / 6], commands(fan_speed="4")),  # one step up
        (CEILING, "fan", "turn_off", [], commands(switch=False)),
        (DEHUMIDIFIER, "humidifier", "turn_on", [], commands(switch=True)),
        (DEHUMIDIFIER, "humidifier", "turn_off", [], commands(switch=False)),
        (DEHUMIDIFIER, "humidifier", "set_humidity", [50], commands(dehumidify_set_value=50)),
    ],
)
def test_actions_send_what_home_assistant_sends(entity, name, platform, action, args, expected):
    target, sent = entity(name, platform)
    getattr(target, action)(*args)
    assert sent == [expected]


def test_a_fan_turns_on_with_speed_and_preset_in_one_call(entity):
    ceiling, sent = entity(CEILING, "fan")
    ceiling.turn_on(preset_mode="sleep")
    assert sent == [commands(switch=True, mode="sleep")]
    tower, sent = entity(TOWER, "fan")
    tower.turn_on(percentage=50, preset_mode="nature")
    assert sent == [commands(switch=True, fan_speed=6, mode="nature")]  # 50% of 1..12


def test_a_product_fixed_by_a_quirk_uses_its_own_speeds_and_modes(entity):
    fan, sent = entity(PRO_BREEZE, "fan")
    fan.device.status.update(switch=True, fan_speed_enum="1", mode="0")  # "1" is low, "0" high
    assert (fan.is_on, fan.percentage, fan.percentage_step) == (True, 50, 50)
    fan.set_percentage(51)
    humidifier = fan.device.entity("humidifier")
    assert (humidifier.mode, humidifier.available_modes) == ("0", ["0", "1"])
    humidifier.set_mode("1")
    assert sent == [commands(fan_speed_enum="0"), commands(mode="1")]


def test_a_humidifier_says_which_way_it_works(entity):
    assert entity(DEHUMIDIFIER, "humidifier")[0].device_class == "dehumidifier"
    assert entity("jsq_r492ifwk6f2ssptb", "humidifier")[0].device_class == "humidifier"


def test_what_a_device_cannot_do_is_refused(entity):
    purifier, sent = entity("kj_fsxtzzhujkrak2oy", "fan")  # presets, no speeds
    with pytest.raises(TuyaError):
        purifier.turn_on(percentage=50)
    ceiling, ceiling_sent = entity(CEILING, "fan")
    for percentage in (0, 150):  # the handlers alone would pick the nearest named speed
        with pytest.raises(ValueError, match="1 to 100"):
            ceiling.turn_on(percentage=percentage)
    assert sent == ceiling_sent == []
    with pytest.raises(ValueError):
        entity(DEHUMIDIFIER, "humidifier")[0].set_humidity(90)
    with pytest.raises(TuyaError):  # this one measures humidity and has no setting for it
        entity("cs_eguoms25tkxtf5u8", "humidifier")[0].set_humidity(50)
