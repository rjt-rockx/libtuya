"""
Tests for DPS discovery engine

This module tests the DPS discovery functionality with mock TinyTuya devices.
"""

import pytest
from unittest.mock import Mock, patch
import time
from libtuya.dps.discovery import (
    DPSDiscoveryEngine, DPSDiscoveryResult, DPSMatch, 
    DiscoveryError, DiscoveryTimeout, DeviceUnreachable
)
from libtuya.dps.mapping_rules import DPSConfidence


class MockTinyTuyaDevice:
    """Mock TinyTuya device for testing"""
    
    def __init__(self, device_id="test_device", available_dps=None, status_data=None):
        self.id = device_id
        self.available_dps = available_dps or {"1": None, "3": None, "5": None}
        self.status_data = status_data or {"dps": {"1": True, "3": 255, "5": "ff0000"}}
        self.dps_to_request = set()
        self.detect_calls = 0
        self.status_calls = 0
    
    def detect_available_dps(self):
        """Mock detect_available_dps method"""
        self.detect_calls += 1
        if self.available_dps is None:
            raise Exception("Device unreachable")
        return self.available_dps.copy()
    
    def status(self):
        """Mock status method"""
        self.status_calls += 1
        if self.status_data is None:
            raise Exception("Status failed")
        return self.status_data.copy()
    
    def add_dps_to_request(self, dps):
        """Mock add_dps_to_request method"""
        if isinstance(dps, (list, tuple)):
            self.dps_to_request.update(dps)
        else:
            self.dps_to_request.add(dps)


