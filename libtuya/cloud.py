"""Smart Life / Tuya Smart account access.

Uses tuya-device-sharing-sdk, the same QR-code login Home Assistant uses, so no
Tuya developer account is needed. The cloud is only required to log in, to
list devices (with their local keys and datapoint maps) and as a fallback when
a device cannot be reached on the LAN.
"""

from __future__ import annotations

import copy
import json
import logging
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import requests
from tuya_sharing import (
    CustomerDevice,
    DeviceFunction,
    DeviceStatusRange,
    LoginControl,
    Manager,
    SharingTokenListener,
)
from tuya_sharing.exceptions import ApiRequestException, TuyaSDKException
from tuya_sharing.mq import SharingMQ

from .errors import CloudError

# The sharing API only accepts clients registered with Tuya. This is the one
# Tuya published for Home Assistant; the app's consent screen names it
# accordingly. There is no client secret.
CLIENT_ID = "HA_3y9q4ak7g4ephrvke"
SCHEMA = "haauthorize"
QR_PREFIX = "tuyaSmart--qrLogin?token="
# The `protocol` of a pushed message in which a device reports status.
REPORT = 4

_LOGGER = logging.getLogger(__name__)
# At DEBUG the SDK logs every decrypted response, tokens and local keys included.
logging.getLogger("tuya_sharing").setLevel(logging.WARNING)

Session = dict[str, Any]
# A device as stored in the cache: the cloud's fields in JSON form.
Record = dict[str, Any]


@dataclass(frozen=True)
class Scene:
    """A tap-to-run scene defined in the app."""

    id: str
    name: str
    home_id: str
    enabled: bool = True


@contextmanager
def _errors(action: str) -> Iterator[None]:
    try:
        yield
    except ApiRequestException as err:
        message = f"{action}: {err.error_message} ({err.error_code})"
        if "sign invalid" in str(err.error_message):
            # How a login that has expired, or been replaced by a newer one, shows up.
            message += "; the saved login is no longer valid, log in again"
        raise CloudError(message) from err
    except requests.RequestException as err:
        # Not the exception's own text: it quotes the URL, user code included.
        raise CloudError(f"{action}: cannot reach the Tuya cloud ({type(err).__name__})") from err
    except TuyaSDKException as err:
        raise CloudError(f"{action}: {err}") from err
    except (AttributeError, KeyError, TypeError) as err:
        # The SDK returns None for an HTTP error and then trips over it.
        raise CloudError(f"{action}: unexpected response from the Tuya cloud") from err


def request_qr(user_code: str) -> str:
    """Start a login; returns a token. Show ``QR_PREFIX + token`` as a QR code."""
    with _errors("login"):
        response = LoginControl().qr_code(CLIENT_ID, SCHEMA, user_code)
        if not response.get("success"):
            raise CloudError(
                f"login refused: {response.get('msg', 'unknown error')} "
                f"(code {response.get('code')}); check the user code"
            )
        return response["result"]["qrcode"]


def poll_login(user_code: str, token: str) -> tuple[Session | None, str]:
    """The session, once the QR code has been scanned and approved.

    Until then the session is None and the second item is what the cloud said.
    """
    with _errors("login"):
        authorised, info = LoginControl().login_result(token, CLIENT_ID, user_code)
        if not authorised:
            return None, f"{info.get('msg', 'no reason given')} (code {info.get('code')})"
        token_keys = ("t", "uid", "expire_time", "access_token", "refresh_token")
        session = {
            "user_code": user_code,
            "terminal_id": info["terminal_id"],
            "endpoint": info["endpoint"],
            # Kept exactly as sent: the SDK derives the expiry from `t` and `expire_time`.
            "token_info": {key: info[key] for key in token_keys},
        }
        return session, "approved"


class _TokenListener(SharingTokenListener):
    def __init__(self, session: Session, save: Callable[[Session], None]) -> None:
        self._session = session
        self._save = save

    def update_token(self, token_info: dict[str, Any]) -> None:
        # Refresh tokens are single-use, so a refreshed one must be stored at once.
        self._session["token_info"] = token_info
        self._save(self._session)


def _retrying(get: Callable[..., Any]) -> Callable[..., Any]:
    """Retry a GET the API rejected for no reason.

    The sharing API is reported to answer valid GETs at random with code 1108
    "uri path invalid" (tuya/tuya-device-sharing-sdk#77). Listing devices takes
    several GETs per device, so one such answer would otherwise fail it.
    """

    def get_with_retries(*args: Any, **kwargs: Any) -> Any:
        for _ in range(2):
            try:
                return get(*args, **kwargs)
            except ApiRequestException as err:
                if str(err.error_code) != "1108":
                    raise
                time.sleep(0.5)
        return get(*args, **kwargs)

    return get_with_retries


