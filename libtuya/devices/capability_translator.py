"""
CapabilityTranslator - Handles DPS mapping and capability translation.

This module provides the CapabilityTranslator class that manages the translation
between device capabilities and DPS indices, value scaling, and capability discovery.
"""

import logging
from typing import Any, Dict, List, Optional

from libtuya.auth.models import DeviceInfo
from libtuya.dps import DPSMapper, DPSMappingInfo, DPSMappingResult
from libtuya.dps.capability_patterns import centralized_dps_mapping
from libtuya.intelligence import DeviceAnalysis, DeviceIntelligence
from libtuya.intelligence.quirks import centralized_quirks
from libtuya.intelligence.scaling import centralized_scaling

logger = logging.getLogger(__name__)


class CapabilityTranslator:
    """
    Translates between device capabilities and DPS indices.

    This class handles:
    - DPS mapping initialization and management
    - Capability to DPCode translation
    - Value scaling for different device types
    - Capability discovery and filtering
    """

    def __init__(
        self,
        device_info: DeviceInfo,
        intelligence: DeviceIntelligence,
        dps_mapper: DPSMapper,
        device_analysis: Optional[DeviceAnalysis] = None,
        entity_capabilities: Optional[List[str]] = None,
    ):
        """
        Initialize capability translator.

        Args:
            device_info: Device information from cloud discovery
            intelligence: Device intelligence database
            dps_mapper: DPS mapping system
            device_analysis: Optional device analysis results
            entity_capabilities: Optional list of capabilities for this specific entity
        """
        self.device_info = device_info
        self.intelligence = intelligence
        self.dps_mapper = dps_mapper
        self.device_analysis = device_analysis
        self.entity_capabilities = entity_capabilities

        # DPS mappings for capabilities
        self.dps_mappings: Dict[str, DPSMappingInfo] = {}

        # Initialize DPS mapping
        self._initialize_dps_mapping()

    def _initialize_dps_mapping(self):
        """
        Initialize DPS mapping for device capabilities.

        This method combines device intelligence with DPS discovery to create
        a comprehensive mapping of capabilities to DPS indices.
        """
        logger.debug(f"Initializing DPS mapping for {self.device_info.id}")

        try:
            # Get device analysis if not provided
            if not self.device_analysis:
                self.device_analysis = self.intelligence.analyze_device(
                    self.device_info.category, self.device_info.to_dict()
                )

            # Use DPS mapper to get mappings
            mapping_result = self.dps_mapper.get_device_mappings(self.device_info.id)

            self.dps_mappings = mapping_result.mappings

            # Filter by entity capabilities if specified
            if self.entity_capabilities:
                filtered_mappings = {}
                for capability in self.entity_capabilities:
                    if capability in self.dps_mappings:
                        filtered_mappings[capability] = self.dps_mappings[capability]
                self.dps_mappings = filtered_mappings

                logger.debug(
                    f"Filtered DPS mappings to {len(self.dps_mappings)} capabilities for entity: {self.entity_capabilities}"
                )

            logger.debug(
                f"Initialized {len(self.dps_mappings)} DPS mappings for {self.device_info.id}: {list(self.dps_mappings.keys())}"
            )

        except Exception as e:
            logger.debug(f"Failed to initialize DPS mapping for {self.device_info.id}: {e}")
            self.dps_mappings = {}

    def capability_to_dpcode(self, capability: str) -> str:
        """
        Convert capability name to DPCode.

        This method handles the translation from libtuya capability names
        to Home Assistant DPCodes for cloud control.

        Args:
            capability: Capability name (e.g., "switch_led")

        Returns:
            Corresponding DPCode (e.g., "switch_led")
        """
        # For most cases, capability names are already DPCodes
        # But we may need special handling for some cases

        # Common capability mappings
        capability_mappings = {
            "switch": "switch_led",
            "brightness": "bright_value",
            "color": "colour_data",
            "color_temp": "temp_value",
            "power": "switch_led",
        }

        # Check if we have a direct mapping
        if capability in capability_mappings:
            dpcode = capability_mappings[capability]
            logger.debug(f"Mapped capability '{capability}' to DPCode '{dpcode}'")
            return dpcode

        # For most cases, the capability name is already the DPCode
        logger.debug(f"Using capability name '{capability}' as DPCode")
        return capability

    def dpcode_to_capability(self, dpcode: str) -> str:
        """
        Convert DPCode to capability name.

        This method handles the reverse translation from Home Assistant DPCodes
        to libtuya capability names.

        Args:
            dpcode: DPCode (e.g., "switch_led")

        Returns:
            Corresponding capability name (e.g., "switch_led")
        """
        # Reverse mappings
        dpcode_mappings = {
            "switch_led": "switch",
            "bright_value": "brightness",
            "colour_data": "color",
            "temp_value": "color_temp",
        }

        # Check if we have a reverse mapping
        if dpcode in dpcode_mappings:
            capability = dpcode_mappings[dpcode]
            logger.debug(f"Mapped DPCode '{dpcode}' to capability '{capability}'")
            return capability

        # For most cases, the DPCode is already the capability name
        logger.debug(f"Using DPCode '{dpcode}' as capability name")
        return dpcode

    def scale_value(self, capability: str, value: Any, mapping_info: DPSMappingInfo) -> Any:
        """
        Scale a value using centralized device scaling.

        Args:
            capability: Capability name
            value: Raw value
            mapping_info: DPS mapping information

        Returns:
            Scaled value
        """
        try:
            # Use centralized scaling interface
            mapping_dict = mapping_info.__dict__ if mapping_info else None
            return centralized_scaling.scale_any_value(value, capability, mapping_dict)
        except Exception as e:
            logger.warning(f"Value scaling failed for {capability}: {e}")
            return value

    def get_switch_capabilities(self) -> List[str]:
        """
        Get switch capabilities available for this device.

        Returns:
            List of switch capability names prioritized by reliability
        """
        if not self.device_analysis:
            return ["switch_led", "switch", "switch_1"]

        # Get capabilities from device analysis
        capabilities = []

        # Add capabilities based on device analysis
        if hasattr(self.device_analysis, "capabilities"):
            for cap_name in self.device_analysis.capabilities:
                if "switch" in cap_name.lower():
                    capabilities.append(cap_name)

        # Add DPS mapped switch capabilities
        for cap_name in self.dps_mappings.keys():
            if "switch" in cap_name.lower() and cap_name not in capabilities:
                capabilities.append(cap_name)

        # Add common fallbacks if no specific capabilities found
        if not capabilities:
            capabilities = [
                "switch_led",
                "switch",
                "switch_1",
                "switch_2",
                "switch_3",
            ]

        logger.debug(f"Found switch capabilities for {self.device_info.id}: {capabilities}")
        return capabilities

    def get_brightness_capabilities(self) -> List[str]:
        """
        Get brightness capabilities available for this device.

        Returns:
            List of brightness capability names
        """
        if not self.device_analysis:
            return ["bright_value", "brightness"]

        capabilities = []

        # Add capabilities based on device analysis
        if hasattr(self.device_analysis, "capabilities"):
            for cap_name in self.device_analysis.capabilities:
                if any(keyword in cap_name.lower() for keyword in ["bright", "dimmer"]):
                    capabilities.append(cap_name)

        # Add DPS mapped brightness capabilities
        for cap_name in self.dps_mappings.keys():
            if (
                any(keyword in cap_name.lower() for keyword in ["bright", "dimmer"])
                and cap_name not in capabilities
            ):
                capabilities.append(cap_name)

        # Add common fallbacks if no specific capabilities found
        if not capabilities:
            capabilities = ["bright_value", "brightness", "bright_value_v2"]

        logger.debug(f"Found brightness capabilities for {self.device_info.id}: {capabilities}")
        return capabilities

    def get_color_capabilities(self) -> List[str]:
        """
        Get color capabilities available for this device.

        Returns:
            List of color capability names
        """
        if not self.device_analysis:
            return ["colour_data", "color"]

        capabilities = []

        # Add capabilities based on device analysis
        if hasattr(self.device_analysis, "capabilities"):
            for cap_name in self.device_analysis.capabilities:
                if any(keyword in cap_name.lower() for keyword in ["color", "colour", "rgb"]):
                    capabilities.append(cap_name)

        # Add DPS mapped color capabilities
        for cap_name in self.dps_mappings.keys():
            if (
                any(keyword in cap_name.lower() for keyword in ["color", "colour", "rgb"])
                and cap_name not in capabilities
            ):
                capabilities.append(cap_name)

        # Add common fallbacks if no specific capabilities found
        if not capabilities:
            capabilities = ["colour_data", "color", "colour_data_v2"]

        logger.debug(f"Found color capabilities for {self.device_info.id}: {capabilities}")
        return capabilities

    def get_color_temperature_capabilities(self) -> List[str]:
        """
        Get color temperature capabilities available for this device.

        Returns:
            List of color temperature capability names
        """
        if not self.device_analysis:
            return ["temp_value", "color_temp"]

        capabilities = []

        # Add capabilities based on device analysis
        if hasattr(self.device_analysis, "capabilities"):
            for cap_name in self.device_analysis.capabilities:
                if any(keyword in cap_name.lower() for keyword in ["temp", "temperature"]):
                    capabilities.append(cap_name)

        # Add DPS mapped temperature capabilities
        for cap_name in self.dps_mappings.keys():
            if (
                any(keyword in cap_name.lower() for keyword in ["temp", "temperature"])
                and cap_name not in capabilities
            ):
                capabilities.append(cap_name)

        # Add common fallbacks if no specific capabilities found
        if not capabilities:
            capabilities = ["temp_value", "color_temp", "temp_value_v2"]

        logger.debug(
            f"Found color temperature capabilities for {self.device_info.id}: {capabilities}"
        )
        return capabilities

    def get_available_capabilities(self) -> List[str]:
        """
        Get all available capabilities for this device.

        Returns:
            List of all capability names
        """
        capabilities = list(self.dps_mappings.keys())

        # Add capabilities from device analysis if available
        if self.device_analysis and hasattr(self.device_analysis, "capabilities"):
            for cap_name in self.device_analysis.capabilities:
                if cap_name not in capabilities:
                    capabilities.append(cap_name)

        # Filter by entity capabilities if specified
        if self.entity_capabilities:
            capabilities = [cap for cap in capabilities if cap in self.entity_capabilities]

        return capabilities

    def get_dps_mapping(self, capability: str) -> Optional[DPSMappingInfo]:
        """
        Get DPS mapping information for a specific capability.

        Args:
            capability: Capability name

        Returns:
            DPS mapping information or None if not found
        """
        return self.dps_mappings.get(capability)

    def has_capability(self, capability: str) -> bool:
        """
        Check if the device has a specific capability.

        Args:
            capability: Capability name to check

        Returns:
            True if capability is available, False otherwise
        """
        return capability in self.dps_mappings

    def get_translator_info(self) -> Dict[str, Any]:
        """
        Get information about the capability translator state.

        Returns:
            Dictionary with translator status and mapping information
        """
        return {
            "device_id": self.device_info.id,
            "device_name": self.device_info.name,
            "device_category": self.device_info.category,
            "has_device_analysis": self.device_analysis is not None,
            "dps_mappings_count": len(self.dps_mappings),
            "available_capabilities": self.get_available_capabilities(),
            "switch_capabilities": self.get_switch_capabilities(),
            "brightness_capabilities": self.get_brightness_capabilities(),
            "color_capabilities": self.get_color_capabilities(),
            "color_temperature_capabilities": self.get_color_temperature_capabilities(),
            "entity_capabilities": self.entity_capabilities,
            "dps_mappings": {
                k: {"dps": v.dps, "data_type": v.data_type} for k, v in self.dps_mappings.items()
            },
        }

    def refresh_mappings(self):
        """
        Refresh DPS mappings by re-running the initialization process.

        This can be useful if device status or capabilities have changed.
        """
        logger.debug(f"Refreshing DPS mappings for {self.device_info.id}")
        self._initialize_dps_mapping()
