"""
Device-specific quirks and edge cases for Tuya devices.

This module handles device-specific workarounds and edge cases discovered
in Home Assistant's Tuya integration.
"""

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


class QuirkType(str, Enum):
    """Types of device quirks."""

    CATEGORY_DUPLICATE = "category_duplicate"
    MULTI_ENTITY = "multi_entity"
    DPCODE_FALLBACK = "dpcode_fallback"
    UNDOCUMENTED_CATEGORY = "undocumented_category"
    SPECIAL_HANDLING = "special_handling"
    VALUE_MAPPING = "value_mapping"
    ENERGY_MONITORING = "energy_monitoring"
    MULTI_GANG_SWITCH = "multi_gang_switch"
    FAN_LIGHT_COMBO = "fan_light_combo"
    COMPLEX_LIGHTING = "complex_lighting"


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
        return self.category_id == category_id or category_id in self.data.get("applies_to", [])


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


@dataclass
class MultiEntityPattern:
    """Represents a multi-entity device pattern."""

    pattern_type: str
    entity_types: List[str]
    frequency: int
    dps_ranges: Dict[str, str]
    dps_mapping: Dict[str, str]
    confidence_threshold: float = 0.8


@dataclass
class EnergyMonitoringPattern:
    """Represents energy monitoring device patterns."""

    phase_count: int  # 1 for single-phase, 3 for three-phase
    dps_mappings: Dict[str, Dict[str, str]]
    typical_dps_range: Tuple[int, int]  # e.g., (100, 130)


