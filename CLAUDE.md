# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

libtuya controls Tuya (Smart Life) devices from Python over the LAN, with no
Tuya developer account and no Home Assistant. It is a library first; the `tuya`
command is a thin front end to it.

It is deliberately glue between three upstream projects, and should stay that
way: prefer using or updating an upstream dependency over writing device
knowledge or protocol code here.

| Need | Comes from |
|---|---|
| QR login, device list, local keys, datapoint maps | `tuya-device-sharing-sdk` |
| What a device's datapoints mean and how values scale | Home Assistant's Tuya tables (vendored, generated into `libtuya/data/ha_tuya.json`) and `tuya-device-handlers` |
| LAN discovery and protocol | `tinytuya` |

Read `docs/architecture.md` before changing how the layers fit.

## Commands

```bash
pip install -e ".[dev]"
pytest                                  # about a second; no network or hardware needed
ruff check . && ruff format --check .   # line length 100
scripts/sync-upstream.sh <ha-release>   # refresh third_party/ and the generated data
python scripts/gen_ha_tables.py         # regenerate the data only
```

Python 3.13+ (required by `tuya-device-handlers`).

## Layout

- `libtuya/client.py` — `Tuya`: saved login, saved device list, lookups, LAN scans. Only module that touches disk.
- `libtuya/cloud.py` — all traffic to Tuya's servers; device records for the cache.
- `libtuya/lan.py` — discovery and `Connection` (one TinyTuya session, locked, errors as exceptions).
- `libtuya/dpmap.py` — LAN datapoints (`{"20": true}`) to and from cloud codes (`{"switch_led": true}`).
- `libtuya/device.py` — `Device`: status, LAN-first transport with cloud fallback, entities.
- `libtuya/entities.py` — `Entity`, `Light`: Home Assistant's view of a device.
- `libtuya/cli.py` — the `tuya` command, using only the public API.
- `scripts/` — upstream sync and the table generator.
- `third_party/home-assistant-core/` — unmodified upstream snapshot. Never edit; see `third_party/README.md`.
- `tests/` — `fake_device.py` is a TCP server speaking the real LAN protocol; devices come from Home Assistant's fixtures.

## Rules of the road

- **Everything above `device.py` speaks cloud terms** (DP codes, cloud-format values). Only `dpmap.py` and `lan.py` know datapoint ids and raw values.
- **Do not guess datapoint ids or invent device tables.** If the cloud gives no map for a device, it is controlled through the cloud.
- **`libtuya/data/ha_tuya.json` is generated.** Change `scripts/gen_ha_tables.py` or re-sync; a test fails if the file and the vendored source disagree.
- **The handlers and SDK pins in `pyproject.toml` follow the vendored Home Assistant release's `manifest.json`.** The generated tables reference handler classes by name.
- **Licensing.** libtuya is MIT; data derived from Home Assistant is Apache-2.0. localtuya and hass-localtuya are GPL-3.0: do not copy code or data from them. Record anything taken from elsewhere in `NOTICE.md`.
- **Never raise TinyTuya's log level to DEBUG**: it logs local keys and weakens protocol 3.5 encryption.
- **The library does not print or prompt.** Errors are `TuyaError` subclasses; interaction lives in `cli.py`.
- **Tests** go through the real TinyTuya client against `FakeTuyaDevice`, or use real device dumps. Prefer one test of real behaviour over several of mocks.

## What cannot be tested here

The cloud (login, device listing, cloud commands) and physical devices. Cloud
code is exercised with the SDK's network layer replaced; say so when a change
depends on live behaviour.
