"""
Device data models for the libtuya devices package.

This module contains the data classes used throughout the device system.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class DeviceCapability:
    """Information about a device capability."""

    name: str
    dpcode: str
    dps_index: Optional[int]
    data_type: str
    current_value: Any = None
    available: bool = False
    scaling_info: Optional[Dict[str, Any]] = None


@dataclass
class DeviceStatus:
    """Current status of an intelligent device."""

    online: bool
    last_update: datetime
    capabilities: Dict[str, DeviceCapability]
    raw_dps: Dict[int, Any]
    errors: List[str]
