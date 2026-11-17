"""Tuya IoT Platform developer account ("cloud project") access.

The other way in besides the QR login of cloud.py: a cloud project on
iot.tuya.com with the user's Smart Life or Tuya Smart account linked to it, as
TinyTuya's wizard sets it up. TinyTuya's Cloud class signs the requests and
keeps the token. It sends them without a timeout, so a stalled connection
blocks the call.

The cloud is asked in the standard instruction set, the vocabulary the QR login
delivers too, so a record looks the same to everything above this module. What
this API does not tell is how that vocabulary relates to a device's own
datapoints on the LAN. A datapoint is therefore mapped for LAN use only where
the device's own description (its "thing model") shows the same type and range,
or where it is a colour in one of the two encodings the sharing SDK defines.
The other datapoints are written through the cloud, and read from the cloud
when the device list is refreshed or the LAN fails; while the LAN answers they
are not read again. Products switched to "DP instruction" mode in the console
are not supported: the standard instruction set is what everything here expects.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from collections.abc import Callable, Collection
from typing import Any
from urllib.parse import urlsplit

import requests
import tinytuya
from tuya_device_handlers.const import DPType

from .cloud import Record, Scene, Session
from .errors import CloudError

_LOGGER = logging.getLogger(__name__)
# At DEBUG TinyTuya logs the Access Secret, the token and every response.
logging.getLogger("tinytuya").setLevel(logging.INFO)

REGIONS = ("cn", "us", "us-e", "eu", "eu-w", "in", "sg")
# TinyTuya's other names for us, us-e and eu-w. A name it does not know it
# sends to the China data centre without a word.
_ALIASES = ("az", "ue", "we")
# Without the id or the secret TinyTuya would use the project in ./tinytuya.json.
_FIELDS = ("region", "access_id", "access_secret", "uid")
_SETUP = (
    "check that the Smart Life / Tuya Smart account is linked to the project (Devices > "
    "Link Tuya App Account), that the region is the project's data centre, and that the "
    "IoT Core trial has not expired (it is extended at iot.tuya.com)"
)
# Tuya error code -> what to do about it.
_HINTS: dict[Any, str] = {
    1004: "check the Access ID and the Access Secret",
    1106: _SETUP,
    28841002: "the project's IoT Core trial has expired; extend it at iot.tuya.com",
    28841105: "under Service API, subscribe to IoT Core and Authorization and authorise "
    "the project for them",
}
# Refusals that concern the whole project, not one product. They are raised even
# where a device could do without the answer, so that an expired trial does not
# quietly leave every device without entities.
_PROJECT_WIDE = {1004, 28841002, 28841105}
_PATHS = {
    "specification": "/v1.1/devices/{}/specifications",
    "thing model": "/v2.0/cloud/thing/{}/model",
}
# What the handlers read from a row's `values` without checking that it is there.
_REQUIRED: dict[DPType | None, set[str]] = {
    DPType.INTEGER: {"min", "max", "scale", "step"},
    DPType.ENUM: {"range"},
    DPType.BITMAP: {"label"},
}
# The sharing SDK's two encodings of a colour that is Json in the cloud and text
# on the device, by the largest saturation each carries.
_COLOUR_ENCODINGS: dict[Any, str] = {1000: "dj_v2_color_alg", 255: "dj_v1_hsv_alg"}

# A specification's readable rows, by part; a thing model's types, by dp id.
_Spec = dict[str, list[dict[str, Any]]]
_Model = dict[int, dict[str, Any]]


def login(
    access_id: str, access_secret: str, region: str, *, uid: str = "", device_id: str = ""
) -> Session:
    """Check a project's credentials against the cloud and return the session to save.

    The project's token does not say whose devices to list: give the linked
    app account's `uid`, or the id of any one of its devices.
    """
    region = region.lower()
    if region not in REGIONS + _ALIASES:
        raise CloudError(f"unknown region {region!r}; it is one of {', '.join(REGIONS)}")
    if not (access_id and access_secret):
        raise CloudError("the project's Access ID and Access Secret are both needed")
    if not (uid or device_id):
        raise CloudError("give the UID of the linked app account or the id of one of its devices")
    session = {
        "kind": "developer",
        "region": region,
        "access_id": access_id,
        "access_secret": access_secret,
        "uid": uid,
    }
    cloud = DeveloperCloud(session)
    if not uid:
        owner = cloud._get("looking up the account", f"/v1.0/devices/{device_id}").get("uid")
        if not (owner and isinstance(owner, str)):
            raise CloudError("looking up the account: unexpected response from the Tuya cloud")
        session["uid"] = owner
    # Answers only if id, secret, region, uid and the account's link all fit.
    if not cloud._list():
        raise CloudError(f"listing devices: the project sees no devices; {_SETUP}")
    return session


def is_session(session: Session) -> bool:
    """Whether a saved session is a developer login with everything it takes."""
    return (
        session.get("kind") == "developer"
        and all(isinstance(session.get(field), str) and session[field] for field in _FIELDS)
        and session["region"].lower() in REGIONS + _ALIASES
    )


class DeveloperCloud:
    """A cloud project with one app account linked to it."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._api: tinytuya.Cloud | None = None  # made on first use: making it asks for a token
        self._lock = threading.Lock()  # TinyTuya's Cloud is not thread-safe

    def devices(self) -> list[Record]:
        """Fetch every device of the account, with specs and datapoint maps."""
        # By product: what the cloud says of one device holds for every device of its kind.
        specs: dict[str, _Spec] = {}
        models: dict[str, _Model] = {}
        records = []
        try:
            for item in self._list():
                product = item.get("product_id") or item["id"]  # without one, a product of its own
                new = product not in specs
                if new:
                    spec = self._optional(item, "specification", _specification, _PROJECT_WIDE)
                    if spec is not None:
                        specs[product] = spec
                if product not in models:
                    model = self._optional(item, "thing model", _model)
                    if model is not None:
                        models[product] = model
                records.append(_record(item, specs.get(product, {}), models.get(product, {})))
                if product not in specs:  # the saved description, if any, is kept
                    records[-1]["incomplete"] = ["specification"]
                if new and (codes := _cloud_only(records[-1])):
                    name = item.get("product_name") or product
                    _LOGGER.info("%s: left to the cloud: %s", name, ", ".join(codes))
        except (AttributeError, KeyError, TypeError, ValueError) as err:  # a list of another shape
            raise CloudError("listing devices: unexpected response from the Tuya cloud") from err
        return records

    def home_ids(self) -> list[str]:
        return []  # only scenes and push are organised by home

    def status(self, device_id: str) -> Record:
        """One device's reachability and status by DP code, in a single request."""
        result = self._get("querying device", f"/v1.0/devices/{device_id}")
        return {"online": bool(result.get("online", True)), "status": _status(result)}

    def send(self, device_id: str, commands: list[dict[str, Any]]) -> None:
        # Not the older /v1.0/devices/{id}/commands: TinyTuya sends every command made with
        # a project's token here, and homebridge-tuya-plus moved here from the older one,
        # which it names as a cause of failed writes. This one is documented, and used in
        # TinyTuya's examples/cloud_rgb_bulb.py, with Json values as objects; the handlers
        # give them as text.
        commands = [command | {"value": _as_object(command["value"])} for command in commands]
        path = f"/v1.0/iot-03/devices/{device_id}/commands"
        self._get("sending command", path, {"commands": commands}, shape=object)

    def logout(self) -> None:
        """Nothing to revoke: the project's tokens expire by themselves."""

    def scenes(self, home_ids: list[str]) -> list[Scene]:
        raise _unavailable("scenes")

    def run_scene(self, scene: Scene) -> None:
        raise _unavailable("scenes")

    def stream_url(self, device_id: str, kind: str) -> str:
        raise _unavailable("camera streams")

    def listen(
        self,
        devices: list[tuple[str, bool]],
        home_ids: list[str],
        on_message: Callable[[dict[str, Any]], None],
    ) -> Callable[[], None]:
        raise _unavailable("push updates from the cloud")

    def _list(self) -> list[dict[str, Any]]:
        path = f"/v1.0/users/{self._session['uid']}/devices"
        items: list[dict[str, Any]] = self._get("listing devices", path, shape=list)
        return items

    def _optional(
        self,
        item: dict[str, Any],
        what: str,
        parse: Callable[[Any], Any],
        fatal: Collection[int] = (),
    ) -> Any:
        """What the cloud says of a device's product; None, with a warning, if nothing.

        A device can do without it, so of Tuya's refusals only those in `fatal` are
        raised. Getting no answer at all (no token, no network, a body that is not
        JSON) is raised as for any request: it says nothing about the product.
        """
        action = f"fetching the {what}"
        reply = self._request(action, _PATHS[what].format(item["id"]))
        if reply.get("code") in fatal:
            raise _refused(action, reply)
        try:
            if reply.get("success"):
                return parse(reply["result"])
            reason = f"{reply.get('msg')} ({reply.get('code')})"
        except (AttributeError, KeyError, TypeError, ValueError):
            reason = "unexpected response"
        _LOGGER.warning("%s: the cloud gave no %s: %s", item.get("name"), what, reason)
        return None

    def _get(self, action: str, path: str, post: Any = None, shape: type = dict) -> Any:
        """The result of a request that has to succeed."""
        reply = self._request(action, path, post)
        if not reply.get("success"):
            raise _refused(action, reply)
        if not isinstance(reply.get("result"), shape):
            raise CloudError(f"{action}: unexpected response from the Tuya cloud")
        return reply["result"]

    def _request(self, action: str, path: str, post: Any = None) -> dict[str, Any]:
        """Tuya's reply to one request, whatever it says."""
        with self._lock:
            # Kept only once a request went through: after a failure TinyTuya's
            # object can be without a token, and then repeats the failure unasked.
            api, self._api = self._api, None
            try:
                api = api or tinytuya.Cloud(
                    apiRegion=self._session["region"],
                    apiKey=self._session["access_id"],
                    apiSecret=self._session["access_secret"],
                )
                reply = api.cloudrequest(path, post=post)
            except requests.RequestException as err:
                # The host only, not the exception's own text: that quotes the URL.
                url = err.request.url if err.request is not None else None
                host = urlsplit(str(url)).hostname if url else None
                kind = type(err).__name__
                raise CloudError(
                    f"{action}: cannot reach {host or 'the Tuya cloud'} ({kind})"
                ) from err
            except (AttributeError, KeyError, TypeError) as err:
                # TinyTuya trips over a token reply of an unexpected shape.
                raise CloudError(f"{action}: unexpected response from the Tuya cloud") from err
            if isinstance(reply, dict) and "Err" not in reply:
                # Tuya's error-code list words 1010 "token is expired", which TinyTuya does
                # not renew (it renews on "token invalid"): the next request takes a new token.
                if reply.get("code") != 1010:
                    self._api = api
                return reply
        raise _no_reply(action, reply)


