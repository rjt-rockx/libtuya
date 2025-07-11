"""
Device Intelligence Database for libtuya.

This module provides a unified interface to Home Assistant's Tuya device intelligence,
including DPCode definitions, device mappings, value scaling, and quirks handling.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union

from .device_mappings import (
    COMMON_LIGHT_CAPABILITIES,
    COMMON_SENSOR_CAPABILITIES,
    COMMON_SWITCH_CAPABILITIES,
    DeviceCategory,
    DeviceMappingManager,
    IntelligenceCapability,
    device_mapping_manager,
)
from .dpcodes import DPCode, DPCodeManager, dpcode_manager
from .quirks import (
    COMMON_QUIRK_PATTERNS,
    DeviceQuirk,
    DeviceQuirksManager,
    DPCodeFallback,
    EntityMapping,
    QuirkType,
    quirks_manager,
)
from .scaling import (
    BRIGHTNESS_PRESETS,
    COLOR_TEMP_PRESETS,
    ColorTypeData,
    EnumTypeData,
    IntegerTypeData,
    ValueScalingManager,
    remap_value,
    scaling_manager,
)


@dataclass
class DeviceAnalysis:
    """Complete analysis of a device's capabilities and characteristics."""

    category_id: str
    canonical_category: str
    category_name: str
    platform: str
    capabilities: List[str]
    supported_dpcodes: List[str]
    quirks: List[DeviceQuirk]
    has_quirks: bool
    is_multi_entity: bool
    entity_mappings: List[EntityMapping]
    scaling_info: Dict[str, Any]
    recommendations: List[str]


@dataclass
class CapabilityInfo:
    """Information about a specific device capability."""

    dpcode: str
    dpcode_name: str
    fallback_dpcodes: List[str]
    data_type: str
    scaling_info: Optional[Union[IntegerTypeData, EnumTypeData]]
    description: str


