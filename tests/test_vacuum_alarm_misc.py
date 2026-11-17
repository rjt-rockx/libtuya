"""What vacuums, alarms, sirens, buttons, cameras and events send and show, as Home Assistant's
own tests (``tests/components/tuya/test_vacuum.py`` and so on) expect for the same devices."""

import base64

import pytest

from libtuya import TuyaError

HOOVER = "sd_i6hyjg3af7doaswm"  # goes home by a cleaning mode; no pause, no suction settings
V20 = "sd_lr33znaodtyarrrz"  # goes home by a switch of its own
ALARM = "mal_gyitctrjj1kefxp2"
C9 = "sp_sdd5f5f2dl5wydjf"  # a camera with a siren
BUROCAM = "sp_rudejjigkywujjvs"


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
        (HOOVER, "vacuum", "return_to_base", [], ("mode", "chargego")),
        (V20, "vacuum", "return_to_base", [], ("switch_charge", True)),
        (V20, "vacuum", "set_fan_speed", ["gentle"], ("suction", "gentle")),
        (HOOVER, "vacuum", "locate", [], ("seek", True)),
        (HOOVER, "vacuum", "start", [], ("power_go", True)),
        (HOOVER, "vacuum", "stop", [], ("power_go", False)),
        (V20, "vacuum", "pause", [], ("pause", True)),
        (ALARM, "alarm_control_panel", "arm_away", [], ("master_mode", "arm")),
        (ALARM, "alarm_control_panel", "arm_home", [], ("master_mode", "home")),
        (ALARM, "alarm_control_panel", "disarm", [], ("master_mode", "disarmed")),
        (ALARM, "alarm_control_panel", "trigger", [], ("master_mode", "sos")),
        (C9, "siren", "turn_on", [], ("siren_switch", True)),
        (C9, "siren", "turn_off", [], ("siren_switch", False)),
        (V20, "button.reset_duster_cloth", "press", [], ("reset_duster_cloth", True)),
        (BUROCAM, "camera", "enable_motion_detection", [], ("motion_switch", True)),
        (BUROCAM, "camera", "disable_motion_detection", [], ("motion_switch", False)),
    ],
)
def test_actions_send_what_home_assistant_sends(entity, name, ref, action, arguments, expected):
    target, sent = entity(name, ref)
    getattr(target, action)(*arguments)
    assert sent == [[expected]]


def test_what_a_device_cannot_do_is_refused(entity):
    hoover, sent = entity(HOOVER, "vacuum")
    with pytest.raises(TuyaError, match="Hoover cannot pause"):
        hoover.pause()
    with pytest.raises(TuyaError, match="no attribute 'fan_speed'"):
        hoover.set_fan_speed("strong")
    v20, v20_sent = entity(V20, "vacuum")
    with pytest.raises(ValueError, match="must be one of"):
        v20.set_fan_speed("turbo")
    assert sent == v20_sent == []


def test_what_is_shown_follows_the_device(entity):
    camera, _ = entity(BUROCAM, "camera")
    assert camera.summary() == {"state": "recording", "motion_detection": True}
    camera.device.status.update(motion_switch=False, record_switch=False)
    assert camera.summary() == {"state": "idle"}
    assert entity(C9, "siren", siren_switch=True)[0].summary() == {"state": "on"}
    vacuum, _ = entity(V20, "vacuum", status="goto_charge", suction="gentle")
    assert (vacuum.activity, vacuum.fan_speed) == ("returning", "gentle")


def test_a_sensor_sets_an_armed_alarm_off_but_its_low_battery_does_not(entity):
    alarm, _ = entity(ALARM, "alarm_control_panel", master_mode="home", master_state="alarm")
    for said, state in (("Test Sensor", "triggered"), ("Sensor Low Battery Test", "armed_home")):
        alarm.device.status["alarm_msg"] = base64.b64encode(said.encode("utf-16be")).decode()
        assert alarm.summary() == {"state": state, "changed_by": said}


def test_a_doorbell_ring_comes_with_its_picture(entity):
    picture = "https://some-picture-url.com/image.jpg"
    ring, _ = entity("sp_csr2fqitalj5o0tq", "event.doorbell_pic", doorbell_pic=None)
    assert ring.summary() == {"event_type": None, "event_types": ["triggered"]}
    ring.device.status["doorbell_pic"] = base64.b64encode(picture.encode()).decode()
    assert (ring.event_type, ring.event_attributes) == ("triggered", {"message": picture})