def _unavailable(what: str) -> CloudError:
    return CloudError(f"{what} are not available with a developer account")


def _refused(action: str, reply: dict[str, Any]) -> CloudError:
    code, hint = reply.get("code"), _HINTS.get(reply.get("code"))
    return CloudError(f"{action}: {reply.get('msg')} ({code})" + (f"; {hint}" if hint else ""))


def _no_reply(action: str, reply: Any) -> CloudError:
    """The error for what TinyTuya returns in place of a reply from Tuya."""
    if reply is None:
        # TinyTuya has by then renewed the token on "token invalid" and asked again.
        return CloudError(
            f"{action}: the Tuya cloud keeps rejecting the project's token; an expired IoT "
            "Core trial is a known cause (it is extended at iot.tuya.com)"
        )
    # Err 911 is a refused token request: TinyTuya keeps Tuya's message for it but not
    # the code, and makes "failed: None" of a reply that was not JSON.
    error = reply if isinstance(reply, dict) else {}
    payload = str(error.get("Payload"))
    if str(error.get("Err")) != "911" or payload.endswith("failed: None"):
        return CloudError(f"{action}: unexpected response from the Tuya cloud")
    if "request time is invalid" in payload:
        hint = "this computer's clock is wrong"
    elif "permission" in payload.lower() or "subscription" in payload.lower():
        hint = _SETUP
    else:
        hint = "check the Access ID, the Access Secret and the region"
    return CloudError(f"{action}: no access token ({payload}); {hint}")


