# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Installation and Setup

```bash
# Install in development mode
pip install -e ".[dev]"

# Install just the library
pip install -e .
```

### Code Quality

```bash
# Format code (line length: 100)
black libtuya/

# Lint code (max line length: 200, relaxed rules)
flake8 libtuya/

# Type checking (lenient configuration)
mypy libtuya/
```

### CLI Usage

```bash
# The library provides a CLI tool accessible via 'tuya' command
tuya login                  # QR code authentication
tuya devices               # List discovered devices
tuya control "device" on   # Control devices
tuya info "device"         # Device information
tuya health               # System health check
```

## Architecture Overview

libtuya is a Python library that combines three key components for Tuya device control:

1. **Authentication System** (`libtuya/auth/`): QR code authentication using tuya-device-sharing-sdk
2. **Device Intelligence** (`libtuya/intelligence/`): Device capability mapping from Home Assistant
3. **Local Control** (`libtuya/devices/`): Fast local control using TinyTuya

### Core Architecture

**Authentication Flow:**

- `TuyaAuthenticator` in `auth/__init__.py` provides the main interface
- `QRAuthenticator` in `auth/qr_auth.py` handles QR code authentication
- `CloudDeviceManager` in `auth/manager.py` manages device discovery
- Thread-safe design with atomic operations and proper locking

**Device System:**

- `IntelligentDeviceRegistry` in `devices/__init__.py` is the main device manager
- `DeviceFactory` in `devices/factory.py` creates appropriate TinyTuya instances
- `IntelligentDevice` in `devices/intelligent_device.py` wraps TinyTuya with intelligence
- Specialized device types: `IntelligentLight`, `IntelligentSwitch`, etc. in `device_types.py`

**Intelligence Layer:**

- `DeviceIntelligence` provides device capability mapping
- JSON data files in `intelligence/data/` contain device mappings, quirks, and scaling rules
- DPS (Data Point) mapping system in `dps/` translates between cloud and local protocols

**CLI System:**

- Thin CLI wrapper in `cli.py` delegates to `cli_core/`
- `TuyaCLICore` handles business logic
- `CommandHandler` processes user commands

### Key Patterns

**Multi-Entity Devices:**
The system handles devices that appear as single hardware but expose multiple entities (e.g., a wall switch with multiple outlets). The `IntelligentDeviceRegistry.create_devices()` method creates separate device instances for each entity while sharing the underlying TinyTuya connection.

**Thread Safety:**
The authentication system uses `ThreadSafeMixin` with read/write locks and `AtomicFlag` for safe concurrent access.

**Error Recovery:**
The `recovery/` module provides retry strategies, error handlers, and diagnostics for robust operation.

## Configuration Notes

- **Black**: 100 character line length, Python 3.8+ target
- **Flake8**: 200 character max line length with extended ignore list for flexibility
- **MyPy**: Lenient configuration with most error checking disabled for development ease
- **Python**: Supports 3.8+ with async/await patterns throughout

## Development Workflow

When adding new device support:

1. Add device mappings to `intelligence/data/device_mappings.json`
2. Update DPS codes in `intelligence/data/dpcodes.json`
3. Add quirks if needed in `intelligence/data/quirks.json`
4. Create specialized device type in `devices/device_types.py` if appropriate
5. Update factory in `devices/factory.py` to recognize the new device

The library follows a "just works" philosophy - minimal configuration should be required from users.
