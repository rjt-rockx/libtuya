"""The `tuya` command: a thin front end to the library."""

from __future__ import annotations

import argparse
import colorsys
import json
import logging
import sys
import time
from collections.abc import Callable
from typing import Any

from . import Device, Entity, Light, Tuya, TuyaError, __version__

USER_CODE_HINT = "Smart Life or Tuya Smart app: Me > Settings > Account and Security > User Code"

# A command returns the data for --json and the text for people.
Result = tuple[dict[str, Any], str]


def _show(value: Any) -> str:
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, tuple):
        return "(" + ", ".join(_show(item) for item in value) + ")"
    return str(value)


def _jsonable(value: Any) -> Any:
    return value if isinstance(value, (bool, int, float, str, type(None))) else _show(value)


def _parse(text: str) -> Any:
    """Read a command-line value: on/off, JSON, or plain text."""
    if text.lower() in ("on", "off"):
        return text.lower() == "on"
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _entity_line(entity: Entity) -> str:
    state = entity.state()
    if len(state) == 1:
        ((attribute, value),) = state.items()
        unit = getattr(entity.wrappers[attribute], "native_unit", None) or ""
        shown = f"{_show(value)} {unit}".rstrip()
    else:
        shown = "  ".join(
            f"{key}={_show(value)}" for key, value in state.items() if value is not None
        )
    return f"  {entity.id:34} {entity.name or '':28} {shown}"


def _device_data(device: Device) -> dict[str, Any]:
    return {
        "id": device.id,
        "name": device.name,
        "category": device.category,
        "product": device.info.product_name,
        "ip": device.address.ip if device.address else None,
        "version": device.address.version if device.address else None,
    }


def _describe(device: Device) -> Result:
    """Current state of a device, entity by entity."""
    entities = {
        entity.id: {
            "name": entity.name,
            "state": {key: _jsonable(value) for key, value in entity.state().items()},
        }
        for entity in device.entities
    }
    address = device.address or "not found"
    lines = [
        f"{device.name}  [{device.info.product_name}, category {device.category}]",
        f"  id {device.id}   LAN {address}   read via {device.transport or 'cache'}",
        *(_entity_line(entity) for entity in device.entities),
    ]
    if not device.entities:
        lines += ["  (no known entities; raw status below)", f"  {device.status}"]
    data = _device_data(device) | {
        "transport": device.transport,
        "status": device.status,
        "entities": entities,
    }
    return {"device": data}, "\n".join(lines)


def login(tuya: Tuya, args: argparse.Namespace) -> Result:
    if tuya.logged_in and not args.force:
        return {"message": "Already logged in"}, "Already logged in (use --force to log in again)."
    user_code = args.user_code or input(f"User code ({USER_CODE_HINT}): ").strip()

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
    devices = tuya.devices(refresh=True)
    found = sum(1 for device in devices if device.address)
    text = f"Logged in. {len(devices)} devices, {found} found on the LAN."
    return {"message": "Logged in", "devices": len(devices), "on_lan": found}, text


def logout(tuya: Tuya, args: argparse.Namespace) -> Result:
    tuya.logout()
    return {"message": "Logged out"}, "Logged out."


def devices(tuya: Tuya, args: argparse.Namespace) -> Result:
    found = tuya.devices(refresh=args.refresh)
    rows = [
        (str(index), device.name, device.info.product_name, device.category, _lan(tuya, device))
        for index, device in enumerate(found, 1)
    ]
    header = ("#", "Name", "Product", "Cat.", "LAN")
    widths = [max(len(row[column]) for row in [header, *rows]) for column in range(len(header))]
    lines = [
        "  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)).rstrip()
        for row in [header, *rows]
    ]
    data = [_device_data(device) | {"index": index} for index, device in enumerate(found, 1)]
    return {"devices": data, "count": len(data)}, "\n".join(lines)


def _lan(tuya: Tuya, device: Device) -> str:
    if device.address:
        return str(device.address)
    gateway = tuya.gateway_of(device)
    return f"via {gateway.name}" if gateway else "not found (cloud only)"


def info(tuya: Tuya, args: argparse.Namespace) -> Result:
    device = tuya.device(args.device)
    device.refresh()
    return _describe(device)


