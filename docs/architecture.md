# Architecture

libtuya is glue. Three upstream projects do the hard parts; this library joins
them so that one QR-code login is enough to control devices locally.

```
            tuya login (once)                     every call afterwards
 ┌─────────────────────────────────┐   ┌──────────────────────────────────────┐
 │ cloud.py                        │   │ entities.py                          │
 │ tuya-device-sharing-sdk         │   │ tuya-device-handlers + ha_tuya.json  │
 │  QR login, tokens               │   │  "light.turn_on(brightness=128)"     │
 │  device list, local keys        │   │        │ commands by DP code         │
 │  datapoint map per device       │   │        ▼                             │
 └───────────────┬─────────────────┘   │ device.py   LAN first, cloud second  │
                 │ saved by client.py  │        │                             │
                 ▼                     │        ▼                             │
        ~/.libtuya/devices.json ──────▶│ dpmap.py    DP code ⇄ dp id, values  │
        ~/.libtuya/session.json        │        │                             │
                                       │        ▼                             │
                                       │ lan.py      TinyTuya over TCP        │
                                       └──────────────────────────────────────┘
```

## Modules

| Module | Responsibility |
|---|---|
| `client.py` | `Tuya`: the saved login, the saved device list, finding a device by name, LAN scans. The only module that touches disk. |
| `cloud.py` | Everything that talks to Tuya's servers, through tuya-device-sharing-sdk. Turns the SDK's device objects into plain records for the cache and back. |
| `lan.py` | Discovery by device id and a `Connection` that wraps one TinyTuya session: explicit errors, a lock, the device22 and protocol 3.2 special cases. |
| `dpmap.py` | Translation between LAN datapoints (`{"20": true}`) and cloud status (`{"switch_led": true}`), in both directions. |
| `device.py` | `Device`: holds the status, picks the transport, builds entities. |
| `entities.py` | `Entity` and `Light`: Home Assistant's view of a device, built with tuya-device-handlers. |
| `cli.py` | The `tuya` command. Uses only the public API. |
| `data/ha_tuya.json` | Generated; see below. |

## The two vocabularies

A device on the LAN speaks numbered datapoints with raw values. The cloud, and
all device logic written against it (Home Assistant's, tuya-device-handlers'),
speaks named codes with normalised values:

| | LAN | Cloud |
|---|---|---|
| power | `"20": true` | `"switch_led": true` |
| brightness | `"22": 500` | `"bright_value_v2": 500` |
| colour | `"24": "007803e801f4"` | `"colour_data_v2": '{"h":120,"s":1000,"v":500}'` |

The cloud publishes the relation per device: for each datapoint id, the code
and the name of a conversion. tuya-device-sharing-sdk calls this
`local_strategy` and implements the conversions for reading (it needs them for
its own push messages). `dpmap.py` uses those for LAN reads and adds the
reverse direction for writes where an exact inverse exists: identity (about
95% of datapoints in Home Assistant's fixtures) and the two colour encodings.
A command that cannot be expressed locally goes through the cloud.

The SDK drops a device's whole map if a single datapoint cannot be pushed in
dp-id form. That limitation is about MQTT, not the LAN, so `cloud.py` fetches
the map itself in that case.

Because every transport ends up writing the same `status` dictionary in cloud
terms, everything above `device.py` is unaware of how a value arrived.

## Entities

Home Assistant's Tuya integration answers "which codes make up which
entity?" in per-category tables (for category `dj`: `switch_led` is the
switch, `bright_value_v2` or `bright_value` the brightness, and so on).
tuya-device-handlers, the library Home Assistant now delegates to, answers
"how do I read and write them?" with wrappers that scale values, convert
colours and patch known-bad products by product id.

The handlers are a normal dependency. The tables live inside Home Assistant
and are not published separately, so a snapshot of the integration is vendored
in `third_party/` and `scripts/gen_ha_tables.py` extracts the tables into
`data/ha_tuya.json`. The generator evaluates only the table definitions, with
every Home Assistant name replaced by a placeholder; it does not need Home
Assistant installed.

`entities.py` then mirrors the dozen lines each Home Assistant platform uses
to call the handlers. The result is checked against Home Assistant itself: for
its 336 device fixtures, libtuya builds exactly the entities recorded in Home
Assistant's own test snapshots.

The handlers version is pinned to the one the vendored Home Assistant release
uses. The tables reference handler classes by name, and the handlers make no
compatibility promise to anyone but Home Assistant.

An `Entity` exposes the handlers' wrappers as named attributes with
`state()` and `set()`. Only `Light.turn_on` adds behaviour of its own (mode
switching between white and colour), following Home Assistant's light entity.

## Transport policy

- **Read and write on the LAN** when the device has a known address and a
  datapoint map.
- **If nothing answers at the address**, listen for the device's broadcast
  once (it may have a new IP) and retry.
- **Otherwise use the cloud**, unless `cloud_fallback=False`.
- **Connect per call.** Devices usually accept one connection; holding it
  would lock out the phone app. `watch()` is the exception and says so.
- **One lock per connection.** TinyTuya is not thread-safe, and all
  sub-devices of a gateway share the gateway's connection.
- **Replies are merged, never trusted as snapshots.** Devices answer with
  whatever changed, and TinyTuya does not match replies to requests.

## Why synchronous

Both TinyTuya and the sharing SDK use blocking sockets, and TinyTuya's
maintainers ask that the protocol not be reimplemented. An async surface here
would be threads in disguise; callers who want one can use
`asyncio.to_thread`.

## What is deliberately absent

- A device database of libtuya's own. Knowledge about devices belongs
  upstream, where it is maintained and tested.
- Guessing datapoint ids. If the cloud gives no map for a device, libtuya uses
  the cloud for it rather than probe.
- Retry frameworks, caches with TTLs, plugin systems. One fallback, one cache
  file.
