# How libtuya compares

Facts about the other projects were checked against their repositories on
16 November 2026. libtuya 2.0 itself has been tested against a simulated
device, a stubbed cloud and Home Assistant's device dumps, and not yet against
a live account or physical devices.

## The projects libtuya builds on or sits next to

| | [Home Assistant `tuya`][ha] | [localtuya] | [hass-localtuya] | [tuya-local] | [TinyTuya] | libtuya |
|---|---|---|---|---|---|---|
| Runs without Home Assistant | no | no | no | no | yes | yes |
| Works without a Tuya developer account | yes (QR login) | keys typed in by hand | keys typed in by hand | yes (QR login with Home Assistant's client id) | keys supplied by hand | yes (QR login with Home Assistant's client id); a developer project also works |
| Local keys come from | not used | developer API or manual | developer API or manual | QR login or manual | wizard using the developer API | QR login or developer API |
| What gives datapoints meaning | cloud codes per category, plus product fixes | you configure each entity | category tables plus the developer API's dp map, else by hand | a database of 1,790 device files, matched by product id or datapoints | raw datapoints; classes for bulbs, covers and 15 contributed device types | Home Assistant's category tables and product fixes, mapped to dp ids by the cloud's own map |
| Control path | cloud | LAN | LAN | LAN | LAN, or cloud via the developer API | LAN, cloud fallback |
| Uses the cloud once set up | always | no | no | no | no | optionally: fallback, writes with no local form, scenes, push |
| LAN protocol | none | own, asyncio, 3.1 to 3.4 | own, asyncio, 3.1 to 3.5 | TinyTuya | own, blocking, 3.1 to 3.5 | TinyTuya |
| Sub-devices behind a gateway | through the cloud | no | yes | yes, you pick the hub | yes | yes, gateway found by shared key |
| Live updates | cloud push | LAN push | LAN push | LAN push | LAN (`receive`, `Monitor`) | LAN (`watch`), cloud push (`subscribe`) |
| Tested on real hardware | yes | yes | yes | yes | yes | not yet |
| Licence | Apache-2.0 | GPL-3.0 | GPL-3.0 | MIT | MIT | MIT, with Apache-2.0 data |

localtuya and hass-localtuya are alternatives to each other: the second is a
fork of the first, they install under the same name, and localtuya has had one
commit in the twelve months to November 2026.

## What libtuya adds

As far as we could find, no single Python library had the combination in the
last column: no Home Assistant, no developer account, local control, and
devices that mean something without per-device configuration. The nearest is
three separate packages by one author (tuyawizard, tuya-interpreter and
rustuya, below).

- TinyTuya has the protocol but, outside its bulb, cover and contributed
  device classes, hands you numbered datapoints; libtuya hands you named
  entities.
- Home Assistant has the meaning but sends every command through the cloud;
  libtuya sends it over the LAN.
- tuya-local has both, inside Home Assistant.

Concretely, compared with using the pieces yourself:

- **The datapoint map is taken from the cloud** rather than guessed or
  configured, including for devices where the SDK throws it away.
- **Writes are translated back to raw datapoints** where an exact inverse
  exists (plain values and two colour encodings), which none of the upstream
  libraries do; the cloud normally does it server-side. Other writes go
  through the cloud.
- **The entities are Home Assistant's, and so is their behaviour.** A test
  checks that for every device fixture in the vendored Home Assistant release
  (329 real devices), libtuya derives the same entities, by unique id, as Home
  Assistant's own test snapshots. Each kind of entity has a class that
  follows Home Assistant's (`Light.turn_on(brightness=, color_temp_kelvin=)`,
  `Climate.set_hvac_mode`, `Cover.open`, `Fan.set_percentage` ...), and a
  second test compares what each class shows with the state Home Assistant
  recorded for every one of those entities.
- **Both paths in one place.** Devices that never answer on the LAN
  (battery-powered, Bluetooth-only) are still controlled, through the cloud.
  The LAN-only integrations cannot reach them.

## Where the others are stronger

- **They are proven on real hardware.** libtuya 2.0 has so far only met a
  simulated device and recorded device data.
- **Home Assistant is always current.** libtuya's device knowledge is a
  snapshot of one Home Assistant release and gains new devices only when it
  is re-synced. Home Assistant also loads product fixes of your own from its
  configuration directory; libtuya uses only those shipped with the handlers.
- **tuya-local knows more odd devices.** Its database covers products whose
  cloud description is empty or wrong. libtuya only knows what the cloud and
  Home Assistant's tables and product fixes know; a device with no published
  datapoints and no fix gets no entities here. (tuya-local, in turn, only
  accepts a device that matches one of its files.)
- **The Home Assistant integrations are services, libtuya is a library.** They
  keep connections alive, reconnect and track availability, and TinyTuya's
  experimental `Monitor` does the same for a standalone program. libtuya
  connects per call; `watch()` is a plain loop.
- **localtuya and hass-localtuya match replies to requests.** TinyTuya does
  not, so libtuya serialises calls and treats every reply as a partial update.
- **Infrared and RF remotes** work in tuya-local, hass-localtuya and TinyTuya,
  and not here (nor in Home Assistant's `tuya`).
- **The login is borrowed.** The QR login uses the client id Tuya issued to
  Home Assistant, as tuya-local's does. Tuya has not said whether other
  software may use it; see [login.md](login.md).
- **TinyTuya supports Python 3.10+**; libtuya needs 3.13 because
  tuya-device-handlers does.

## Others in the same space

Not used by libtuya; listed so you can pick the right tool.

- [tuyawizard](https://github.com/3735943886/tuyawizard),
  [tuya-interpreter](https://github.com/3735943886/tuya-interpreter) and
  [rustuya](https://github.com/3735943886/rustuya) (MIT, one author): QR
  login to a device list with keys; a Rust engine with a Python wrapper that
  turns such a device entry and raw datapoints into named properties and
  back, using its own rule packs; and a LAN library. Together they cover the
  same ground as libtuya, as three packages you join yourself.
  tuya-interpreter was first published in October 2026.
- [tuya-local-key](https://github.com/vineetchoudhary/tuya-local-key)
  (Apache-2.0): a web UI and CLI that does the QR login and shows keys,
  addresses and live values. An application rather than a library.
- [open-tuya](https://github.com/cheziyi/open-tuya) (MIT, TypeScript): the
  same overall design for Node, using tuya-local's device database. First
  published in October 2026; its README says it has barely been tested
  against real devices.

[ha]: https://github.com/home-assistant/core/tree/dev/homeassistant/components/tuya
[localtuya]: https://github.com/rospogrigio/localtuya
[hass-localtuya]: https://github.com/xZetsubou/hass-localtuya
[tuya-local]: https://github.com/make-all/tuya-local
[TinyTuya]: https://github.com/jasonacox/tinytuya
