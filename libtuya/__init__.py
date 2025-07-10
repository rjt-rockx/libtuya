"""
libtuya - A unified Python library for Tuya device control.

This library provides a "just works" Tuya integration system that combines
the authentication capabilities of tuya-device-sharing-sdk, the device intelligence
of Home Assistant's Tuya integration, and the fast local control of TinyTuya.

Key Features:
- QR code authentication with Smart Life app
- Automatic device discovery with local keys
- Intelligent device control with proper scaling
- Multiple interfaces (Python API, CLI, REST API)
- No manual configuration required

Quick Start:
    from libtuya import TuyaAuthenticator

    # Authenticate with QR code
    auth = TuyaAuthenticator()
    session = auth.authenticate_with_qr()

    # Discover devices
    devices = auth.get_devices_with_keys()

    # Control devices
    for device in devices:
        if device.category == "dj":  # Light
            auth.send_command(device.id, [
                {"code": "switch_1", "value": True},
                {"code": "bright_value", "value": 800}
            ])
"""

from .auth import TuyaAuthenticator

__version__ = "0.1.0"
__author__ = "libtuya"
__email__ = "contact@libtuya.dev"
__description__ = "A unified Python library for Tuya device control"

# Export main classes
__all__ = ["TuyaAuthenticator"]
