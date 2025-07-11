"""
Data models for Tuya authentication and device management.

This module defines the data structures used throughout the authentication system,
including authentication sessions and device information wrapping.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class AuthSession:
    """
    Represents an authenticated Tuya session with token management.

    This class manages authentication tokens, their expiration, and provides
    methods for token validation and refresh.
    """

    access_token: str
    refresh_token: str
    uid: str
    expire_time: int  # Unix timestamp in milliseconds
    t: int  # Response timestamp
    client_id: str = "HA_3y9q4ak7g4ephrvke"
    user_code: str = ""
    terminal_id: str = ""
    endpoint: str = "https://apigw.iotbing.com"

    @property
    def is_expired(self) -> bool:
        """Check if the access token is expired or will expire soon."""
        now = int(datetime.now().timestamp() * 1000)
        # Add 1 minute buffer
        return (self.expire_time - 60000) <= now

    @property
    def expires_in_minutes(self) -> int:
        """Get minutes until token expires."""
        now = int(datetime.now().timestamp() * 1000)
        remaining_ms = self.expire_time - now
        return max(0, remaining_ms // 60000)

    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary for persistence."""
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "uid": self.uid,
            "expire_time": self.expire_time,
            "t": self.t,
            "client_id": self.client_id,
            "user_code": self.user_code,
            "terminal_id": self.terminal_id,
            "endpoint": self.endpoint,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuthSession":
        """Create session from dictionary."""
        return cls(**data)

    def to_json(self) -> str:
        """Convert session to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> "AuthSession":
        """Create session from JSON string."""
        return cls.from_dict(json.loads(json_str))


@dataclass
class DeviceInfo:
    """
    Wrapper around CustomerDevice with enhanced functionality.

    This class provides a clean interface to device information while preserving
    all the original CustomerDevice data and adding convenience methods.
    """

    id: str
    name: str
    local_key: str
    category: str
    product_id: str
    product_name: str
    online: bool
    ip: str
    uuid: str
    asset_id: str
    sub: bool = False
    icon: str = ""
    time_zone: str = ""
    active_time: int = 0
    create_time: int = 0
    update_time: int = 0
    set_up: bool = False
    support_local: bool = False
    local_strategy: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    status: Dict[str, Any] = field(default_factory=dict)
    function: Dict[str, Any] = field(default_factory=dict)
    status_range: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_customer_device(cls, device) -> "DeviceInfo":
        """
        Create DeviceInfo from a tuya_sharing CustomerDevice.

        Args:
            device: CustomerDevice object from tuya-device-sharing-sdk

        Returns:
            DeviceInfo instance with all device data
        """
        return cls(
            id=device.id,
            name=device.name,
            local_key=device.local_key,
            category=device.category,
            product_id=device.product_id,
            product_name=device.product_name,
            online=device.online,
            ip=device.ip,
            uuid=device.uuid,
            asset_id=getattr(device, "asset_id", ""),
            sub=getattr(device, "sub", False),
            icon=getattr(device, "icon", ""),
            time_zone=getattr(device, "time_zone", ""),
            active_time=getattr(device, "active_time", 0),
            create_time=getattr(device, "create_time", 0),
            update_time=getattr(device, "update_time", 0),
            set_up=getattr(device, "set_up", False),
            support_local=getattr(device, "support_local", False),
            local_strategy=getattr(device, "local_strategy", {}),
            status=getattr(device, "status", {}),
            function=getattr(device, "function", {}),
            status_range=getattr(device, "status_range", {}),
        )

    @property
    def has_local_key(self) -> bool:
        """Check if device has a valid local key."""
        return bool(self.local_key and self.local_key.strip())

    @property
    def can_control_locally(self) -> bool:
        """Check if device can be controlled locally."""
        return self.has_local_key and self.online and bool(self.ip)

    @property
    def device_type(self) -> str:
        """Get human-readable device type based on category."""
        # Map device categories to readable types
        type_mapping = {
            "dj": "Light",
            "cz": "Socket",
            "kg": "Switch",
            "pc": "Power Strip",
            "xdd": "Bulb",
            "fsd": "Fan",
            "cl": "Curtain",
            "ms": "Sensor",
            "wk": "Thermostat",
            "sp": "Smart Plug",
        }
        return type_mapping.get(self.category, f"Unknown ({self.category})")

    def get_status_value(self, code: str, default=None):
        """Get a specific status value by code."""
        return self.status.get(code, default)

    def has_function(self, code: str) -> bool:
        """Check if device supports a specific function."""
        return code in self.function

    def get_function_range(self, code: str) -> Optional[Dict[str, Any]]:
        """Get the range/options for a specific function."""
        return self.status_range.get(code)

    # Adapter properties for backward compatibility with DPS module field names
    @property
    def device_id(self) -> str:
        """Alias for id field (DPS module compatibility)."""
        return self.id

    @property
    def model(self) -> str:
        """Alias for product_name field (DPS module compatibility)."""
        return self.product_name

    @property
    def ip_address(self) -> str:
        """Alias for ip field (DPS module compatibility)."""
        return self.ip

    @property
    def protocol_version(self) -> Optional[str]:
        """Protocol version for DPS operations (DPS module compatibility)."""
        # Extract from local_strategy if available, otherwise default to 3.3
        if self.local_strategy:
            # Check if protocol version is stored in local_strategy
            for strategy in self.local_strategy.values():
                if isinstance(strategy, dict) and "protocol" in strategy:
                    return str(strategy["protocol"])
        return "3.3"  # Default protocol version

    def to_dict(self) -> Dict[str, Any]:
        """Convert device info to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "local_key": self.local_key,
            "category": self.category,
            "product_id": self.product_id,
            "product_name": self.product_name,
            "online": self.online,
            "ip": self.ip,
            "uuid": self.uuid,
            "asset_id": self.asset_id,
            "sub": self.sub,
            "icon": self.icon,
            "time_zone": self.time_zone,
            "active_time": self.active_time,
            "create_time": self.create_time,
            "update_time": self.update_time,
            "set_up": self.set_up,
            "support_local": self.support_local,
            "local_strategy": self.local_strategy,
            "status": self.status,
            "function": self.function,
            "status_range": self.status_range,
            "device_type": self.device_type,
            "can_control_locally": self.can_control_locally,
            # Include adapter field names for backward compatibility
            "device_id": self.device_id,
            "model": self.model,
            "ip_address": self.ip_address,
            "protocol_version": self.protocol_version,
        }


