"""
Device Resolver - Device identification and resolution

This module handles the logic for resolving device identifiers (names, indices, IDs)
to actual device objects or IDs.
"""

import logging
from typing import Any, Dict, List, Optional

from rich.console import Console

logger = logging.getLogger(__name__)


class DeviceResolver:
    """Resolves device identifiers to device IDs."""

    def __init__(self, console: Optional[Console] = None):
        """Initialize device resolver."""
        self.console = console or Console(highlight=False)

    def resolve_device_identifier(
        self,
        identifier: str,
        device_indices: Dict[int, str],
        devices: Dict[str, Any],
        cached_device_info: Dict[str, Dict],
    ) -> Optional[str]:
        """
        Resolve a device identifier to a device ID.

        Args:
            identifier: Can be:
                - Device index number (1, 2, 3, etc.)
                - Full device ID
                - Partial device name (case-insensitive)
                - Full device name (case-insensitive)
            device_indices: Mapping from index to device_id
            devices: Full device objects keyed by device_id
            cached_device_info: Cached device info keyed by device_id

        Returns:
            Device ID if found, None otherwise
        """
        # Use cached device info if available, otherwise use full devices
        device_source = cached_device_info if cached_device_info else {}
        if not device_source and not devices:
            return None

        # Try as device index first
        try:
            index = int(identifier)
            if index in device_indices:
                return device_indices[index]
        except ValueError:
            pass

        # Try as exact device ID
        if devices and identifier in devices:
            return identifier
        elif identifier in device_source:
            return identifier

        # Try partial matching on device names (case-insensitive)
        identifier_lower = identifier.lower()
        matches = []

        # Search in cached device info first
        if device_source:
            for device_id, device_info in device_source.items():
                device_name_lower = device_info["name"].lower()
                # Exact name match
                if device_name_lower == identifier_lower:
                    return device_id
                # Partial name match
                elif identifier_lower in device_name_lower:
                    matches.append({"id": device_id, "name": device_info["name"]})

        # If no cached info, search in full devices
        elif devices:
            for device in devices.values():
                device_name_lower = device.name.lower()
                # Exact name match
                if device_name_lower == identifier_lower:
                    return device.id
                # Partial name match
                elif identifier_lower in device_name_lower:
                    matches.append({"id": device.id, "name": device.name})

        # If we have exactly one partial match, use it
        if len(matches) == 1:
            return matches[0]["id"]

        # If multiple matches, show them to the user
        if len(matches) > 1:
            self.console.print(f"[yellow]Multiple devices match '{identifier}':[/yellow]")
            for i, device in enumerate(matches, 1):
                self.console.print(f"  {i}. {device['name']}")
            self.console.print("[yellow]Please be more specific.[/yellow]")

        return None

    def update_device_indices(
        self, sorted_devices: List[Any], current_indices: Dict[int, str]
    ) -> Dict[int, str]:
        """
        Update device indices, preserving existing mappings where possible.

        Args:
            sorted_devices: List of devices to assign indices to
            current_indices: Current index to device_id mapping

        Returns:
            Updated device indices mapping
        """
        # Create a reverse mapping from device_id to current index
        reverse_indices = {device_id: index for index, device_id in current_indices.items()}

        # Track which indices are already used
        used_indices = set()
        new_device_indices = {}

        # First pass: assign existing indices to devices that already have them
        for device in sorted_devices:
            device_id = getattr(device, 'id', getattr(device, 'device_id', None))
            if device_id and device_id in reverse_indices:
                existing_index = reverse_indices[device_id]
                new_device_indices[existing_index] = device_id
                used_indices.add(existing_index)

        # Second pass: assign new indices to devices that don't have them
        next_index = 1
        for device in sorted_devices:
            device_id = getattr(device, 'id', getattr(device, 'device_id', None))
            if device_id and device_id not in reverse_indices:
                # Find the next available index
                while next_index in used_indices:
                    next_index += 1

                new_device_indices[next_index] = device_id
                used_indices.add(next_index)
                next_index += 1

        return new_device_indices
