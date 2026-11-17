# Architecture

libtuya is glue. Three upstream projects do the hard parts; this library joins
them so that one QR-code login is enough to control devices locally.

```
            tuya login (once)                     every call afterwards
 ┌─────────────────────────────────┐   ┌──────────────────────────────────────┐
 │ cloud.py                        │   │ entities/                            │
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
| `client.py` | `Tuya`: the saved login, the saved device list, finding a device by name, LAN scans. The only module that reads or writes the state directory. |
| `cloud.py` | Everything the QR login sends to Tuya's servers, through tuya-device-sharing-sdk. Turns the SDK's device objects into plain records for the cache and back. One lock around every request (the SDK renews its token without one). |
| `developer.py` | The same for a Tuya developer project, through TinyTuya's `Cloud`, producing the same records. |
| `lan.py` | Discovery by device id and a `Connection` that wraps one TinyTuya session: explicit errors, a lock, the device22 and protocol 3.2 special cases. |
| `dpmap.py` | Translation between LAN datapoints (`{"20": true}`) and cloud status (`{"switch_led": true}`), in both directions. |
| `device.py` | `Device`: holds the status, picks the transport, builds entities. |
| `entities/` | `Entity` and one class per Home Assistant platform (`Light`, `Climate`, `Cover`, `Fan`, `Sensor`, ...): Home Assistant's view of a device and its behaviour, built with tuya-device-handlers. |
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
nine in ten datapoints in Home Assistant's fixtures) and the two colour encodings.
A command that cannot be expressed locally goes through the cloud.

The SDK drops a device's whole map if a single datapoint cannot be pushed in
dp-id form. That limitation is about MQTT, not the LAN, so `cloud.py` fetches
the map itself in that case.

Values the device did not report are skipped, not decoded: the SDK's
conversions would turn a missing, empty or unknown enumeration value into the
first value the datapoint can take.

A developer project's API (`developer.py`) speaks the same cloud vocabulary
but does not publish the conversions. It is asked for the device's own
description ("thing model") as well, and a datapoint is mapped for the LAN
only where that confirms the same type and range, or where a colour's
saturation range names one of the SDK's two colour encodings. Everything
else goes through the cloud.

Because every transport ends up writing the same `status` dictionary in cloud
terms, everything above `device.py` is unaware of how a value arrived, and of
which kind of login listed the device.

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

`entities/base.py` then mirrors the dozen lines each Home Assistant platform
uses to call the handlers. The result is checked against Home Assistant itself: a
test derives the entity descriptions for every device fixture in the vendored
release and compares them, device by device, with Home Assistant's own test
snapshots. An entity with nothing to read or write (one climate entity among
the fixtures) is then left out; cameras are always kept, as Home Assistant
keeps them.

The handlers version is pinned to the one the vendored Home Assistant release
uses. The tables reference handler classes by name, and the handlers make no
compatibility promise to anyone but Home Assistant.

An `Entity` exposes the handlers' wrappers as named attributes with
`state()`, `describe()` and `set()`. On top of that, each platform has a class
that follows Home Assistant's entity class for it: properties under Home
Assistant's names and value domains (`is_on`, `brightness` 0-255, `hvac_mode`,
`current_position` 0-100 with 100 open, `percentage`, `activity` ...),
methods named after Home Assistant's services (`turn_on(brightness=...,
color_temp_kelvin=...)`, `set_hvac_mode`, `open`, `set_position`,
`set_percentage`, `return_to_base` ...), each sending the commands Home
Assistant would send in one call, and `summary()`, the state and attributes
Home Assistant would show.

`tests/test_ha_parity.py` compares `summary()` with Home Assistant's recorded
state for every fixture entity of every platform, and the per-platform tests
check the commands of the important actions against Home Assistant's own
tests. Where libtuya departs from Home Assistant it is to refuse instead of
guessing: an argument a device cannot use raises `TuyaError`, a bad value
`ValueError`, where Home Assistant sometimes drops or converts it.

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
- **A write is sent once.** A refusal comes back as an error reply and goes
  to the cloud; the return code in an acknowledgement is not a refusal (Tuya's
  open device code sends 1 for success). A write that may have arrived
  unacknowledged raises instead of being repeated through the cloud.
- **A refresh keeps what only the saved list has**: LAN addresses, a
  device's description when the cloud fails to give it this time, and the
  whole list when the cloud answers with none.

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
