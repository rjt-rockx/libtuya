# Third-party notices

libtuya's own code is under the MIT licence (`LICENSE`). It stands on other
people's work, listed here with what is taken from each and on what terms.

## Included in this repository

### Home Assistant Core (Apache License 2.0)

<https://github.com/home-assistant/core>, by the Home Assistant Core
contributors. Licence text: `third_party/home-assistant-core/LICENSE.md`.

- `third_party/home-assistant-core/` is an unmodified copy of the Tuya
  integration and its device fixtures, at the commit recorded in
  `third_party/home-assistant-core/UPSTREAM`.
- `libtuya/data/ha_tuya.json` is **derived** from that copy by
  `scripts/gen_ha_tables.py`. It holds the integration's per-category entity
  descriptions and English entity names, changed as follows: converted from
  Python to JSON, descriptions marked deprecated left out, callables dropped,
  and Home Assistant's own constants reduced to their names.
- `Light.turn_on` in `libtuya/entities.py` follows the logic of
  `TuyaLightEntity.async_turn_on` in `homeassistant/components/tuya/light.py`,
  rewritten for this library.

## Used as dependencies

Installed from PyPI, not copied.

| Project | Licence | Role |
|---|---|---|
| [TinyTuya](https://github.com/jasonacox/tinytuya) | MIT | The LAN protocol: discovery and protocol versions 3.1 to 3.5 |
| [tuya-device-sharing-sdk](https://github.com/tuya/tuya-device-sharing-sdk) | MIT | Smart Life QR login, device list, value conversions |
| [tuya-device-handlers](https://github.com/home-assistant-libs/tuya-device-handlers) | MIT | Reading and writing datapoints in friendly units, per-product fixes |
| [qrcode](https://github.com/lincolnloop/python-qrcode) | BSD | Drawing the login QR code in the terminal |
| [cryptography](https://github.com/pyca/cryptography) | Apache-2.0 or BSD | Needed by the sharing SDK and TinyTuya |

## Studied, nothing copied

- [tuya-local](https://github.com/make-all/tuya-local) (MIT) showed that the
  Smart Life QR login can supply local keys for LAN control, and its device
  handling informed how libtuya treats retries and partial status reports.
- [localtuya](https://github.com/rospogrigio/localtuya) and
  [hass-localtuya](https://github.com/xZetsubou/hass-localtuya) are GPL-3.0.
  Their behaviour was read for comparison; no code or data from them is in
  this repository.

## The Home Assistant client id

The sharing API only accepts clients registered with Tuya. libtuya uses the
one Tuya published for Home Assistant (`HA_3y9q4ak7g4ephrvke`), as tuya-local
and other projects do, so the app's consent screen says "Home Assistant" when
you log in. Tuya has not said whether other software may use it.

## Earlier revisions

Revisions before 2.0 (up to commit `4384beb`) carried material without its
licence or any attribution: tables copied from Home Assistant Core, two data
files reproduced from localtuya (`mode_mappings.json` and `scenes.json`, added
in `d03c0d8`; GPL-3.0, in a package labelled MIT) and statistics derived from
tuya-local. All of it was removed in 2.0; it remains only in the git history.
