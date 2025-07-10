# LibTuya - Just Works Tuya Integration

A Python library that provides seamless Tuya device control by combining the authentication capabilities of `tuya-device-sharing-sdk`, the device intelligence of Home Assistant's Tuya integration, and the fast local control of TinyTuya.

## Key Features

- **🔐 Zero-config Authentication**: QR code authentication eliminates the need for developer accounts
- **🧠 Intelligent Device Control**: Leverages Home Assistant's device intelligence for 316 DPCode definitions
- **⚡ Fast Local Control**: Automatic local key extraction enables millisecond response times
- **🎯 Just Works**: No manual configuration, device keys, or complex setup required
- **🛠️ Multiple Interfaces**: CLI tool, REST API, and Python library
- **📦 Smart Caching**: Device information cached for instant access
- **🔍 Flexible Device Lookup**: Control devices by number, name, or ID
- **🔄 Session Persistence**: Authentication persists across CLI sessions

## Quick Start

### Installation

```bash
pip install libtuya
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

## Architecture

LibTuya consists of four main components:

1. **Device Intelligence Database** (`libtuya.intelligence`)
   - 316 DPCode definitions from Home Assistant
   - Device category mappings for 60+ device types
   - Value scaling and conversion logic
   - Device-specific quirks and edge cases

2. **Authentication System** (`libtuya.auth`)
   - QR code authentication flow
   - Automatic local key extraction
   - Session management and token refresh
   - Uses Home Assistant's client ID for compatibility

3. **DPS Discovery Engine** (`libtuya.dps`)
   - Bulletproof DPS mapping heuristics
   - Capability-to-DPS index mapping
   - Handles unknown devices gracefully
   - Confidence scoring and fallback strategies

4. **Intelligent Device Factory** (`libtuya.devices`)
   - Combines cloud discovery with local control
   - Automatic device class selection
   - High-level control methods
   - Error recovery and resilience
   - Smart caching for faster response
   - Device name/number resolution

## Supported Devices

LibTuya supports all major Tuya device categories:

- **Lights** (`dj`): Brightness, color, color temperature, scenes
- **Switches** (`kg`): On/off, power monitoring, multi-channel
- **Climate** (`wk`): Temperature, humidity, mode control
- **Covers** (`cl`): Position, movement, calibration
- **Sensors** (`pir`, `mcs`): Motion, door/window, environmental
- **Appliances** (`fs`, `jsq`): Fans, humidifiers, specialized controls

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
git clone https://github.com/libtuya/libtuya.git
cd libtuya
pip install -e ".[dev]"
```

### Run Tests

```bash
pytest tests/                        # Run all tests
pytest tests/intelligence/           # Test device intelligence
pytest tests/auth/                   # Test authentication
pytest tests/devices/                # Test device control
pytest tests/dps/                    # Test DPS mapping
```

### Code Quality

```bash
black libtuya/                       # Format code
flake8 libtuya/                      # Lint code
mypy libtuya/                        # Type checking
```

## Project Structure

```text
libtuya/
├── libtuya/
│   ├── __init__.py                  # Main package exports
│   ├── cli.py                       # Command-line interface
│   ├── auth/                        # Authentication system
│   │   ├── __init__.py
│   │   ├── qr_auth.py              # QR code authentication
│   │   ├── manager.py              # Device discovery
│   │   └── models.py               # Data structures
│   ├── intelligence/               # Device intelligence database
│   │   ├── __init__.py
│   │   ├── dpcodes.py              # DPCode definitions
│   │   ├── device_mappings.py      # Category mappings
│   │   ├── scaling.py              # Value scaling
│   │   └── quirks.py               # Device quirks
│   ├── dps/                        # DPS discovery engine
│   │   ├── __init__.py
│   │   ├── mapping_rules.py        # Mapping heuristics
│   │   ├── discovery.py            # TinyTuya discovery
│   │   └── mapper.py               # Main mapping interface
│   ├── devices/                    # Device factory pattern
│   │   ├── __init__.py
│   │   ├── factory.py              # Device factory
│   │   ├── intelligent_device.py   # Core device wrapper
│   │   └── device_types.py         # Specialized devices
│   └── recovery/                   # Error recovery system
│       ├── __init__.py
│       ├── exceptions.py           # Custom exceptions
│       ├── retry_strategies.py     # Retry logic
│       ├── error_handlers.py       # Recovery handlers
│       └── diagnostics.py          # Health monitoring
├── tests/                          # Test suite
├── examples/                       # Usage examples
├── intelligence/                   # Extracted HA intelligence
├── analysis/                       # Design analysis
├── setup.py                        # Package setup
└── requirements.txt                # Dependencies
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- **Home Assistant Community** - Device intelligence and compatibility data
- **TinyTuya Project** - Local device control capabilities
- **Tuya Inc.** - Device sharing SDK and cloud integration
- **Python Community** - Excellent libraries and tools

## Support

- 📖 [Documentation](https://libtuya.readthedocs.io)
- 🐛 [Bug Reports](https://github.com/libtuya/libtuya/issues)
- 💬 [Discussions](https://github.com/libtuya/libtuya/discussions)
- 📧 [Email Support](mailto:support@libtuya.dev)
