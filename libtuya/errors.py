"""Exceptions raised by libtuya."""


class TuyaError(Exception):
    """Base class for libtuya errors."""


class NotLoggedIn(TuyaError):
    """No saved Smart Life session; run `tuya login` or `Tuya.login()`."""


class DeviceNotFound(TuyaError):
    """No device, or more than one, matches the given name, number or id."""


class CloudError(TuyaError):
    """The Tuya cloud rejected a request or could not be reached."""


class LanError(TuyaError):
    """The device could not be reached or refused the request on the LAN.

    `code` is TinyTuya's error code as a string (e.g. "901" unreachable, "914"
    wrong key or protocol version) when the error came from the device
    connection, else None.
    """

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class Unmapped(TuyaError):
    """A status code cannot be translated to a LAN datapoint for this device."""
