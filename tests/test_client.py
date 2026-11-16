"""The account side: login, the device list and its cache, scenes, cloud push and fallback.

The cloud SDK's network layer is replaced; everything above it is real.
"""

import json
import stat
from types import SimpleNamespace

import pytest
from conftest import record
from tuya_sharing import CustomerDevice, DeviceFunction, DeviceStatusRange
from tuya_sharing.exceptions import ApiRequestException

from libtuya import CloudError, DeviceNotFound, NotLoggedIn, Scene, Tuya
from libtuya import client as client_module
from libtuya import cloud as cloud_module
from libtuya.lan import LanAddress

BULB = "dj_k3okx0w3bsgmindp"
PLUG = "znjdq_au6dqazvkxqnpaak"
SESSION = {
    "user_code": "code",
    "terminal_id": "terminal",
    "endpoint": "https://example.invalid",
    "token_info": {
        "t": 1,
        "uid": "u",
        "expire_time": 7200,
        "access_token": "a",
        "refresh_token": "r",
    },
}
NEW_TOKEN = {**SESSION["token_info"], "access_token": "a2", "refresh_token": "r2"}


def sdk_device(name: str, keep_map: bool) -> CustomerDevice:
    """A device as the SDK builds it, optionally without its datapoint map."""
    data = record(name)
    device = CustomerDevice(**{k: v for k, v in data.items() if k != "local_strategy"})
    device.function = {code: DeviceFunction(**item) for code, item in data["function"].items()}
    device.status_range = {
        code: DeviceStatusRange(**item) for code, item in data["status_range"].items()
    }
    if keep_map:
        device.local_strategy = {int(dp): item for dp, item in data["local_strategy"].items()}
    return device


class FakeApi:
    """Stands in for the SDK's signed HTTP client."""

    def __init__(self):
        self.posted = []
        self.rejections = 1
        self.post_answer = {"success": True}

    def get(self, path, params=None):
        if self.rejections:  # the real API turns down a valid request now and then
            self.rejections -= 1
            raise ApiRequestException(error_code=1108, error_message="uri path invalid")
        if path == "/v1.0/m/life/ha/devices/detail":
            status = [{"code": "switch_1", "value": True}, {"code": "cur_power", "value": 999}]
            return {"success": True, "result": [{"online": False, "status": status}]}
        # What /status returns for the plug; one datapoint is not usable locally.
        assert path == f"/v1.0/m/life/devices/{PLUG}/status"
        relation = {
            "valueConvert": "default",
            "valueType": "Boolean",
            "valueDesc": "{}",
            "enumMappingMap": {},
        }
        return {
            "success": True,
            "result": {
                "productKey": "au6dqazvkxqnpaak",
                "dpStatusRelationDTOS": [
                    relation
                    | {
                        "dpId": 1,
                        "statusCode": "switch_1",
                        "statusFormat": '{"switch_1":"$"}',
                        "supportLocal": True,
                    },
                    relation
                    | {
                        "dpId": 41,
                        "statusCode": "child_lock",
                        "statusFormat": '{"child_lock":"$"}',
                        "supportLocal": False,
                    },
                ],
            },
        }

    def post(self, path, params=None, body=None):
        self.posted.append((path, body))
        return self.post_answer


class FakeManager:
    """Stands in for tuya_sharing.Manager."""

    def __init__(self, client_id, user_code, terminal_id, endpoint, token_info, listener):
        self.listener = listener
        self.customer_api = FakeApi()
        self.device_map = {}
        self.user_homes = []
        self.triggered = []
        home = SimpleNamespace(id=7, name="Home")
        scene = SimpleNamespace(scene_id="s1", name="Movie night", home_id="7", enabled=True)
        self.home_repository = SimpleNamespace(query_homes=lambda: [home])
        self.scene_repository = SimpleNamespace(
            query_scenes=lambda home_ids: [scene] if home_ids == ["7"] else [],
            trigger_scene=lambda home_id, scene_id: self.triggered.append((home_id, scene_id)),
        )

    def update_device_cache(self):
        self.listener.update_token(NEW_TOKEN)  # the SDK refreshes tokens as a side effect
        self.user_homes = self.home_repository.query_homes()
        for device in (sdk_device(BULB, keep_map=True), sdk_device(PLUG, keep_map=False)):
            self.device_map[device.id] = device