class DeviceIntelligence:
    """
    Main interface for the Device Intelligence Database.

    This class provides a unified API for accessing all Tuya device intelligence
    extracted from Home Assistant's integration.
    """

    def __init__(self):
        """Initialize the device intelligence system."""
        self.dpcode_manager = dpcode_manager
        self.mapping_manager = device_mapping_manager
        self.scaling_manager = scaling_manager
        self.quirks_manager = quirks_manager

        # Cache for analyzed devices
        self._device_cache = {}
        self._capability_cache = {}

    def analyze_device(
        self, category_id: str, device_info: Optional[Dict[str, Any]] = None
    ) -> DeviceAnalysis:
        """
        Perform complete analysis of a device category.

        Args:
            category_id: Device category ID
            device_info: Optional additional device information

        Returns:
            DeviceAnalysis object with complete device intelligence
        """
        # Check cache first
        cache_key = f"{category_id}_{hash(str(device_info))}"
        if cache_key in self._device_cache:
            return self._device_cache[cache_key]

        # Resolve canonical category
        canonical_category = self.quirks_manager.get_canonical_category(category_id)

        # Get basic category info
        category = self.mapping_manager.get_category(canonical_category)
        if not category:
            # Handle unknown category
            category = DeviceCategory(
                category_id=canonical_category,
                name=f"Unknown Device ({canonical_category})",
                capabilities=[],
                platform="unknown",
            )

        # Get capabilities and DPCodes
        capabilities = self.mapping_manager.get_capabilities(canonical_category)
        supported_dpcodes = self._get_dpcodes_for_capabilities(capabilities)

        # Get quirks
        quirks = self.quirks_manager.get_quirks_for_category(category_id)
        has_quirks = len(quirks) > 0

        # Check for multi-entity devices
        is_multi_entity = self.quirks_manager.is_multi_entity_device(canonical_category)
        entity_mappings = self.quirks_manager.get_multi_entity_mappings(canonical_category)

        # Get scaling information
        scaling_info = self._get_scaling_info(capabilities)

        # Generate recommendations
        recommendations = self._generate_recommendations(
            category_id, canonical_category, quirks, capabilities
        )

        # Create analysis
        analysis = DeviceAnalysis(
            category_id=category_id,
            canonical_category=canonical_category,
            category_name=category.name,
            platform=category.platform,
            capabilities=capabilities,
            supported_dpcodes=supported_dpcodes,
            quirks=quirks,
            has_quirks=has_quirks,
            is_multi_entity=is_multi_entity,
            entity_mappings=entity_mappings,
            scaling_info=scaling_info,
            recommendations=recommendations,
        )

        # Cache the result
        self._device_cache[cache_key] = analysis
        return analysis

    def get_capabilities(self, category_id: str) -> List[str]:
        """
        Get capabilities for a device category.

        Args:
            category_id: Device category ID

        Returns:
            List of capability names
        """
        canonical_category = self.quirks_manager.get_canonical_category(category_id)
        return self.mapping_manager.get_capabilities(canonical_category)

    def get_dpcodes_for_category(self, category_id: str) -> List[str]:
        """
        Get DPCodes for a device category.

        Args:
            category_id: Device category ID

        Returns:
            List of DPCode values
        """
        capabilities = self.get_capabilities(category_id)
        return self._get_dpcodes_for_capabilities(capabilities)

    def get_capability_info(self, dpcode: str) -> Optional[CapabilityInfo]:
        """
        Get detailed information about a capability.

        Args:
            dpcode: DPCode to get info for

        Returns:
            CapabilityInfo object or None if not found
        """
        if dpcode in self._capability_cache:
            return self._capability_cache[dpcode]

        # Get DPCode name
        dpcode_name = self.dpcode_manager.get_name_by_code(dpcode)
        if not dpcode_name:
            return None

        # Get fallback DPCodes
        fallback_dpcodes = self.quirks_manager.get_fallback_dpcodes(dpcode)

        # Determine data type and scaling info
        data_type = "unknown"
        scaling_info = None

        # Check common patterns for data type
        if "bright" in dpcode.lower():
            data_type = "integer"
            scaling_info = BRIGHTNESS_PRESETS.get("lights_10_1000")
        elif "temp" in dpcode.lower():
            data_type = "integer"
            scaling_info = COLOR_TEMP_PRESETS.get("warm_cool_1000_10000")
        elif "switch" in dpcode.lower():
            data_type = "boolean"
        elif "colour" in dpcode.lower() or "color" in dpcode.lower():
            data_type = "string"
        elif "mode" in dpcode.lower():
            data_type = "enum"

        # Create capability info
        capability_info = CapabilityInfo(
            dpcode=dpcode,
            dpcode_name=dpcode_name,
            fallback_dpcodes=fallback_dpcodes,
            data_type=data_type,
            scaling_info=scaling_info,
            description=f"DPCode {dpcode} ({dpcode_name})",
        )

        # Cache the result
        self._capability_cache[dpcode] = capability_info
        return capability_info

    def scale_value(
        self,
        dpcode: str,
        value: Union[int, float],
        category_id: str,
        target_range: Optional[Tuple[int, int]] = None,
    ) -> Union[int, float]:
        """
        Scale a device value using appropriate scaling logic.

        Args:
            dpcode: DPCode for the value
            value: Raw device value
            category_id: Device category
            target_range: Optional target range (min, max)

        Returns:
            Scaled value
        """
        # Get capability info
        capability_info = self.get_capability_info(dpcode)
        if not capability_info or not capability_info.scaling_info:
            return value

        # Use scaling info
        scaling_info = capability_info.scaling_info
        if isinstance(scaling_info, IntegerTypeData):
            if target_range:
                return scaling_info.remap_value_to(value, target_range[0], target_range[1])
            else:
                return scaling_info.scale_value(value)

        return value

    def convert_color_data(
        self, r: int, g: int, b: int, output_format: str = "hsv"
    ) -> Union[str, Tuple]:
        """
        Convert RGB color data to device format.

        Args:
            r: Red component (0-255)
            g: Green component (0-255)
            b: Blue component (0-255)
            output_format: Output format ("hsv", "hex", "rgb")

        Returns:
            Converted color data
        """
        if output_format == "hsv":
            return self.scaling_manager.convert_rgb_to_hsv(r, g, b)
        elif output_format == "hex":
            return f"#{r:02x}{g:02x}{b:02x}"
        elif output_format == "rgb":
            return (r, g, b)
        else:
            raise ValueError(f"Unsupported output format: {output_format}")

    def suggest_device_category(self, available_dpcodes: List[str]) -> List[str]:
        """
        Suggest device categories based on available DPCodes.

        Args:
            available_dpcodes: List of available DPCode values

        Returns:
            List of suggested category IDs
        """
        # Convert DPCodes to capabilities
        capabilities = []
        for dpcode in available_dpcodes:
            # This is a simplified mapping - in practice, you'd have more sophisticated logic
            if dpcode in ["switch_led", "bright_value", "colour_data"]:
                capabilities.append(dpcode)

        # Get category suggestions
        suggestions = self.mapping_manager.get_category_suggestions(capabilities)

        # Sort by relevance (categories with more matching capabilities first)
        def relevance_score(category_id: str) -> int:
            category_capabilities = self.get_capabilities(category_id)
            return len(set(capabilities) & set(category_capabilities))

        suggestions.sort(key=relevance_score, reverse=True)
        return suggestions

    def validate_device_setup(
        self, category_id: str, available_dpcodes: List[str]
    ) -> Dict[str, Any]:
        """
        Validate device setup against expected capabilities.

        Args:
            category_id: Device category ID
            available_dpcodes: Available DPCode values

        Returns:
            Validation results
        """
        analysis = self.analyze_device(category_id)
        expected_dpcodes = analysis.supported_dpcodes

        available_set = set(available_dpcodes)
        expected_set = set(expected_dpcodes)

        missing = expected_set - available_set
        extra = available_set - expected_set

        # Check for fallback DPCodes
        resolved_missing = []
        for dpcode in missing:
            fallbacks = self.quirks_manager.get_fallback_dpcodes(dpcode)
            if any(fallback in available_set for fallback in fallbacks):
                resolved_missing.append(dpcode)

        # Remove resolved missing DPCodes
        missing = missing - set(resolved_missing)

        return {
            "valid": len(missing) == 0,
            "category_analysis": analysis,
            "expected_dpcodes": expected_dpcodes,
            "available_dpcodes": available_dpcodes,
            "missing_dpcodes": list(missing),
            "extra_dpcodes": list(extra),
            "resolved_via_fallbacks": resolved_missing,
            "recommendations": analysis.recommendations,
        }

    def _get_dpcodes_for_capabilities(self, capabilities: List[str]) -> List[str]:
        """Get DPCodes for a list of capabilities."""
        dpcodes = []
        for capability in capabilities:
            # This is a simplified mapping - in practice, you'd have more sophisticated logic
            if capability in [
                "switch_led",
                "bright_value",
                "colour_data",
                "temp_value",
                "work_mode",
            ]:
                dpcodes.append(capability)
        return dpcodes

    def _get_scaling_info(self, capabilities: List[str]) -> Dict[str, Any]:
        """Get scaling information for capabilities."""
        scaling_info = {}

        for capability in capabilities:
            if "bright" in capability.lower():
                scaling_info[capability] = {
                    "type": "integer",
                    "common_ranges": ["10-1000", "25-255", "1-100"],
                    "default_range": "10-1000",
                }
            elif "temp" in capability.lower():
                scaling_info[capability] = {
                    "type": "integer",
                    "common_ranges": ["1000-10000K", "100-1000 mireds"],
                    "default_range": "1000-10000K",
                }
            elif "colour" in capability.lower():
                scaling_info[capability] = {
                    "type": "string",
                    "formats": ["HSV", "RGB", "hex"],
                    "default_format": "HSV",
                }

        return scaling_info

    def _generate_recommendations(
        self,
        category_id: str,
        canonical_category: str,
        quirks: List[DeviceQuirk],
        capabilities: List[str],
    ) -> List[str]:
        """Generate recommendations for device handling."""
        recommendations = []

        # Category-specific recommendations
        if category_id != canonical_category:
            recommendations.append(
                f"Use canonical category '{canonical_category}' instead of '{category_id}'"
            )

        # Quirk-based recommendations
        for quirk in quirks:
            if quirk.workaround:
                recommendations.append(quirk.workaround)

        # Capability-based recommendations
        if "bright_value" in capabilities:
            recommendations.append("Use brightness scaling with 10-1000 range as default")

        if "colour_data" in capabilities:
            recommendations.append("Implement HSV color conversion with proper scaling")

        if "temp_value" in capabilities:
            recommendations.append("Handle color temperature with Kelvin to mireds conversion")

        return recommendations

    def get_system_stats(self) -> Dict[str, Any]:
        """Get statistics about the intelligence database."""
        return {
            "dpcodes": {
                "total_count": self.dpcode_manager.get_total_count(),
                "categories_covered": len(self.mapping_manager.get_all_categories()),
            },
            "device_categories": self.mapping_manager.get_category_stats(),
            "quirks": self.quirks_manager.get_quirk_summary(),
            "cache_stats": {
                "analyzed_devices": len(self._device_cache),
                "cached_capabilities": len(self._capability_cache),
            },
        }


# Export main classes and functions
__all__ = [
    "DeviceIntelligence",
    "DeviceAnalysis",
    "CapabilityInfo",
    "DPCode",
    "DeviceCategory",
    "DeviceQuirk",
    "IntegerTypeData",
    "EnumTypeData",
    "ColorTypeData",
    "remap_value",
    "COMMON_LIGHT_CAPABILITIES",
    "COMMON_SWITCH_CAPABILITIES",
    "COMMON_SENSOR_CAPABILITIES",
    "BRIGHTNESS_PRESETS",
    "COLOR_TEMP_PRESETS",
    "COMMON_QUIRK_PATTERNS",
]
