"""End to end: libtuya -> TinyTuya -> TCP -> a fake device speaking the real LAN protocol.

The devices are real ones from Home Assistant's fixtures, with the datapoint
maps their owners' accounts reported.
"""

import json
import socket
import threading

import pytest
import tinytuya
from conftest import fake, local_key, record
from fake_device import FakeTuyaDevice

from libtuya import Device, LanError, Tuya
from libtuya import client as client_module
from libtuya import lan as lan_module
from libtuya.lan import LanAddress, discover

BULB = "dj_k3okx0w3bsgmindp"  # RGB+white bulb: dps 20 switch, 21 mode, 22 brightness, 24 colour
PLUG = "znjdq_au6dqazvkxqnpaak"  # metering plug: dps 1 switch, 17 energy, 19 power, 41 child lock
GATEWAY = "wfcon_b25mh8sxawsgndck"
BULB_DPS = {"20": False, "21": "white", "22": 500, "23": 1000, "24": "000003e803e8"}
PLUG_DPS = {"1": False, "17": 3, "18": 258, "19": 143, "20": 2286, "38": "memory", "41": False}


class StubCloud:
    """Records what would have gone to the cloud."""

    def __init__(self):
        self.sent = []

    def send(self, device_id, commands):
        self.sent.append((device_id, commands))

    def status(self, device_id):
        return {"online": True, "status": record(device_id)["status"]}


@pytest.fixture(params=["3.3", "3.4", "3.5"])
def bulb(make_device, request):
    version = request.param
    with fake(BULB, version, BULB_DPS) as device:
        yield make_device(BULB, LanAddress("127.0.0.1", version, device.port)), device


@pytest.fixture
def plug(make_device):
    with fake(PLUG, "3.4", PLUG_DPS) as device:
        yield make_device(PLUG, LanAddress("127.0.0.1", "3.4", device.port)), device


def test_a_light_on_every_protocol_version(bulb):
    device, on_the_wire = bulb
    light = device.entity("light")

    assert device.refresh()["bright_value_v2"] == 500
    assert device.transport == "lan"
    assert light.state()["switch"] is False

    light.turn_on(brightness=128, hs_color=(120, 100))

    # One frame, in the device's own terms: on, colour mode, HSV as hex.
    assert len(on_the_wire.received) == 1
    dps = on_the_wire.dps
    assert (dps["20"], dps["21"], dps["24"]) == (True, "colour", "007803e801f6")
    # ... and the entity reflects it without another read.
    assert light.in_color_mode
    assert light.brightness == 128
    assert light.state()["color_data"] == pytest.approx((120, 100, 128), abs=0.1)


def test_switching_and_reading_a_plug(plug):
    device, on_the_wire = plug
    device.turn_on()
    assert on_the_wire.dps["1"] is True
    device.toggle()
    assert on_the_wire.dps["1"] is False

    on_the_wire.dps["19"] = 1270
    device.refresh()
    power = device.entity("sensor.cur_power")
    assert (power.value, power.wrappers["sensor"].native_unit) == (127.0, "W")

    device.set_raw(child_lock=True)  # a DP code, unscaled
    assert on_the_wire.dps["41"] is True


def test_the_cloud_takes_over_when_the_lan_cannot(bulb, tuya):
    device, on_the_wire = bulb
    tuya._cloud = cloud = StubCloud()

    # A scene has no exact LAN form, so it goes through the cloud ...
    device.set_raw(scene_data_v2='{"scene_num": 2}')
    assert cloud.sent == [(BULB, [{"code": "scene_data_v2", "value": '{"scene_num": 2}'}])]
    assert (device.transport, on_the_wire.received) == ("cloud", [])

    # ... and so does everything once the device stops answering.
    on_the_wire.stop()
    device.turn_on()
    assert cloud.sent[-1] == (BULB, [{"code": "switch_led", "value": True}])
    assert device.status["switch_led"] is True

    tuya.cloud_fallback = False
    with pytest.raises(LanError):
        device.turn_off()