class TestDPSDiscoveryEngine:
    """Test DPS discovery engine functionality"""
    
    def test_init(self):
        """Test discovery engine initialization"""
        engine = DPSDiscoveryEngine()
        assert engine.discovery_timeout == 30.0
        assert engine.probe_delay == 0.1
        assert engine.max_retries == 3
        assert engine.enable_extended_probe == True
        
        # Test custom initialization
        engine = DPSDiscoveryEngine(
            discovery_timeout=60.0,
            probe_delay=0.2,
            max_retries=5,
            enable_extended_probe=False
        )
        assert engine.discovery_timeout == 60.0
        assert engine.probe_delay == 0.2
        assert engine.max_retries == 5
        assert engine.enable_extended_probe == False
    
    def test_discover_available_dps_success(self):
        """Test successful DPS discovery"""
        mock_device = MockTinyTuyaDevice(
            available_dps={"1": None, "3": None, "5": None},
            status_data={"dps": {"1": True, "3": 255, "5": "ff0000"}}
        )
        
        engine = DPSDiscoveryEngine()
        result = engine.discover_available_dps(mock_device)
        
        assert result.success == True
        assert result.available_dps == {1, 3, 5}
        assert result.discovered_values == {1: None, 3: None, 5: None}
        assert result.error is None
        assert result.discovery_time > 0
        assert mock_device.detect_calls == 1
    
    def test_discover_available_dps_failure(self):
        """Test DPS discovery failure"""
        mock_device = MockTinyTuyaDevice(available_dps=None)
        
        engine = DPSDiscoveryEngine()
        result = engine.discover_available_dps(mock_device)
        
        assert result.success == False
        assert result.error is not None
        assert result.available_dps == set()
        assert result.discovered_values == {}
    
    def test_discover_with_tinytuya_success(self):
        """Test TinyTuya discovery success"""
        mock_device = MockTinyTuyaDevice(
            available_dps={"1": True, "3": 255, "5": "ff0000"}
        )
        
        engine = DPSDiscoveryEngine()
        result = engine._discover_with_tinytuya(mock_device)
        
        assert result is not None
        assert result == {1: True, 3: 255, 5: "ff0000"}
        assert mock_device.detect_calls == 1
    
    def test_discover_with_tinytuya_failure(self):
        """Test TinyTuya discovery failure"""
        mock_device = MockTinyTuyaDevice(available_dps=None)
        
        engine = DPSDiscoveryEngine()
        result = engine._discover_with_tinytuya(mock_device)
        
        assert result is None
        assert mock_device.detect_calls == 1
    
    def test_discover_with_tinytuya_string_keys(self):
        """Test TinyTuya discovery with string keys"""
        mock_device = MockTinyTuyaDevice(
            available_dps={"1": True, "3": 255, "invalid": "test"}
        )
        
        engine = DPSDiscoveryEngine()
        result = engine._discover_with_tinytuya(mock_device)
        
        assert result is not None
        assert result == {1: True, 3: 255}  # Should filter out invalid key
    
    def test_manual_dps_probe(self):
        """Test manual DPS probing"""
        mock_device = MockTinyTuyaDevice(
            available_dps=None,  # Force manual probe
            status_data={"dps": {"1": True, "3": 255}}
        )
        
        engine = DPSDiscoveryEngine(enable_extended_probe=False)
        result = engine._manual_dps_probe(mock_device)
        
        assert result.success == True
        assert len(result.probed_ranges) == 1
        assert result.probed_ranges[0] == range(1, 12)
    
    def test_probe_dps_range(self):
        """Test probing specific DPS range"""
        mock_device = MockTinyTuyaDevice(
            status_data={"dps": {"1": True, "3": 255, "5": "ff0000"}}
        )
        
        engine = DPSDiscoveryEngine(probe_delay=0.01)  # Faster for testing
        result = engine._probe_dps_range(mock_device, range(1, 6))
        
        assert result == {1: True, 3: 255, 5: "ff0000"}
        assert len(mock_device.dps_to_request) == 5  # Should have added 5 DPS
    
    def test_match_capabilities_to_dps(self):
        """Test matching capabilities to DPS"""
        engine = DPSDiscoveryEngine()
        
        expected_capabilities = ["switch_led", "bright_value", "colour_data"]
        available_dps = {1, 3, 5}
        discovered_values = {1: True, 3: 255, 5: "ff0000"}
        
        matches = engine.match_capabilities_to_dps(
            expected_capabilities=expected_capabilities,
            available_dps=available_dps,
            device_category="dj",
            discovered_values=discovered_values
        )
        
        assert len(matches) == 3
        
        # Check first match (switch_led -> DPS 1)
        switch_match = next(m for m in matches if m.capability == "switch_led")
        assert switch_match.dps == 1
        assert switch_match.confidence == DPSConfidence.HIGH
        assert switch_match.value == True
        
        # Check second match (bright_value -> DPS 3)
        bright_match = next(m for m in matches if m.capability == "bright_value")
        assert bright_match.dps == 3
        assert bright_match.confidence == DPSConfidence.HIGH
        assert bright_match.value == 255
        
        # Check third match (colour_data -> DPS 5)
        color_match = next(m for m in matches if m.capability == "colour_data")
        assert color_match.dps == 5
        assert color_match.confidence == DPSConfidence.HIGH
        assert color_match.value == "ff0000"
    
    def test_match_capabilities_prioritization(self):
        """Test capability prioritization in matching"""
        engine = DPSDiscoveryEngine()
        
        # Test that switch capabilities are prioritized
        capabilities = ["colour_data", "switch_led", "bright_value"]
        prioritized = engine._prioritize_capabilities(capabilities)
        
        assert prioritized.index("switch_led") < prioritized.index("bright_value")
        assert prioritized.index("bright_value") < prioritized.index("colour_data")
    
    def test_match_capabilities_no_available_dps(self):
        """Test matching when no DPS available"""
        engine = DPSDiscoveryEngine()
        
        matches = engine.match_capabilities_to_dps(
            expected_capabilities=["switch_led", "bright_value"],
            available_dps=set(),
            device_category="dj"
        )
        
        assert len(matches) == 0
    
    def test_match_capabilities_partial_match(self):
        """Test matching with partial DPS availability"""
        engine = DPSDiscoveryEngine()
        
        matches = engine.match_capabilities_to_dps(
            expected_capabilities=["switch_led", "bright_value", "colour_data"],
            available_dps={1, 3},  # Missing DPS 5
            device_category="dj"
        )
        
        assert len(matches) == 2
        capabilities = [m.capability for m in matches]
        assert "switch_led" in capabilities
        assert "bright_value" in capabilities
        assert "colour_data" not in capabilities
    
    def test_verify_dps_match(self):
        """Test DPS match verification"""
        engine = DPSDiscoveryEngine()
        
        # Test switch verification
        switch_match = DPSMatch(
            capability="switch_led",
            dps=1,
            confidence=DPSConfidence.HIGH,
            reason="test"
        )
        assert engine._verify_dps_match(switch_match, True) == True
        assert engine._verify_dps_match(switch_match, 1) == True
        assert engine._verify_dps_match(switch_match, "true") == True
        assert engine._verify_dps_match(switch_match, "invalid") == False
        
        # Test brightness verification
        bright_match = DPSMatch(
            capability="bright_value",
            dps=3,
            confidence=DPSConfidence.HIGH,
            reason="test"
        )
        assert engine._verify_dps_match(bright_match, 255) == True
        assert engine._verify_dps_match(bright_match, 0) == True
        assert engine._verify_dps_match(bright_match, 1000) == True
        assert engine._verify_dps_match(bright_match, -1) == False
        assert engine._verify_dps_match(bright_match, 1001) == False
        
        # Test color verification
        color_match = DPSMatch(
            capability="colour_data",
            dps=5,
            confidence=DPSConfidence.HIGH,
            reason="test"
        )
        assert engine._verify_dps_match(color_match, "ff0000") == True
        assert engine._verify_dps_match(color_match, {"h": 0, "s": 255, "v": 255}) == True
        assert engine._verify_dps_match(color_match, 123) == False
    
    def test_discover_and_match_success(self):
        """Test combined discovery and matching"""
        mock_device = MockTinyTuyaDevice(
            available_dps={"1": True, "3": 255, "5": "ff0000"}
        )
        
        engine = DPSDiscoveryEngine()
        discovery_result, matches = engine.discover_and_match(
            tinytuya_device=mock_device,
            expected_capabilities=["switch_led", "bright_value", "colour_data"],
            device_category="dj"
        )
        
        assert discovery_result.success == True
        assert len(matches) == 3
        assert all(m.confidence == DPSConfidence.HIGH for m in matches)
    
    def test_discover_and_match_discovery_failure(self):
        """Test combined discovery and matching with discovery failure"""
        mock_device = MockTinyTuyaDevice(available_dps=None)
        
        engine = DPSDiscoveryEngine()
        discovery_result, matches = engine.discover_and_match(
            tinytuya_device=mock_device,
            expected_capabilities=["switch_led", "bright_value"],
            device_category="dj"
        )
        
        assert discovery_result.success == False
        assert len(matches) == 0
    
    def test_get_discovery_stats(self):
        """Test discovery statistics"""
        engine = DPSDiscoveryEngine()
        
        # Test successful result
        result = DPSDiscoveryResult(
            available_dps={1, 3, 5},
            discovered_values={1: True, 3: 255, 5: "ff0000"},
            discovery_time=1.5,
            success=True,
            probed_ranges=[range(1, 12)]
        )
        
        stats = engine.get_discovery_stats(result)
        assert stats['success'] == True
        assert stats['dps_count'] == 3
        assert stats['discovery_time'] == 1.5
        assert stats['ranges_probed'] == 1
        assert stats['has_values'] == True
        assert stats['error'] is None
        assert stats['dps_indices'] == [1, 3, 5]
        
        # Test failed result
        result = DPSDiscoveryResult(
            success=False,
            error="Device unreachable"
        )
        
        stats = engine.get_discovery_stats(result)
        assert stats['success'] == False
        assert stats['dps_count'] == 0
        assert stats['error'] == "Device unreachable"
    
    def test_validate_dps_mapping_success(self):
        """Test DPS mapping validation with good mappings"""
        engine = DPSDiscoveryEngine()
        
        matches = [
            DPSMatch(
                capability="switch_led",
                dps=1,
                confidence=DPSConfidence.HIGH,
                reason="Standard light switch",
                verified=True
            ),
            DPSMatch(
                capability="bright_value",
                dps=3,
                confidence=DPSConfidence.HIGH,
                reason="Brightness control",
                verified=True
            )
        ]
        
        validation = engine.validate_dps_mapping(matches)
        assert validation['valid'] == True
        assert validation['score'] > 0.8
        assert validation['has_critical'] == True
        assert validation['has_duplicates'] == False
        assert len(validation['issues']) == 0
    
    def test_validate_dps_mapping_failure(self):
        """Test DPS mapping validation with poor mappings"""
        engine = DPSDiscoveryEngine()
        
        # No matches
        validation = engine.validate_dps_mapping([])
        assert validation['valid'] == False
        assert validation['score'] == 0.0
        assert 'No matches found' in validation['issues']
        
        # No critical capability
        matches = [
            DPSMatch(
                capability="colour_data",
                dps=5,
                confidence=DPSConfidence.LOW,
                reason="Low confidence match"
            )
        ]
        
        validation = engine.validate_dps_mapping(matches)
        assert validation['valid'] == False
        assert validation['has_critical'] == False
        assert 'No critical switch capability found' in validation['issues']
    
    def test_validate_dps_mapping_duplicates(self):
        """Test DPS mapping validation with duplicates"""
        engine = DPSDiscoveryEngine()
        
        matches = [
            DPSMatch(
                capability="switch_led",
                dps=1,
                confidence=DPSConfidence.HIGH,
                reason="Switch"
            ),
            DPSMatch(
                capability="switch_1",
                dps=1,  # Same DPS
                confidence=DPSConfidence.HIGH,
                reason="Switch alt"
            )
        ]
        
        validation = engine.validate_dps_mapping(matches)
        assert validation['valid'] == False
        assert validation['has_duplicates'] == True
        assert 'Duplicate DPS assignments detected' in validation['issues']
    
    def test_timeout_handling(self):
        """Test timeout handling in discovery"""
        engine = DPSDiscoveryEngine(discovery_timeout=0.1)  # Very short timeout
        
        # Mock device that takes too long
        mock_device = MockTinyTuyaDevice(available_dps=None)
        
        with patch('time.sleep') as mock_sleep:
            mock_sleep.side_effect = lambda x: time.sleep(0.2)  # Longer than timeout
            
            result = engine.discover_available_dps(mock_device)
            assert result.success == False
            assert result.error is not None
    
    def test_extended_probe_setting(self):
        """Test extended probe setting"""
        mock_device = MockTinyTuyaDevice(
            available_dps=None,
            status_data={"dps": {"1": True}}
        )
        
        # Test with extended probe disabled
        engine = DPSDiscoveryEngine(enable_extended_probe=False)
        result = engine._manual_dps_probe(mock_device)
        assert len(result.probed_ranges) == 1
        
        # Test with extended probe enabled
        engine = DPSDiscoveryEngine(enable_extended_probe=True)
        result = engine._manual_dps_probe(mock_device)
        assert len(result.probed_ranges) == 3  # Should probe all ranges