def control(tuya: Tuya, args: argparse.Namespace) -> Result:
    device = tuya.device(args.device)
    action = args.action.lower()
    value = args.value

    def need_value() -> str:
        if value is None:
            raise TuyaError(f"`{action}` needs a value")
        return value

    def light() -> Light:
        entity = device.entity(args.entity) if args.entity else device.power
        if not isinstance(entity, Light):
            raise TuyaError(f"{entity.id} is not a light")
        return entity

    if action == "status":
        device.refresh()
        return _describe(device)
    if action in ("on", "off"):
        entity = device.entity(args.entity) if args.entity else device.power
        entity.set(switch=action == "on")
    elif action == "toggle":
        device.refresh()
        entity = device.entity(args.entity) if args.entity else device.power
        entity.set(switch=not entity.value)
    elif action == "brightness":
        percent = float(need_value())
        if not 0 <= percent <= 100:
            raise TuyaError("brightness is a percentage, 0 to 100")
        device.refresh()  # whether to dim the colour or the white depends on the current mode
        light().turn_on(brightness=percent * 255 / 100)
    elif action == "color":
        text = need_value().lstrip("#")
        if len(text) != 6:
            raise TuyaError("color is given as RRGGBB, for example ff8800")
        red, green, blue = (int(text[index : index + 2], 16) / 255 for index in (0, 2, 4))
        hue, saturation, brightness = colorsys.rgb_to_hsv(red, green, blue)
        light().turn_on(hs=(hue * 360, saturation * 100), brightness=round(brightness * 255))
    elif action == "temperature":
        number = float(need_value())
        if args.entity or any(isinstance(entity, Light) for entity in device.entities):
            light().turn_on(kelvin=round(number))  # colour temperature in kelvin
        else:
            device.entity("climate").set(set_temperature=number)
    else:
        raise TuyaError(f"unknown action {action!r}")
    data = {"device": device.name, "action": action, "value": value, "transport": device.transport}
    return data, f"{device.name}: {action}{' ' + value if value else ''} (via {device.transport})"


def set_(tuya: Tuya, args: argparse.Namespace) -> Result:
    device = tuya.device(args.device)
    if args.raw:
        if len(args.values) != 1:
            raise TuyaError("--raw takes a DP code and one value")
        device.set({args.target: _parse(args.values[0])})
        target = args.target
    else:
        entity = device.entity(args.target)
        if all("=" in value for value in args.values):
            pairs = (value.split("=", 1) for value in args.values)
            entity.set(**{attribute: _parse(value) for attribute, value in pairs})
        elif len(args.values) == 1:
            entity.set(_parse(args.values[0]))
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
                print(json.dumps(changed), flush=True)
            else:
                shown = "  ".join(f"{code}={_show(value)}" for code, value in changed.items())
                print(f"{time.strftime('%H:%M:%S')}  {shown}", flush=True)
    except KeyboardInterrupt:
        pass
    return {}, ""


def scan(tuya: Tuya, args: argparse.Namespace) -> Result:
    found = tuya.scan(args.timeout)
    names = {device.id: device.name for device in tuya.devices()}
    lines = [f"{names[dev_id]:30} {address}" for dev_id, address in found.items()]
    data = {"found": {dev_id: vars(address) for dev_id, address in found.items()}}
    return data, "\n".join(lines) or "No devices answered."


def locate(tuya: Tuya, args: argparse.Namespace) -> Result:
    device = tuya.device(args.device)
    address = tuya.locate(device, args.ip, args.protocol)
    return {
        "device": device.name,
        **vars(address),
    }, f"{device.name}: {address}"


def health(tuya: Tuya, args: argparse.Namespace) -> Result:
    known = tuya.devices() if tuya.logged_in or (tuya.home / "devices.json").exists() else []
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
        prog="tuya", description="Control Tuya devices, locally where possible."
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

    command = add(
        "login", login, "Log in by scanning a QR code with the Smart Life or Tuya Smart app"
    )
    command.add_argument("-u", "--user-code", help=USER_CODE_HINT)
    command.add_argument(
        "--force", action="store_true", help="log in again even if a session exists"
    )
    add("logout", logout, "Revoke the login and delete saved keys")
    command = add("devices", devices, "List devices")
    command.add_argument(
        "--refresh", action="store_true", help="ask the cloud again and rescan the LAN"
    )
    command = add("info", info, "Show a device and the current state of its entities")
    command.add_argument("device", help="number from `tuya devices`, name, part of a name, or id")
    command = add(
        "control", control, "Switch a device, or set a light's brightness, color or temperature"
    )
    command.add_argument("device")
    command.add_argument(
        "action",
        help="on, off, toggle, status, brightness PERCENT, color RRGGBB, temperature VALUE",
    )
    command.add_argument("value", nargs="?")
    command.add_argument(
        "-e", "--entity", help="act on this entity instead of the device's main one"
    )
    command = add(
        "set",
        set_,
        "Set an entity (`set DEVICE number.temp_set 21.5`, `set DEVICE light brightness=128`)",
    )
    command.add_argument("device")
    command.add_argument("target", help="entity id, key or name; with --raw, a DP code")
    command.add_argument("values", nargs="+", metavar="VALUE")
    command.add_argument(
        "--raw", action="store_true", help="write a DP code with an unscaled value"
    )
    command = add("watch", watch, "Print status changes as the device reports them")
    command.add_argument("device")
    command = add("scan", scan, "Look for the devices on the LAN")
    command.add_argument("--timeout", type=float, default=8.0)
    command = add("locate", locate, "Set a device's LAN address by hand")
    command.add_argument("device")
    command.add_argument("ip")
    command.add_argument("--protocol", help="protocol version, e.g. 3.4 (probed if omitted)")
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
        message = str(err)
        if args.json:
            print(json.dumps({"success": False, "error": message}))
        else:
            print(f"error: {message}", file=sys.stderr)
        return 1
    if args.json and args.command != "watch":
        print(json.dumps({"success": True, **data}, default=str))
    elif text:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
