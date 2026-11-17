"""Reads the entity states Home Assistant recorded for its device fixtures.

The vendored snapshot files are syrupy "amber" text: Python-like literals with
enum members and placeholders in angle brackets.
"""

import re
from functools import cache
from typing import Any

from conftest import FIXTURES, fixture_names

SNAPSHOTS = FIXTURES.parent / "snapshots"
_BLOCK = re.compile(
    r"^# name: test_platform_setup_and_discovery\[(?P<entity_id>.+?)-(?P<kind>entry|state)\]\n"
    r"(?P<body>.*?)^# ---$",
    re.MULTILINE | re.DOTALL,
)
_NAMES = {
    "__builtins__": {},
    "dict": dict,
    "list": list,
    "set": set,
    "tuple": lambda *items: tuple(items),
    "ReadOnlyDict": dict,
    "StateSnapshot": dict,
    "EntityRegistryEntrySnapshot": dict,
}


def _parse(body: str) -> dict[str, Any]:
    body = re.sub(r"<[\w.]+: ('(?:[^'\\]|\\.)*'|-?\d+)>", r"\1", body)  # enum member -> its value
    body = re.sub(r"<[^<>]*>", "None", body)  # <ANY>, <DeviceEntry ...>
    return eval(body.strip(), dict(_NAMES))


@cache
def states(platform: str) -> dict[tuple[str, str], dict[str, Any]]:
    """Home Assistant's state per entity: {(fixture name, entity key): {"state", "attributes"}}."""
    device_ids = {name.replace("_", "")[::-1]: name for name in fixture_names()}
    entries: dict[str, tuple[str, str]] = {}
    recorded: dict[tuple[str, str], dict[str, Any]] = {}
    text = (SNAPSHOTS / f"test_{platform}.ambr").read_text()
    for block in _BLOCK.finditer(text):
        data = _parse(block["body"])
        if block["kind"] == "entry":
            unique = data["unique_id"].removeprefix("tuya.")
            device_id = max((i for i in device_ids if unique.startswith(i)), key=len)
            entries[data["entity_id"]] = (device_ids[device_id], unique[len(device_id) :])
        else:
            recorded[entries[data["entity_id"]]] = {
                "state": data["state"],
                "attributes": data["attributes"],
            }
    return recorded
