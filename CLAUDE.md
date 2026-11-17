# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

libtuya controls Tuya (Smart Life) devices from Python over the LAN, without
Home Assistant, after one login with the phone app's QR code (or, for those who
have one, a Tuya developer project). It is a library first; the `tuya`
command is a thin front end to it.

It is deliberately glue between three upstream projects, and should stay that
way: prefer using or updating an upstream dependency over writing device
knowledge or protocol code here.

| Need | Comes from |
|---|---|
| QR login, device list, local keys, datapoint maps | `tuya-device-sharing-sdk` |
| What a device's datapoints mean and how values scale | Home Assistant's Tuya tables (vendored, generated into `libtuya/data/ha_tuya.json`) and `tuya-device-handlers` |
| LAN discovery and protocol; the developer project's cloud API | `tinytuya` |

Read `docs/architecture.md` before changing how the layers fit.

## Commands

```bash
pip install -e ".[dev]"
pytest                                  # a few seconds; no network or hardware needed
ruff check . && ruff format --check .   # line length 100
mypy                                    # the package ships py.typed
scripts/sync-upstream.sh <ha-release>   # refresh third_party/ and the generated data
python scripts/gen_ha_tables.py         # regenerate the data only
```

Python 3.13+ (required by `tuya-device-handlers`).

## Layout

- `libtuya/client.py` — `Tuya`: saved login, saved device list, lookups, LAN scans. Only module that touches disk.
- `libtuya/cloud.py` — the QR login and all its traffic to Tuya's servers; device records for the cache.
- `libtuya/developer.py` — the same for a developer project, through TinyTuya's `Cloud`; maps a datapoint for the LAN only where the device's thing model confirms it.
- `libtuya/lan.py` — discovery and `Connection` (one TinyTuya session, locked, errors as exceptions).
- `libtuya/dpmap.py` — LAN datapoints (`{"20": true}`) to and from cloud codes (`{"switch_led": true}`).
- `libtuya/device.py` — `Device`: status, LAN-first transport with cloud fallback, entities.
- `libtuya/entities/` — `Entity` and one class per Home Assistant platform (`Light`, `Climate`,
  `Cover`, ...): Home Assistant's view of a device and its behaviour. `tests/test_ha_parity.py`
  checks every class's `summary()` against Home Assistant's recorded states.
- `libtuya/cli.py` — the `tuya` command, using only the public API.
- `scripts/` — upstream sync and the table generator.
- `third_party/home-assistant-core/` — unmodified upstream snapshot. Never edit; see `third_party/README.md`.
- `tests/` — `fake_device.py` is a TCP server speaking the real LAN protocol; `fake_cloud.py` fakes the sharing API under the real SDK, `fake_openapi.py` the developer API under TinyTuya's real `Cloud`; devices come from Home Assistant's fixtures.

## Rules of the road

- **Everything above `device.py` speaks cloud terms** (DP codes, cloud-format values). Only `dpmap.py` and `lan.py` know datapoint ids and raw values.
- **Do not guess datapoint ids or invent device tables.** If the cloud gives no map for a device, it is controlled through the cloud.
- **`libtuya/data/ha_tuya.json` is generated.** Change `scripts/gen_ha_tables.py` or re-sync; a test fails if the file and the vendored source disagree.
- **The handlers and SDK pins in `pyproject.toml` follow the vendored Home Assistant release's `manifest.json`.** The generated tables reference handler classes by name.
- **Licensing.** libtuya is MIT; data derived from Home Assistant is Apache-2.0. localtuya and hass-localtuya are GPL-3.0: do not copy code or data from them. Record anything taken from elsewhere in `NOTICE.md`.
- **Never raise TinyTuya's or the sharing SDK's log level to DEBUG**: they log local keys, tokens and a developer project's Access Secret, and TinyTuya's DEBUG weakens protocol 3.5 encryption.
- **The library does not print or prompt.** Errors are `TuyaError` subclasses; interaction lives in `cli.py`.
- **Tests** go through the real TinyTuya client against `FakeTuyaDevice`, the real SDKs against the HTTP fakes, or use real device dumps. Prefer one test of real behaviour over several of mocks.

## What cannot be tested here

The cloud (login, device listing, cloud commands) and physical devices. Cloud
code is exercised against HTTP-level fakes with the real SDKs on top; say so
when a change depends on live behaviour.
