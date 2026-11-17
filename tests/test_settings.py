"""What switches, numbers and selects are sent and show: the commands and states Home
Assistant's own tests (``tests/components/tuya/test_switch.py`` and so on) expect for the
same devices."""

import pytest

SOCKET = "cz_PGEkBctAbtzKOZng"
ALARM = "mal_gyitctrjj1kefxp2"
BLINDS = "cl_zah67ekd"
PUMP = "hwsb_ircs2n82vgrozoew"  # the cloud describes none of its settings; a product quirk does
TANK = "ywcgq_h8lvyoahr6s6aybf"  # counts its heights in millimetres, shows them in metres
HEAT_PUMP = "znrb_gpzittzfnzhduquz"  # its temperature setting names no unit


@pytest.fixture
def entity(make_device):
    """Makes one entity of a fixture device and the list of what it sends, call by call."""

    def make(name, ref, **status):
        device = make_device(name)
        device.status.update(status)
        sent = []
        device.send = lambda commands: sent.append([(c["code"], c["value"]) for c in commands])
        return device.entity(ref), sent

    return make


@pytest.mark.parametrize(
    ("name", "ref", "action", "arguments", "expected"),
    [
        (SOCKET, "switch", "turn_on", [], ("switch", True)),
        (SOCKET, "switch", "turn_off", [], ("switch", False)),
        (ALARM, "number.delay_set", "set", [18], ("delay_set", 18)),
        (PUMP, "number", "set", [75], ("speed_set", 75)),
        (TANK, "number.installation_height", "set", [1.5], ("installation_height", 1500)),
        (BLINDS, "select", "select", ["forward"], ("control_back_mode", "forward")),
        (PUMP, "select", "select", ["AI"], ("mode", "AI")),
    ],
)
def test_actions_send_what_home_assistant_sends(entity, name, ref, action, arguments, expected):
    target, sent = entity(name, ref)
    getattr(target, action)(*arguments)
    assert sent == [[expected]]


def test_a_value_the_device_does_not_take_is_refused(entity):
    direction, sent = entity(BLINDS, "select")
    for option in ("hello", 1):
        with pytest.raises(ValueError, match="must be one of"):
            direction.select(option)
    delay, delay_sent = entity(ALARM, "number.delay_set")
    with pytest.raises(ValueError, match="out of range 0.0 to 999.0"):
        delay.set(1000)
    assert sent == delay_sent == []


def test_a_quirk_gives_a_pump_its_settings(entity):
    speed, _ = entity(PUMP, "number", speed_set=50)
    assert (speed.value, speed.min, speed.max, speed.step, speed.unit) == (50, 30, 120, 5, "%")
    mode, _ = entity(PUMP, "select", mode="MI")
    assert (mode.option, mode.options) == ("MI", ["MI", "AI", "backwash"])


@pytest.mark.parametrize(("setting", "unit"), [("c", "°C"), ("f", "°F"), ("k", "")])
def test_a_temperature_without_a_unit_follows_the_devices_own_setting(entity, setting, unit):
    temperature, _ = entity(HEAT_PUMP, "number.temp_set", temp_unit_convert=setting)
    assert (temperature.value, temperature.unit) == (28, unit)


@pytest.mark.parametrize(
    ("reported", "state"), [(True, "on"), (False, "off"), (None, None), ("some string", None)]
)
def test_a_switch_is_on_off_or_unknown(entity, reported, state):
    socket, _ = entity(SOCKET, "switch", switch=reported)
    assert socket.summary() == {"state": state}
