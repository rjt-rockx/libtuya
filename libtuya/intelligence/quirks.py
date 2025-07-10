"""
Device-specific quirks and edge cases for Tuya devices.

This module handles device-specific workarounds and edge cases discovered
in Home Assistant's Tuya integration.
"""

import json
from typing import Dict, List, Optional, Set, Any, Tuple
from pathlib import Path
from dataclasses import dataclass
from enum import Enum


class QuirkType(str, Enum):
    """Types of device quirks."""

    CATEGORY_DUPLICATE = "category_duplicate"
    MULTI_ENTITY = "multi_entity"
    DPCODE_FALLBACK = "dpcode_fallback"
    UNDOCUMENTED_CATEGORY = "undocumented_category"
    SPECIAL_HANDLING = "special_handling"
    VALUE_MAPPING = "value_mapping"


@dataclass
class DeviceQuirk:
    """Represents a device-specific quirk or edge case."""

    category_id: str
    quirk_type: QuirkType
    description: str
    data: Dict[str, Any]
    workaround: Optional[str] = None

    def applies_to_category(self, category_id: str) -> bool:
        """Check if this quirk applies to a specific category."""
        return self.category_id == category_id or category_id in self.data.get(
            "applies_to", []
        )


@dataclass
class EntityMapping:
    """Represents an entity mapping for multi-entity devices."""

    key: str
    brightness_dpcode: Optional[str] = None
    entity_type: str = "light"
    additional_dpcodes: Optional[List[str]] = None


@dataclass
class DPCodeFallback:
    """Represents a DPCode fallback sequence."""

    primary_dpcode: str
    fallback_dpcodes: List[str]
    description: str