@dataclass
class QRCodeData:
    """
    Represents QR code data for authentication.

    Contains the QR code content and associated metadata for the authentication flow.
    """

    qr_code: str  # QR code content/URL
    token: str  # Token for polling login status
    expires_in: int = 600  # QR code validity in seconds

    @property
    def is_expired(self) -> bool:
        """Check if QR code has expired (placeholder - actual expiry tracking would need timestamp)."""
        # In a real implementation, you'd track creation time
        return False

    def to_dict(self) -> Dict[str, Any]:
        """Convert QR code data to dictionary."""
        return {
            "qr_code": self.qr_code,
            "token": self.token,
            "expires_in": self.expires_in,
        }


@dataclass
class AuthenticationError(Exception):
    """
    Custom exception for authentication-related errors.
    """

    message: str
    error_code: str = "UNKNOWN"
    details: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"Authentication Error [{self.error_code}]: {self.message}"


@dataclass
class DeviceDiscoveryResult:
    """
    Result of device discovery operation.

    Contains discovered devices and metadata about the discovery process.
    """

    devices: List[DeviceInfo]
    total_count: int
    discovery_time: datetime = field(default_factory=datetime.now)
    errors: List[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """Check if discovery was successful."""
        return len(self.errors) == 0

    @property
    def devices_with_local_keys(self) -> List[DeviceInfo]:
        """Get only devices that have local keys."""
        return [device for device in self.devices if device.has_local_key]

    @property
    def online_devices(self) -> List[DeviceInfo]:
        """Get only online devices."""
        return [device for device in self.devices if device.online]

    @property
    def controllable_devices(self) -> List[DeviceInfo]:
        """Get devices that can be controlled locally."""
        return [device for device in self.devices if device.can_control_locally]

    def get_devices_by_category(self, category: str) -> List[DeviceInfo]:
        """Get devices by category."""
        return [device for device in self.devices if device.category == category]

    def to_dict(self) -> Dict[str, Any]:
        """Convert discovery result to dictionary."""
        return {
            "devices": [device.to_dict() for device in self.devices],
            "total_count": self.total_count,
            "discovery_time": self.discovery_time.isoformat(),
            "errors": self.errors,
            "success": self.success,
            "devices_with_keys": len(self.devices_with_local_keys),
            "online_devices": len(self.online_devices),
            "controllable_devices": len(self.controllable_devices),
        }
