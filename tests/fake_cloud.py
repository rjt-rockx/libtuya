"""A fake of the Smart Life sharing API at the HTTP layer, so that the real SDK runs offline.

It takes a request only with the current access token, encrypts each answer with the key the SDK
derives for that request, and ends the old token pair when it issues a new one, as the real one
does in the debug log from home-assistant/core#191973 relayed in tuya-device-sharing-sdk PR #82.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import threading
import time
from typing import Any

import requests
from conftest import record
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ENDPOINT = "https://fake-cloud.invalid"


def session(expired: bool = False) -> dict[str, Any]:
    """A saved login for the fake; an expired one is renewed before the first request."""
    issued = int(time.time() * 1000) - (3 * 3600 * 1000 if expired else 0)
    tokens = {"t": issued, "expire_time": 7200, "access_token": "a0", "refresh_token": "r0"}
    return {"user_code": "c", "terminal_id": "t", "endpoint": ENDPOINT, "token_info": tokens}


def _response(body: dict[str, Any]) -> requests.Response:
    response = requests.Response()
    response.status_code = 200
    response._content = json.dumps({"t": int(time.time() * 1000), **body}).encode()
    return response


class FakeCloud:
    """The service, with Home Assistant's fixture devices `names` in one home.

    Tests may change ``homes``, ``relations`` (each device's datapoint relations) and ``fail``
    (path -> the body answered instead). ``commands`` lists the devices commanded;
    ``refreshing`` is set while a token renewal is answered, for ``refresh_time`` s.
    """

    def __init__(self, *names: str) -> None:
        self.devices = {name: record(name) for name in names}
        self.homes = [{"ownerId": 7, "name": "Home"}]
        self.relations = {name: [] for name in names}
        for name, device in self.devices.items():
            for dp_id, item in device["local_strategy"].items():
                relation = dict(item["config_item"])
                for key in ("statusFormat", "valueDesc"):  # JSON text; some fixtures parsed it
                    if not isinstance(relation[key], str):
                        relation[key] = json.dumps(relation[key])
                relation |= {"dpId": int(dp_id), "statusCode": item["status_code"]}
                relation |= {"valueConvert": item["value_convert"], "supportLocal": True}
                self.relations[name].append(relation)
        self.fail: dict[str, Any] = {}
        self.commands: list[str] = []
        self.refreshing, self.refresh_time = threading.Event(), 0.0
        self._tokens = ("a0", "r0")

    def request(self, method: str, url: str, headers: dict, **kwargs: Any) -> requests.Response:
        path = url.removeprefix(ENDPOINT)
        if (failure := self.fail.get(path)) is not None:
            return _response(failure)
        access, refresh = self._tokens
        if headers.get("X-token") != access:
            return _response({"success": False, "code": "-9999999", "msg": "sign invalid"})
        result = json.dumps(self._result(path)).encode()
        # Encrypted with the key the SDK derives for this request (tuya_sharing/customerapi.py).
        rid = headers["X-requestId"]
        hash_key = hashlib.md5((rid + refresh).encode()).hexdigest()
        key = hmac.new(rid.encode(), hash_key.encode(), hashlib.sha256).hexdigest()[:16]
        nonce = os.urandom(12)
        sealed = nonce + AESGCM(key.encode()).encrypt(nonce, result, None)
        return _response({"success": True, "result": base64.b64encode(sealed).decode()})

    def _result(self, path: str) -> Any:
        device = self.devices.get(name := path.split("/")[-2], {})
        if path == f"/v1.0/m/token/{self._tokens[1]}":
            number = int(self._tokens[0][1:]) + 1
            self._tokens = (f"a{number}", f"r{number}")  # the old pair is dead from now on
            self.refreshing.set()
            time.sleep(self.refresh_time)
            tokens = {"accessToken": self._tokens[0], "refreshToken": self._tokens[1]}
            return tokens | {"expireTime": 7200, "uid": "u"}
        if path == "/v1.0/m/life/users/homes":
            return self.homes
        if path == "/v1.0/m/life/ha/home/devices":
            described = ("function", "status_range", "local_strategy", "status")
            listed = self.devices.values()
            return [{k: v for k, v in d.items() if k not in described} for d in listed]
        if path.endswith("/specifications"):
            functions, status = device["function"].values(), device["status_range"].values()
            return {"functions": [*functions], "status": [*status]}
        if path.endswith("/status"):
            relations = self.relations[name]
            return {"productKey": device["product_id"], "dpStatusRelationDTOS": relations}
        if path.endswith(("/custom-type", "/dp-report-types")):
            return []
        if path.endswith("/commands"):
            self.commands.append(name)
            return True
        raise AssertionError(f"the fake cloud does not serve {path}")