class DeviceQuirksManager:
    """
    Manages device-specific quirks and provides workaround functionality.
    """

    def __init__(self):
        """Initialize the device quirks manager."""
        self._quirks_data = None
        self._category_duplicates = {}
        self._multi_entity_devices = {}
        self._dpcode_fallbacks = {}
        self._undocumented_categories = {}
        self._special_handling = {}
        self._quirks_index = {}
        self._load_data()

    def _load_data(self) -> None:
        """Load and cache quirks data from JSON file."""
        intelligence_dir = Path(__file__).parent.parent.parent / "intelligence"
        quirks_file = intelligence_dir / "quirks.json"

        with open(quirks_file, "r") as f:
            self._quirks_data = json.load(f)

        # Process different types of quirks
        self._process_category_duplicates()
        self._process_multi_entity_devices()
        self._process_dpcode_fallbacks()
        self._process_undocumented_categories()
        self._build_quirks_index()

    def _process_category_duplicates(self) -> None:
        """Process category duplicate mappings."""
        duplicates = self._quirks_data.get("category_duplicates", {})
        if "mappings" in duplicates:
            for duplicate, original in duplicates["mappings"].items():
                self._category_duplicates[duplicate] = original

                # Create quirk entry
                quirk = DeviceQuirk(
                    category_id=duplicate,
                    quirk_type=QuirkType.CATEGORY_DUPLICATE,
                    description=f"Category '{duplicate}' is a duplicate of '{original}'",
                    data={"original_category": original},
                    workaround=f"Use category '{original}' instead",
                )
                self._quirks_index[duplicate] = quirk

    def _process_multi_entity_devices(self) -> None:
        """Process multi-entity device configurations."""
        multi_entity = self._quirks_data.get("multi_entity_devices", {})
        if "examples" in multi_entity:
            for category_id, device_info in multi_entity["examples"].items():
                entity_mappings = []

                for entity_data in device_info.get("entities", []):
                    mapping = EntityMapping(
                        key=entity_data["key"],
                        brightness_dpcode=entity_data.get("brightness"),
                        entity_type=entity_data.get("type", "light"),
                    )
                    entity_mappings.append(mapping)

                self._multi_entity_devices[category_id] = entity_mappings

                # Create quirk entry
                quirk = DeviceQuirk(
                    category_id=category_id,
                    quirk_type=QuirkType.MULTI_ENTITY,
                    description=f"Device creates multiple entities: {device_info['name']}",
                    data={"name": device_info["name"], "entities": entity_mappings},
                    workaround="Handle multiple entity creation during device setup",
                )
                self._quirks_index[category_id] = quirk

    def _process_dpcode_fallbacks(self) -> None:
        """Process DPCode fallback sequences."""
        fallbacks = self._quirks_data.get("dpcode_fallbacks", {})
        if "examples" in fallbacks:
            for fallback_name, fallback_info in fallbacks["examples"].items():
                if isinstance(fallback_info, str):
                    # Extract DPCodes from string format like "(DPCode.A, DPCode.B)"
                    if fallback_info.startswith("(") and fallback_info.endswith(")"):
                        dpcode_str = fallback_info[1:-1]
                        dpcodes = [
                            code.strip().replace("DPCode.", "")
                            for code in dpcode_str.split(",")
                        ]
                        if len(dpcodes) >= 2:
                            fallback = DPCodeFallback(
                                primary_dpcode=dpcodes[0],
                                fallback_dpcodes=dpcodes[1:],
                                description=f"Fallback sequence for {fallback_name}",
                            )
                            self._dpcode_fallbacks[fallback_name] = fallback

    def _process_undocumented_categories(self) -> None:
        """Process undocumented device categories."""
        undocumented = self._quirks_data.get("undocumented_categories", {})
        if "categories" in undocumented:
            for category_id, description in undocumented["categories"].items():
                self._undocumented_categories[category_id] = description

                # Create quirk entry
                quirk = DeviceQuirk(
                    category_id=category_id,
                    quirk_type=QuirkType.UNDOCUMENTED_CATEGORY,
                    description=f"Undocumented category: {description}",
                    data={"description": description},
                    workaround="Use heuristic detection and best-guess mappings",
                )
                self._quirks_index[category_id] = quirk

    def _build_quirks_index(self) -> None:
        """Build index of all quirks for fast lookups."""
        # Index is built incrementally in other methods
        pass

    def get_canonical_category(self, category_id: str) -> str:
        """
        Get the canonical category ID, resolving duplicates.

        Args:
            category_id: Category ID to resolve

        Returns:
            Canonical category ID
        """
        return self._category_duplicates.get(category_id, category_id)

    def is_duplicate_category(self, category_id: str) -> bool:
        """
        Check if a category is a duplicate of another.

        Args:
            category_id: Category ID to check

        Returns:
            True if it's a duplicate, False otherwise
        """
        return category_id in self._category_duplicates

    def get_multi_entity_mappings(self, category_id: str) -> List[EntityMapping]:
        """
        Get entity mappings for multi-entity devices.

        Args:
            category_id: Category ID to check

        Returns:
            List of EntityMapping objects
        """
        return self._multi_entity_devices.get(category_id, [])

    def is_multi_entity_device(self, category_id: str) -> bool:
        """
        Check if a device creates multiple entities.

        Args:
            category_id: Category ID to check

        Returns:
            True if multi-entity, False otherwise
        """
        return category_id in self._multi_entity_devices

    def get_dpcode_fallbacks(self, dpcode_name: str) -> Optional[DPCodeFallback]:
        """
        Get DPCode fallback sequence.

        Args:
            dpcode_name: DPCode name to get fallbacks for

        Returns:
            DPCodeFallback object or None
        """
        return self._dpcode_fallbacks.get(dpcode_name)

    def get_fallback_dpcodes(self, primary_dpcode: str) -> List[str]:
        """
        Get fallback DPCodes for a primary DPCode.

        Args:
            primary_dpcode: Primary DPCode to get fallbacks for

        Returns:
            List of fallback DPCodes
        """
        for fallback in self._dpcode_fallbacks.values():
            if fallback.primary_dpcode == primary_dpcode:
                return fallback.fallback_dpcodes
        return []

    def is_undocumented_category(self, category_id: str) -> bool:
        """
        Check if a category is undocumented.

        Args:
            category_id: Category ID to check

        Returns:
            True if undocumented, False otherwise
        """
        return category_id in self._undocumented_categories

    def get_undocumented_description(self, category_id: str) -> Optional[str]:
        """
        Get description for undocumented category.

        Args:
            category_id: Category ID to get description for

        Returns:
            Description string or None
        """
        return self._undocumented_categories.get(category_id)

    def get_quirks_for_category(self, category_id: str) -> List[DeviceQuirk]:
        """
        Get all quirks that apply to a specific category.

        Args:
            category_id: Category ID to get quirks for

        Returns:
            List of DeviceQuirk objects
        """
        quirks = []

        # Check direct quirks
        if category_id in self._quirks_index:
            quirks.append(self._quirks_index[category_id])

        # Check for quirks that apply to multiple categories
        for quirk in self._quirks_index.values():
            if quirk.applies_to_category(category_id) and quirk not in quirks:
                quirks.append(quirk)

        return quirks

    def has_quirks(self, category_id: str) -> bool:
        """
        Check if a category has any quirks.

        Args:
            category_id: Category ID to check

        Returns:
            True if has quirks, False otherwise
        """
        return len(self.get_quirks_for_category(category_id)) > 0

    def apply_category_quirks(self, category_id: str) -> str:
        """
        Apply category-level quirks (like duplicate resolution).

        Args:
            category_id: Original category ID

        Returns:
            Processed category ID
        """
        # Resolve duplicates
        canonical_category = self.get_canonical_category(category_id)

        return canonical_category

    def get_dpcode_with_fallbacks(
        self, category_id: str, dpcode_name: str
    ) -> List[str]:
        """
        Get DPCode with fallbacks for a specific use case.

        Args:
            category_id: Device category
            dpcode_name: DPCode name/use case

        Returns:
            List of DPCodes to try in order
        """
        # Check for category-specific fallbacks
        fallback_key = f"{category_id}_{dpcode_name}"
        fallback = self.get_dpcode_fallbacks(fallback_key)

        if fallback:
            return [fallback.primary_dpcode] + fallback.fallback_dpcodes

        # Check for general fallbacks
        fallback = self.get_dpcode_fallbacks(dpcode_name)
        if fallback:
            return [fallback.primary_dpcode] + fallback.fallback_dpcodes

        # No fallbacks found
        return []

    def get_quirk_summary(self) -> Dict[str, Any]:
        """
        Get summary of all quirks in the system.

        Returns:
            Dictionary with quirk statistics
        """
        quirk_counts = {}
        for quirk_type in QuirkType:
            quirk_counts[quirk_type.value] = 0

        for quirk in self._quirks_index.values():
            quirk_counts[quirk.quirk_type.value] += 1

        return {
            "total_quirks": len(self._quirks_index),
            "quirk_counts": quirk_counts,
            "category_duplicates": len(self._category_duplicates),
            "multi_entity_devices": len(self._multi_entity_devices),
            "dpcode_fallbacks": len(self._dpcode_fallbacks),
            "undocumented_categories": len(self._undocumented_categories),
        }

    def validate_category_against_quirks(
        self, category_id: str, expected_behavior: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate expected behavior against known quirks.

        Args:
            category_id: Category ID to validate
            expected_behavior: Expected device behavior

        Returns:
            Validation results with quirk considerations
        """
        results = {
            "category_id": category_id,
            "canonical_category": self.get_canonical_category(category_id),
            "has_quirks": self.has_quirks(category_id),
            "quirks": self.get_quirks_for_category(category_id),
            "warnings": [],
            "recommendations": [],
        }

        # Check for category duplicates
        if self.is_duplicate_category(category_id):
            results["warnings"].append(
                f"Category '{category_id}' is a duplicate of '{results['canonical_category']}'"
            )
            results["recommendations"].append(
                f"Use category '{results['canonical_category']}' instead"
            )

        # Check for multi-entity devices
        if self.is_multi_entity_device(category_id):
            entity_mappings = self.get_multi_entity_mappings(category_id)
            results["warnings"].append(
                f"Device creates {len(entity_mappings)} entities"
            )
            results["recommendations"].append(
                "Handle multiple entity creation during device setup"
            )

        # Check for undocumented categories
        if self.is_undocumented_category(category_id):
            description = self.get_undocumented_description(category_id)
            results["warnings"].append(f"Category is undocumented: {description}")
            results["recommendations"].append(
                "Use heuristic detection and conservative mappings"
            )

        return results


# Common quirk detection patterns
COMMON_QUIRK_PATTERNS = {
    "brightness_fallback": ["bright_value_v2", "bright_value"],
    "color_temp_fallback": ["temp_value_v2", "temp_value"],
    "color_data_fallback": ["colour_data_v2", "colour_data"],
    "switch_fallback": ["switch_led", "switch_1", "switch"],
}

# Known problematic categories that need special handling
PROBLEMATIC_CATEGORIES = {
    "mbd": "VECINO RGBW light - limited documentation",
    "qjdcz": "Unknown product - multiple capabilities",
    "hxd": "Wake Up Light II - complex entity mapping",
    "tyd": "Outdoor Flood Light - weather-specific features",
}

# Default instance for easy access
quirks_manager = DeviceQuirksManager()
