"""
DPS Discovery Engine for libtuya

This module provides intelligent DPS discovery using TinyTuya's detect_available_dps()
method combined with confidence-based matching against expected capabilities.

Key features:
- Uses TinyTuya's detect_available_dps() to probe actual device capabilities
- Implements intelligent matching of expected vs actual DPS
- Handles multiple DPS ranges (1-11, 20-31, 100-111)
- Provides confidence scoring for DPS matches
- Robust error handling for discovery failures
"""

import logging
import time
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum

from .mapping_rules import DPSMappingRules, DPSConfidence


logger = logging.getLogger(__name__)


class DiscoveryError(Exception):
    """Base exception for DPS discovery errors"""

    pass


class DiscoveryTimeout(DiscoveryError):
    """Raised when DPS discovery times out"""

    pass


class DeviceUnreachable(DiscoveryError):
    """Raised when device is unreachable during discovery"""

    pass


@dataclass
class DPSDiscoveryResult:
    """Result of DPS discovery operation"""

    available_dps: Set[int] = field(default_factory=set)
    discovered_values: Dict[int, Any] = field(default_factory=dict)
    discovery_time: float = 0.0
    success: bool = False
    error: Optional[str] = None
    probed_ranges: List[range] = field(default_factory=list)

    def __post_init__(self):
        """Validate discovery result"""
        if self.success and not self.available_dps:
            logger.warning("Discovery marked as successful but no DPS found")


@dataclass
class DPSMatch:
    """Represents a match between capability and DPS"""

    capability: str
    dps: int
    confidence: DPSConfidence
    reason: str
    value: Any = None
    verified: bool = False

    def __str__(self):
        return f"{self.capability} -> DPS {self.dps} ({self.confidence.name}, {self.reason})"


