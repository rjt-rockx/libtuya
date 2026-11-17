"""What a light sends when it is turned on.

The commands in the first test are the ones Home Assistant expects for the
same actions on the same devices (``test_action`` in its
``tests/components/tuya/test_light.py``); brightness 0 is its light service's
way of turning a light off.
"""

import pytest

from libtuya import TuyaError

GARAGE = "dj_mki13ie507rlry4r"  # colour and plain white; on, white, brightness 138
TUNABLE = "dj_ilddqqih3tucdk68"  # white of adjustable temperature, no colour
ON = {"code": "switch_led", "value": True}
WHITE = {"code": "work_mode", "value": "white"}
COLOUR = {"code": "work_mode", "value": "colour"}


def level(raw):
    return {"code": "bright_value_v2", "value": raw}


def colour(h, s, v):
    return {"code": "colour_data_v2", "value": f'{{"h": {h}, "s": {s}, "v": {v}}}'}


@pytest.fixture
def light(make_device, monkeypatch):
    """Build a fixture's light; returns it with the list of its calls to `Device.send`."""

    def build(name, entity="light.switch_led", **status):
        device = make_device(name)
        device.status.update(status)
        sent = []
        monkeypatch.setattr(device, "send", sent.append)
        return device.entity(entity), sent

    return build


@pytest.mark.parametrize(
    ("name", "arguments", "expected"),
    [
        (GARAGE, {"white": True}, [ON, WHITE, level(546)]),
        (GARAGE, {"brightness": 150}, [ON, level(592)]),
        (GARAGE, {"brightness": 0}, [{"code": "switch_led", "value": False}]),
        (GARAGE, {"white": True, "brightness": 150}, [ON, WHITE, level(592)]),
        (GARAGE, {"brightness": 255, "hs": (10.1, 20.2)}, [ON, COLOUR, colour(10, 202, 1000)]),
        (
            TUNABLE,
            {"brightness": 255, "kelvin": 5000},
            [ON, {"code": "temp_value", "value": 221}, {"code": "bright_value", "value": 255}],
        ),
    ],
)
def test_turn_on_sends_what_home_assistant_sends(light, name, arguments, expected):
    entity, sent = light(name)
    entity.turn_on(**arguments)
    assert sent == [expected]


def test_brightness_belongs_to_whatever_is_showing(light):
    """Dimming changes the white channel in white mode (above), the colour in colour mode."""
    entity, sent = light(GARAGE, work_mode="colour")
    assert (entity.color_mode, entity.brightness) == ("hs", 138)
    entity.turn_on(brightness=150)
    assert sent == [[ON, COLOUR, colour(243, 860, 588)]]
    # ... and a colour asked for in white mode takes over the white's brightness.
    entity, sent = light(GARAGE)
    entity.turn_on(hs=(120, 100))
    assert sent == [[ON, COLOUR, colour(120, 1000, 541)]]


def test_a_light_says_why_it_refuses_and_sends_nothing(light):
    garage, sent = light(GARAGE)
    with pytest.raises(TuyaError, match="no adjustable colour temperature"):
        garage.turn_on(kelvin=3000)
    with pytest.raises(ValueError, match="only one of"):
        garage.turn_on(hs=(0, 100), white=True)
    with pytest.raises(ValueError, match="level as brightness"):
        garage.turn_on(white=150)  # Home Assistant's other way to say white=True, brightness=150
    with pytest.raises(ValueError, match="hue 0-360"):
        garage.turn_on(hs=(120, 50, 200))
    assert sent == []
    with pytest.raises(TuyaError, match="no plain white mode"):
        light(TUNABLE)[0].turn_on(white=True)
    with pytest.raises(TuyaError, match="no adjustable brightness"):
        light("clkg_nhyj64w2", "light.switch_backlight")[0].turn_on(brightness=100)
