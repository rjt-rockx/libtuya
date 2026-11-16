"""Smart Life / Tuya Smart account access.

Uses tuya-device-sharing-sdk, the same QR-code login Home Assistant uses, so no
Tuya developer account is needed. The cloud is only required to log in, to
list devices (with their local keys and datapoint maps) and as a fallback when
a device cannot be reached on the LAN.
"""

from __future__ import annotations

import copy
import logging
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
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

from .errors import CloudError

# The sharing API only accepts clients registered with Tuya. This is the one
# registered for Home Assistant; the app's consent screen names it accordingly.
CLIENT_ID = "HA_3y9q4ak7g4ephrvke"
SCHEMA = "haauthorize"
QR_PREFIX = "tuyaSmart--qrLogin?token="

_LOGGER = logging.getLogger(__name__)

Session = dict[str, Any]
# A device as stored in the cache: the cloud's fields in JSON form.
Record = dict[str, Any]


@contextmanager
def _errors(action: str) -> Iterator[None]:
    try:
        yield
    except ApiRequestException as err:
        raise CloudError(f"{action}: {err.error_message} ({err.error_code})") from err
    except (TuyaSDKException, requests.RequestException) as err:
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


def poll_login(user_code: str, token: str) -> Session | None:
    """Return the session once the QR code has been scanned and approved."""
    with _errors("login"):
        authorised, info = LoginControl().login_result(token, CLIENT_ID, user_code)
        if not authorised:
            return None
        return {
            "user_code": user_code,
            "terminal_id": info["terminal_id"],
            "endpoint": info["endpoint"],
            "token_info": {
                key: info[key]
                for key in ("t", "uid", "expire_time", "access_token", "refresh_token")
            },
        }


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

    Since autumn 2026 the sharing API answers roughly one valid GET in twenty
    with code 1108 "uri path invalid" (tuya/tuya-device-sharing-sdk#77), and
    listing devices takes several GETs per device.
    """

    def get_with_retries(path: str, params: dict[str, Any] | None = None) -> Any:
        for _ in range(2):
            try:
                return get(path, params)
            except ApiRequestException as err:
                if str(err.error_code) != "1108":
                    raise
                time.sleep(0.5)
        return get(path, params)

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

    def device(self, device_id: str) -> Record | None:
        """Fetch one device again, e.g. for its current status."""
        with _errors("querying device"):
            found = self._manager.device_repository.query_devices_by_ids([device_id])
            return self._record(found[0]) if found else None

    def logout(self) -> None:
        """Revoke this login on the server."""
        with _errors("logging out"):
            self._manager.unload()

    def send(self, device_id: str, commands: list[dict[str, Any]]) -> None:
        # Posted directly: the SDK's own send_commands silently drops a command
        # that repeats the previous one within ten seconds.
        with _errors("sending command"):
            self._manager.customer_api.post(
                f"/v1.1/m/thing/{device_id}/commands", None, {"commands": commands}
            )

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
                    record["local_strategy"] = self._local_strategy(device.id)
            except CloudError as err:  # the device then works through the cloud only
                _LOGGER.warning("%s: %s", device.name, err)
        return record

    def _local_strategy(self, device_id: str) -> dict[int, dict[str, Any]]:
        """Get the datapoint map for a device the SDK left without one.

        The SDK discards the whole map when a single datapoint cannot be
        pushed in dp-id form over MQTT. That has no bearing on the LAN, so the
        datapoints that can are kept here.
        """
        response = self._manager.customer_api.get(f"/v1.0/m/life/devices/{device_id}/status")
        result = response.get("result") or {}
        return {
            relation["dpId"]: {
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
            for relation in result.get("dpStatusRelationDTOS") or ()
            if relation.get("supportLocal")
        }


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
    # The SDK's flag for "this map is usable"; product quirks only add their
    # datapoints to the map when it is set.
    device.support_local = bool(device.local_strategy)
    return device
