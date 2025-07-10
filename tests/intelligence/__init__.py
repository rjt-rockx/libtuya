"""
Test suite for the libtuya intelligence database.

This package contains comprehensive tests for all intelligence database components
including DPCode management, device mappings, scaling logic, and quirks handling.
"""

# Test imports for convenience
from .test_dpcodes import TestDPCodeManager, TestDPCodeEnum
from .test_device_mappings import TestDeviceMappingManager, TestDeviceCategory
from .test_scaling import (
    TestIntegerTypeData, TestEnumTypeData, TestColorTypeData, 
    TestRemapValue, TestValueScalingManager
)
from .test_quirks import (
    TestDeviceQuirksManager, TestDeviceQuirk, TestEntityMapping, TestDPCodeFallback
)
from .test_intelligence import TestDeviceIntelligence, TestDeviceAnalysis, TestCapabilityInfo

__all__ = [
    "TestDPCodeManager",
    "TestDPCodeEnum",
    "TestDeviceMappingManager", 
    "TestDeviceCategory",
    "TestIntegerTypeData",
    "TestEnumTypeData",
    "TestColorTypeData",
    "TestRemapValue",
    "TestValueScalingManager",
    "TestDeviceQuirksManager",
    "TestDeviceQuirk",
    "TestEntityMapping",
    "TestDPCodeFallback",
    "TestDeviceIntelligence",
    "TestDeviceAnalysis",
    "TestCapabilityInfo"
]