class DPSDiscoveryEngine:
    """
    Engine for discovering and matching DPS indices using TinyTuya
    """

    def __init__(
        self,
        discovery_timeout: float = 30.0,
        probe_delay: float = 0.1,
        max_retries: int = 3,
        enable_extended_probe: bool = True,
    ):
        """
        Initialize DPS discovery engine

        Args:
            discovery_timeout: Maximum time to spend on discovery (seconds)
            probe_delay: Delay between DPS probes (seconds)
            max_retries: Maximum number of retry attempts
            enable_extended_probe: Whether to probe extended DPS ranges
        """
        self.discovery_timeout = discovery_timeout
        self.probe_delay = probe_delay
        self.max_retries = max_retries
        self.enable_extended_probe = enable_extended_probe

        self.mapping_rules = DPSMappingRules()

    def discover_available_dps(self, tinytuya_device) -> DPSDiscoveryResult:
        """
        Discover available DPS indices using TinyTuya's detect_available_dps()

        Args:
            tinytuya_device: TinyTuya device instance

        Returns:
            DPSDiscoveryResult with discovered DPS indices
        """
        start_time = time.time()
        result = DPSDiscoveryResult()

        try:
            logger.info(f"Starting DPS discovery for device {tinytuya_device.id}")

            # Use TinyTuya's built-in discovery
            discovered_dps = self._discover_with_tinytuya(tinytuya_device)

            if discovered_dps:
                result.available_dps = set(discovered_dps.keys())
                result.discovered_values = discovered_dps
                result.success = True
                logger.info(f"TinyTuya discovered DPS: {sorted(result.available_dps)}")
            else:
                # Fallback to manual probing
                logger.warning(
                    "TinyTuya detection failed, falling back to manual probing"
                )
                result = self._manual_dps_probe(tinytuya_device)

        except Exception as e:
            logger.error(f"DPS discovery failed: {e}")
            result.error = str(e)
            result.success = False

        finally:
            result.discovery_time = time.time() - start_time

        return result

    def _discover_with_tinytuya(self, tinytuya_device) -> Optional[Dict[int, Any]]:
        """
        Use TinyTuya's detect_available_dps() method

        Args:
            tinytuya_device: TinyTuya device instance

        Returns:
            Dictionary of DPS indices to values or None if failed
        """
        try:
            # TinyTuya's detect_available_dps() returns a dict like {'1': None, '3': None}
            # We need to convert string keys to integers
            discovered = tinytuya_device.detect_available_dps()

            if discovered:
                # Convert string keys to integers and filter out None values
                result = {}
                for dps_str, value in discovered.items():
                    try:
                        dps_int = int(dps_str)
                        result[dps_int] = value
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid DPS key: {dps_str}")
                        continue

                return result if result else None

        except Exception as e:
            logger.error(f"TinyTuya detect_available_dps() failed: {e}")
            return None

    def _manual_dps_probe(self, tinytuya_device) -> DPSDiscoveryResult:
        """
        Manual DPS probing as fallback when TinyTuya detection fails

        Args:
            tinytuya_device: TinyTuya device instance

        Returns:
            DPSDiscoveryResult with manually discovered DPS
        """
        result = DPSDiscoveryResult()
        start_time = time.time()

        try:
            # Get DPS ranges to probe
            ranges_to_probe = self.mapping_rules.get_common_dps_ranges()

            if not self.enable_extended_probe:
                # Only probe the first range (most common)
                ranges_to_probe = ranges_to_probe[:1]

            for dps_range in ranges_to_probe:
                if time.time() - start_time > self.discovery_timeout:
                    raise DiscoveryTimeout(
                        f"Discovery timeout after {self.discovery_timeout}s"
                    )

                result.probed_ranges.append(dps_range)
                discovered_in_range = self._probe_dps_range(tinytuya_device, dps_range)

                result.available_dps.update(discovered_in_range.keys())
                result.discovered_values.update(discovered_in_range)

                # Small delay between ranges
                time.sleep(self.probe_delay)

            result.success = len(result.available_dps) > 0

        except Exception as e:
            logger.error(f"Manual DPS probe failed: {e}")
            result.error = str(e)
            result.success = False

        return result

    def _probe_dps_range(self, tinytuya_device, dps_range: range) -> Dict[int, Any]:
        """
        Probe a specific range of DPS indices

        Args:
            tinytuya_device: TinyTuya device instance
            dps_range: Range of DPS indices to probe

        Returns:
            Dictionary of discovered DPS to values
        """
        discovered = {}

        try:
            logger.debug(f"Probing DPS range {dps_range.start}-{dps_range.stop-1}")

            # Clear existing DPS requests
            tinytuya_device.dps_to_request = {}

            # DPS 1 must always be sent (TinyTuya requirement)
            tinytuya_device.add_dps_to_request(1)

            # Add the range we want to probe
            tinytuya_device.add_dps_to_request(dps_range)

            # Request status with the probed DPS range
            logger.debug(
                f"Requesting status for DPS: {sorted(tinytuya_device.dps_to_request.keys())}"
            )

            # Try multiple times with increasing delays
            for attempt in range(self.max_retries):
                try:
                    status = tinytuya_device.status()
                    if status and "dps" in status:
                        logger.debug(f"Got status response: {status}")

                        # Extract DPS values from the response
                        for dps_str, value in status["dps"].items():
                            try:
                                dps_int = int(dps_str)
                                if (
                                    dps_int in dps_range or dps_int == 1
                                ):  # Include DPS 1 as well
                                    discovered[dps_int] = value
                                    logger.debug(f"Discovered DPS {dps_int}: {value}")
                            except (ValueError, TypeError):
                                logger.warning(f"Invalid DPS key: {dps_str}")
                                continue

                        # If we got any DPS, break out of retry loop
                        if discovered:
                            break

                    else:
                        logger.debug(f"No DPS data in status response: {status}")

                except Exception as e:
                    logger.debug(f"Status request attempt {attempt + 1} failed: {e}")
                    if attempt < self.max_retries - 1:
                        time.sleep(
                            self.probe_delay * (attempt + 1)
                        )  # Exponential backoff
                    else:
                        raise

        except Exception as e:
            logger.error(f"DPS range probing failed for {dps_range}: {e}")
            # Don't return empty dict, return what we have so far

        logger.debug(
            f"Discovered DPS in range {dps_range.start}-{dps_range.stop-1}: {list(discovered.keys())}"
        )
        return discovered

    def match_capabilities_to_dps(
        self,
        expected_capabilities: List[str],
        available_dps: Set[int],
        device_category: Optional[str] = None,
        discovered_values: Optional[Dict[int, Any]] = None,
    ) -> List[DPSMatch]:
        """
        Match expected capabilities to available DPS indices

        Args:
            expected_capabilities: List of expected capability names
            available_dps: Set of available DPS indices
            device_category: Optional device category for better matching
            discovered_values: Optional dict of DPS values for validation

        Returns:
            List of DPSMatch objects with confidence scores
        """
        matches = []
        used_dps = set()

        logger.info(
            f"Matching capabilities {expected_capabilities} to DPS {sorted(available_dps)}"
        )

        # Sort capabilities by priority (switch first, then brightness, etc.)
        prioritized_capabilities = self._prioritize_capabilities(expected_capabilities)

        for capability in prioritized_capabilities:
            # Get predicted DPS for this capability
            predictions = self.mapping_rules.predict_dps_for_capability(
                capability, device_category
            )

            # Find the best available match
            best_match = None
            for dps, confidence, reason in predictions:
                if dps in available_dps and dps not in used_dps:
                    # Create match
                    match = DPSMatch(
                        capability=capability,
                        dps=dps,
                        confidence=confidence,
                        reason=reason,
                        value=discovered_values.get(dps) if discovered_values else None,
                    )

                    # Try to verify the match if we have values
                    if discovered_values and dps in discovered_values:
                        match.verified = self._verify_dps_match(
                            match, discovered_values[dps]
                        )

                    best_match = match
                    break

            if best_match:
                matches.append(best_match)
                used_dps.add(best_match.dps)
                logger.debug(
                    f"Matched {capability} to DPS {best_match.dps} with confidence {best_match.confidence.name}"
                )
            else:
                logger.warning(f"No available DPS found for capability {capability}")

        # Sort matches by confidence (highest first)
        matches.sort(key=lambda x: x.confidence.value, reverse=True)

        return matches

    def _prioritize_capabilities(self, capabilities: List[str]) -> List[str]:
        """
        Prioritize capabilities for matching (switch first, then brightness, etc.)

        Args:
            capabilities: List of capability names

        Returns:
            Prioritized list of capabilities
        """
        priority_order = [
            "switch",
            "switch_led",
            "switch_1",  # Switches first
            "bright_value",
            "bright_value_v2",
            "bright_value_1",  # Brightness
            "colour_data",
            "colour_data_v2",
            "colour_data_hsv",  # Color
            "temp_value",
            "temp_value_v2",  # Color temperature
            "work_mode",
            "mode",  # Modes
        ]

        # Sort capabilities by priority
        prioritized = []
        remaining = capabilities.copy()

        # Add high-priority capabilities first
        for priority_cap in priority_order:
            if priority_cap in remaining:
                prioritized.append(priority_cap)
                remaining.remove(priority_cap)

        # Add remaining capabilities
        prioritized.extend(remaining)

        return prioritized

    def _verify_dps_match(self, match: DPSMatch, value: Any) -> bool:
        """
        Verify if a DPS match makes sense based on the discovered value

        Args:
            match: DPSMatch to verify
            value: Discovered value for the DPS

        Returns:
            True if the match appears valid
        """
        try:
            # Switch capabilities should have boolean values
            if "switch" in match.capability.lower():
                return isinstance(value, bool) or value in [
                    0,
                    1,
                    "0",
                    "1",
                    "true",
                    "false",
                ]

            # Brightness capabilities should have numeric values
            if "bright" in match.capability.lower():
                return isinstance(value, (int, float)) and 0 <= value <= 1000

            # Color capabilities might have string or dict values
            if (
                "colour" in match.capability.lower()
                or "color" in match.capability.lower()
            ):
                return isinstance(value, (str, dict))

            # Temperature capabilities should have numeric values
            if "temp" in match.capability.lower():
                return isinstance(value, (int, float)) and 0 <= value <= 10000

            # Mode capabilities might have string or numeric values
            if "mode" in match.capability.lower():
                return isinstance(value, (str, int))

            # Default: assume match is valid
            return True

        except Exception as e:
            logger.debug(f"Verification failed for {match}: {e}")
            return False

    def discover_and_match(
        self,
        tinytuya_device,
        expected_capabilities: List[str],
        device_category: Optional[str] = None,
    ) -> Tuple[DPSDiscoveryResult, List[DPSMatch]]:
        """
        Discover available DPS and match to expected capabilities in one operation

        Args:
            tinytuya_device: TinyTuya device instance
            expected_capabilities: List of expected capability names
            device_category: Optional device category for better matching

        Returns:
            Tuple of (DPSDiscoveryResult, List[DPSMatch])
        """
        # Discover available DPS
        discovery_result = self.discover_available_dps(tinytuya_device)

        # Match capabilities to DPS
        matches = []
        if discovery_result.success:
            matches = self.match_capabilities_to_dps(
                expected_capabilities=expected_capabilities,
                available_dps=discovery_result.available_dps,
                device_category=device_category,
                discovered_values=discovery_result.discovered_values,
            )

        return discovery_result, matches

    def get_discovery_stats(self, result: DPSDiscoveryResult) -> Dict[str, Any]:
        """
        Get statistics about a discovery operation

        Args:
            result: DPSDiscoveryResult to analyze

        Returns:
            Dictionary of statistics
        """
        return {
            "success": result.success,
            "dps_count": len(result.available_dps),
            "discovery_time": result.discovery_time,
            "ranges_probed": len(result.probed_ranges),
            "has_values": len(result.discovered_values) > 0,
            "error": result.error,
            "dps_indices": sorted(result.available_dps),
        }

    def validate_dps_mapping(self, matches: List[DPSMatch]) -> Dict[str, Any]:
        """
        Validate the quality of DPS mappings

        Args:
            matches: List of DPSMatch objects

        Returns:
            Dictionary with validation results
        """
        if not matches:
            return {
                "valid": False,
                "score": 0.0,
                "issues": ["No matches found"],
                "recommendations": ["Check device connectivity and category"],
            }

        # Calculate average confidence
        total_confidence = sum(match.confidence.value for match in matches)
        avg_confidence = total_confidence / len(matches)

        # Check for critical capabilities
        critical_caps = ["switch", "switch_led", "switch_1"]
        has_critical = any(match.capability in critical_caps for match in matches)

        # Check for duplicates
        dps_used = [match.dps for match in matches]
        has_duplicates = len(dps_used) != len(set(dps_used))

        # Calculate score
        score = avg_confidence
        if has_critical:
            score += 0.1
        if has_duplicates:
            score -= 0.2

        # Generate issues and recommendations
        issues = []
        recommendations = []

        if not has_critical:
            issues.append("No critical switch capability found")
            recommendations.append("Verify device is a controllable device")

        if has_duplicates:
            issues.append("Duplicate DPS assignments detected")
            recommendations.append("Review device category and capabilities")

        low_confidence_matches = [m for m in matches if m.confidence.value < 0.5]
        if low_confidence_matches:
            issues.append(f"{len(low_confidence_matches)} low confidence matches")
            recommendations.append("Consider device-specific testing")

        return {
            "valid": score > 0.5 and has_critical and not has_duplicates,
            "score": min(1.0, max(0.0, score)),
            "avg_confidence": avg_confidence,
            "has_critical": has_critical,
            "has_duplicates": has_duplicates,
            "issues": issues,
            "recommendations": recommendations,
            "match_count": len(matches),
            "high_confidence_count": len(
                [m for m in matches if m.confidence.value >= 0.7]
            ),
        }
