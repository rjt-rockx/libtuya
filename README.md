# libtuya

A Python library for controlling Tuya (Smart Life / Tuya Smart) devices over
your local network, with the device knowledge of Home Assistant's Tuya
integration and without running Home Assistant.

```python
from libtuya import Climate, Light, Tuya

tuya = Tuya()  # the login saved in ~/.libtuya
lamp = tuya.device("Living room")  # by name, part of a name, or id
lamp.entity("light", Light).turn_on(brightness=128, color_temp_kelvin=3000)

heater = tuya.device("Bedroom heater").entity("climate", Climate)
heater.set_hvac_mode("heat")
heater.set_temperature(21)
print(heater.current_temperature, heater.hvac_modes)
```

Log in once with the phone app (or a Tuya developer project). From then on
your devices are controlled directly over the LAN, by name, through entities
that behave like Home Assistant's: a light has `brightness` and `hs_color`,
a thermostat `hvac_mode` and `set_temperature()`, a blind
`current_position` and `open()`. A device that cannot be reached locally is
controlled through the cloud instead.

libtuya is glue between three projects and adds as little as it can:

| Piece | From | What libtuya gets from it |
|---|---|---|
| Account access | [tuya-device-sharing-sdk] | QR-code login with the phone app, the device list, each device's local key and its datapoint map; scenes and cloud push |
| Device knowledge | [Home Assistant]'s Tuya integration and [tuya-device-handlers] | Which datapoints form a light, a thermostat or a sensor, how their values scale, fixes for products that misreport themselves, and how each kind of entity behaves |
| Local control | [TinyTuya] | Discovery and the LAN protocol, versions 3.1 to 3.5; a developer project's cloud API |

> **Status.** Version 2.0 is a rewrite. It is tested against a simulated
> device that speaks the real LAN protocol, against a fake of Tuya's cloud
> service driven through the real SDK, and against Home Assistant's
> recordings of 329 real devices, but not yet against a live account or
> physical devices. Reports are welcome.

## Install

Python 3.13 or newer.

```bash
pip install git+https://github.com/rjt-rockx/libtuya.git
```

## Log in

Either way of logging in stores a session in `~/.libtuya` (or `$LIBTUYA_HOME`, or the
directory passed as `Tuya(home)`), saves the device list with each device's
local key, and looks for the devices on the LAN.

**With the Smart Life or Tuya Smart app** (no developer account needed):

```bash
tuya login
```

It asks for your **user code** (in the app: *Me* > gear icon > *Account and
Security* > *User Code*) and shows a QR code. Scan it with the app (*+* >
*Scan*) and approve. The app's consent screen says "Home Assistant": libtuya
uses the client id Tuya issued to Home Assistant, as other projects do
([docs/login.md](docs/login.md) explains what that means). Apps of other
brands do not offer this login.

From Python, `show_qr` receives the text to show as a QR code:

```python
tuya.login("your-user-code", show_qr=print)
tuya.devices(refresh=True)
```

**With a Tuya developer project**, if you already have one (TinyTuya's
wizard and localtuya use them) and your app account is linked to it:

```bash
tuya login --access-id ID --region eu --uid APP_ACCOUNT_UID
```