@pytest.mark.parametrize("version", ["3.3", "3.4", "3.5"])
@pytest.mark.parametrize("code", [1, 16777216])
def test_an_acknowledgement_code_is_not_a_refusal(make_device, tuya, version, code):
    """TuyaOpen's device code acknowledges every command with code 1, carried out or not."""
    tuya._cloud = cloud = StubCloud()
    with fake(PLUG, version, PLUG_DPS, ack_code=code) as on_the_wire:
        device = make_device(PLUG, LanAddress("127.0.0.1", version, on_the_wire.port))
        device.set_raw(switch_1=True)
        assert (device.transport, len(on_the_wire.received), cloud.sent) == ("lan", 1, [])

        tuya.cloud_fallback = False
        device.set_raw(switch_1=False)
        assert on_the_wire.dps["1"] is False


def test_an_answer_without_any_status_is_not_taken_for_one(make_device, tuya):
    tuya._cloud = StubCloud()
    with fake(PLUG, "3.3", {}) as on_the_wire:
        device = make_device(PLUG, LanAddress("127.0.0.1", "3.3", on_the_wire.port))
        device.refresh()
        assert device.transport == "cloud"


def test_a_command_nobody_acknowledged_is_sent_once(make_device, tuya, monkeypatch):
    """Neither TinyTuya's retries, nor a new address, nor the cloud may repeat it: it could be
    "feed the cat"."""
    tuya.timeout = 0.3
    tuya._cloud = cloud = StubCloud()
    received = []

    def swallow(server: socket.socket) -> None:
        try:
            while True:
                connection, _ = server.accept()
                with connection:
                    while data := connection.recv(4096):
                        received.append(data)
        except OSError:
            pass  # the server was closed

    with socket.create_server(("127.0.0.1", 0)) as server, fake(PLUG, "3.3") as elsewhere:
        threading.Thread(target=swallow, args=(server,), daemon=True).start()
        device = make_device(PLUG, LanAddress("127.0.0.1", "3.3", server.getsockname()[1]))
        moved = LanAddress("127.0.0.1", "3.3", elsewhere.port)
        monkeypatch.setattr(client_module, "discover", lambda keys, timeout: {PLUG: moved})
        with pytest.raises(LanError, match="may or may not"):
            device.turn_on()
    assert b"".join(received).count(bytes.fromhex("000055aa")) == 1
    assert elsewhere.received == [] and cloud.sent == []


def test_a_wrong_local_key_is_reported(make_device, tuya):
    tuya.cloud_fallback = False
    with fake(BULB, "3.4", BULB_DPS) as on_the_wire:  # the bulb's key, not the plug's
        device = make_device(PLUG, LanAddress("127.0.0.1", "3.4", on_the_wire.port))
        with pytest.raises(LanError) as error:
            device.refresh()
        assert error.value.code == "914"


def test_a_device_with_a_new_address_is_found_again(make_device, tuya, monkeypatch):
    with socket.create_server(("127.0.0.1", 0)) as unused:
        stale = LanAddress("127.0.0.1", "3.3", unused.getsockname()[1])
    with fake(PLUG, "3.3", PLUG_DPS) as on_the_wire:
        device = make_device(PLUG, stale)
        current = LanAddress("127.0.0.1", "3.3", on_the_wire.port)
        monkeypatch.setattr(client_module, "discover", lambda keys, timeout: {PLUG: current})

        assert device.refresh()["cur_power"] == 143
        assert (device.transport, device.address) == ("lan", current)
        assert Tuya(tuya.home).device(PLUG).address == current  # and it was saved


