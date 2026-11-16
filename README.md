# libtuya

Control Tuya (Smart Life / Tuya Smart) devices from Python, over your local
network, without a Tuya developer account and without Home Assistant.

```python
from libtuya import Tuya

tuya = Tuya()  # uses the login saved by `tuya login`
lamp = tuya.device("Living room")
lamp.turn_on()
lamp.entity("light").turn_on(brightness=128, kelvin=3000)
```

It joins three existing pieces and adds only the glue between them:

| Piece | From | What libtuya gets from it |
|---|---|---|
| Account access | [tuya-device-sharing-sdk] | QR-code login with the phone app, the device list, each device's local key and its datapoint map |
| Device knowledge | [Home Assistant]'s Tuya integration and [tuya-device-handlers] | Which datapoints form a light, a thermostat or a sensor, how their values scale, and fixes for products that misreport themselves |
| Local control | [TinyTuya] | Discovery and the LAN protocol, versions 3.1 to 3.5 |

After the first login the cloud is only contacted when a device cannot be
reached on the LAN.

> **Status.** Version 2.0 is a rewrite. It is tested against a simulated
> device speaking the real LAN protocol and against Home Assistant's corpus of
> real-device dumps, but not yet against a live account or physical devices.
> Reports are welcome.

## Install

Python 3.13 or newer.

```bash
pip install git+https://github.com/rjt-rockx/libtuya.git
```

## Command line

```bash
tuya login
```

It asks for your **user code** (in the Smart Life or Tuya Smart app: *Me* >
gear icon > *Account and Security* > *User Code*) and shows a QR code. Scan it
with the app (*+* > *Scan*) and approve. The app's consent screen says "Home
Assistant"; see [NOTICE.md](NOTICE.md#the-home-assistant-client-id) for why.
App brands other than Smart Life and Tuya Smart do not work with this login.

```bash
tuya devices                         # list devices and where they are on the LAN
tuya control "Living room" on        # by name, part of a name, number or id
tuya control 1 toggle
tuya control lamp brightness 60      # percent
tuya control lamp color ff8800
tuya control lamp temperature 3000   # kelvin for a light, degrees for a thermostat
tuya info lamp                       # every entity and its current value
tuya set heater number.temp_set 21.5
tuya set lamp light brightness=128 color_temp=4000
tuya set plug countdown_1 60 --raw   # a raw DP code, unscaled
tuya watch plug                      # print changes as the device reports them
```

Every command takes `--json`. `tuya --local ...` never falls back to the
cloud. `tuya devices --refresh` asks the cloud again (new devices, changed
keys) and rescans the LAN.

## Library

```python
from libtuya import Tuya

tuya = Tuya()  # state in ~/.libtuya, or Tuya("/some/dir")

# First time only. show_qr gets the text to render as a QR code.
tuya.login("your-user-code", show_qr=print)

for device in tuya.devices():
    print(device.name, device.category, device.address)

plug = tuya.device("Desk plug")
plug.refresh()  # read the device, returns status by DP code
plug.status  # {"switch_1": True, "cur_power": 127, ...}
plug.transport  # "lan" or "cloud": what served the last call
plug.turn_off()
plug.set(countdown_1=60)  # raw DP codes, unscaled values

for entity in plug.entities:  # what Home Assistant would show
    print(entity.id, entity.name, entity.state())
plug.entity("sensor.cur_power").value  # 12.7  (scaled, in entity.wrappers[...].native_unit)

lamp = tuya.device("Living room")
light = lamp.entity("light")
light.turn_on(brightness=200, hs=(30, 80))  # brightness 0-255, hue 0-360, saturation 0-100
light.set(color_temp=2700)

for changed in plug.watch():  # blocks; pushes from the device
    print(changed)
```

The API is synchronous, because TinyTuya and the sharing SDK are. From asyncio
use `await asyncio.to_thread(lamp.turn_on)`. Calls on one device are
serialised, so sharing a `Tuya` between threads is fine.

Errors are exceptions, all subclasses of `libtuya.TuyaError`: `NotLoggedIn`,
`DeviceNotFound`, `CloudError`, `LanError`.

The layers are usable on their own: `libtuya.lan` (discovery, connections),
`libtuya.dpmap` (LAN datapoints to and from cloud codes), `libtuya.entities`.
[docs/architecture.md](docs/architecture.md) explains how they fit.

## What to expect

- **One connection per device.** Most devices accept a single LAN connection.
  If the phone app, Home Assistant or another tool is holding it, libtuya
  falls back to the cloud. libtuya itself connects per call and lets go,
  except during `watch`.
- **Devices that are not on the LAN.** Battery-powered and Bluetooth-only
  devices never answer locally; they are controlled through the cloud.
- **Sub-devices** (Zigbee and the like) are reached through their gateway,
  which libtuya identifies by its shared local key.
- **Other subnets, VLANs, Docker.** Discovery relies on broadcasts. Where they
  do not arrive, give the address once: `tuya locate DEVICE 192.168.4.20`.
- **Re-paired devices get a new local key.** Run `tuya devices --refresh`.
- **Some writes always use the cloud**: datapoints whose LAN form cannot be
  derived from the cloud value (light scenes and music mode, a few
  enumerations). Reading them locally works.
- **Thermostats are in Celsius.**
- **Not covered**: camera streams, infrared remotes, scenes, cloud push
  updates, and devices for which the cloud publishes no datapoints.

## How it compares

| | Needs Home Assistant | Needs a developer account | Control | Meaning of datapoints |
|---|---|---|---|---|
| Home Assistant `tuya` | yes | no | cloud | per-category tables + product fixes |
| localtuya | yes | for automatic keys | local | configured by hand |
| tuya-local | yes | no | local | database of 1,790 device files |
| TinyTuya | no | for its key wizard | local | none; raw datapoints |
| **libtuya** | no | no | local, cloud fallback | Home Assistant's tables + product fixes |

More in [docs/comparison.md](docs/comparison.md), including where the others
are stronger.

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check . && ruff format --check .
```

Home Assistant's Tuya integration is vendored under `third_party/` and turned
into `libtuya/data/ha_tuya.json`. To move to a newer Home Assistant release:

```bash
scripts/sync-upstream.sh 2026.12.0
```

then update the two pinned versions in `pyproject.toml` if the tests say so.
See [third_party/README.md](third_party/README.md).

## Licence and credits

MIT for libtuya's own code; the data derived from Home Assistant is
Apache-2.0. [NOTICE.md](NOTICE.md) lists everything this project builds on.

[tuya-device-sharing-sdk]: https://github.com/tuya/tuya-device-sharing-sdk
[Home Assistant]: https://github.com/home-assistant/core/tree/dev/homeassistant/components/tuya
[tuya-device-handlers]: https://github.com/home-assistant-libs/tuya-device-handlers
[TinyTuya]: https://github.com/jasonacox/tinytuya
