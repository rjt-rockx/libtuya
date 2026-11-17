"""The `tuya` command: a thin front end to the library."""

from __future__ import annotations

import argparse
import colorsys
import enum
import getpass
import json
import logging
import sys
import threading
import time
from collections.abc import Callable
from typing import Any

from . import Climate, Device, Entity, Light, Tuya, TuyaError, __version__

# `tuya control DEVICE ACTION` for these calls the entity method of the same name.
_PLAIN_ACTIONS = (
    "open", "close", "stop", "start", "pause", "return_to_base", "locate", "press",
    "arm_home", "arm_away", "disarm", "trigger",
)  # fmt: skip

USER_CODE_HINT = "Smart Life or Tuya Smart app: Me > gear icon > Account and Security > User Code"

# A command returns the data for --json and the text for people.
Result = tuple[dict[str, Any], str]


def _show(value: Any) -> str:
    """A value as people read it."""
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, tuple):
        return "(" + ", ".join(_show(item) for item in value) + ")"
    return str(value)


def _plain(value: Any) -> Any:
    """A value as JSON can carry it."""
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, (bool, int, float, str, type(None))):
        return value
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_plain(item) for item in value]
    return str(value)


def _parse(text: str) -> Any:
    """Read a command-line value: on/off, JSON, or plain text."""
    if text.lower() in ("on", "off"):
        return text.lower() == "on"
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _parse_for(entity: Entity, attribute: str | None, text: str) -> Any:
    """Read a value for an entity attribute; a choice the device offers is taken as typed."""
    wrapper = entity.wrappers.get(attribute or next(iter(entity.wrappers)))
    choices = [str(option) for option in getattr(wrapper, "options", None) or ()]
    return text if text in choices else _parse(text)


def _where(tuya: Tuya, device: Device) -> str:
    """Where a device is on the LAN, in words."""
    if device.address:
        return str(device.address)
    gateway = tuya.gateway_of(device)
    return f"via {gateway.name}" if gateway else "not found (cloud only)"


def _entity_line(entity: Entity) -> str:
    described = entity.describe()
    if len(described) == 1:
        (details,) = described.values()
        shown = f"{_show(details['value'])} {details.get('unit', '')}".rstrip()
    else:
        shown = "  ".join(
            f"{attribute}={_show(details['value'])}"
            for attribute, details in described.items()
            if details["value"] is not None
        )
    return f"  {entity.id:34} {entity.name or '':28} {shown}"


def _device_data(device: Device) -> dict[str, Any]:
    return {
        "id": device.id,
        "name": device.name,
        "category": device.category,
        "product": device.product_name,
        "ip": device.address.ip if device.address else None,
        "version": device.address.version if device.address else None,
    }


def _describe(tuya: Tuya, device: Device) -> Result:
    """Current state of a device, entity by entity."""
    entities = {
        entity.id: {"name": entity.name, "attributes": _plain(entity.describe())}
        for entity in device.entities
    }
    lines = [
        f"{device.name}  [{device.product_name}, category {device.category}]",
        f"  id {device.id}   LAN {_where(tuya, device)}   read via {device.transport}",
        *(_entity_line(entity) for entity in device.entities),
    ]
    if not device.entities:
        lines += ["  (no known entities; raw status below)", f"  {device.status}"]
    data = _device_data(device) | {
        "transport": device.transport,
        "status": _plain(device.status),
        "entities": entities,
    }
    return {"device": data}, "\n".join(lines)


def _qr_login(tuya: Tuya, user_code: str | None) -> None:
    if not user_code:
        print(f"User code ({USER_CODE_HINT}): ", end="", file=sys.stderr, flush=True)
        user_code = input().strip()

    def show_qr(text: str) -> None:
        import qrcode

        code = qrcode.QRCode(border=2)
        code.add_data(text)
        code.print_ascii(out=sys.stderr, invert=True)
        print(
            "Scan this with the app (the + button, then Scan) and approve the login.",
            file=sys.stderr,
        )

    tuya.login(user_code, show_qr)


def login(tuya: Tuya, args: argparse.Namespace) -> Result:
    if tuya.logged_in and not args.force:
        return {"message": "Already logged in"}, "Already logged in (use --force to log in again)."
    if args.access_id:
        secret = args.access_secret or getpass.getpass("Access Secret of the cloud project: ")
        tuya.login_developer(
            args.access_id,
            secret,
            args.region or "",
            uid=args.uid or "",
            device_id=args.device_id or "",
        )
    elif args.region or args.uid or args.device_id or args.access_secret:
        raise TuyaError("--region, --uid, --device-id and --access-secret go with --access-id")
    else:
        _qr_login(tuya, args.user_code)
    devices = tuya.devices(refresh=True)
    found = sum(1 for device in devices if device.address)
    text = f"Logged in. {len(devices)} devices, {found} found on the LAN."
    return {"message": "Logged in", "devices": len(devices), "on_lan": found}, text