def _as_object(value: Any) -> Any:
    """A command value as this API takes it: JSON text of an object or array as that object."""
    try:
        parsed = json.loads(value) if isinstance(value, str) else None
    except ValueError:
        return value
    return parsed if isinstance(parsed, (dict, list)) else value


def _status(item: dict[str, Any]) -> dict[str, Any]:
    """Status by DP code; a Json value as text, as the QR login gives and the handlers read it."""
    status = {}
    for entry in item.get("status") or ():
        if isinstance(entry, dict) and "code" in entry and "value" in entry:
            value = entry["value"]
            as_text = isinstance(value, (dict, list))
            status[entry["code"]] = json.dumps(value, separators=(",", ":")) if as_text else value
    return status


def _specification(result: dict[str, Any]) -> _Spec:
    """The rows of a specification, without those the handlers could not parse."""
    spec: _Spec = {"functions": [], "status": []}
    for part, rows in spec.items():
        for row in result.get(part) or ():
            try:
                rows.append(_row(row))
            except (AttributeError, KeyError, TypeError, ValueError):
                _LOGGER.warning("Ignoring a %s row that cannot be read: %r", part, row)
    return spec


def _row(row: dict[str, Any]) -> dict[str, Any]:
    """A specification row as the handlers take it; raises if they could not parse it."""
    values, dp_id = row.get("values"), row.get("dp_id")
    text = values if isinstance(values, str) else json.dumps(values or {})
    kind = DPType.try_parse(row.get("type", ""))
    if kind not in (DPType.BOOLEAN, DPType.STRING):
        parsed = json.loads(text)
        if not isinstance(parsed, dict) or _REQUIRED.get(kind, set()) - parsed.keys():
            raise ValueError(f"incomplete values for {row.get('type')}: {text}")
    return {
        "code": row["code"],
        "type": row.get("type", ""),
        "values": text,
        "dp_id": None if dp_id is None else int(dp_id),
    }


