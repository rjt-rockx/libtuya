"""
DPS Mapper for libtuya

This module provides the main capability-to-DPS mapping functionality, combining
Home Assistant intelligence with TinyTuya discovery to create bidirectional
mappings between device capabilities and DPS indices.

Key features:
- Combines HA intelligence with TinyTuya discovery
- Creates bidirectional mapping (capability ↔ DPS)
- Handles edge cases and device quirks
- Implements fallback strategies for failed mappings
- Supports multi-entity devices
- Provides mapping persistence and caching
"""

import logging
import json
import time
from typing import Dict, List, Optional, Set, Tuple, Any, Union
from dataclasses import dataclass, field, asdict
from pathlib import Path

from .mapping_rules import DPSMappingRules, DPSConfidence
from .discovery import DPSDiscoveryEngine, DPSDiscoveryResult, DPSMatch


logger = logging.getLogger(__name__)


@dataclass
class DeviceInfo:
    """Device information for DPS mapping"""

    device_id: str
    category: str
    name: Optional[str] = None
    model: Optional[str] = None
    local_key: Optional[str] = None
    ip_address: Optional[str] = None
    protocol_version: Optional[str] = None

    def __post_init__(self):
        """Validate device info"""
        if not self.device_id:
            raise ValueError("Device ID is required")
        if not self.category:
            raise ValueError("Device category is required")


@dataclass
class DPSMappingInfo:
    """Information about a DPS mapping"""

    capability: str
    dpcode: str
    dps: int
    data_type: str
    confidence: float
    scaling_info: Optional[Dict[str, Any]] = None
    device_id: Optional[str] = None
    reason: Optional[str] = None
    value_type: Optional[str] = None
    value_range: Optional[Tuple[Any, Any]] = None
    scale_factor: Optional[float] = None
    verified: bool = False
    last_updated: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        data = asdict(self)
        if isinstance(self.confidence, DPSConfidence):
            data["confidence"] = self.confidence.name
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DPSMappingInfo":
        """Create from dictionary"""
        data = data.copy()
        if "confidence" in data and isinstance(data["confidence"], str):
            data["confidence"] = DPSConfidence[data["confidence"]]
        return cls(**data)