def logout(tuya: Tuya, args: argparse.Namespace) -> Result:
    tuya.logout()
    return {"message": "Logged out"}, "Logged out."


def devices(tuya: Tuya, args: argparse.Namespace) -> Result:
    found = tuya.devices(refresh=args.refresh)
    missing = {device.id: device.record.get("incomplete") or [] for device in found}
    rows = [
        (
            str(index),
            device.name + (" *" if missing[device.id] else ""),
            device.product_name,
            device.category,
            _where(tuya, device),
        )
        for index, device in enumerate(found, 1)
    ]
    header = ("#", "Name", "Product", "Cat.", "LAN")
    widths = [max(len(row[column]) for row in [header, *rows]) for column in range(len(header))]
    lines = [
        "  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)).rstrip()
        for row in [header, *rows]
    ]
    if any(missing.values()):
        lines.append(
            "* not fully described by the Tuya cloud at the last refresh; "
            "try `tuya devices --refresh` again later"
        )
    data = [
        _device_data(device) | {"index": index, "incomplete": missing[device.id]}
        for index, device in enumerate(found, 1)
    ]
    return {"devices": data, "count": len(data)}, "\n".join(lines)


def info(tuya: Tuya, args: argparse.Namespace) -> Result:
    device = tuya.device(args.device)
    device.refresh()
    return _describe(tuya, device)


def control(tuya: Tuya, args: argparse.Namespace) -> Result:
    device = tuya.device(args.device)
    action = args.action.lower()
    value = args.value
    if action == "status":
        return info(tuya, args)

    def entity() -> Entity:
        return device.entity(args.entity) if args.entity else device.power

    def light() -> Light:
        if not isinstance(chosen := entity(), Light):
            raise TuyaError(f"{chosen.id} is not a light")
        return chosen

    def able_to(method: str) -> Any:
        """The entity to act on: the one named, else the device's only one with `method`."""
        if args.entity:
            chosen = device.entity(args.entity)
            if not callable(getattr(chosen, method, None)):
                raise TuyaError(f"{chosen.id} cannot {action}")
            return chosen
        able = [e for e in device.entities if callable(getattr(e, method, None))]
        if len(able) == 1:
            return able[0]
        if able:
            raise TuyaError(
                f"several entities can {action}; pick one with --entity: "
                + ", ".join(e.id for e in able)
            )
        raise TuyaError(f"{device.name} has nothing that can {action}")

    def number() -> float:
        if value is None:
            raise TuyaError(f"`{action}` needs a value")
        return float(value)

    def word() -> str:
        if value is None:
            raise TuyaError(f"`{action}` needs a value")
        return value

    with device.connected():
        if action in ("on", "off"):
            entity().turn_on() if action == "on" else entity().turn_off()
        elif action == "toggle":
            device.refresh()
            entity().turn_off() if entity().value else entity().turn_on()
        elif action in _PLAIN_ACTIONS:
            getattr(able_to(action), action)()
        elif action == "position":
            able_to("set_position").set_position(round(number()))
        elif action == "mode":
            able_to("set_hvac_mode").set_hvac_mode(word())
        elif action == "preset":
            able_to("set_preset_mode").set_preset_mode(word())
        elif action == "speed":
            able_to("set_percentage").set_percentage(number())
        elif action == "humidity":
            able_to("set_humidity").set_humidity(round(number()))
        elif action == "brightness":
            if not 0 <= (percent := number()) <= 100:
                raise TuyaError("brightness is a percentage, 0 to 100")
            device.refresh()  # whether to dim the colour or the white depends on the mode
            light().turn_on(brightness=percent * 255 / 100)
        elif action == "color":
            text = (value or "").lstrip("#")
            if len(text) != 6:
                raise TuyaError("color is given as RRGGBB, for example ff8800")
            red, green, blue = (int(text[index : index + 2], 16) / 255 for index in (0, 2, 4))
            hue, saturation, brightness = colorsys.rgb_to_hsv(red, green, blue)
            light().turn_on(hs_color=(hue * 360, saturation * 100), brightness=brightness * 255)
        elif action == "temperature":
            # Degrees for a thermostat, kelvin for a light: the one named, else a thermostat.
            climate = (e for e in device.entities if isinstance(e, Climate))
            target = device.entity(args.entity) if args.entity else next(climate, None)
            if isinstance(target, Climate):
                target.set_temperature(number())
            else:
                light().turn_on(color_temp_kelvin=round(number()))
        else:
            raise TuyaError(f"unknown action {action!r}")
    data = {"device": device.name, "action": action, "value": value, "transport": device.transport}
    return data, f"{device.name}: {action}{' ' + value if value else ''} (via {device.transport})"


