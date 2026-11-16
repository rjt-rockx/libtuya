"""Translation between LAN datapoints and cloud status codes.

On the LAN a device speaks numbered datapoints with raw values, for example
``{"20": True, "24": "000003e803e8"}``. The cloud, and the device logic built
on it, speaks named codes: ``{"switch_led": True, "colour_data_v2":
'{"h": 0, "s": 1000, "v": 1000}'}``.

The cloud says how the two relate for every device (``local_strategy`` in
tuya-device-sharing-sdk): the code behind each datapoint id and the name of the
conversion that turns the raw value into the cloud one. The SDK implements
those conversions for reading. Writing needs the opposite direction, which is
implemented here for the conversions that have an exact inverse.
"""

from __future__ import annotations

import colorsys
import json
import logging
from collections.abc import Callable, Mapping
from typing import Any

from tuya_sharing import strategy

from .errors import Unmapped

_LOGGER = logging.getLogger(__name__)


def _as_dict(value: Any) -> dict[str, Any]:
    return json.loads(value) if isinstance(value, str) else value


def _hsv(value: Any, limits: tuple[int, int, int]) -> tuple[int, int, int]:
    """Hue, saturation and value of a cloud colour, checked to fit their hex fields."""
    colour = _as_dict(value)
    hsv = (round(colour["h"]), round(colour["s"]), round(colour["v"]))
    if not all(0 <= part <= limit for part, limit in zip(hsv, limits, strict=True)):
        raise ValueError(f"colour {hsv} is out of range")
    return hsv


def _encode_colour_v2(value: Any, config: dict[str, Any]) -> str:
    hue, saturation, brightness = _hsv(value, (0xFFFF, 0xFFFF, 0xFFFF))
    return f"{hue:04x}{saturation:04x}{brightness:04x}"


def _encode_colour_v1(value: Any, config: dict[str, Any]) -> str:
    hue, saturation, brightness = _hsv(value, (360, 255, 255))
    rgb = colorsys.hsv_to_rgb(hue / 360, saturation / 255, brightness / 255)
    red, green, blue = (round(channel * 255) for channel in rgb)
    return f"{red:02x}{green:02x}{blue:02x}{hue:04x}{saturation:02x}{brightness:02x}"


# Conversion name -> function turning a cloud value back into the raw one.
# Conversions missing here can be read from the LAN but are written via the
# cloud. That includes "enum": several raw values, of unknown type, can stand
# for one cloud value.
_ENCODERS: dict[str, Callable[[Any, dict[str, Any]], Any]] = {
    "default": lambda value, config: value,
    "dj_v2_color_alg": _encode_colour_v2,
    "dj_v1_hsv_alg": _encode_colour_v1,
}


class DpMap:
    """The datapoints of one device, built from its ``local_strategy``."""

    def __init__(self, local_strategy: Mapping[Any, Mapping[str, Any]] | None) -> None:
        # dp id -> (conversion name, config); code -> dp id
        self._by_id: dict[int, tuple[str, dict[str, Any]]] = {}
        self._by_code: dict[str, int] = {}
        for dp_id, item in (local_strategy or {}).items():
            # The SDK's conversions expect these two as JSON text; device dumps
            # sometimes carry them already parsed.
            config = dict(item["config_item"])
            for key in ("statusFormat", "valueDesc"):
                if not isinstance(config.get(key), str):
                    config[key] = json.dumps(config.get(key) or {})
            self._by_id[int(dp_id)] = (item["value_convert"], config)
            # A datapoint can be reported under one code and commanded under
            # another (e.g. `energy_reset` / `clear_energy`).
            for code in (*json.loads(config["statusFormat"]), item["status_code"]):
                self._by_code.setdefault(code, int(dp_id))

    def __bool__(self) -> bool:
        return bool(self._by_id)

    @property
    def dp_ids(self) -> list[int]:
        return sorted(self._by_id)

    def dp_id(self, code: str) -> int | None:
        """Datapoint id behind a status or command code."""
        return self._by_code.get(code)

    def decode(self, dps: Mapping[Any, Any]) -> dict[str, Any]:
        """Turn raw LAN datapoints into cloud status, skipping unknown ones."""
        status: dict[str, Any] = {}
        for dp_id, raw in dps.items():
            if (entry := self._by_id.get(int(dp_id))) is None:
                continue
            convert, config = entry
            try:
                code, value = strategy.convert(convert, (None, raw), config)
            except Exception as err:  # the SDK's conversions raise all sorts
                _LOGGER.debug("Cannot convert dp %s=%r with %s: %s", dp_id, raw, convert, err)
                continue
            status[code] = value
        return status

    def encode(self, commands: list[dict[str, Any]]) -> dict[str, Any]:
        """Turn cloud commands into raw LAN datapoints.

        Raises Unmapped if any command cannot be expressed on the LAN, so the
        caller can send the whole batch through the cloud instead.
        """
        dps: dict[str, Any] = {}
        for command in commands:
            code, value = command["code"], command["value"]
            if (dp_id := self._by_code.get(code)) is None:
                raise Unmapped(f"no datapoint known for {code!r}")
            convert, config = self._by_id[dp_id]
            if (encoder := _ENCODERS.get(convert)) is None:
                raise Unmapped(
                    f"{code!r} uses conversion {convert!r}, which is read-only on the LAN"
                )
            try:
                raw = encoder(value, config)
            except (KeyError, TypeError, ValueError) as err:
                raise Unmapped(f"cannot convert {code!r}={value!r} for the LAN: {err}") from err
            if isinstance(raw, str) and " " in raw:
                # TinyTuya strips every space from what it sends.
                raise Unmapped(f"text with spaces ({code!r}) cannot be sent over the LAN")
            dps[str(dp_id)] = raw
        return dps