def test_watching_pushes(plug):
    device, on_the_wire = plug
    energy = device.entity("sensor.add_ele")
    assert energy.value is None  # the plug reports increments; no total without following them

    changes = device.watch()
    assert next(changes)["switch_1"] is False  # starts with the full status
    on_the_wire.push({"1": True})  # someone presses the button
    assert next(changes) == {"switch_1": True}
    on_the_wire.push({"17": 7})
    on_the_wire.push({"17": 5})
    assert [next(changes), next(changes)] == [{"add_ele": 7}, {"add_ele": 5}]
    assert energy.value == pytest.approx(0.012)  # kWh
    changes.close()


def test_watching_re_reads_report_only_what_changed(plug, monkeypatch):
    device, on_the_wire = plug
    monkeypatch.setattr(lan_module, "FULL_STATUS_INTERVAL", 0)  # re-read on every pass
    changes = device.watch()
    assert len(next(changes)) > 1  # the full status first
    on_the_wire.dps["1"] = True  # changed without a push: only a re-read sees it
    assert next(changes) == {"switch_1": True}
    changes.close()


def test_a_sub_device_is_reached_through_its_gateway(make_device, tuya):
    with fake(GATEWAY, "3.4", cids={"node-1": dict(PLUG_DPS)}) as on_the_wire:
        gateway = make_device(GATEWAY, LanAddress("127.0.0.1", "3.4", on_the_wire.port))
        # A sub-device has its gateway's key and no address of its own.
        child = make_device(PLUG, local_key=local_key(GATEWAY), node_id="node-1")
        assert tuya.gateway_of(child) is gateway

        assert child.refresh()["cur_power"] == 143
        child.turn_on()
        assert on_the_wire.cids["node-1"]["1"] is True
        assert child.transport == "lan"


def test_discovery_reads_device_broadcasts():
    """The real scanner, fed the datagram a protocol 3.4 device broadcasts."""
    body = json.dumps({"ip": "127.0.0.1", "gwId": PLUG, "version": "3.4", "encrypt": True})
    payload = b"\x00" * 4 + tinytuya.encrypt(body.encode(), tinytuya.udpkey)
    message = tinytuya.TuyaMessage(
        0, tinytuya.UDP_NEW, 0, payload, 0, True, tinytuya.PREFIX_55AA_VALUE, False
    )
    datagram = tinytuya.pack_message(message)
    found_it = threading.Event()

    def announce() -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
            while not found_it.wait(0.2):
                udp.sendto(datagram, ("127.0.0.1", 6667))

    announcer = threading.Thread(target=announce, daemon=True)
    announcer.start()
    try:
        found = discover({PLUG: local_key(PLUG)}, timeout=5)
    except LanError as err:
        pytest.skip(f"cannot listen for broadcasts here: {err}")
    finally:
        found_it.set()
        announcer.join()
    assert found == {PLUG: LanAddress("127.0.0.1", "3.4")}


def test_a_hub_without_a_key_of_its_own(tuya):
    """Some hubs come without a local key; their sub-devices carry the one the hub answers to."""
    hub_record = record(GATEWAY)
    del hub_record["local_key"]
    key = local_key(PLUG)
    with FakeTuyaDevice(GATEWAY, key, "3.4", cids={"node-1": dict(PLUG_DPS)}) as on_the_wire:
        hub = Device(tuya, hub_record, LanAddress("127.0.0.1", "3.4", on_the_wire.port))
        child = Device(tuya, record(PLUG, node_id="node-1"))
        tuya._devices = [hub, child]
        assert tuya.gateway_of(child) is hub

        child.turn_on()
        assert on_the_wire.cids["node-1"]["1"] is True
        assert tuya.scan() == {}  # and a device without a key does not upset a scan


def test_a_product_fix_can_supply_the_datapoint_map(make_device):
    """The cloud gives no map for this meter; tuya-device-handlers knows its datapoints."""
    assert not record("cz_dhto3y4uachr1wll")["local_strategy"]
    assert make_device("cz_dhto3y4uachr1wll").dp_map.dp_ids