class FakeQueue:
    """Stands in for the SDK's MQTT client; the test plays the broker."""

    def __init__(self, api, home_ids, devices):
        FakeQueue.opened = self
        self.home_ids, self.devices, self.running = home_ids, devices, False

    def add_message_listener(self, listener):
        self.deliver = listener

    def start(self):
        self.running = True

    def stop(self):
        self.running = False


@pytest.fixture
def logged_in(tuya: Tuya, monkeypatch) -> Tuya:
    tuya._write("session.json", SESSION)
    monkeypatch.setattr(cloud_module, "Manager", FakeManager)
    monkeypatch.setattr(cloud_module, "SharingMQ", FakeQueue)
    monkeypatch.setattr(cloud_module.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        client_module, "discover", lambda keys, timeout: {BULB: LanAddress("192.168.1.20", "3.4")}
    )
    return tuya


def test_login_stores_the_session_as_the_cloud_gave_it(tuya: Tuya, monkeypatch):
    answers = iter(
        [
            (False, {"msg": "not scanned yet", "code": 1}),
            ConnectionError("a network blip"),
            (True, {**SESSION, **NEW_TOKEN}),
        ]
    )

    class FakeLoginControl:
        def qr_code(self, client_id, schema, user_code):
            return {"success": True, "result": {"qrcode": "token123"}}

        def login_result(self, token, client_id, user_code):
            if isinstance(answer := next(answers), Exception):
                raise cloud_module.requests.ConnectionError(answer)
            return answer

    monkeypatch.setattr(cloud_module, "LoginControl", FakeLoginControl)
    shown = []
    assert not tuya.logged_in
    tuya.login("code", shown.append, interval=0)

    assert shown == ["tuyaSmart--qrLogin?token=token123"]
    assert tuya.logged_in
    # `t` and `expire_time` must reach the SDK untouched: it derives the
    # expiry from them, and a converted value stops tokens being refreshed.
    saved = json.loads((tuya.home / "session.json").read_text())
    assert saved == SESSION | {"token_info": NEW_TOKEN, "client_id": cloud_module.CLIENT_ID}

    monkeypatch.setattr(
        FakeLoginControl, "login_result", lambda *args: (False, {"msg": "expired", "code": 9})
    )
    with pytest.raises(CloudError, match=r"expired \(code 9\)"):  # says why, not just "timeout"
        tuya.login("code", shown.append, timeout=0.01, interval=0)


def test_devices_need_a_login(tuya: Tuya):
    with pytest.raises(NotLoggedIn):
        tuya.devices()


def test_devices_are_fetched_once_then_served_from_the_cache(logged_in: Tuya, monkeypatch):
    bulb, plug = logged_in.devices()
    assert (bulb.name, bulb.address) == (
        "Portal Casa Carro Jalimy",
        LanAddress("192.168.1.20", "3.4"),
    )
    assert plug.address is None  # did not answer the scan
    # The SDK had no datapoint map for the plug; the one fetched directly
    # (at the second attempt) keeps only what can be used locally.
    assert plug.dp_map.dp_ids == [1]

    for name in ("session.json", "devices.json"):  # tokens and local keys
        assert stat.S_IMODE((logged_in.home / name).stat().st_mode) == 0o600
    assert json.loads((logged_in.home / "session.json").read_text())["token_info"] == NEW_TOKEN

    monkeypatch.setattr(cloud_module, "Manager", None)  # any cloud use would now fail
    again = Tuya(logged_in.home).devices()
    assert [(d.id, d.address, d.dp_map.dp_ids) for d in again] == [
        (d.id, d.address, d.dp_map.dp_ids) for d in (bulb, plug)
    ]
    assert [entity.id for entity in again[1].entities] == [entity.id for entity in plug.entities]