class Cloud:
    """A logged-in account."""

    def __init__(self, session: Session, save: Callable[[Session], None]) -> None:
        self._manager = Manager(
            CLIENT_ID,
            session["user_code"],
            session["terminal_id"],
            session["endpoint"],
            session["token_info"],
            _TokenListener(session, save),
        )
        self._manager.customer_api.get = _retrying(self._manager.customer_api.get)

    def devices(self) -> list[Record]:
        """Fetch every device of the account, with specs and datapoint maps."""
        with _errors("listing devices"):
            self._manager.update_device_cache()
            return [self._record(device) for device in self._manager.device_map.values()]

    def home_ids(self) -> list[str]:
        """The account's homes; scenes and push updates are organised by home."""
        with _errors("listing homes"):
            if not self._manager.user_homes:
                self._manager.user_homes = self._manager.home_repository.query_homes()
            return [str(home.id) for home in self._manager.user_homes]

    def status(self, device_id: str) -> Record | None:
        """One device's reachability and status by DP code, in a single request."""
        with _errors("querying device"):
            response = self._manager.customer_api.get(
                "/v1.0/m/life/ha/devices/detail", {"devIds": device_id}
            )
            for item in response.get("result") or ():
                status = {
                    entry["code"]: entry["value"]
                    for entry in item.get("status") or ()
                    if "code" in entry and "value" in entry
                }
                return {"online": item.get("online", True), "status": status}
        return None

    def scenes(self, home_ids: list[str]) -> list[Scene]:
        with _errors("listing scenes"):
            return [
                Scene(str(scene.scene_id), scene.name, str(scene.home_id), bool(scene.enabled))
                for scene in self._manager.scene_repository.query_scenes(home_ids)
            ]

    def run_scene(self, scene: Scene) -> None:
        with _errors("running scene"):
            self._manager.scene_repository.trigger_scene(scene.home_id, scene.id)

    def stream_url(self, device_id: str, kind: str) -> str:
        """A short-lived URL for a camera's live stream (rtsp, hls, flv or rtmp)."""
        with _errors("requesting stream"):
            url = self._manager.get_device_stream_allocate(device_id, kind)
        if not url:
            raise CloudError(f"the cloud offers no {kind} stream for this device")
        return url

    def listen(
        self,
        devices: list[tuple[str, bool]],
        home_ids: list[str],
        on_message: Callable[[dict[str, Any]], None],
    ) -> Callable[[], None]:
        """Open the push channel (MQTT) and return a function that closes it.

        `devices` pairs each device id with whether the cloud reports it by
        dp id rather than by code (the record's `support_local`). Messages are
        delivered on a background thread; the SDK reconnects by itself.
        """
        subscribed = [
            SimpleNamespace(id=dev_id, support_local=by_dp_id) for dev_id, by_dp_id in devices
        ]
        queue = SharingMQ(self._manager.customer_api, home_ids, subscribed)
        queue.daemon = True  # must not keep the program alive
        queue.add_message_listener(on_message)
        queue.start()
        return queue.stop

    def logout(self) -> None:
        """Revoke this login on the server."""
        with _errors("logging out"):
            self._manager.unload()

    def send(self, device_id: str, commands: list[dict[str, Any]]) -> None:
        # Posted directly: the SDK's own send_commands silently drops a command
        # that repeats the previous one within ten seconds.
        with _errors("sending command"):
            response = self._manager.customer_api.post(
                f"/v1.1/m/thing/{device_id}/commands", None, {"commands": commands}
            )
            if not response:  # what the SDK returns for an HTTP error
                raise CloudError("sending command: the Tuya cloud answered with an error")

    def _record(self, device: CustomerDevice) -> Record:
        record = dict(vars(device))
        record["function"] = {code: dict(vars(item)) for code, item in device.function.items()}
        record["status_range"] = {
            code: dict(vars(item)) for code, item in device.status_range.items()
        }
        record["local_strategy"] = device.local_strategy
        if not device.local_strategy:
            try:
                with _errors("fetching the datapoint map"):
                    record["local_strategy"] = self._local_strategy(device)
            except CloudError as err:  # the device then works through the cloud only
                _LOGGER.warning("%s: %s", device.name, err)
        return record

    def _local_strategy(self, device: CustomerDevice) -> dict[int, dict[str, Any]]:
        """Get the datapoint map for a device the SDK left without one.

        The SDK discards the whole map when a single datapoint cannot be pushed
        in dp-id form over MQTT, or when the device reports by code there.
        Neither matters on the LAN, so the datapoints that are usable locally,
        and whose code the device's own specification knows, are kept here.
        """
        response = self._manager.customer_api.get(f"/v1.0/m/life/devices/{device.id}/status")
        result = response.get("result") or {}
        known = device.function.keys() | device.status_range.keys()
        strategy = {}
        for relation in result.get("dpStatusRelationDTOS") or ():
            codes = {relation["statusCode"], *json.loads(relation["statusFormat"])}
            if relation.get("supportLocal") and codes & known:
                strategy[relation["dpId"]] = {
                    "value_convert": relation["valueConvert"],
                    "status_code": relation["statusCode"],
                    "config_item": {
                        "statusFormat": relation["statusFormat"],
                        "valueDesc": relation["valueDesc"],
                        "valueType": relation["valueType"],
                        "enumMappingMap": relation["enumMappingMap"],
                        "pid": result.get("productKey"),
                    },
                }
        return strategy


def load_device(record: Record) -> CustomerDevice:
    """Build the SDK's device object from a record, leaving the record untouched."""
    data = copy.deepcopy(record)
    device = CustomerDevice(**data)
    device.function = {code: DeviceFunction(**item) for code, item in data["function"].items()}
    device.status_range = {
        code: DeviceStatusRange(**item) for code, item in data["status_range"].items()
    }
    # JSON turns the datapoint ids into strings.
    device.local_strategy = {int(dp_id): item for dp_id, item in data["local_strategy"].items()}
    # The SDK's flag for "reports arrive by dp id". Product quirks add their
    # datapoint ids to the map only when it is set, and the LAN always speaks dp ids.
    device.support_local = True
    return device
