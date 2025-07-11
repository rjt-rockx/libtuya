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

## Dependencies

- `tuya-device-sharing-sdk>=0.2.0`

## Thread Safety

**✅ FULLY THREAD-SAFE** - The authentication system now provides complete thread safety:

### Thread Safety Guarantees

- **Session Operations**: All authentication and session management operations are thread-safe
- **Device Discovery**: Concurrent device discovery operations are properly synchronized
- **Token Refresh**: Token refresh operations are atomic and thread-safe
- **Cache Operations**: All device and status caches use thread-safe implementations
- **Initialization**: Device initialization is handled by thread-safe one-time initializers

### Concurrency Patterns

```python
from libtuya.auth import TuyaAuthenticator
import threading

# Safe to use same authenticator instance across threads
authenticator = TuyaAuthenticator()

def worker_thread():
    # Each thread can safely perform authentication
    qr_code = authenticator.start_qr_auth()
    
    # Safe concurrent device discovery
    devices = authenticator.get_devices_with_keys(force_refresh=True)
    
    # Thread-safe access to session info
    session_info = authenticator.get_session_info()

# Start multiple worker threads
threads = []
for i in range(5):
    thread = threading.Thread(target=worker_thread)
    threads.append(thread)
    thread.start()

for thread in threads:
    thread.join()
```

### Performance Characteristics

- **Read Operations**: Optimized with reader-writer locks for high concurrency
- **Write Operations**: Exclusive access with minimal blocking
- **Cache Access**: Lock-free reads for cached data with TTL management
- **Initialization**: One-time thread-safe initialization prevents duplicate work

### Implementation Details

The thread safety is implemented using:
- Reader-writer locks for performance optimization
- Thread-safe caches with automatic cleanup
- Atomic flags for state management
- One-time initializers for expensive operations
- Proper lock ordering to prevent deadlocks

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
