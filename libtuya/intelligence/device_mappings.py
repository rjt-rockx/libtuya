"""
Device category to capability mappings for Tuya devices.

This module contains mappings from device categories to their supported
capabilities, extracted from Home Assistant's Tuya integration.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


@dataclass
class IntelligenceCapability:
    """Represents a device capability with intelligence metadata."""

    name: str
    category: str
    supported_dpcodes: List[str]
    notes: Optional[str] = None

    def __post_init__(self):
        """Ensure supported_dpcodes is always a list."""
        if isinstance(self.supported_dpcodes, str):
            self.supported_dpcodes = [self.supported_dpcodes]


@dataclass
class DeviceCategory:
    """Represents a complete device category with all its capabilities."""

    category_id: str
    name: str
    capabilities: List[str]
    notes: Optional[str] = None
    platform: str = "unknown"


class DeviceMappingManager:
    """
    Manages device category mappings and provides lookup functionality.
    """

    def __init__(self):
        """Initialize the device mapping manager."""
        self._mappings_data = None
        self._category_cache = {}
        self._platform_cache = {}
        self._capability_index = {}
        self._load_data()

    def _load_data(self) -> None:
        """Load and cache device mapping data from JSON file."""
        intelligence_dir = Path(__file__).parent / "data"
        mappings_file = intelligence_dir / "device_mappings.json"

        with open(mappings_file, "r") as f:
            self._mappings_data = json.load(f)

        # Build category cache and indexes
        self._build_caches()

    def _build_caches(self) -> None:
        """Build internal caches for fast lookups."""
        if self._mappings_data is None:
            return
        categories = self._mappings_data["categories"]

        for platform, platform_categories in categories.items():
            self._platform_cache[platform] = {}

            for category_id, category_data in platform_categories.items():
                # Create DeviceCategory object
                device_category = DeviceCategory(
                    category_id=category_id,
                    name=category_data["name"],
                    capabilities=category_data.get("capabilities", []),  # Modified line
                    notes=category_data.get("notes"),
                    platform=platform,
                )

                # Cache by category ID
                self._category_cache[category_id] = device_category
                self._platform_cache[platform][category_id] = device_category

                # Index capabilities for reverse lookup
                for capability in category_data.get("capabilities", []):  # Modified line
                    if capability not in self._capability_index:
                        self._capability_index[capability] = []
                    self._capability_index[capability].append(category_id)

    def get_category(self, category_id: str) -> Optional[DeviceCategory]:
        """
        Get device category information.

        Args:
            category_id: The category ID (e.g., "dj", "kg")

        Returns:
            DeviceCategory object or None if not found
        """
        return self._category_cache.get(category_id)

    def get_categories_by_platform(self, platform: str) -> Dict[str, DeviceCategory]:
        """
        Get all categories for a specific platform.

        Args:
            platform: Platform name (e.g., "lights", "switches")

        Returns:
            Dictionary mapping category IDs to DeviceCategory objects
        """
        return self._platform_cache.get(platform, {})

    def get_capabilities(self, category_id: str) -> List[str]:
        """
        Get capabilities for a device category.

        Args:
            category_id: The category ID

        Returns:
            List of capability names
        """
        category = self.get_category(category_id)
        return category.capabilities if category else []

    def get_categories_with_capability(self, capability: str) -> List[str]:
        """
        Get all categories that support a specific capability.

        Args:
            capability: Capability name (e.g., "bright_value")

        Returns:
            List of category IDs that support the capability
        """
        return self._capability_index.get(capability, [])

    def has_capability(self, category_id: str, capability: str) -> bool:
        """
        Check if a category supports a specific capability.

        Args:
            category_id: The category ID
            capability: Capability name

        Returns:
            True if supported, False otherwise
        """
        capabilities = self.get_capabilities(category_id)
        return capability in capabilities

    def get_all_categories(self) -> List[DeviceCategory]:
        """
        Get all device categories.

        Returns:
            List of all DeviceCategory objects
        """
        return list(self._category_cache.values())

    def get_all_platforms(self) -> List[str]:
        """
        Get all platform names.

        Returns:
            List of platform names
        """
        return list(self._platform_cache.keys())

    def get_all_capabilities(self) -> Set[str]:
        """
        Get all unique capabilities across all categories.

        Returns:
            Set of all capability names
        """
        return set(self._capability_index.keys())

    def search_categories(self, pattern: str) -> List[DeviceCategory]:
        """
        Search for categories by name or ID.

        Args:
            pattern: Pattern to search for (case-insensitive)

        Returns:
            List of matching DeviceCategory objects
        """
        pattern_lower = pattern.lower()
        matches = []

        for category in self._category_cache.values():
            if (
                pattern_lower in category.category_id.lower()
                or pattern_lower in category.name.lower()
            ):
                matches.append(category)

        return matches

    def get_category_suggestions(self, capabilities: List[str]) -> List[str]:
        """
        Get category suggestions based on required capabilities.

        Args:
            capabilities: List of required capabilities

        Returns:
            List of category IDs that support all capabilities
        """
        if not capabilities:
            return []

        # Find categories that support all capabilities
        candidate_categories = None

        for capability in capabilities:
            categories_with_capability = set(self.get_categories_with_capability(capability))

            if candidate_categories is None:
                candidate_categories = categories_with_capability
            else:
                candidate_categories = candidate_categories.intersection(categories_with_capability)

        return list(candidate_categories) if candidate_categories else []

    def get_platform_for_category(self, category_id: str) -> Optional[str]:
        """
        Get the platform for a given category.

        Args:
            category_id: The category ID

        Returns:
            Platform name or None if not found
        """
        category = self.get_category(category_id)
        return category.platform if category else None

    def get_category_stats(self) -> Dict[str, Any]:
        """
        Get statistics about device categories.

        Returns:
            Dictionary with category statistics
        """
        total_categories = len(self._category_cache)
        total_platforms = len(self._platform_cache)
        total_capabilities = len(self._capability_index)

        platform_counts = {
            platform: len(categories) for platform, categories in self._platform_cache.items()
        }

        capability_usage = {
            capability: len(categories) for capability, categories in self._capability_index.items()
        }

        return {
            "total_categories": total_categories,
            "total_platforms": total_platforms,
            "total_capabilities": total_capabilities,
            "categories_per_platform": platform_counts,
            "capability_usage": capability_usage,
        }

    def validate_category_mapping(
        self, category_id: str, expected_capabilities: List[str]
    ) -> Dict[str, Any]:
        """
        Validate that a category has expected capabilities.

        Args:
            category_id: The category ID to validate
            expected_capabilities: List of expected capabilities

        Returns:
            Dictionary with validation results
        """
        category = self.get_category(category_id)

        if not category:
            return {
                "valid": False,
                "error": f"Category '{category_id}' not found",
            }

        actual_capabilities = set(category.capabilities)
        expected_capabilities_set = set(expected_capabilities)

        missing = expected_capabilities_set - actual_capabilities
        extra = actual_capabilities - expected_capabilities_set

        return {
            "valid": len(missing) == 0,
            "category": category,
            "missing_capabilities": list(missing),
            "extra_capabilities": list(extra),
            "matches": len(missing) == 0 and len(extra) == 0,
        }


# Common device patterns for quick access
COMMON_LIGHT_CAPABILITIES = [
    "switch_led",
    "bright_value",
    "colour_data",
    "temp_value",
    "work_mode",
]

COMMON_SWITCH_CAPABILITIES = [
    "switch_1",
    "switch_2",
    "switch_3",
    "switch_backlight",
]

COMMON_SENSOR_CAPABILITIES = [
    "battery_percentage",
    "va_temperature",
    "va_humidity",
    "bright_state",
]

COMMON_CLIMATE_CAPABILITIES = [
    "switch",
    "temp_set",
    "temp_current",
    "mode",
    "fan_speed_enum",
]


# Default instance for easy access
device_mapping_manager = DeviceMappingManager()