def test_a_refresh_keeps_addresses_of_devices_that_stay_silent(logged_in: Tuya, monkeypatch):
    logged_in.devices()
    monkeypatch.setattr(client_module, "discover", lambda keys, timeout: {})
    bulb, _ = logged_in.devices(refresh=True)
    assert bulb.address == LanAddress("192.168.1.20", "3.4")


def test_finding_a_device(logged_in: Tuya):
    bulb, plug = logged_in.devices()
    assert logged_in.device(1) is logged_in.device("1") is bulb
    assert logged_in.device(plug.id) is plug
    assert logged_in.device("smart circuit breaker") is plug
    assert logged_in.device("carro") is bulb
    with pytest.raises(DeviceNotFound, match="several"):
        logged_in.device("a")
    with pytest.raises(DeviceNotFound, match="no device"):
        logged_in.device("toaster")


def test_the_cloud_serves_a_device_the_lan_cannot_reach(logged_in: Tuya):
    _, plug = logged_in.devices()  # the plug has no LAN address
    api = logged_in.cloud._manager.customer_api

    plug.refresh()
    assert (plug.transport, plug.online) == ("cloud", False)
    assert plug.entity("sensor.cur_power").value == 99.9

    plug.turn_off()
    command = {"commands": [{"code": "switch_1", "value": False}]}
    assert api.posted == [(f"/v1.1/m/thing/{PLUG}/commands", command)]

    api.post_answer = None  # what the SDK returns when the server answers with an HTTP error
    with pytest.raises(CloudError):
        plug.turn_on()
    assert plug.status["switch_1"] is False  # and nothing was assumed


def test_scenes(logged_in: Tuya):
    scenes = logged_in.scenes()
    assert scenes == [Scene(id="s1", name="Movie night", home_id="7")]
    logged_in.run_scene("Movie night")
    logged_in.run_scene(scenes[0])
    assert logged_in.cloud._manager.triggered == [("7", "s1")] * 2


def test_cloud_push_reaches_subscribers(logged_in: Tuya):
    bulb, plug = logged_in.devices()
    seen = []
    stop = logged_in.subscribe(lambda device, changed: seen.append((device.name, changed)))
    queue = FakeQueue.opened
    assert queue.running and queue.home_ids == ["7"]

    # Reports come by datapoint id with raw values, or by code, depending on the device.
    report = {"devId": BULB, "status": [{"dpId": 24, "value": "007803e801f4", "t": 1}]}
    queue.deliver({"protocol": 4, "data": report})
    report = {"devId": PLUG, "status": [{"code": "switch_1", "value": True, "t": 2}]}
    queue.deliver({"protocol": 4, "data": report})
    queue.deliver({"protocol": 20, "data": {"bizCode": "offline", "bizData": {"devId": PLUG}}})
    queue.deliver({"protocol": 4, "data": {"devId": "someone else's", "status": []}})

    assert seen == [
        (bulb.name, {"colour_data_v2": '{"h": 120, "s": 1000, "v": 500}'}),
        (plug.name, {"switch_1": True}),
        (plug.name, {}),
    ]
    assert bulb.entity("light").state()["color_data"] == pytest.approx((120, 100, 127.5))
    assert (plug.status["switch_1"], plug.online) == (True, False)
    stop()
    assert not queue.running


def test_a_login_renewed_by_another_process_is_picked_up(logged_in: Tuya, monkeypatch):
    """Refresh tokens are single-use, so two processes sharing a home can leave one stale."""
    _, plug = logged_in.devices()

    def refuse(*args):
        raise ApiRequestException(error_code=-9999999, error_message="sign invalid")

    logged_in.cloud._manager.customer_api.post = refuse  # this process's login has gone stale
    plug.turn_off()  # ... so the saved session is read again, and that one works
    assert logged_in.cloud._manager.customer_api.posted

    monkeypatch.setattr(FakeApi, "post", refuse)  # nothing newer was saved
    with pytest.raises(NotLoggedIn, match="no longer valid"):
        plug.turn_on()
