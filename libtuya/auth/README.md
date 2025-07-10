# libtuya Authentication System

The authentication system provides QR code-based authentication for the Tuya Cloud API and automatic device discovery with local keys.

## Features

- **QR Code Authentication**: Uses Smart Life app for secure authentication
- **Automatic Device Discovery**: Discovers all devices with local keys
- **Token Management**: Handles token refresh and session persistence
- **Real-time Updates**: Supports real-time device status updates
- **Error Handling**: Comprehensive error handling with retry logic

## Quick Start

```python
from libtuya.auth import TuyaAuthenticator

# Initialize authenticator
authenticator = TuyaAuthenticator()

# QR code authentication
qr_code = authenticator.start_qr_auth()
print(qr_code)  # Display QR code to user

# Wait for authentication
session = authenticator.wait_for_auth(timeout=300)

# Get devices with local keys
devices = authenticator.get_devices_with_keys()
for device in devices:
    print(f"Device: {device.name}, Local Key: {device.local_key}")
```

## Architecture

### Core Components

1. **TuyaAuthenticator**: Main interface for authentication and device management
2. **QRAuthenticator**: Handles QR code generation and authentication flow
3. **DeviceManager**: Manages device discovery and real-time updates
4. **AuthSession**: Token management and session persistence
5. **DeviceInfo**: Device information wrapper with convenience methods

### Authentication Flow

1. Generate QR code with Home Assistant client ID
2. User scans QR code with Smart Life app
3. Poll for authentication completion
4. Initialize device manager with tokens
5. Discover devices with automatic local key extraction

### Device Discovery

The system automatically discovers all devices associated with the authenticated account and extracts local keys for each device. This eliminates the need for manual key extraction or developer accounts.

## Configuration

The authentication system uses the following configuration:

- **Client ID**: `HA_3y9q4ak7g4ephrvke` (Home Assistant)
- **Schema**: `haauthorize`
- **Endpoint**: `https://apigw.iotbing.com`

## Error Handling

The system includes comprehensive error handling for:

- Network connectivity issues
- Token expiration and refresh
- Device discovery failures
- Authentication timeouts
- Invalid QR codes

## Testing

Run the test suite with:

```bash
pytest tests/auth/
```

## Dependencies

- `tuya-device-sharing-sdk>=0.2.0`
- `pytest>=7.0.0` (for testing)

## Thread Safety

The authentication system is not thread-safe. Use separate instances for concurrent access or implement appropriate locking mechanisms.

## Security Considerations

- Tokens are stored in memory and should be persisted securely
- Local keys are sensitive and should be handled appropriately
- Network communication uses HTTPS but may be subject to MITM attacks
- QR codes contain sensitive authentication information

## Limitations

- Requires Smart Life app for authentication
- Depends on Tuya Cloud API availability
- Regional API endpoints may vary
- Token refresh requires network connectivity