def set_(tuya: Tuya, args: argparse.Namespace) -> Result:
    device = tuya.device(args.device)
    if args.raw:
        if len(args.values) != 1:
            raise TuyaError("--raw takes a DP code and one value")
        device.set_raw({args.target: _parse(args.values[0])})
        target = args.target
    else:
        entity = device.entity(args.target)
        if all("=" in value for value in args.values):
            pairs = [value.split("=", 1) for value in args.values]
            entity.set(**{name: _parse_for(entity, name, text) for name, text in pairs})
        elif len(args.values) == 1:
            entity.set(_parse_for(entity, None, args.values[0]))
        else:
            raise TuyaError("give one value, or attribute=value pairs")
        target = entity.id
    data = {"device": device.name, "target": target, "transport": device.transport}
    return data, f"{device.name}: {target} set (via {device.transport})"


def watch(tuya: Tuya, args: argparse.Namespace) -> Result:
    device = tuya.device(args.device)
    print(f"Watching {device.name}; Ctrl-C to stop.", file=sys.stderr)
    try:
        for changed in device.watch():
            if args.json:
                print(json.dumps(_plain(changed)), flush=True)
            else:
                shown = "  ".join(f"{code}={_show(value)}" for code, value in changed.items())
                print(f"{time.strftime('%H:%M:%S')}  {shown}", flush=True)
    except KeyboardInterrupt:
        pass
    return {}, ""


def listen(tuya: Tuya, args: argparse.Namespace) -> Result:
    def show(device: Device, changed: dict[str, Any]) -> None:
        if args.json:
            line = json.dumps({"device": device.name, "online": device.online} | _plain(changed))
        else:
            shown = "  ".join(f"{code}={_show(value)}" for code, value in changed.items())
            line = f"{time.strftime('%H:%M:%S')}  {device.name}: {shown or _show(device.online)}"
        print(line, flush=True)

    stop = tuya.subscribe(show)
    print("Listening to the cloud for every device; Ctrl-C to stop.", file=sys.stderr)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        stop()
    return {}, ""


def scenes(tuya: Tuya, args: argparse.Namespace) -> Result:
    found = tuya.scenes()
    data = [{"id": scene.id, "name": scene.name, "enabled": scene.enabled} for scene in found]
    return {"scenes": data}, "\n".join(scene.name for scene in found) or "No scenes."


def scene(tuya: Tuya, args: argparse.Namespace) -> Result:
    tuya.run_scene(args.name)
    return {"scene": args.name}, f"Ran {args.name}."


def scan(tuya: Tuya, args: argparse.Namespace) -> Result:
    found = tuya.scan(args.timeout)
    names = {device.id: device.name for device in tuya.devices()}
    lines = [f"{names[dev_id]:30} {address}" for dev_id, address in found.items()]
    data = {"found": {dev_id: vars(address) for dev_id, address in found.items()}}
    return data, "\n".join(lines) or "No devices answered."


def locate(tuya: Tuya, args: argparse.Namespace) -> Result:
    device = tuya.device(args.device)
    address = tuya.locate(device, args.ip, args.protocol)
    return {"device": device.name, **vars(address)}, f"{device.name}: {address}"


