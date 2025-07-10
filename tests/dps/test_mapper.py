"""
Tests for DPS mapper

This module tests the main DPS mapper functionality including caching,
bidirectional mapping, and integration with discovery engine.
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from libtuya.dps.mapper import (
    DPSMapper, DeviceInfo, DPSMappingInfo, DPSMappingCache
)
from libtuya.dps.mapping_rules import DPSConfidence
from libtuya.dps.discovery import DPSDiscoveryResult, DPSMatch


class MockTinyTuyaDevice:
    """Mock TinyTuya device for testing"""
    
    def __init__(self, device_id="test_device", available_dps=None):
        self.id = device_id
        self.available_dps = available_dps or {"1": True, "3": 255, "5": "ff0000"}
    
    def detect_available_dps(self):
        return self.available_dps.copy()


class TestDeviceInfo:
    """Test DeviceInfo class"""
    
    def test_init_valid(self):
        """Test valid DeviceInfo initialization"""
        device_info = DeviceInfo(
            device_id="test_device",
            category="dj",
            name="Test Light",
            model="TL001",
            local_key="1234567890abcdef",
            ip_address="192.168.1.100",
            protocol_version="3.3"
        )
        
        assert device_info.device_id == "test_device"
        assert device_info.category == "dj"
        assert device_info.name == "Test Light"
        assert device_info.model == "TL001"
        assert device_info.local_key == "1234567890abcdef"
        assert device_info.ip_address == "192.168.1.100"
        assert device_info.protocol_version == "3.3"
    
    def test_init_minimal(self):
        """Test minimal DeviceInfo initialization"""
        device_info = DeviceInfo(device_id="test_device", category="dj")
        
        assert device_info.device_id == "test_device"
        assert device_info.category == "dj"
        assert device_info.name is None
        assert device_info.model is None
        assert device_info.local_key is None
        assert device_info.ip_address is None
        assert device_info.protocol_version is None
    
    def test_init_invalid(self):
        """Test invalid DeviceInfo initialization"""
        with pytest.raises(ValueError, match="Device ID is required"):
            DeviceInfo(device_id="", category="dj")
        
        with pytest.raises(ValueError, match="Device category is required"):
            DeviceInfo(device_id="test_device", category="")


class TestDPSMappingInfo:
    """Test DPSMappingInfo class"""
    
    def test_init(self):
        """Test DPSMappingInfo initialization"""
        mapping = DPSMappingInfo(
            device_id="test_device",
            capability="switch_led",
            dpcode="switch_led",
            dps=1,
            confidence=DPSConfidence.HIGH,
            reason="Standard light switch",
            value_type="boolean",
            value_range=(0, 1),
            scale_factor=1.0,
            verified=True
        )
        
        assert mapping.device_id == "test_device"
        assert mapping.capability == "switch_led"
        assert mapping.dps == 1
        assert mapping.confidence == DPSConfidence.HIGH
        assert mapping.reason == "Standard light switch"
        assert mapping.value_type == "boolean"
        assert mapping.value_range == (0, 1)
        assert mapping.scale_factor == 1.0
        assert mapping.verified == True
        assert mapping.last_updated > 0
    
    def test_to_dict(self):
        """Test converting to dictionary"""
        mapping = DPSMappingInfo(
            device_id="test_device",
            capability="switch_led",
            dpcode="switch_led",
            dps=1,
            confidence=DPSConfidence.HIGH,
            reason="Standard light switch"
        )
        
        data = mapping.to_dict()
        assert data['device_id'] == "test_device"
        assert data['capability'] == "switch_led"
        assert data['dps'] == 1
        assert data['confidence'] == "HIGH"
        assert data['reason'] == "Standard light switch"
    
    def test_from_dict(self):
        """Test creating from dictionary"""
        data = {
            'device_id': "test_device",
            'capability': "switch_led",
            'dpcode': "switch_led",
            'dps': 1,
            'confidence': "HIGH",
            'reason': "Standard light switch",
            'value_type': "boolean",
            'verified': True,
            'last_updated': 1234567890.0
        }
        
        mapping = DPSMappingInfo.from_dict(data)
        assert mapping.device_id == "test_device"
        assert mapping.capability == "switch_led"
        assert mapping.dps == 1
        assert mapping.confidence == DPSConfidence.HIGH
        assert mapping.reason == "Standard light switch"
        assert mapping.value_type == "boolean"
        assert mapping.verified == True
        assert mapping.last_updated == 1234567890.0


class TestDPSMappingCache:
    """Test DPS mapping cache functionality"""
    
    def test_init(self):
        """Test cache initialization"""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir)
            cache = DPSMappingCache(cache_dir)
            
            assert cache.cache_dir == cache_dir
            assert cache.cache_file == cache_dir / 'dps_mappings.json'
            assert isinstance(cache._cache, dict)
    
    def test_get_set_mapping(self):
        """Test getting and setting mappings"""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = DPSMappingCache(Path(temp_dir))
            
            # Test getting non-existent mapping
            mapping = cache.get_mapping("device1", "switch_led")
            assert mapping is None
            
            # Test setting mapping
            mapping_info = DPSMappingInfo(
                device_id="device1",
                capability="switch_led",
                dpcode="switch_led",
                dps=1,
                confidence=DPSConfidence.HIGH,
                reason="test"
            )
            cache.set_mapping(mapping_info)
            
            # Test getting mapping
            retrieved = cache.get_mapping("device1", "switch_led")
            assert retrieved is not None
            assert retrieved.device_id == "device1"
            assert retrieved.capability == "switch_led"
            assert retrieved.dps == 1
    
    def test_get_device_mappings(self):
        """Test getting all mappings for a device"""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = DPSMappingCache(Path(temp_dir))
            
            # Add multiple mappings
            mappings = [
                DPSMappingInfo("device1", "switch_led", dpcode="switch_led", dps=1, confidence=DPSConfidence.HIGH, reason="test1"),
                DPSMappingInfo("device1", "bright_value", dpcode="bright_value", dps=3, confidence=DPSConfidence.HIGH, reason="test2"),
                DPSMappingInfo("device2", "switch", dpcode="switch", dps=1, confidence=DPSConfidence.HIGH, reason="test3")
            ]
            
            for mapping in mappings:
                cache.set_mapping(mapping)
            
            # Get mappings for device1
            device1_mappings = cache.get_device_mappings("device1")
            assert len(device1_mappings) == 2
            assert "switch_led" in device1_mappings
            assert "bright_value" in device1_mappings
            
            # Get mappings for device2
            device2_mappings = cache.get_device_mappings("device2")
            assert len(device2_mappings) == 1
            assert "switch" in device2_mappings
            
            # Get mappings for non-existent device
            device3_mappings = cache.get_device_mappings("device3")
            assert len(device3_mappings) == 0
    
    def test_clear_device(self):
        """Test clearing device mappings"""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = DPSMappingCache(Path(temp_dir))
            
            # Add mappings
            mapping1 = DPSMappingInfo("device1", "switch_led", dpcode="switch_led", dps=1, confidence=DPSConfidence.HIGH, reason="test1")
            mapping2 = DPSMappingInfo("device2", "switch", dpcode="switch", dps=1, confidence=DPSConfidence.HIGH, reason="test2")
            cache.set_mapping(mapping1)
            cache.set_mapping(mapping2)
            
            # Clear device1
            cache.clear_device("device1")
            
            # Check device1 cleared
            device1_mappings = cache.get_device_mappings("device1")
            assert len(device1_mappings) == 0
            
            # Check device2 still exists
            device2_mappings = cache.get_device_mappings("device2")
            assert len(device2_mappings) == 1
    
    def test_clear_all(self):
        """Test clearing all mappings"""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = DPSMappingCache(Path(temp_dir))
            
            # Add mappings
            mapping1 = DPSMappingInfo("device1", "switch_led", dpcode="switch_led", dps=1, confidence=DPSConfidence.HIGH, reason="test1")
            mapping2 = DPSMappingInfo("device2", "switch", dpcode="switch", dps=1, confidence=DPSConfidence.HIGH, reason="test2")
            cache.set_mapping(mapping1)
            cache.set_mapping(mapping2)
            
            # Clear all
            cache.clear_all()
            
            # Check all cleared
            device1_mappings = cache.get_device_mappings("device1")
            device2_mappings = cache.get_device_mappings("device2")
            assert len(device1_mappings) == 0
            assert len(device2_mappings) == 0
    
    def test_persistence(self):
        """Test cache persistence to disk"""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir)
            
            # Create cache and add mapping
            cache1 = DPSMappingCache(cache_dir)
            mapping = DPSMappingInfo("device1", "switch_led", dpcode="switch_led", dps=1, confidence=DPSConfidence.HIGH, reason="test")
            cache1.set_mapping(mapping)
            
            # Create new cache instance (should load from disk)
            cache2 = DPSMappingCache(cache_dir)
            retrieved = cache2.get_mapping("device1", "switch_led")
            
            assert retrieved is not None
            assert retrieved.device_id == "device1"
            assert retrieved.capability == "switch_led"
            assert retrieved.dps == 1


class TestDPSMapper:
    """Test DPS mapper functionality"""
    
    def test_init(self):
        """Test DPSMapper initialization"""
        mapper = DPSMapper()
        assert mapper.enable_cache == True
        assert mapper.cache is not None
        assert mapper.discovery_engine is not None
        assert mapper.mapping_rules is not None
        assert isinstance(mapper._device_mappings, dict)
        
        # Test without cache
        mapper = DPSMapper(enable_cache=False)
        assert mapper.enable_cache == False
        assert mapper.cache is None
    
    def test_discover_dps_mapping_success(self):
        """Test successful DPS mapping discovery"""
        mock_device = MockTinyTuyaDevice(
            available_dps={"1": True, "3": 255, "5": "ff0000"}
        )
        
        device_info = DeviceInfo(device_id="test_device", category="dj")
        expected_capabilities = ["switch_led", "bright_value", "colour_data"]
        
        with tempfile.TemporaryDirectory() as temp_dir:
            mapper = DPSMapper(cache_dir=Path(temp_dir))
            
            mappings = mapper.discover_dps_mapping(
                device_info=device_info,
                expected_capabilities=expected_capabilities,
                tinytuya_device=mock_device
            )
            
            assert len(mappings) == 3
            assert "switch_led" in mappings
            assert "bright_value" in mappings
            assert "colour_data" in mappings
            
            # Check mapping details
            switch_mapping = mappings["switch_led"]
            assert switch_mapping.dps == 1
            assert switch_mapping.confidence == DPSConfidence.HIGH
            assert switch_mapping.verified == True
    
    def test_discover_dps_mapping_with_cache(self):
        """Test DPS mapping discovery with cache"""
        mock_device = MockTinyTuyaDevice()
        device_info = DeviceInfo(device_id="test_device", category="dj")
        expected_capabilities = ["switch_led", "bright_value"]
        
        with tempfile.TemporaryDirectory() as temp_dir:
            mapper = DPSMapper(cache_dir=Path(temp_dir))
            
            # First discovery (should cache)
            mappings1 = mapper.discover_dps_mapping(
                device_info=device_info,
                expected_capabilities=expected_capabilities,
                tinytuya_device=mock_device
            )
            
            # Second discovery (should use cache)
            mappings2 = mapper.discover_dps_mapping(
                device_info=device_info,
                expected_capabilities=expected_capabilities,
                tinytuya_device=mock_device
            )
            
            assert len(mappings1) == len(mappings2)
            assert mappings1.keys() == mappings2.keys()
    
    def test_discover_dps_mapping_force_discovery(self):
        """Test forcing discovery to bypass cache"""
        mock_device = MockTinyTuyaDevice()
        device_info = DeviceInfo(device_id="test_device", category="dj")
        expected_capabilities = ["switch_led"]
        
        with tempfile.TemporaryDirectory() as temp_dir:
            mapper = DPSMapper(cache_dir=Path(temp_dir))
            
            # First discovery
            mappings1 = mapper.discover_dps_mapping(
                device_info=device_info,
                expected_capabilities=expected_capabilities,
                tinytuya_device=mock_device
            )
            
            # Force discovery (should bypass cache)
            mappings2 = mapper.discover_dps_mapping(
                device_info=device_info,
                expected_capabilities=expected_capabilities,
                tinytuya_device=mock_device,
                force_discovery=True
            )
            
            assert len(mappings1) == len(mappings2)
            assert mappings1.keys() == mappings2.keys()
    
    def test_get_dps_for_capability(self):
        """Test getting DPS for capability"""
        mapper = DPSMapper(enable_cache=False)
        
        # Add test mapping
        mapping = DPSMappingInfo(
            device_id="test_device",
            capability="switch_led",
            dpcode="switch_led",
            dps=1,
            confidence=DPSConfidence.HIGH,
            reason="test"
        )
        mapper._device_mappings["test_device"] = {"switch_led": mapping}
        
        # Test getting existing capability
        dps = mapper.get_dps_for_capability("test_device", "switch_led")
        assert dps == 1
        
        # Test getting non-existent capability
        dps = mapper.get_dps_for_capability("test_device", "nonexistent")
        assert dps is None
        
        # Test getting from non-existent device
        dps = mapper.get_dps_for_capability("nonexistent_device", "switch_led")
        assert dps is None
    
    def test_get_capability_for_dps(self):
        """Test getting capability for DPS"""
        mapper = DPSMapper(enable_cache=False)
        
        # Add test mappings
        mapping1 = DPSMappingInfo(
            device_id="test_device",
            capability="switch_led",
            dpcode="switch_led",
            dps=1,
            confidence=DPSConfidence.HIGH,
            reason="test"
        )
        mapping2 = DPSMappingInfo(
            device_id="test_device",
            capability="bright_value",
            dpcode="bright_value",
            dps=3,
            confidence=DPSConfidence.HIGH,
            reason="test"
        )
        mapper._device_mappings["test_device"] = {
            "switch_led": mapping1,
            "bright_value": mapping2
        }
        
        # Test getting existing DPS
        capability = mapper.get_capability_for_dps("test_device", 1)
        assert capability == "switch_led"
        
        capability = mapper.get_capability_for_dps("test_device", 3)
        assert capability == "bright_value"
        
        # Test getting non-existent DPS
        capability = mapper.get_capability_for_dps("test_device", 999)
        assert capability is None
    
    def test_get_all_mappings(self):
        """Test getting all mappings for device"""
        mapper = DPSMapper(enable_cache=False)
        
        # Add test mappings
        mapping1 = DPSMappingInfo("test_device", "switch_led", dpcode="switch_led", dps=1, confidence=DPSConfidence.HIGH, reason="test1")
        mapping2 = DPSMappingInfo("test_device", "bright_value", dpcode="bright_value", dps=3, confidence=DPSConfidence.HIGH, reason="test2")
        mapper._device_mappings["test_device"] = {
            "switch_led": mapping1,
            "bright_value": mapping2
        }
        
        # Get all mappings
        all_mappings = mapper.get_all_mappings("test_device")
        assert len(all_mappings) == 2
        assert "switch_led" in all_mappings
        assert "bright_value" in all_mappings
        
        # Test non-existent device
        all_mappings = mapper.get_all_mappings("nonexistent_device")
        assert len(all_mappings) == 0
    
    def test_get_dps_to_capability_mapping(self):
        """Test getting bidirectional DPS to capability mapping"""
        mapper = DPSMapper(enable_cache=False)
        
        # Add test mappings
        mapping1 = DPSMappingInfo("test_device", "switch_led", dpcode="switch_led", dps=1, confidence=DPSConfidence.HIGH, reason="test1")
        mapping2 = DPSMappingInfo("test_device", "bright_value", dpcode="bright_value", dps=3, confidence=DPSConfidence.HIGH, reason="test2")
        mapper._device_mappings["test_device"] = {
            "switch_led": mapping1,
            "bright_value": mapping2
        }
        
        # Get DPS to capability mapping
        dps_mapping = mapper.get_dps_to_capability_mapping("test_device")
        assert dps_mapping == {1: "switch_led", 3: "bright_value"}
    
    def test_update_mapping(self):
        """Test updating mappings"""
        mapper = DPSMapper(enable_cache=False)
        
        # Update mapping
        mapper.update_mapping(
            device_id="test_device",
            capability="switch_led",
            dps=1,
            confidence=DPSConfidence.HIGH,
            reason="Manual update"
        )
        
        # Check mapping was added
        dps = mapper.get_dps_for_capability("test_device", "switch_led")
        assert dps == 1
        
        # Check mapping details
        mappings = mapper.get_all_mappings("test_device")
        mapping = mappings["switch_led"]
        assert mapping.dps == 1
        assert mapping.confidence == DPSConfidence.HIGH
        assert mapping.reason == "Manual update"
        assert mapping.verified == False
    
    def test_remove_mapping(self):
        """Test removing mappings"""
        mapper = DPSMapper(enable_cache=False)
        
        # Add mapping
        mapper.update_mapping("test_device", "switch_led", 1, DPSConfidence.HIGH, "test")
        
        # Verify mapping exists
        dps = mapper.get_dps_for_capability("test_device", "switch_led")
        assert dps == 1
        
        # Remove mapping
        mapper.remove_mapping("test_device", "switch_led")
        
        # Verify mapping is gone
        dps = mapper.get_dps_for_capability("test_device", "switch_led")
        assert dps is None
    
    def test_clear_device_mappings(self):
        """Test clearing all mappings for device"""
        mapper = DPSMapper(enable_cache=False)
        
        # Add mappings
        mapper.update_mapping("test_device", "switch_led", 1, DPSConfidence.HIGH, "test1")
        mapper.update_mapping("test_device", "bright_value", 3, DPSConfidence.HIGH, "test2")
        
        # Verify mappings exist
        mappings = mapper.get_all_mappings("test_device")
        assert len(mappings) == 2
        
        # Clear mappings
        mapper.clear_device_mappings("test_device")
        
        # Verify mappings are gone
        mappings = mapper.get_all_mappings("test_device")
        assert len(mappings) == 0
    
    def test_get_mapping_summary(self):
        """Test getting mapping summary"""
        mapper = DPSMapper(enable_cache=False)
        
        # Test empty device
        summary = mapper.get_mapping_summary("test_device")
        assert summary['device_id'] == "test_device"
        assert summary['mapping_count'] == 0
        assert summary['capabilities'] == []
        assert summary['dps_indices'] == []
        assert summary['avg_confidence'] == 0.0
        assert summary['has_critical'] == False
        
        # Add mappings
        mapper.update_mapping("test_device", "switch_led", dpcode="switch_led", dps=1, confidence=DPSConfidence.HIGH, reason="test1")
        mapper.update_mapping("test_device", "bright_value", dpcode="bright_value", dps=3, confidence=DPSConfidence.MEDIUM, reason="test2")
        
        # Test with mappings
        summary = mapper.get_mapping_summary("test_device")
        assert summary['device_id'] == "test_device"
        assert summary['mapping_count'] == 2
        assert "switch_led" in summary['capabilities']
        assert "bright_value" in summary['capabilities']
        assert summary['dps_indices'] == [1, 3]
        assert summary['avg_confidence'] == (0.9 + 0.6) / 2
        assert summary['has_critical'] == True  # switch_led is critical
        assert summary['high_confidence_count'] == 1
        assert summary['verified_count'] == 0
    
    def test_infer_value_type(self):
        """Test value type inference"""
        mapper = DPSMapper(enable_cache=False)
        
        assert mapper._infer_value_type(True) == 'boolean'
        assert mapper._infer_value_type(123) == 'integer'
        assert mapper._infer_value_type(123.45) == 'float'
        assert mapper._infer_value_type("test") == 'string'
        assert mapper._infer_value_type({"key": "value"}) == 'object'
        assert mapper._infer_value_type([1, 2, 3]) == 'array'
        assert mapper._infer_value_type(None) == 'unknown'
    
    def test_export_import_mappings(self):
        """Test exporting and importing mappings"""
        with tempfile.TemporaryDirectory() as temp_dir:
            mapper = DPSMapper(enable_cache=False)
            export_file = Path(temp_dir) / "test_mappings.json"
            
            # Add mappings
            mapper.update_mapping("test_device", "switch_led", dpcode="switch_led", dps=1, confidence=DPSConfidence.HIGH, reason="test1")
            mapper.update_mapping("test_device", "bright_value", dpcode="bright_value", dps=3, confidence=DPSConfidence.MEDIUM, reason="test2")
            
            # Export mappings
            mapper.export_mappings("test_device", export_file)
            assert export_file.exists()
            
            # Clear mappings
            mapper.clear_device_mappings("test_device")
            assert len(mapper.get_all_mappings("test_device")) == 0
            
            # Import mappings
            device_id = mapper.import_mappings(export_file)
            assert device_id == "test_device"
            
            # Verify mappings restored
            mappings = mapper.get_all_mappings("test_device")
            assert len(mappings) == 2
            assert "switch_led" in mappings
            assert "bright_value" in mappings
    
    def test_validate_mapping(self):
        """Test mapping validation"""
        mapper = DPSMapper(enable_cache=False)
        
        # Test empty mappings
        validation = mapper.validate_mapping("test_device")
        assert validation['valid'] == False
        assert validation['score'] == 0.0
        assert 'No mappings found' in validation['issues']
        
        # Add good mappings
        mapper.update_mapping("test_device", "switch_led", dpcode="switch_led", dps=1, confidence=DPSConfidence.HIGH, reason="test1")
        mapper.update_mapping("test_device", "bright_value", dpcode="bright_value", dps=3, confidence=DPSConfidence.HIGH, reason="test2")
        
        # Test validation
        validation = mapper.validate_mapping("test_device")
        assert validation['valid'] == True
        assert validation['score'] > 0.8
        assert validation['has_critical'] == True
        assert validation['has_duplicates'] == False