See [With a developer project](#with-a-developer-project).

## Using the library

### Devices

```python
from libtuya import Sensor, Tuya

tuya = Tuya()  # Tuya(home=None, *, cloud_fallback=True, timeout=5.0)
for device in tuya.devices():  # the saved list; devices(refresh=True) asks the cloud again
    print(device.name, device.category, device.product_name)

tuya.saved_devices()  # the saved list only: never asks the cloud or scans
plug = tuya.device("Desk plug")  # or tuya.device(3): the number `tuya devices` shows
plug.refresh()  # read the device; returns its status by DP code
plug.status  # {"switch_1": True, "cur_power": 143, ...}
plug.transport  # "lan" or "cloud": what served the last call
plug.turn_off()  # the device's main switch, light, fan ...
plug.set_raw(countdown_1=60)  # DP codes directly, with the cloud's raw values
```

Every call connects, does its work and lets go, because most devices accept
only one LAN connection and the phone app may want it. To do several things
in a row on one connection:

```python
with lamp.connected():
    lamp.refresh()
    lamp.entity("light", Light).turn_on(hs_color=(30, 80))
```

### Entities

A device is a set of entities, the ones Home Assistant creates for it
(less any with nothing to read or write). Each kind has a class with Home Assistant's properties, actions and
units: brightness 0-255, positions and percentages 0-100 (100 is open),
colour as hue 0-360 and saturation 0-100.

```python
for entity in plug.entities:
    print(entity.id, entity.name, entity.summary())
# select.relay_status Power-on behavior {'state': 'memory', 'options': ['off', 'on', 'memory']}
# sensor.cur_power    Power             {'state': 14.3}
# switch.switch_1     Switch 1          {'state': 'on'}
# ...

power = plug.entity("sensor.cur_power", Sensor)
power.value, power.unit  # 14.3, "W"
```

`device.entity(ref)` finds an entity by id (`light.switch_led`), key,
platform or name; with a class as second argument it also checks the kind and
tells a type checker what comes back. All classes are importable from
`libtuya`:

| Class | Reads | Does |
|---|---|---|
| `Light` | `is_on`, `brightness`, `color_mode`, `supported_color_modes`, `hs_color`, `color_temp_kelvin`, `min_/max_color_temp_kelvin` | `turn_on(brightness=, color_temp_kelvin=, hs_color=, white=)`, `turn_off()` |
| `Climate` | `hvac_mode(s)`, `current_temperature`, `target_temperature`, `min_temp`, `max_temp`, `target_temperature_step`, `preset_mode(s)`, `fan_mode(s)`, `swing_mode(s)`, humidity | `set_hvac_mode`, `set_temperature`, `set_preset_mode`, `set_fan_mode`, `set_swing_mode`, `set_humidity` |
| `Cover` | `current_position`, `current_tilt_position`, `is_closed` | `open`, `close`, `stop`, `set_position`, `set_tilt_position` |
| `Valve` | `is_open`, `is_closed` | `open`, `close` |
| `Fan` | `is_on`, `percentage`, `percentage_step`, `preset_mode(s)`, `oscillating`, `current_direction` | `turn_on(percentage=, preset_mode=)`, `set_percentage`, `set_preset_mode`, `oscillate`, `set_direction` |
| `Humidifier` | `is_on`, `current_humidity`, `target_humidity`, `mode`, `available_modes`, `device_class` | `set_humidity`, `set_mode`, `turn_on`, `turn_off` |
| `Vacuum` | `activity`, `fan_speed`, `fan_speed_list` | `start`, `stop`, `pause`, `return_to_base`, `locate`, `set_fan_speed` |
| `AlarmControlPanel` | `alarm_state`, `changed_by` | `arm_home`, `arm_away`, `disarm`, `trigger` |
| `Camera` | `is_recording`, `motion_detection_enabled` | `stream_source()`, `enable_/disable_motion_detection` |
| `Switch`, `Siren` | `is_on` | `turn_on`, `turn_off` |
| `Number` | `value`, `min`, `max`, `step`, `unit` | `set(value)` |
| `Select` | `option`, `options` | `select(option)` |
| `Sensor` | `value`, `unit`, `options` | |
| `BinarySensor` | `is_on` | |
| `Button` | | `press()` |
| `Event` | `event_type`, `event_types`, `event_attributes` | |

Every entity also has a generic side: `summary()` is what Home Assistant
would show (its state and attributes), `describe()` lists each underlying
attribute with its value, unit, limits and choices, and `set(**attributes)`
writes them. An action sends the same commands Home Assistant's entity
would, in one call. Where Home Assistant would quietly drop or convert an
argument the device cannot use, libtuya raises instead; values are still
rounded to the device's step, as there.

Values are as of the last `refresh()`, write or push; before any, they are
the ones saved with the device list.

### Live updates

```python
for changed in plug.watch():  # blocks; the full status first, then each change
    print(changed)  # {"cur_power": 131}

stop = tuya.subscribe(lambda device, changed: print(device.name, changed))
...  # pushes from the cloud, for every device, on a thread
stop()
```

`watch()` holds the device's one connection while it runs. `subscribe()`
needs the app login and uses Tuya's MQTT service.

### Scenes and cameras

```python
for scene in tuya.scenes():  # the app's tap-to-run scenes
    print(scene.name)
tuya.run_scene("Good night")

doorbell.stream_url("rtsp")  # or hls, flv, rtmp: a short-lived URL from the cloud
```

### Errors, threads and asyncio

Failures raise subclasses of `libtuya.TuyaError`: `NotLoggedIn`,
`DeviceNotFound`, `CloudError`, `LanError` (with TinyTuya's error `code`) and
`Unmapped`. A value a device does not accept raises `ValueError`.

A write that may have reached the device without being acknowledged raises
`LanError` rather than being repeated through the cloud, because repeating a
one-shot command ("feed now") could run it twice. With
`Tuya(cloud_fallback=False)` a device the LAN cannot serve raises instead of
going through the cloud; refreshing the device list, scenes, `subscribe()`
and stream URLs still use it.

The API is synchronous, because TinyTuya and the sharing SDK are. From
asyncio use `await asyncio.to_thread(lamp.turn_on)`. Calls on one device are
serialised and cloud requests are made one at a time, so sharing a `Tuya`
between threads is fine.

The lower layers are usable on their own: `libtuya.lan` (discovery,
connections) and `libtuya.dpmap` (LAN datapoints to and from cloud codes).
[docs/architecture.md](docs/architecture.md) explains how the layers fit.

## Command line

The `tuya` command is a thin front end to the library.

```bash
tuya devices                          # list devices and where they are on the LAN
tuya devices --refresh                # ask the cloud again (new devices, changed keys), rescan
tuya info lamp                        # every entity and its current value
tuya control "Living room" on         # by name, part of a name, number or id
tuya control 1 toggle
tuya control lamp brightness 60       # percent
tuya control lamp color ff8800
tuya control lamp temperature 3000    # kelvin for a light, degrees for a thermostat
tuya control heater mode heat         # also: preset, speed, humidity
tuya control blinds position 40       # also: open, close, stop
tuya control robot return_to_base     # also: start, pause, locate, press, arm_away ...
tuya set heater climate set_temperature=21.5
tuya set plug countdown_1 60 --raw    # a raw DP code, unscaled
tuya watch plug                       # the status, then changes as the device reports them
tuya listen                           # changes of every device, from the cloud
tuya scenes
tuya scene "Good night"
tuya scan
tuya locate lamp 192.168.4.20
```

Every command takes `--json`; `tuya --local ...` never falls back to the cloud; `-v`
shows what happens.

## With a developer project

If you use TinyTuya or localtuya you may already have a cloud project on
Tuya's IoT Platform. libtuya can log in with it instead of the app:

```bash
tuya login --access-id ID --region eu --uid APP_ACCOUNT_UID   # the Access Secret is asked for
tuya login --access-id ID --region eu --device-id ANY_DEVICE_ID
```

```python
tuya.login_developer("access-id", "access-secret", "eu", uid="...")  # or device_id="..."
```

What the project needs, as TinyTuya's README describes it: a cloud project
on [iot.tuya.com](https://iot.tuya.com/) in the data centre of your app
account (not always the obvious one), your app account linked to it
(*Devices* > *Link Tuya App Account*), and the *IoT Core* and
*Authorization* services subscribed under *Service API*. IoT Core is a free
trial that has to be extended every few months. Regions are `cn`, `us`,
`us-e`, `eu`, `eu-w`, `in` and `sg`. The UID is shown with the linked
account; `--device-id` with any one of your devices finds it instead.

From `tinytuya.json`: `apiKey` is the Access ID, `apiSecret` the Access
Secret, `apiRegion` the region, and any device id in it works as
`--device-id`. Leave your products in Tuya's default instruction mode;
"DP instruction" mode is not supported.

Compared with the app login:

- Scenes, cloud push (`subscribe`) and camera stream URLs are not available.
- A datapoint is used on the LAN only where the device's own description
  confirms its local form; check what was left out with
  `tuya -v devices --refresh`. The rest is written through the cloud and
  read from it when the device list is refreshed or the LAN fails.
- Counters that report increments (energy) read as plain values.
- Cloud requests count against the trial's quota: a refresh makes one for
  the list and two per kind of device, and a device that answers on the LAN
  makes none. TinyTuya
  sends them without a timeout.
- `logout` only deletes the saved files; the Access Secret stays valid.

## What to expect

- **One connection per device.** Most devices accept a single LAN
  connection. If the phone app, Home Assistant or another tool is holding it,
  libtuya falls back to the cloud.
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
- **A status is what the device last reported.** Some metering plugs update
  power readings on the LAN only when asked in a way libtuya does not use
  yet.
- **The cloud is flaky at times.** A refresh that fails, or describes a
  device only in part, keeps what was saved (`tuya devices` marks such a
  device with `*`). Network errors name the host; with the app login,
  requests time out after 5 s connecting and 30 s waiting.
- **Thermostats work in Celsius**, also one set to Fahrenheit; a temperature
  sensor reads in the device's own unit (`Sensor.unit`).
- **Not covered**: infrared and RF remotes, and devices for which the cloud
  publishes no datapoints.

## How it compares

| | Needs Home Assistant | Needs a developer account | Control | Meaning of datapoints |
|---|---|---|---|---|
| Home Assistant `tuya` | yes | no | cloud | per-category tables + product fixes |
| localtuya | yes | for automatic keys | local | configured by hand |
| hass-localtuya | yes | for automatic keys and setup | local | category tables + the developer API's dp map |
| tuya-local | yes | no | local | database of 1,790 device files |
| TinyTuya | no | for its key wizard | local | raw datapoints; classes for some device types |
| **libtuya** | no | no (either works) | local, cloud fallback | Home Assistant's tables, product fixes and entity behaviour |

More in [docs/comparison.md](docs/comparison.md), including where the others
are stronger.

## Development

```bash
pip install -e ".[dev]"
pytest                                  # a few seconds; no network or hardware needed
ruff check . && ruff format --check .
mypy libtuya
```

The tests run the real TinyTuya client against `tests/fake_device.py`, a
device that speaks the LAN protocol, and the real sharing SDK against
`tests/fake_cloud.py`, a fake of Tuya's service. Every entity class is
compared with what Home Assistant recorded for the same 329 devices.

Home Assistant's Tuya integration is vendored under `third_party/` and turned
into `libtuya/data/ha_tuya.json`. To move to a newer Home Assistant release:

```bash
scripts/sync-upstream.sh 2026.12.0
```

then update the two pinned versions in `pyproject.toml` if the tests say so.
See [third_party/README.md](third_party/README.md).

## Licence and credits

MIT for libtuya's own code; the data and behaviour derived from Home
Assistant are Apache-2.0. [NOTICE.md](NOTICE.md) lists everything this
project builds on.

[tuya-device-sharing-sdk]: https://github.com/tuya/tuya-device-sharing-sdk
[Home Assistant]: https://github.com/home-assistant/core/tree/dev/homeassistant/components/tuya
[tuya-device-handlers]: https://github.com/home-assistant-libs/tuya-device-handlers
[TinyTuya]: https://github.com/jasonacox/tinytuya