def _model(result: dict[str, Any]) -> _Model:
    """Each datapoint's type on the device, by dp id (the thing model's abilityId)."""
    model = result.get("model") or {}
    if isinstance(model, str):  # documented as JSON text
        model = json.loads(model)
    return {
        int(item["abilityId"]): item.get("typeSpec") or {}
        for service in model.get("services") or ()
        for item in service.get("properties") or ()
    }


def _record(item: dict[str, Any], spec: _Spec, model: _Model) -> Record:
    def describe(row: dict[str, Any]) -> dict[str, Any]:
        return {key: row[key] for key in ("code", "type", "values")}

    status = _status(item)
    record = {
        "id": item["id"],
        "name": item.get("name") or item["id"],
        "category": item.get("category", ""),
        "product_id": item.get("product_id", ""),
        "product_name": item.get("product_name", ""),
        "online": bool(item.get("online", True)),
        "local_key": item.get("local_key", ""),
        "sub": bool(item.get("sub")),
        "uuid": item.get("uuid", ""),
        "status": status,
        "function": {row["code"]: describe(row) for row in spec.get("functions", ())},
        "status_range": {
            row["code"]: describe(row) | {"report_type": None} for row in spec.get("status", ())
        },
        "local_strategy": _local_strategy(spec, model, status, item.get("product_id", "")),
    }
    if item.get("node_id"):  # a sub-device's address on its gateway
        record["node_id"] = item["node_id"]
    return record


def _local_strategy(
    spec: _Spec, model: _Model, status: dict[str, Any], product_id: str
) -> dict[int, dict[str, Any]]:
    """The datapoints whose LAN form is known, in the sharing SDK's format."""
    everything = [row for part in ("status", "functions") for row in spec.get(part, ())]
    datapoints: dict[int, dict[str, dict[str, Any]]] = {}
    for part in ("status", "functions"):
        for row in spec.get(part, ()):
            if row["dp_id"] is not None:
                datapoints.setdefault(row["dp_id"], {})[part] = row
    strategy = {}
    for dp_id, rows in datapoints.items():
        # DpMap sends a code to this datapoint by the code alone, so every row of that
        # code has to name this dp id and pass.
        codes = {row["code"] for row in rows.values()}
        related = [row for row in everything if row["code"] in codes]
        if any(row["dp_id"] != dp_id for row in related):
            continue
        conversions = {_conversion(row, model.get(dp_id, {}), status) for row in related}
        if len(conversions) != 1 or None in conversions:
            continue
        reported = rows.get("status") or rows["functions"]
        commanded = rows.get("functions") or rows["status"]
        strategy[dp_id] = {
            "value_convert": conversions.pop(),
            "status_code": commanded["code"],
            "config_item": {
                "statusFormat": json.dumps({reported["code"]: "$"}),
                "valueDesc": reported["values"],
                "valueType": reported["type"],
                "enumMappingMap": {},
                "pid": product_id,
            },
        }
    return strategy


def _conversion(
    row: dict[str, Any], on_device: dict[str, Any], status: dict[str, Any]
) -> str | None:
    """How a datapoint's LAN value becomes the cloud's; None if that is not known."""
    try:
        kind = DPType.try_parse(row["type"])
        device_kind = DPType.try_parse(on_device.get("type", ""))
        colour = row["code"] in ("colour_data", "colour_data_v2") and device_kind is DPType.STRING
        if kind is DPType.JSON:
            # The encoding is told by the colour's own saturation range, not by the dp id:
            # tuya-local's device files have both layouts at dp 5 and at dp 24.
            limit = json.loads(row["values"])["s"]["max"] if colour else None
            return _COLOUR_ENCODINGS.get(limit)
        if kind is DPType.STRING:
            # The sharing SDK converts some text to other text, so the type proves nothing.
            # Twelve hexadecimal digits are the colour the handlers read and write as text.
            value = str(status.get(row["code"]))
            return "default" if colour and re.fullmatch("[0-9a-fA-F]{12}", value) else None
        if kind is None or kind is not device_kind:
            return None
        values = json.loads(row["values"]) if kind in (DPType.INTEGER, DPType.ENUM) else {}
        if kind is DPType.INTEGER and any(values[end] != on_device[end] for end in ("min", "max")):
            return None
        if kind is DPType.ENUM and not set(values["range"]) <= set(on_device["range"]):
            return None
    except (AttributeError, KeyError, TypeError, ValueError):  # nothing to compare with
        return None
    return "default"


def _cloud_only(record: Record) -> list[str]:
    """The codes of a record that have no LAN mapping."""
    mapped: set[str] = set()
    for item in record["local_strategy"].values():
        mapped |= {item["status_code"], *json.loads(item["config_item"]["statusFormat"])}
    return sorted((record["function"].keys() | record["status_range"].keys()) - mapped)
