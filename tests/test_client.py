"""Login, the device list and its cache, with the cloud SDK's network layer replaced."""

import json
import stat

import pytest
from conftest import record
from tuya_sharing import CustomerDevice, DeviceFunction, DeviceStatusRange
from tuya_sharing.exceptions import ApiRequestException

from libtuya import DeviceNotFound, NotLoggedIn, Tuya
from libtuya import client as client_module
from libtuya import cloud as cloud_module
from libtuya.lan import LanAddress

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
    def __init__(self):
        self.posted = []
        self.rejections = 1

    def get(self, path, params=None):
        if self.rejections:  # the real API turns down a valid request now and then
            self.rejections -= 1
            raise ApiRequestException(error_code=1108, error_message="uri path invalid")
        # What /status returns for the plug; one datapoint is not usable locally.
        assert path == "/v1.0/m/life/devices/znjdq_au6dqazvkxqnpaak/status"
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


class FakeManager:
    """Stands in for tuya_sharing.Manager."""

    def __init__(self, client_id, user_code, terminal_id, endpoint, token_info, listener):
        self.token_info, self.listener = token_info, listener
        self.customer_api = FakeApi()
        self.device_map = {}

    def update_device_cache(self):
        self.listener.update_token(NEW_TOKEN)  # the SDK refreshes tokens as a side effect
        for device in (
            sdk_device("dj_k3okx0w3bsgmindp", keep_map=True),
            sdk_device("znjdq_au6dqazvkxqnpaak", keep_map=False),
        ):
            self.device_map[device.id] = device


@pytest.fixture
def logged_in(tuya: Tuya, monkeypatch) -> Tuya:
    tuya._write("session.json", SESSION)
    monkeypatch.setattr(cloud_module, "Manager", FakeManager)
    monkeypatch.setattr(cloud_module.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        client_module,
        "discover",
        lambda keys, timeout: {"dj_k3okx0w3bsgmindp": LanAddress("192.168.1.20", "3.4")},
    )
    return tuya


def test_login_stores_the_session_as_the_cloud_gave_it(tuya: Tuya, monkeypatch):
    answers = iter([(False, {"msg": "not scanned yet"}), (True, {**SESSION, **NEW_TOKEN})])

    class FakeLoginControl:
        def qr_code(self, client_id, schema, user_code):
            return {"success": True, "result": {"qrcode": "token123"}}

        def login_result(self, token, client_id, user_code):
            return next(answers)

    monkeypatch.setattr(cloud_module, "LoginControl", FakeLoginControl)
    shown = []
    assert not tuya.logged_in
    tuya.login("code", shown.append, interval=0)

    assert shown == ["tuyaSmart--qrLogin?token=token123"]
    assert tuya.logged_in
    # `t` and `expire_time` must reach the SDK untouched: it derives the
    # expiry from them, and a converted value stops tokens being refreshed.
    saved = json.loads((tuya.home / "session.json").read_text())
    assert saved == SESSION | {"token_info": NEW_TOKEN}


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
    # keeps only what can be used locally.
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
    assert logged_in.device("1") is bulb
    assert logged_in.device(plug.id) is plug
    assert logged_in.device("smart circuit breaker") is plug
    assert logged_in.device("carro") is bulb
    with pytest.raises(DeviceNotFound, match="several"):
        logged_in.device("a")
    with pytest.raises(DeviceNotFound, match="no device"):
        logged_in.device("toaster")
