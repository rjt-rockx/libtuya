#!/usr/bin/env python3
"""Generate libtuya/data/ha_tuya.json from the vendored Home Assistant source.

Home Assistant's Tuya platforms each hold a table saying which DP codes make up
which entity for a device category (for a `dj` bulb: `switch_led` is the
switch, `bright_value_v2` the brightness, ...). Those tables are not published
as a library, so they are extracted here into plain data.

Only the module-level assignments and helper functions of each platform file
are evaluated. Names that would come from Home Assistant are replaced by
opaque placeholders, so nothing from Home Assistant needs to be installed.
"""

import ast
import builtins
import enum
import json
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "third_party" / "home-assistant-core"
SRC = VENDOR / "homeassistant" / "components" / "tuya"
OUT = ROOT / "libtuya" / "data" / "ha_tuya.json"

# platform module -> name of its table
TABLES = {
    "alarm_control_panel": "ALARM",
    "binary_sensor": "BINARY_SENSORS",
    "button": "BUTTONS",
    "camera": "CAMERAS",
    "climate": "CLIMATE_DESCRIPTIONS",
    "cover": "COVERS",
    "event": "EVENTS",
    "fan": "FANS",
    "humidifier": "HUMIDIFIERS",
    "light": "LIGHTS",
    "number": "NUMBERS",
    "select": "SELECTS",
    "sensor": "SENSORS",
    "siren": "SIRENS",
    "switch": "SWITCHES",
    "vacuum": "VACUUMS",
    "valve": "VALVES",
}


class HA:
    """Placeholder for anything imported from Home Assistant."""

    def __init__(self, path: str):
        self.path = path

    def __getattr__(self, name: str) -> "HA":
        return HA(f"{self.path}.{name}")

    def __call__(self, *args, **kwargs) -> "HA":
        return HA(f"{self.path}()")

    def __getitem__(self, item) -> "HA":
        return HA(f"{self.path}[]")

    # Deliberately not iterable: a table entry that expands a placeholder
    # (`*something_from_home_assistant`) must fail rather than vanish.
    __iter__ = None


class Ref(str):
    """A name imported from tuya_device_handlers, written 'module:attr'."""

    def __getattr__(self, name: str) -> "Ref":
        if name.startswith("__"):
            raise AttributeError(name)
        return Ref(f"{self}.{name}")


class Namespace(dict):
    """Module globals that resolve unknown names to placeholders."""

    def __init__(self, imports: dict[str, str], enums: dict[str, type]):
        super().__init__(enums)
        self.imports = imports

    def __missing__(self, name: str):
        if hasattr(builtins, name):
            raise KeyError(name)  # let the real builtin be found
        if name.endswith("EntityDescription"):
            return dict
        origin = self.imports.get(name, "")
        if origin.startswith("tuya_device_handlers"):
            return Ref(origin)
        return HA(name)


def load_enums() -> dict[str, type]:
    """Build the real DPCode/DeviceCategory enums from const.py."""
    tree = ast.parse((SRC / "const.py").read_text())
    wanted = ("DPCode", "DeviceCategory", "WorkMode")
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name in wanted]
    namespace: dict = {"StrEnum": enum.StrEnum}
    exec(compile(ast.Module(classes, []), "const.py", "exec"), namespace)
    return {name: namespace[name] for name in wanted}


def to_json(value):
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, Ref):
        return {"$ref": str(value)}
    if isinstance(value, HA):
        return {"$ha": value.path}
    if isinstance(value, dict):
        return {key: to_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [to_json(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(to_json(item) for item in value)
    return value


def extract(platform: str, table: str, enums: dict[str, type]) -> dict[str, list[dict]]:
    tree = ast.parse((SRC / f"{platform}.py").read_text())
    imports = {
        alias.asname or alias.name: f"{node.module}:{alias.name}"
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module
        for alias in node.names
    }
    namespace = Namespace(imports, enums)
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and node.value is not None:
            node = ast.Assign([node.target], node.value, lineno=node.lineno, col_offset=0)
        elif isinstance(node, ast.FunctionDef):
            # Helpers that build descriptions. Their annotations may name
            # classes defined further down, so drop them.
            node.returns = None
            node.decorator_list = []
            for argument in ast.walk(node.args):
                if isinstance(argument, ast.arg):
                    argument.annotation = None
        elif not isinstance(node, ast.Assign):
            continue
        exec(compile(ast.Module([node], []), f"{platform}.py", "exec"), namespace)
    result = {}
    for category, descriptions in namespace[table].items():
        if isinstance(descriptions, dict):  # one description per category
            descriptions = (descriptions,)
        result[category.value] = [
            to_json(
                {
                    key: value
                    for key, value in description.items()
                    if not isinstance(value, types.FunctionType)  # channel predicates
                }
            )
            for description in descriptions
            # Kept by Home Assistant only for entities created before a move.
            if not description.get("deprecated")
        ]
    return result


def entity_names() -> dict[str, dict[str, str]]:
    """English entity names, by platform and translation key."""
    entities = json.loads((SRC / "strings.json").read_text())["entity"]
    return {
        platform: {key: value["name"] for key, value in keys.items() if "name" in value}
        for platform, keys in entities.items()
    }


def build() -> dict:
    upstream = dict(
        line.split(": ", 1) for line in (VENDOR / "UPSTREAM").read_text().splitlines() if line
    )
    enums = load_enums()
    return {
        "source": {
            "repository": upstream["repository"],
            "ref": upstream["ref"],
            "commit": upstream["commit"],
            "license": "Apache-2.0",
            "generator": "scripts/gen_ha_tables.py",
        },
        "requirements": json.loads((SRC / "manifest.json").read_text())["requirements"],
        "names": entity_names(),
        "platforms": {
            platform: extract(platform, table, enums) for platform, table in TABLES.items()
        },
    }


def main() -> None:
    data = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
    count = sum(len(d) for cats in data["platforms"].values() for d in cats.values())
    print(f"{OUT.relative_to(ROOT)}: {count} entity descriptions")


if __name__ == "__main__":
    main()
