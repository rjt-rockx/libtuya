# libtuya

A Python library that provides seamless Tuya device control by combining the authentication capabilities of [tuya-device-sharing-sdk](https://github.com/tuya/tuya-device-sharing-sdk), the device intelligence of [Home Assistant](https://github.com/home-assistant/core), and the fast local control of [TinyTuya](https://github.com/jasonacox/tinytuya).

## Quick Start

### Installation

```bash
git clone https://github.com/rjt-rockx/libtuya.git
cd libtuya
pip install -e .
```

### CLI Usage

```bash
# Authenticate with QR code
tuya login

# Discover and list devices
tuya devices

# Control devices (using name, number, or ID)
tuya control "Living Room Light" on
tuya control 1 off                    # Use device number from 'tuya devices'
tuya control lamp brightness 75       # Partial name matching
tuya control "Living Room Light" color "#FF0000"

# Get device status
tuya control "Living Room Light" status

# Show detailed device information
tuya info "Living Room Light"

# Check system health
tuya health

# Clear authentication session
tuya logout
```

### Python Library Usage

```python
from libtuya import TuyaAuthenticator, DeviceManager
import asyncio

async def main():
    # Authenticate
    authenticator = TuyaAuthenticator()
    qr_code = authenticator.start_qr_auth("my-session")
    print(f"Scan QR code: {qr_code}")

    session = await authenticator.wait_for_auth_async()

    # Discover and control devices
    manager = DeviceManager()
    devices = await manager.discover_devices(session)

    for device in devices:
        print(f"Device: {device.name}")
        await device.turn_on()
        await device.set_brightness_percentage(75)

asyncio.run(main())
```

## Command Reference

### Authentication

```bash
tuya login [--user-code CODE]         # QR code authentication
tuya logout                           # Clear stored session
tuya health                           # System health check
```

### Device Discovery and Listing

```bash
tuya devices                          # List devices (uses cache when available)
tuya devices --refresh                # Force fresh discovery
tuya devices --cached                 # Show only cached devices
tuya devices --json                   # Output as JSON
```

### Device Control

```bash
# Basic control (DEVICE can be number, name, or ID)
tuya control DEVICE on                # Turn device on
tuya control DEVICE off               # Turn device off
tuya control DEVICE toggle            # Toggle device state
tuya control DEVICE status            # Get current status

# Advanced control
tuya control DEVICE brightness 75     # Set brightness (0-100)
tuya control DEVICE color "#FF0000"   # Set RGB color

# JSON output for automation
tuya control DEVICE on --json         # Returns JSON response
```

### Device Information

```bash
tuya info DEVICE                      # Show detailed device info
tuya info DEVICE --json               # Output as JSON
```

## Development

### Setup Development Environment

```bash
git clone https://github.com/rjt-rockx/libtuya.git
cd libtuya
pip install -e ".[dev]"
```

### Code Quality

```bash
black libtuya/                       # Format code
flake8 libtuya/                      # Lint code
mypy libtuya/                        # Type checking
```
