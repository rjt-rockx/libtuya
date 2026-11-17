# How login works, and where it comes from

libtuya logs in to a Smart Life or Tuya Smart account the way Home Assistant
does: with a QR code scanned in the phone app, through an API Tuya built for
Home Assistant. This page explains what that is, how it has changed over the
years, and what it means to depend on it.

Nothing here could be tried against Tuya's servers while writing libtuya 2.0.
It is taken from the source and history of the projects that use the API
(Home Assistant, tuya-device-sharing-sdk, tuya-local). What could not be
established that way is marked as unknown.

## The idea, which is older than the mechanism

Tuya has given Home Assistant its own entrance to the consumer app account
since 2018. The entrance has been rebuilt twice:

| Home Assistant | Library | You provide | Talks to |
|---|---|---|---|
| 0.74 to 2021.9 (2018 to 2021) | `tuyapy`, then the fork `tuyaha` | app e-mail, password, country code | `px1.tuya{us,eu,cn}.com/homeassistant/...`, polled |
| 2021.10 to 2024.1 | `tuya-iot-py-sdk` | a cloud project's Access ID and Secret, plus the app account and password | the developer platform (`openapi.tuya*.com`), with MQTT push |
| 2024.2 to today | `tuya-device-sharing-sdk` | a user code, then a QR scan in the app | `apigw.iotbing.com/v1.0/m/life/home-assistant/...`, then a regional gateway, with MQTT push |

The first was dropped because Tuya stopped maintaining it. The second made
every user create a developer project whose "IoT Core" trial kept expiring;
Tuya's own words for it were "inconvenient and frustrating". The third, the
current one, needs no developer account. Each change forced every user to log
in again.

The current login has not changed since Tuya first published it in May 2023:
same host, paths, parameters and signing through every SDK release up to
0.2.15. What changed is around it (the data model, MQTT handling, error
types).

## What happens when you log in

1. libtuya asks for a login token, sending three things: a client id
   (`HA_3y9q4ak7g4ephrvke`), a schema (`haauthorize`) and your **user code**
   from the app (*Me* > gear icon > *Account and Security* > *User Code*).
2. It shows `tuyaSmart--qrLogin?token=<token>` as a QR code. You scan it in
   the app and approve; the app's consent screen names Home Assistant.
3. libtuya asks whether the token has been approved, every two seconds for up
   to three minutes. Home Assistant asks once, when you say you are done;
   other tools poll as libtuya does. What the server answers before approval,
   and how long a QR code lives, is unknown.
4. The answer carries an access token, a refresh token, their lifetime, a
   terminal id and the address of the regional gateway for your account.
   libtuya stores them, untouched, in `session.json` (mode 0600) together
   with the client id they belong to.

After that every request is encrypted and signed with a key derived from the
refresh token. Tokens are renewed as needed; a renewal replaces both tokens,
so libtuya writes the new pair to disk at once and, if a request is refused
as stale, reads the file again before giving up (another process may have
renewed it). `Tuya.logout()` revokes the login at Tuya.

There is no client secret anywhere. The client id is a public identifier that
Tuya issued and published; the user code is not used again after login.

## What libtuya takes from it

Three things, once, at `devices(refresh=True)`:

- the device list with each device's specification, which is what Home
  Assistant uses;
- the datapoint map, which Home Assistant's SDK uses to decode push messages
  and libtuya uses for the LAN;
- each device's **local key**. Home Assistant never reads it. It simply
  arrives in the device list, and it is what makes LAN control possible.

Scenes, push updates and the cloud fallback use the same session later.

## What this means for you

- **It is Home Assistant's identity.** Tuya has never said whether other
  software may use this client id; the question has been open on the SDK's
  tracker since 2023. No one has reported being blocked, and with no secret
  Tuya could hardly tell callers apart. `Tuya.login(..., client_id=, schema=)`
  takes another pair should that change.
- **Only Smart Life and Tuya Smart accounts work.** Other brands' apps do not
  have the user code.
- **The local key is a side effect.** Tuya could stop sending it without
  Home Assistant noticing. Keys already saved would keep working until a
  device is re-paired.
- **The cloud has been unreliable since mid-2026**: random refusals of valid
  requests, rate limiting, and logins invalidated during a token renewal.
  libtuya retries the first, and otherwise keeps away from the cloud once the
  device list is saved.
- **Whether a libtuya login disturbs an existing Home Assistant login on the
  same account is unknown.** If Home Assistant asks you to re-authenticate
  after you log in here, that is the likely cause.
- **Tuya has replaced this API twice in eight years.** If it does so again,
  the keys and datapoint maps in `devices.json` remain usable on the LAN, and
  a developer project (`tuya login --access-id ...`, see the README) is a
  second way in that does not depend on Home Assistant's client id.

Requests time out after 5 s connecting and 30 s waiting for an answer, the
user code is stripped and URL-quoted before the SDK puts it in a URL, and a
network error names the host it could not reach.