@dataclass
class MultiGangPattern:
    """Represents multi-gang switch patterns."""

    gang_count: int
    switch_dps: List[str]
    timer_dps: List[str]
    config_dps: List[str]


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

        # New multi-entity pattern data
        self._multi_entity_patterns = {}
        self._energy_monitoring_patterns = {}
        self._multi_gang_patterns = {}
        self._fan_light_patterns = {}

        self._load_data()

    def _load_data(self) -> None:
        """Load and cache quirks data from JSON file."""
        intelligence_dir = Path(__file__).parent / "data"
        quirks_file = intelligence_dir / "quirks.json"

        with open(quirks_file, "r") as f:
            self._quirks_data = json.load(f)

        # Process different types of quirks
        self._process_category_duplicates()
        self._process_multi_entity_devices()
        self._process_dpcode_fallbacks()
        self._process_undocumented_categories()

        # Process new multi-entity patterns
        self._process_multi_entity_patterns()
        self._process_energy_monitoring_patterns()
        self._process_multi_gang_patterns()
        self._process_fan_light_patterns()

        self._build_quirks_index()

    def _process_category_duplicates(self) -> None:
        """Process category duplicate mappings."""
        duplicates = self._quirks_data.get("category_duplicates", {}) if self._quirks_data else {}
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
        multi_entity = (
            self._quirks_data.get("multi_entity_devices", {}) if self._quirks_data else {}
        )
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
                    data={
                        "name": device_info["name"],
                        "entities": entity_mappings,
                    },
                    workaround="Handle multiple entity creation during device setup",
                )
                self._quirks_index[category_id] = quirk

    def _process_dpcode_fallbacks(self) -> None:
        """Process DPCode fallback sequences."""
        fallbacks = self._quirks_data.get("dpcode_fallbacks", {}) if self._quirks_data else {}
        if "examples" in fallbacks:
            for fallback_name, fallback_info in fallbacks["examples"].items():
                if isinstance(fallback_info, str):
                    # Extract DPCodes from string format like "(DPCode.A, DPCode.B)"
                    if fallback_info.startswith("(") and fallback_info.endswith(")"):
                        dpcode_str = fallback_info[1:-1]
                        dpcodes = [
                            code.strip().replace("DPCode.", "") for code in dpcode_str.split(",")
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
        undocumented = (
            self._quirks_data.get("undocumented_categories", {}) if self._quirks_data else {}
        )
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

    def _process_multi_entity_patterns(self) -> None:
        """Process multi-entity pattern recognition data."""
        pattern_data = self._quirks_data.get("multi_entity_pattern_recognition", {})
        common_combinations = pattern_data.get("common_combinations", {})

        for pattern_name, pattern_info in common_combinations.items():
            pattern = MultiEntityPattern(
                pattern_type=pattern_name,
                entity_types=pattern_info.get("entity_types", []),
                frequency=pattern_info.get("frequency", 0),
                dps_ranges=pattern_info.get("dps_patterns", {}),
                dps_mapping=pattern_info.get("dps_patterns", {}).get("typical_mapping", {}),
                confidence_threshold=0.8,
            )
            self._multi_entity_patterns[pattern_name] = pattern

    def _process_energy_monitoring_patterns(self) -> None:
        """Process energy monitoring patterns."""
        energy_data = self._quirks_data.get("multi_entity_pattern_recognition", {}).get(
            "energy_monitoring_detailed", {}
        )

        # Single phase pattern
        if "single_phase" in energy_data:
            single_phase = EnergyMonitoringPattern(
                phase_count=1,
                dps_mappings={"phase_a": energy_data["single_phase"]},
                typical_dps_range=(103, 110),
            )
            self._energy_monitoring_patterns["single_phase"] = single_phase

        # Three phase pattern
        if "three_phase" in energy_data:
            three_phase = EnergyMonitoringPattern(
                phase_count=3,
                dps_mappings=energy_data["three_phase"],
                typical_dps_range=(101, 129),
            )
            self._energy_monitoring_patterns["three_phase"] = three_phase

    def _process_multi_gang_patterns(self) -> None:
        """Process multi-gang switch patterns."""
        gang_data = self._quirks_data.get("multi_entity_pattern_recognition", {}).get(
            "multi_gang_patterns", {}
        )
        switch_patterns = gang_data.get("switch_patterns", {})

        for gang_type, pattern_info in switch_patterns.items():
            gang_count = int(gang_type.split("_")[0])
            pattern = MultiGangPattern(
                gang_count=gang_count,
                switch_dps=pattern_info.get("switches", []),
                timer_dps=pattern_info.get("timers", []),
                config_dps=pattern_info.get("config", []),
            )
            self._multi_gang_patterns[gang_type] = pattern

    def _process_fan_light_patterns(self) -> None:
        """Process fan+light combination patterns."""
        fan_light_data = self._quirks_data.get("multi_entity_pattern_recognition", {}).get(
            "fan_light_combos", {}
        )
        patterns = fan_light_data.get("patterns", {})

        for pattern_name, pattern_info in patterns.items():
            self._fan_light_patterns[pattern_name] = pattern_info

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

    def get_dpcode_with_fallbacks(self, category_id: str, dpcode_name: str) -> List[str]:
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
            results["warnings"].append(f"Device creates {len(entity_mappings)} entities")
            results["recommendations"].append("Handle multiple entity creation during device setup")

        # Check for undocumented categories
        if self.is_undocumented_category(category_id):
            description = self.get_undocumented_description(category_id)
            results["warnings"].append(f"Category is undocumented: {description}")
            results["recommendations"].append("Use heuristic detection and conservative mappings")

        return results

    def detect_multi_entity_pattern(
        self, available_dps: List[int], device_category: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        Detect multi-entity patterns based on available DPS indices.

        Args:
            available_dps: List of available DPS indices
            device_category: Optional device category for context

        Returns:
            Dictionary with pattern detection results or None if no pattern detected
        """
        dps_set = set(available_dps)
        detection_results = {
            "detected_patterns": [],
            "entity_count_estimate": 1,
            "confidence": 0.0,
            "recommendations": [],
        }

        # Check for energy monitoring patterns
        energy_pattern = self._detect_energy_monitoring(dps_set)
        if energy_pattern:
            detection_results["detected_patterns"].append(energy_pattern)

        # Check for multi-gang switch patterns
        gang_pattern = self._detect_multi_gang_switch(dps_set)
        if gang_pattern:
            detection_results["detected_patterns"].append(gang_pattern)

        # Check for fan+light combinations
        fan_light_pattern = self._detect_fan_light_combo(dps_set)
        if fan_light_pattern:
            detection_results["detected_patterns"].append(fan_light_pattern)

        # Check for complex lighting patterns
        lighting_pattern = self._detect_complex_lighting(dps_set)
        if lighting_pattern:
            detection_results["detected_patterns"].append(lighting_pattern)

        # Calculate overall confidence and entity count
        if detection_results["detected_patterns"]:
            detection_results["confidence"] = max(
                p.get("confidence", 0) for p in detection_results["detected_patterns"]
            )
            detection_results["entity_count_estimate"] = sum(
                p.get("entity_count", 1) for p in detection_results["detected_patterns"]
            )
            detection_results["recommendations"] = [
                p.get("recommendation")
                for p in detection_results["detected_patterns"]
                if p.get("recommendation")
            ]
            return detection_results

        return None

    def _detect_energy_monitoring(self, dps_set: Set[int]) -> Optional[Dict[str, Any]]:
        """Detect energy monitoring device patterns."""
        # Check for DPS 100+ range with systematic patterns
        high_dps = [dps for dps in dps_set if dps >= 100]
        if len(high_dps) < 3:
            return None

        # Check for single-phase pattern (103-110)
        single_phase_dps = [103, 104, 105, 109, 110]
        single_phase_matches = len([dps for dps in single_phase_dps if dps in dps_set])

        # Check for three-phase pattern
        phase_a_dps = [103, 104, 105, 109]
        phase_b_dps = [113, 114, 115, 119]
        phase_c_dps = [123, 124, 125, 129]

        phase_a_matches = len([dps for dps in phase_a_dps if dps in dps_set])
        phase_b_matches = len([dps for dps in phase_b_dps if dps in dps_set])
        phase_c_matches = len([dps for dps in phase_c_dps if dps in dps_set])

        if single_phase_matches >= 3:
            return {
                "pattern_type": "energy_monitoring",
                "subtype": "single_phase",
                "confidence": min(single_phase_matches / len(single_phase_dps), 1.0),
                "entity_count": single_phase_matches,
                "matched_dps": [dps for dps in single_phase_dps if dps in dps_set],
                "recommendation": f"Create {single_phase_matches} energy monitoring entities",
            }
        elif phase_a_matches >= 2 and (phase_b_matches >= 2 or phase_c_matches >= 2):
            total_matches = phase_a_matches + phase_b_matches + phase_c_matches
            return {
                "pattern_type": "energy_monitoring",
                "subtype": "three_phase",
                "confidence": min(total_matches / (len(phase_a_dps) * 3), 1.0),
                "entity_count": total_matches,
                "matched_dps": (
                    [dps for dps in phase_a_dps if dps in dps_set]
                    + [dps for dps in phase_b_dps if dps in dps_set]
                    + [dps for dps in phase_c_dps if dps in dps_set]
                ),
                "recommendation": f"Create {total_matches} energy monitoring entities for three-phase system",
            }

        return None

    def _detect_multi_gang_switch(self, dps_set: Set[int]) -> Optional[Dict[str, Any]]:
        """Detect multi-gang switch patterns."""
        # Check for switch DPS in range 1-6
        switch_dps = [dps for dps in dps_set if 1 <= dps <= 6]
        timer_dps = [dps for dps in dps_set if 9 <= dps <= 14]
        config_dps = [dps for dps in dps_set if 38 <= dps <= 43]

        if len(switch_dps) < 2:
            return None

        # Determine gang count
        gang_count = len(switch_dps)
        expected_timers = gang_count
        expected_config = gang_count

        # Calculate confidence based on pattern completeness
        timer_score = min(len(timer_dps) / expected_timers, 1.0) if expected_timers > 0 else 0
        config_score = min(len(config_dps) / expected_config, 1.0) if expected_config > 0 else 0
        switch_score = 1.0  # We already confirmed switches exist

        confidence = switch_score * 0.6 + timer_score * 0.3 + config_score * 0.1

        if confidence >= 0.6:  # Require at least switches + some other evidence
            return {
                "pattern_type": "multi_gang_switch",
                "subtype": f"{gang_count}_gang",
                "confidence": confidence,
                "entity_count": gang_count,
                "switch_dps": switch_dps,
                "timer_dps": timer_dps,
                "config_dps": config_dps,
                "recommendation": f"Create {gang_count} switch entities with timers and config",
            }

        return None

    def _detect_fan_light_combo(self, dps_set: Set[int]) -> Optional[Dict[str, Any]]:
        """Detect fan+light combination patterns."""
        # Check for light DPS in range 20-26
        light_dps = [dps for dps in dps_set if 20 <= dps <= 26]
        # Check for fan DPS in range 60-65
        fan_dps = [dps for dps in dps_set if 60 <= dps <= 65]

        if len(light_dps) >= 2 and len(fan_dps) >= 2:
            confidence = min((len(light_dps) + len(fan_dps)) / 6, 1.0)
            return {
                "pattern_type": "fan_light_combo",
                "subtype": "ceiling_fan_light",
                "confidence": confidence,
                "entity_count": 2,  # One light entity, one fan entity
                "light_dps": light_dps,
                "fan_dps": fan_dps,
                "recommendation": "Create separate light and fan entities",
            }

        return None

    def _detect_complex_lighting(self, dps_set: Set[int]) -> Optional[Dict[str, Any]]:
        """Detect complex lighting patterns with DPS 20-26 ranges."""
        # Check for DPS in the 20-26 range (advanced lighting features)
        lighting_dps = [dps for dps in dps_set if 20 <= dps <= 26]

        if len(lighting_dps) >= 3:
            confidence = min(len(lighting_dps) / 7, 1.0)  # 7 is max expected DPS in range
            return {
                "pattern_type": "complex_lighting",
                "subtype": "advanced_features",
                "confidence": confidence,
                "entity_count": 1 + len(lighting_dps) // 3,  # Main light + feature entities
                "lighting_dps": lighting_dps,
                "recommendation": f"Create advanced lighting entity with {len(lighting_dps)} features",
            }

        return None

    def categorize_entity_type(self, dps: int, capability: str) -> str:
        """
        Categorize entity type as config, diagnostic, or primary.

        Args:
            dps: DPS index
            capability: Capability name

        Returns:
            Entity category: 'config', 'diagnostic', or 'primary'
        """
        # Config entities (DPS 38+, certain capabilities)
        config_capabilities = {
            "switch_backlight",
            "child_lock",
            "basic_indicator",
            "do_not_disturb",
            "filter_reset",
            "anion",
            "timer",
        }

        # Diagnostic entities (typically high DPS ranges for monitoring, status, fault codes)
        diagnostic_capabilities = {
            "status",
            "fault",
            "error",
            "diagnostic",
            "alarm",
            "warning",
        }

        # Check for energy monitoring capabilities first (primary regardless of DPS)
        energy_terms = {
            "voltage",
            "current",
            "power",
            "energy",
            "watt",
            "amp",
            "volt",
        }
        if any(term in capability.lower() for term in energy_terms):
            return "primary"

        if any(term in capability.lower() for term in diagnostic_capabilities):
            return "diagnostic"

        if dps >= 38 or capability in config_capabilities:
            return "config"

        # Other high DPS are typically diagnostic
        if dps >= 100:
            return "diagnostic"

        # Primary entities (main device functions)
        return "primary"

    def get_multi_entity_patterns(self) -> Dict[str, MultiEntityPattern]:
        """Get all available multi-entity patterns."""
        return self._multi_entity_patterns.copy()

    def get_energy_monitoring_patterns(
        self,
    ) -> Dict[str, EnergyMonitoringPattern]:
        """Get all available energy monitoring patterns."""
        return self._energy_monitoring_patterns.copy()

    def get_multi_gang_patterns(self) -> Dict[str, MultiGangPattern]:
        """Get all available multi-gang patterns."""
        return self._multi_gang_patterns.copy()

    def get_fan_light_patterns(self) -> Dict[str, Any]:
        """Get all available fan+light patterns."""
        return self._fan_light_patterns.copy()


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


class CentralizedQuirksInterface:
    """
    Centralized quirks interface that provides clean access to device quirks handling.

    This interface acts as a facade for the complex DeviceQuirksManager, providing
    simple methods that other components can use without coupling to the internal
    quirks structure. It's already well-centralized, so this mainly provides cleaner APIs.
    """

    def __init__(self):
        """Initialize centralized quirks interface."""
        self._quirks_manager = DeviceQuirksManager()

    def has_quirks(self, category_id: str) -> bool:
        """
        Check if a device category has any known quirks.

        Args:
            category_id: Device category identifier

        Returns:
            True if the category has quirks, False otherwise
        """
        return self._quirks_manager.has_quirks(category_id)

    def get_category_redirect(self, category_id: str) -> Optional[str]:
        """
        Get the redirect category if this category is a duplicate.

        This handles the common case where device categories have duplicates
        that should be mapped to the canonical category.

        Args:
            category_id: Device category to check

        Returns:
            Canonical category ID if redirect exists, None otherwise
        """
        return self._quirks_manager.get_category_redirect(category_id)

    def is_multi_entity_device(self, category_id: str) -> bool:
        """
        Check if a device category represents a multi-entity device.

        Args:
            category_id: Device category identifier

        Returns:
            True if device creates multiple entities, False otherwise
        """
        return self._quirks_manager.is_multi_entity_device(category_id)

    def get_multi_entity_config(self, category_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        Get multi-entity configuration for a device category.

        Args:
            category_id: Device category identifier

        Returns:
            List of entity configurations or None if not multi-entity
        """
        entities = self._quirks_manager.get_multi_entity_entities(category_id)
        if not entities:
            return None

        # Convert to simple dictionary format
        entity_configs = []
        for entity in entities:
            config = {
                "key": entity.key,
                "entity_type": entity.entity_type,
                "brightness_dpcode": entity.brightness_dpcode,
                "additional_dpcodes": entity.additional_dpcodes or [],
            }
            entity_configs.append(config)

        return entity_configs

    def get_dpcode_fallbacks(self, dpcode: str) -> List[str]:
        """
        Get fallback DPCodes for a given DPCode.

        Args:
            dpcode: Primary DPCode to get fallbacks for

        Returns:
            List of fallback DPCodes in order of preference
        """
        fallback = self._quirks_manager.get_dpcode_fallback(dpcode)
        if fallback:
            return fallback.fallback_dpcodes
        return []

    def detect_multi_entity_pattern(
        self, category_id: str, available_dps: Dict[int, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Detect multi-entity patterns in device DPS data.

        Args:
            category_id: Device category
            available_dps: Available DPS data from device

        Returns:
            Multi-entity pattern information or None
        """
        pattern = self._quirks_manager.detect_multi_entity_pattern(category_id, available_dps)
        if not pattern:
            return None

        return {
            "pattern_type": pattern.pattern_type,
            "entity_types": pattern.entity_types,
            "confidence": pattern.frequency / 100.0,  # Convert to confidence score
            "dps_ranges": pattern.dps_ranges,
            "dps_mapping": pattern.dps_mapping,
        }

    def needs_special_handling(self, category_id: str) -> bool:
        """
        Check if a device category needs special handling.

        Args:
            category_id: Device category identifier

        Returns:
            True if special handling is required, False otherwise
        """
        return category_id in self._quirks_manager._special_handling

    def get_special_handling_info(self, category_id: str) -> Optional[Dict[str, Any]]:
        """
        Get special handling information for a device category.

        Args:
            category_id: Device category identifier

        Returns:
            Special handling information or None
        """
        return self._quirks_manager._special_handling.get(category_id)

    def get_all_quirks_for_category(self, category_id: str) -> List[Dict[str, Any]]:
        """
        Get all quirks that apply to a device category.

        Args:
            category_id: Device category identifier

        Returns:
            List of quirk information dictionaries
        """
        all_quirks = self._quirks_manager.get_quirks_for_category(category_id)

        quirk_info = []
        for quirk in all_quirks:
            info = {
                "type": quirk.quirk_type.value,
                "description": quirk.description,
                "workaround": quirk.workaround,
                "data": quirk.data,
            }
            quirk_info.append(info)

        return quirk_info

    def apply_category_quirks(self, category_id: str) -> str:
        """
        Apply all relevant quirks to a device category and return the corrected category.

        This is a convenience method that applies redirects and other category-level
        quirks to return the category that should actually be used.

        Args:
            category_id: Original device category

        Returns:
            Corrected device category after applying quirks
        """
        # Apply category redirect if it exists
        redirect = self.get_category_redirect(category_id)
        if redirect:
            return redirect

        # Return original category if no quirks apply
        return category_id


# Default instances for easy access
quirks_manager = DeviceQuirksManager()
centralized_quirks = CentralizedQuirksInterface()
