# How libtuya compares

Facts below were checked against the upstream repositories in November 2026.

## The projects libtuya builds on or sits next to

| | [Home Assistant `tuya`][ha] | [localtuya] | [hass-localtuya] | [tuya-local] | [TinyTuya] | libtuya |
|---|---|---|---|---|---|---|
| Runs without Home Assistant | no | no | no | no | yes | yes |
| Works without a Tuya developer account | yes (QR login) | keys typed in by hand | keys typed in by hand | yes (QR login) | keys supplied by hand | yes (QR login) |
| Local keys come from | not used | developer API or manual | developer API or manual | QR login or manual | wizard using the developer API | QR login |
| What gives datapoints meaning | cloud codes per category, plus product fixes | you configure each entity | category templates plus the developer API's dp map | a database of 1,790 device files, matched by product | nothing; raw datapoints (helpers for bulbs and covers) | Home Assistant's category tables and product fixes, mapped to dp ids by the cloud's own map |
| Control path | cloud | LAN | LAN | LAN | LAN | LAN, cloud fallback |
| LAN protocol | none | own, asyncio, 3.1 to 3.4 | own, asyncio, 3.1 to 3.5 | TinyTuya | own, blocking, 3.1 to 3.5 | TinyTuya |
| Sub-devices behind a gateway | through the cloud | no | yes | yes, you pick the hub | yes | yes, gateway found by shared key |
| Live updates | cloud push | LAN push | LAN push | LAN push | LAN (`receive`, `Monitor`) | LAN (`watch`) |
| Licence | Apache-2.0 | GPL-3.0 | GPL-3.0 | MIT | MIT | MIT, with Apache-2.0 data |

## What libtuya adds

The combination in the last column did not exist as a Python library: no Home
Assistant, no developer account, local control, and devices that mean
something without per-device configuration.

- TinyTuya has the protocol but hands you datapoint 22; libtuya hands you
  `brightness`.
- Home Assistant has the meaning but sends every command through the cloud;
  libtuya sends it over the LAN.
- tuya-local has both, inside Home Assistant.

Concretely, compared with using the pieces yourself:

- **The datapoint map is taken from the cloud** rather than guessed or
  configured, including for devices where the SDK throws it away.
- **Writes are translated back to raw datapoints**, which none of the upstream
  libraries do (the cloud normally does it server-side).
- **The entities are Home Assistant's.** For Home Assistant's 336 device
  fixtures libtuya builds exactly the entities in Home Assistant's own test
  snapshots (1,565 of them).

## Where the others are stronger

- **tuya-local knows more odd devices.** Its database covers products whose
  cloud description is empty or wrong. libtuya only knows what the cloud and
  Home Assistant's tables know; a device with no published datapoints gets no
  entities here.
- **The Home Assistant integrations are services, libtuya is a library.** They
  keep connections alive, reconnect, back off and track availability.
  libtuya connects per call; `watch()` is a plain loop.
- **localtuya's protocol code matches replies to requests.** TinyTuya does
  not, so libtuya serialises calls and treats every reply as a partial update.
- **Home Assistant's entity classes have more behaviour.** libtuya composes
  commands for lights; for climate, fans, covers and vacuums it exposes the
  individual attributes (`hvac_mode`, `set_temperature`, `instruction`,
  `set_position`, ...) and leaves combining them to you.
- **Cloud push, scenes, camera streams and infrared remotes** are in Home
  Assistant and not here.
- **TinyTuya supports Python 3.10+**; libtuya needs 3.13 because
  tuya-device-handlers does.

## Others in the same space

Not used by libtuya; listed so you can pick the right tool.

- [tuya-local-key](https://github.com/vineetchoudhary/tuya-local-key)
  (Apache-2.0): a web UI and CLI that does the QR login and shows keys,
  addresses and live values. An application rather than a library.
- [tuyawizard](https://github.com/3735943886/tuyawizard) (MIT): QR login to a
  device list with keys, from the author of the `rustuya` LAN library.
- [open-tuya](https://github.com/cheziyi/open-tuya) (MIT, TypeScript): the
  same overall design for Node, using tuya-local's device database.

[ha]: https://github.com/home-assistant/core/tree/dev/homeassistant/components/tuya
[localtuya]: https://github.com/rospogrigio/localtuya
[hass-localtuya]: https://github.com/xZetsubou/hass-localtuya
[tuya-local]: https://github.com/make-all/tuya-local
[TinyTuya]: https://github.com/jasonacox/tinytuya