class DPSMappingCache:
    """Cache for DPS mappings to avoid repeated discovery"""

    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Initialize cache

        Args:
            cache_dir: Directory for cache files (default: ~/.libtuya/cache)
        """
        if cache_dir is None:
            cache_dir = Path.home() / ".libtuya" / "cache"

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.cache_file = self.cache_dir / "dps_mappings.json"
        self._cache: Dict[str, Dict[str, DPSMappingInfo]] = {}

        self._load_cache()

    def _load_cache(self):
        """Load cache from disk"""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, "r") as f:
                    data = json.load(f)

                for device_id, mappings in data.items():
                    self._cache[device_id] = {}
                    for capability, mapping_data in mappings.items():
                        self._cache[device_id][capability] = DPSMappingInfo.from_dict(
                            mapping_data
                        )

                logger.debug(f"Loaded {len(self._cache)} device mappings from cache")
        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")
            self._cache = {}

    def _save_cache(self):
        """Save cache to disk"""
        try:
            data = {}
            for device_id, mappings in self._cache.items():
                data[device_id] = {}
                for capability, mapping in mappings.items():
                    data[device_id][capability] = mapping.to_dict()

            with open(self.cache_file, "w") as f:
                json.dump(data, f, indent=2)

            logger.debug(f"Saved {len(self._cache)} device mappings to cache")
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")

    def get_mapping(self, device_id: str, capability: str) -> Optional[DPSMappingInfo]:
        """Get cached mapping for device and capability"""
        return self._cache.get(device_id, {}).get(capability)

    def set_mapping(self, mapping: DPSMappingInfo):
        """Cache a mapping"""
        if mapping.device_id not in self._cache:
            self._cache[mapping.device_id] = {}

        self._cache[mapping.device_id][mapping.capability] = mapping
        self._save_cache()

    def get_device_mappings(self, device_id: str) -> Dict[str, DPSMappingInfo]:
        """Get all cached mappings for a device"""
        return self._cache.get(device_id, {}).copy()

    def clear_device(self, device_id: str):
        """Clear all mappings for a device"""
        if device_id in self._cache:
            del self._cache[device_id]
            self._save_cache()

    def clear_all(self):
        """Clear all cached mappings"""
        self._cache = {}
        self._save_cache()


class DPSMapper:
    """
    Main DPS mapper that combines HA intelligence with TinyTuya discovery
    """

    def __init__(
        self,
        enable_cache: bool = True,
        cache_dir: Optional[Path] = None,
        discovery_timeout: float = 30.0,
        enable_extended_probe: bool = True,
    ):
        """
        Initialize DPS mapper

        Args:
            enable_cache: Whether to enable mapping cache
            cache_dir: Directory for cache files
            discovery_timeout: Timeout for DPS discovery
            enable_extended_probe: Whether to probe extended DPS ranges
        """
        self.enable_cache = enable_cache
        self.cache = DPSMappingCache(cache_dir) if enable_cache else None

        self.discovery_engine = DPSDiscoveryEngine(
            discovery_timeout=discovery_timeout,
            enable_extended_probe=enable_extended_probe,
        )

        self.mapping_rules = DPSMappingRules()

        # Current mappings for active devices
        self._device_mappings: Dict[str, Dict[str, DPSMappingInfo]] = {}

    def discover_dps_mapping(
        self,
        device_info: DeviceInfo,
        expected_capabilities: List[str],
        tinytuya_device,
        force_discovery: bool = False,
    ) -> Dict[str, DPSMappingInfo]:
        """
        Discover DPS mapping for a device

        Args:
            device_info: Information about the device
            expected_capabilities: List of expected capability names
            tinytuya_device: TinyTuya device instance
            force_discovery: Force discovery even if cached

        Returns:
            Dictionary mapping capability names to DPSMappingInfo
        """
        device_id = device_info.device_id

        # Check cache first
        if not force_discovery and self.enable_cache:
            cached_mappings = self.cache.get_device_mappings(device_id)
            if cached_mappings:
                # Filter to only requested capabilities
                relevant_mappings = {
                    cap: mapping
                    for cap, mapping in cached_mappings.items()
                    if cap in expected_capabilities
                }
                if relevant_mappings:
                    logger.info(f"Using cached mappings for device {device_id}")
                    self._device_mappings[device_id] = relevant_mappings
                    return relevant_mappings

        logger.info(
            f"Discovering DPS mapping for device {device_id} category {device_info.category}"
        )

        # Discover available DPS and match to capabilities
        discovery_result, matches = self.discovery_engine.discover_and_match(
            tinytuya_device=tinytuya_device,
            expected_capabilities=expected_capabilities,
            device_category=device_info.category,
        )

        if not discovery_result.success:
            logger.error(
                f"DPS discovery failed for device {device_id}: {discovery_result.error}"
            )
            return {}

        # Convert matches to mapping info
        mappings = {}
        for match in matches:
            mapping_info = DPSMappingInfo(
                device_id=device_id,
                capability=match.capability,
                dps=match.dps,
                confidence=match.confidence,
                reason=match.reason,
                verified=match.verified,
                value_type=(
                    self._infer_value_type(match.value)
                    if match.value is not None
                    else None
                ),
            )

            mappings[match.capability] = mapping_info

            # Cache the mapping
            if self.enable_cache:
                self.cache.set_mapping(mapping_info)

        # Store in current mappings
        self._device_mappings[device_id] = mappings

        logger.info(f"Discovered {len(mappings)} DPS mappings for device {device_id}")
        return mappings

    def get_dps_for_capability(self, device_id: str, capability: str) -> Optional[int]:
        """
        Get DPS index for a capability

        Args:
            device_id: Device identifier
            capability: Capability name

        Returns:
            DPS index or None if not found
        """
        mappings = self._device_mappings.get(device_id, {})
        mapping = mappings.get(capability)
        return mapping.dps if mapping else None

    def get_capability_for_dps(self, device_id: str, dps: int) -> Optional[str]:
        """
        Get capability name for a DPS index

        Args:
            device_id: Device identifier
            dps: DPS index

        Returns:
            Capability name or None if not found
        """
        mappings = self._device_mappings.get(device_id, {})
        for capability, mapping in mappings.items():
            if mapping.dps == dps:
                return capability
        return None

    def get_all_mappings(self, device_id: str) -> Dict[str, DPSMappingInfo]:
        """
        Get all mappings for a device

        Args:
            device_id: Device identifier

        Returns:
            Dictionary of capability to DPSMappingInfo
        """
        return self._device_mappings.get(device_id, {}).copy()

    def get_dps_to_capability_mapping(self, device_id: str) -> Dict[int, str]:
        """
        Get bidirectional mapping from DPS to capability

        Args:
            device_id: Device identifier

        Returns:
            Dictionary mapping DPS indices to capability names
        """
        mappings = self._device_mappings.get(device_id, {})
        return {mapping.dps: capability for capability, mapping in mappings.items()}

    def validate_mapping(self, device_id: str) -> Dict[str, Any]:
        """
        Validate the quality of mappings for a device

        Args:
            device_id: Device identifier

        Returns:
            Dictionary with validation results
        """
        mappings = self._device_mappings.get(device_id, {})
        if not mappings:
            return {
                "valid": False,
                "score": 0.0,
                "issues": ["No mappings found"],
                "recommendations": ["Run discovery first"],
            }

        # Convert to DPSMatch format for validation
        matches = []
        for capability, mapping in mappings.items():
            match = DPSMatch(
                capability=capability,
                dps=mapping.dps,
                confidence=mapping.confidence,
                reason=mapping.reason,
                verified=mapping.verified,
            )
            matches.append(match)

        return self.discovery_engine.validate_dps_mapping(matches)

    def update_mapping(
        self,
        device_id: str,
        capability: str,
        dps: int,
        confidence: DPSConfidence,
        reason: str,
    ):
        """
        Manually update a mapping

        Args:
            device_id: Device identifier
            capability: Capability name
            dps: DPS index
            confidence: Confidence level
            reason: Reason for the mapping
        """
        mapping_info = DPSMappingInfo(
            device_id=device_id,
            capability=capability,
            dps=dps,
            confidence=confidence,
            reason=reason,
            verified=False,
            last_updated=time.time(),
        )

        if device_id not in self._device_mappings:
            self._device_mappings[device_id] = {}

        self._device_mappings[device_id][capability] = mapping_info

        # Update cache
        if self.enable_cache:
            self.cache.set_mapping(mapping_info)

        logger.info(f"Updated mapping for {device_id}: {capability} -> DPS {dps}")

    def remove_mapping(self, device_id: str, capability: str):
        """
        Remove a mapping

        Args:
            device_id: Device identifier
            capability: Capability name
        """
        mappings = self._device_mappings.get(device_id, {})
        if capability in mappings:
            del mappings[capability]
            logger.info(f"Removed mapping for {device_id}: {capability}")

    def clear_device_mappings(self, device_id: str):
        """
        Clear all mappings for a device

        Args:
            device_id: Device identifier
        """
        if device_id in self._device_mappings:
            del self._device_mappings[device_id]

        if self.enable_cache:
            self.cache.clear_device(device_id)

        logger.info(f"Cleared all mappings for device {device_id}")

    def get_mapping_summary(self, device_id: str) -> Dict[str, Any]:
        """
        Get a summary of mappings for a device

        Args:
            device_id: Device identifier

        Returns:
            Dictionary with mapping summary
        """
        mappings = self._device_mappings.get(device_id, {})

        if not mappings:
            return {
                "device_id": device_id,
                "mapping_count": 0,
                "capabilities": [],
                "dps_indices": [],
                "avg_confidence": 0.0,
                "has_critical": False,
            }

        capabilities = list(mappings.keys())
        dps_indices = [mapping.dps for mapping in mappings.values()]
        confidences = [mapping.confidence.value for mapping in mappings.values()]

        # Check for critical capabilities
        critical_caps = ["switch", "switch_led", "switch_1"]
        has_critical = any(cap in critical_caps for cap in capabilities)

        return {
            "device_id": device_id,
            "mapping_count": len(mappings),
            "capabilities": capabilities,
            "dps_indices": sorted(dps_indices),
            "avg_confidence": sum(confidences) / len(confidences),
            "has_critical": has_critical,
            "high_confidence_count": len([c for c in confidences if c >= 0.7]),
            "verified_count": len([m for m in mappings.values() if m.verified]),
        }

    def _infer_value_type(self, value: Any) -> str:
        """
        Infer the type of a value

        Args:
            value: Value to analyze

        Returns:
            String representation of the type
        """
        if isinstance(value, bool):
            return "boolean"
        elif isinstance(value, int):
            return "integer"
        elif isinstance(value, float):
            return "float"
        elif isinstance(value, str):
            return "string"
        elif isinstance(value, dict):
            return "object"
        elif isinstance(value, list):
            return "array"
        else:
            return "unknown"

    def export_mappings(self, device_id: str, file_path: Path):
        """
        Export mappings to a file

        Args:
            device_id: Device identifier
            file_path: Path to export file
        """
        mappings = self._device_mappings.get(device_id, {})

        export_data = {
            "device_id": device_id,
            "export_time": time.time(),
            "mappings": {
                capability: mapping.to_dict()
                for capability, mapping in mappings.items()
            },
        }

        with open(file_path, "w") as f:
            json.dump(export_data, f, indent=2)

        logger.info(f"Exported {len(mappings)} mappings to {file_path}")

    def import_mappings(self, file_path: Path) -> str:
        """
        Import mappings from a file

        Args:
            file_path: Path to import file

        Returns:
            Device ID of imported mappings
        """
        with open(file_path, "r") as f:
            import_data = json.load(f)

        device_id = import_data["device_id"]
        mappings = {}

        for capability, mapping_data in import_data["mappings"].items():
            mappings[capability] = DPSMappingInfo.from_dict(mapping_data)

        self._device_mappings[device_id] = mappings

        # Update cache
        if self.enable_cache:
            for mapping in mappings.values():
                self.cache.set_mapping(mapping)

        logger.info(f"Imported {len(mappings)} mappings for device {device_id}")
        return device_id