def health(tuya: Tuya, args: argparse.Namespace) -> Result:
    # Only what is saved: this command must not log in, fetch or scan. After a login
    # devices.json can hold LAN addresses and no device list yet.
    try:
        saved = json.loads((tuya.home / "devices.json").read_text())
    except (OSError, ValueError):
        saved = {}
    known = tuya.devices() if isinstance(saved, dict) and saved.get("devices") else []
    data = {
        "home": str(tuya.home),
        "logged_in": tuya.logged_in,
        "devices": len(known),
        "on_lan": sum(1 for device in known if device.address),
    }
    text = (
        f"State directory: {data['home']}\n"
        f"Logged in:       {'yes' if data['logged_in'] else 'no (run `tuya login`)'}\n"
        f"Devices:         {data['devices']} known, {data['on_lan']} with a LAN address"
    )
    return {"health": data}, text


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tuya",
        description="Control Tuya devices, locally where possible.",
        epilog="Options above go before the command; --json goes after it.",
    )
    parser.add_argument("--version", action="version", version=f"libtuya {__version__}")
    parser.add_argument(
        "-v", "--verbose", action="count", default=0, help="log what is going on (-vv for more)"
    )
    parser.add_argument("--home", help="state directory (default ~/.libtuya or $LIBTUYA_HOME)")
    parser.add_argument("--local", action="store_true", help="never fall back to the cloud")
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    def add(
        name: str, handler: Callable[[Tuya, argparse.Namespace], Result], text: str
    ) -> argparse.ArgumentParser:
        command = commands.add_parser(name, help=text, description=text)
        command.add_argument("--json", action="store_true", help="print JSON")
        command.set_defaults(handler=handler)
        return command

    device_help = "number from `tuya devices`, name, part of a name, or id"
    command = add(
        "login",
        login,
        "Log in by scanning a QR code with the Smart Life or Tuya Smart app, "
        "or through a Tuya IoT Platform cloud project (--access-id)",
    )
    command.add_argument("-u", "--user-code", help=USER_CODE_HINT)
    command.add_argument(
        "--force", action="store_true", help="log in again even if a session exists"
    )
    project = command.add_argument_group("with a cloud project instead of a QR code")
    project.add_argument("--access-id", help="the project's Access ID")
    project.add_argument("--access-secret", help="the project's Access Secret (asked if omitted)")
    project.add_argument(
        "--region", help="the project's data centre: cn, us, us-e, eu, eu-w, in or sg"
    )
    account = project.add_mutually_exclusive_group()
    account.add_argument("--uid", help="UID of the app account linked to the project")
    account.add_argument("--device-id", help="or the id of any one of that account's devices")
    add("logout", logout, "Delete the saved login and keys (a QR login is also revoked)")
    command = add("devices", devices, "List devices")
    command.add_argument(
        "--refresh", action="store_true", help="ask the cloud again and rescan the LAN"
    )
    command = add("info", info, "Read a device and show its entities")
    command.add_argument("device", help=device_help)
    command = add("control", control, "Switch, dim, open, start ... a device the way its app would")
    command.add_argument("device", help=device_help)
    command.add_argument(
        "action",
        help="on, off, toggle, status; brightness PERCENT, color RRGGBB, "
        "temperature DEGREES (thermostat) or KELVIN (light); open, close, stop, "
        "position PERCENT; mode HVAC_MODE, preset NAME, speed PERCENT, humidity PERCENT; "
        "start, pause, return_to_base, locate; press; arm_home, arm_away, disarm, trigger",
    )
    command.add_argument("value", nargs="?")
    command.add_argument(
        "-e", "--entity", help="act on this entity instead of the device's main one"
    )
    command = add(
        "set",
        set_,
        "Set an entity: `set DEVICE switch.child_lock on`, "
        "`set DEVICE climate set_temperature=21.5`",
    )
    command.add_argument("device", help=device_help)
    command.add_argument("target", help="entity id, key or name; with --raw, a DP code")
    command.add_argument("values", nargs="+", metavar="VALUE", help="a value, or ATTRIBUTE=VALUE")
    command.add_argument(
        "--raw", action="store_true", help="write a DP code with an unscaled value"
    )
    command = add("watch", watch, "Print status changes as the device reports them")
    command.add_argument("device", help=device_help)
    add("listen", listen, "Print status changes of every device, as pushed by the cloud")
    add("scenes", scenes, "List the scenes defined in the app")
    command = add("scene", scene, "Run a scene")
    command.add_argument("name", help="scene name or id")
    command = add("scan", scan, "Look for the devices on the LAN")
    command.add_argument("--timeout", type=float, default=8.0, help="seconds to listen")
    command = add("locate", locate, "Set a device's LAN address by hand")
    command.add_argument("device", help=device_help)
    command.add_argument("ip")
    command.add_argument("--protocol", help="protocol version, e.g. 3.4 (found out if omitted)")
    add("health", health, "Show login and device cache state")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(
        level=(logging.WARNING, logging.INFO, logging.DEBUG)[min(args.verbose, 2)],
        format="%(levelname)s %(name)s: %(message)s",
    )
    if not args.verbose:
        # The device handlers warn about every value a device reports outside its own spec.
        logging.getLogger("tuya_device_handlers").setLevel(logging.ERROR)
    try:
        data, text = args.handler(Tuya(args.home, cloud_fallback=not args.local), args)
    except (TuyaError, ValueError) as err:
        if args.json:
            print(json.dumps({"success": False, "error": str(err)}))
        else:
            print(f"error: {err}", file=sys.stderr)
        return 1
    if args.json and args.command not in ("watch", "listen"):
        print(json.dumps({"success": True, **data}))
    elif text:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
