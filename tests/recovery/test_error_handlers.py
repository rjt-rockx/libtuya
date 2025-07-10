"""
Tests for libtuya error handlers and recovery mechanisms.

This module tests all error recovery handlers and the recovery
coordination system.
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock

from libtuya.recovery.error_handlers import (
    RecoveryResult,
    BaseRecoveryHandler,
    AuthenticationRecovery,
    DeviceConnectionRecovery,
    DPSMappingRecovery,
    ProtocolRecovery,
    NetworkRecovery,
    RecoveryCoordinator,
    default_recovery_coordinator
)
from libtuya.recovery.exceptions import (
    TuyaError,
    AuthenticationError,
    QRCodeError,
    TokenError,
    DeviceConnectionError,
    LocalKeyError,
    IPDiscoveryError,
    DPSMappingError,
    UnknownDeviceError,
    CapabilityMismatchError,
    ProtocolError,
    VersionDetectionError,
    CommandError,
    NetworkError,
    ConnectivityError,
    DNSError,
    TimeoutError
)
from libtuya.recovery.retry_strategies import RetryManager


class TestRecoveryResult:
    """Test RecoveryResult class."""
    
    def test_recovery_result_success(self):
        """Test successful recovery result."""
        result = RecoveryResult(
            success=True,
            message="Recovery succeeded",
            recovered_data={"key": "value"},
            fallback_used=False,
            retry_recommended=False
        )
        
        assert result.success is True
        assert result.message == "Recovery succeeded"
        assert result.recovered_data == {"key": "value"}
        assert result.fallback_used is False
        assert result.retry_recommended is False
        assert isinstance(result.timestamp, float)
    
    def test_recovery_result_failure(self):
        """Test failed recovery result."""
        result = RecoveryResult(
            success=False,
            message="Recovery failed",
            retry_recommended=True
        )
        
        assert result.success is False
        assert result.message == "Recovery failed"
        assert result.recovered_data == {}
        assert result.fallback_used is False
        assert result.retry_recommended is True


class TestBaseRecoveryHandler:
    """Test BaseRecoveryHandler functionality."""
    
    def test_base_handler_abstract_methods(self):
        """Test that BaseRecoveryHandler is abstract."""
        with pytest.raises(TypeError):
            BaseRecoveryHandler()
    
    def test_base_handler_initialization(self):
        """Test BaseRecoveryHandler initialization."""
        class TestHandler(BaseRecoveryHandler):
            def can_handle(self, error):
                return True
            
            def recover(self, error, context):
                return RecoveryResult(True, "Test recovery")
        
        handler = TestHandler()
        assert isinstance(handler.retry_manager, RetryManager)
        assert handler.recovery_attempts == 0
        assert handler.last_recovery_time == 0
        assert handler.get_priority() == 50
    
    def test_base_handler_reset_state(self):
        """Test BaseRecoveryHandler state reset."""
        class TestHandler(BaseRecoveryHandler):
            def can_handle(self, error):
                return True
            
            def recover(self, error, context):
                self.recovery_attempts += 1
                self.last_recovery_time = time.time()
                return RecoveryResult(True, "Test recovery")
        
        handler = TestHandler()
        handler.recovery_attempts = 5
        handler.last_recovery_time = time.time()
        
        handler.reset_recovery_state()
        assert handler.recovery_attempts == 0
        assert handler.last_recovery_time == 0


class TestAuthenticationRecovery:
    """Test AuthenticationRecovery handler."""
    
    def test_can_handle_authentication_errors(self):
        """Test that handler can handle authentication errors."""
        handler = AuthenticationRecovery()
        
        assert handler.can_handle(AuthenticationError("test")) is True
        assert handler.can_handle(QRCodeError("test")) is True
        assert handler.can_handle(TokenError("test")) is True
        assert handler.can_handle(NetworkError("test")) is False
    
    def test_priority(self):
        """Test handler priority."""
        handler = AuthenticationRecovery()
        assert handler.get_priority() == 10
    
    def test_recover_qr_code_timeout(self):
        """Test QR code timeout recovery."""
        handler = AuthenticationRecovery()
        error = QRCodeError("QR code timeout")
        
        result = handler.recover(error, {})
        
        assert result.success is False
        assert "timeout" in result.message.lower()
        assert result.retry_recommended is True
    
    def test_recover_qr_code_invalid(self):
        """Test invalid QR code recovery."""
        handler = AuthenticationRecovery()
        error = QRCodeError("Invalid QR code")
        
        result = handler.recover(error, {})
        
        assert result.success is False
        assert "invalid" in result.message.lower()
        assert result.retry_recommended is True
    
    def test_recover_token_expired(self):
        """Test expired token recovery."""
        handler = AuthenticationRecovery()
        error = TokenError("Token expired", expired=True)
        
        result = handler.recover(error, {})
        
        assert result.success is False
        assert "refresh" in result.message.lower() or "re-authenticate" in result.message.lower()
    
    def test_recover_token_invalid(self):
        """Test invalid token recovery."""
        handler = AuthenticationRecovery()
        error = TokenError("Invalid token")
        
        result = handler.recover(error, {})
        
        assert result.success is False
        assert "invalid" in result.message.lower()
        assert result.retry_recommended is False
    
    def test_recover_generic_auth_error(self):
        """Test generic authentication error recovery."""
        handler = AuthenticationRecovery()
        error = AuthenticationError("Generic auth error")
        
        result = handler.recover(error, {})
        
        assert result.success is False
        assert result.retry_recommended is True
    
    def test_recovery_attempts_increment(self):
        """Test that recovery attempts increment."""
        handler = AuthenticationRecovery()
        error = AuthenticationError("test")
        
        assert handler.recovery_attempts == 0
        handler.recover(error, {})
        assert handler.recovery_attempts == 1
        handler.recover(error, {})
        assert handler.recovery_attempts == 2


class TestDeviceConnectionRecovery:
    """Test DeviceConnectionRecovery handler."""
    
    def test_can_handle_device_connection_errors(self):
        """Test that handler can handle device connection errors."""
        handler = DeviceConnectionRecovery()
        
        assert handler.can_handle(DeviceConnectionError("test")) is True
        assert handler.can_handle(LocalKeyError("test")) is True
        assert handler.can_handle(IPDiscoveryError("test")) is True
        assert handler.can_handle(AuthenticationError("test")) is False
    
    def test_priority(self):
        """Test handler priority."""
        handler = DeviceConnectionRecovery()
        assert handler.get_priority() == 20
    
    def test_recover_local_key_validation_failed(self):
        """Test local key validation failure recovery."""
        handler = DeviceConnectionRecovery()
        error = LocalKeyError(
            "Key validation failed",
            device_id="DEV123",
            key_validation_failed=True
        )
        
        result = handler.recover(error, {})
        
        assert result.success is False
        assert result.retry_recommended is True
    
    def test_recover_local_key_encryption_error(self):
        """Test local key encryption error recovery."""
        handler = DeviceConnectionRecovery()
        error = LocalKeyError(
            "Encryption error",
            device_id="DEV123",
            encryption_error=True
        )
        
        result = handler.recover(error, {})
        
        assert result.success is False
        assert "encryption" in result.message.lower()
        assert result.retry_recommended is True
    
    def test_recover_ip_discovery_network_scan_failed(self):
        """Test IP discovery network scan failure recovery."""
        handler = DeviceConnectionRecovery()
        error = IPDiscoveryError(
            "Network scan failed",
            device_id="DEV123",
            network_scan_failed=True
        )
        
        result = handler.recover(error, {})
        
        assert result.success is False
        assert result.retry_recommended is True
    
    def test_recover_ip_discovery_device_offline(self):
        """Test IP discovery device offline recovery."""
        handler = DeviceConnectionRecovery()
        error = IPDiscoveryError(
            "Device offline",
            device_id="DEV123",
            device_offline=True
        )
        
        result = handler.recover(error, {})
        
        assert result.success is False
        assert "offline" in result.message.lower()
        assert result.retry_recommended is True
    
    def test_recover_generic_connection_error(self):
        """Test generic connection error recovery."""
        handler = DeviceConnectionRecovery()
        error = DeviceConnectionError("Connection failed")
        
        result = handler.recover(error, {})
        
        assert result.success is False
        assert result.retry_recommended is True


class TestDPSMappingRecovery:
    """Test DPSMappingRecovery handler."""
    
    def test_can_handle_dps_mapping_errors(self):
        """Test that handler can handle DPS mapping errors."""
        handler = DPSMappingRecovery()
        
        assert handler.can_handle(DPSMappingError("test")) is True
        assert handler.can_handle(UnknownDeviceError("test")) is True
        assert handler.can_handle(CapabilityMismatchError("test")) is True
        assert handler.can_handle(DeviceConnectionError("test")) is False
    
    def test_priority(self):
        """Test handler priority."""
        handler = DPSMappingRecovery()
        assert handler.get_priority() == 30
    
    def test_recover_unknown_device_with_fallback(self):
        """Test unknown device recovery with fallback mapping."""
        handler = DPSMappingRecovery()
        error = UnknownDeviceError(
            "Unknown device",
            available_dps=[1, 2, 3],
            device_info={"model": "TEST123"}
        )
        
        result = handler.recover(error, {})
        
        # Should create fallback mapping
        assert result.success is True
        assert result.fallback_used is True
        assert "mapping" in result.recovered_data
        assert result.recovered_data["mapping"]["switch"] == 1
    
    def test_recover_unknown_device_no_dps(self):
        """Test unknown device recovery without DPS."""
        handler = DPSMappingRecovery()
        error = UnknownDeviceError("Unknown device", available_dps=[])
        
        result = handler.recover(error, {})
        
        assert result.success is False
        assert result.retry_recommended is False
    
    def test_recover_capability_mismatch(self):
        """Test capability mismatch recovery."""
        handler = DPSMappingRecovery()
        error = CapabilityMismatchError(
            "Capability mismatch",
            available_dps=[1, 2, 3, 4],
            expected_dps=[1, 3, 5],
            missing_capabilities=["brightness"],
            unexpected_capabilities=["timer"]
        )
        
        result = handler.recover(error, {})
        
        assert result.success is True
        assert result.fallback_used is True
        assert "mapping" in result.recovered_data
    
    def test_recover_generic_mapping_error(self):
        """Test generic mapping error recovery."""
        handler = DPSMappingRecovery()
        error = DPSMappingError("Mapping failed", available_dps=[1, 2, 3])
        
        result = handler.recover(error, {})
        
        assert result.success is True
        assert result.fallback_used is True
        assert "mapping" in result.recovered_data
    
    def test_create_fallback_mapping_comprehensive(self):
        """Test comprehensive fallback mapping creation."""
        handler = DPSMappingRecovery()
        
        mapping = handler._create_fallback_mapping([1, 2, 3, 4, 5], {})
        
        assert mapping["switch"] == 1
        assert mapping["mode"] == 2
        assert mapping["brightness"] == 3
        assert mapping["temperature"] == 4
        assert mapping["color"] == 5
    
    def test_create_fallback_mapping_partial(self):
        """Test partial fallback mapping creation."""
        handler = DPSMappingRecovery()
        
        mapping = handler._create_fallback_mapping([1, 3], {})
        
        assert mapping["switch"] == 1
        assert mapping["brightness"] == 3
        assert "mode" not in mapping
    
    def test_create_fallback_mapping_empty(self):
        """Test empty fallback mapping creation."""
        handler = DPSMappingRecovery()
        
        mapping = handler._create_fallback_mapping([], {})
        
        assert mapping is None


class TestProtocolRecovery:
    """Test ProtocolRecovery handler."""
    
    def test_can_handle_protocol_errors(self):
        """Test that handler can handle protocol errors."""
        handler = ProtocolRecovery()
        
        assert handler.can_handle(ProtocolError("test")) is True
        assert handler.can_handle(VersionDetectionError("test")) is True
        assert handler.can_handle(CommandError("test")) is True
        assert handler.can_handle(NetworkError("test")) is False
    
    def test_priority(self):
        """Test handler priority."""
        handler = ProtocolRecovery()
        assert handler.get_priority() == 40
    
    def test_recover_version_detection_error(self):
        """Test version detection error recovery."""
        handler = ProtocolRecovery()
        error = VersionDetectionError(
            "Version detection failed",
            attempted_versions=["3.1", "3.2"]
        )
        
        result = handler.recover(error, {})
        
        assert result.success is False
        assert result.retry_recommended is True
        assert "3.3" in result.recovered_data.get("suggested_version", "")
    
    def test_recover_version_detection_all_attempted(self):
        """Test version detection error with all versions attempted."""
        handler = ProtocolRecovery()
        error = VersionDetectionError(
            "Version detection failed",
            attempted_versions=["3.1", "3.2", "3.3", "3.4"]
        )
        
        result = handler.recover(error, {})
        
        assert result.success is False
        assert result.retry_recommended is False
        assert "manual" in result.message.lower()
    
    def test_recover_command_error_dps(self):
        """Test command error recovery with DPS issue."""
        handler = ProtocolRecovery()
        error = CommandError("DPS format error")
        
        result = handler.recover(error, {})
        
        assert result.success is False
        assert "dps" in result.message.lower()
        assert result.retry_recommended is True
    
    def test_recover_command_error_version(self):
        """Test command error recovery with version issue."""
        handler = ProtocolRecovery()
        error = CommandError("Protocol version mismatch")
        
        result = handler.recover(error, {})
        
        assert result.success is False
        assert "version" in result.message.lower()
        assert result.retry_recommended is True
    
    def test_recover_generic_protocol_error(self):
        """Test generic protocol error recovery."""
        handler = ProtocolRecovery()
        error = ProtocolError("Protocol error")
        
        result = handler.recover(error, {})
        
        assert result.success is False
        assert result.retry_recommended is True


class TestNetworkRecovery:
    """Test NetworkRecovery handler."""
    
    def test_can_handle_network_errors(self):
        """Test that handler can handle network errors."""
        handler = NetworkRecovery()
        
        assert handler.can_handle(NetworkError("test")) is True
        assert handler.can_handle(ConnectivityError("test")) is True
        assert handler.can_handle(DNSError("test")) is True
        assert handler.can_handle(TimeoutError("test")) is True
        assert handler.can_handle(AuthenticationError("test")) is False
    
    def test_priority(self):
        """Test handler priority."""
        handler = NetworkRecovery()
        assert handler.get_priority() == 60
    
    def test_recover_connectivity_error(self):
        """Test connectivity error recovery."""
        handler = NetworkRecovery()
        error = ConnectivityError("No internet connection")
        
        result = handler.recover(error, {})
        
        assert result.success is False
        assert "connectivity" in result.message.lower()
        assert result.retry_recommended is True
    
    def test_recover_dns_error(self):
        """Test DNS error recovery."""
        handler = NetworkRecovery()
        error = DNSError("DNS resolution failed")
        
        result = handler.recover(error, {})
        
        assert result.success is False
        assert "dns" in result.message.lower()
        assert result.retry_recommended is True
    
    def test_recover_timeout_error(self):
        """Test timeout error recovery."""
        handler = NetworkRecovery()
        error = TimeoutError("Operation timed out")
        
        result = handler.recover(error, {})
        
        assert result.success is False
        assert "timeout" in result.message.lower()
        assert result.retry_recommended is True
    
    def test_recover_generic_network_error(self):
        """Test generic network error recovery."""
        handler = NetworkRecovery()
        error = NetworkError("Network error")
        
        result = handler.recover(error, {})
        
        assert result.success is False
        assert result.retry_recommended is True


class TestRecoveryCoordinator:
    """Test RecoveryCoordinator functionality."""
    
    def test_coordinator_initialization(self):
        """Test coordinator initialization."""
        coordinator = RecoveryCoordinator()
        
        assert len(coordinator.handlers) == 5  # Default handlers
        assert coordinator.recovery_stats["total_attempts"] == 0
        assert coordinator.recovery_stats["successful_recoveries"] == 0
        assert coordinator.recovery_stats["failed_recoveries"] == 0
        assert coordinator.recovery_stats["fallback_used"] == 0
    
    def test_handlers_sorted_by_priority(self):
        """Test that handlers are sorted by priority."""
        coordinator = RecoveryCoordinator()
        
        priorities = [handler.get_priority() for handler in coordinator.handlers]
        assert priorities == sorted(priorities)
    
    def test_add_custom_handler(self):
        """Test adding custom handler."""
        coordinator = RecoveryCoordinator()
        initial_count = len(coordinator.handlers)
        
        class CustomHandler(BaseRecoveryHandler):
            def can_handle(self, error):
                return isinstance(error, ValueError)
            
            def recover(self, error, context):
                return RecoveryResult(True, "Custom recovery")
            
            def get_priority(self):
                return 1
        
        custom_handler = CustomHandler()
        coordinator.add_handler(custom_handler)
        
        assert len(coordinator.handlers) == initial_count + 1
        # Should be first due to priority 1
        assert coordinator.handlers[0] == custom_handler
    
    def test_recover_with_appropriate_handler(self):
        """Test recovery with appropriate handler."""
        coordinator = RecoveryCoordinator()
        error = AuthenticationError("Auth failed")
        
        result = coordinator.recover(error, {})
        
        assert isinstance(result, RecoveryResult)
        assert coordinator.recovery_stats["total_attempts"] == 1
        if result.success:
            assert coordinator.recovery_stats["successful_recoveries"] == 1
        else:
            assert coordinator.recovery_stats["failed_recoveries"] == 1
    
    def test_recover_with_no_handler(self):
        """Test recovery with no appropriate handler."""
        coordinator = RecoveryCoordinator()
        error = ValueError("Standard error")
        
        result = coordinator.recover(error, {})
        
        assert result.success is False
        assert "no recovery handler" in result.message.lower()
        assert coordinator.recovery_stats["failed_recoveries"] == 1
    
    def test_recover_with_handler_exception(self):
        """Test recovery when handler raises exception."""
        coordinator = RecoveryCoordinator()
        
        class FailingHandler(BaseRecoveryHandler):
            def can_handle(self, error):
                return isinstance(error, ValueError)
            
            def recover(self, error, context):
                raise Exception("Handler failed")
            
            def get_priority(self):
                return 1
        
        coordinator.add_handler(FailingHandler())
        error = ValueError("Test error")
        
        result = coordinator.recover(error, {})
        
        assert result.success is False
        assert "handler failed" in result.message.lower()
        assert coordinator.recovery_stats["failed_recoveries"] == 1
    
    def test_recovery_stats(self):
        """Test recovery statistics."""
        coordinator = RecoveryCoordinator()
        
        # Mock successful recovery
        with patch.object(coordinator.handlers[0], 'recover') as mock_recover:
            mock_recover.return_value = RecoveryResult(
                success=True,
                message="Success",
                fallback_used=True
            )
            
            coordinator.recover(AuthenticationError("test"), {})
        
        stats = coordinator.get_recovery_stats()
        
        assert stats["total_attempts"] == 1
        assert stats["successful_recoveries"] == 1
        assert stats["failed_recoveries"] == 0
        assert stats["fallback_used"] == 1
        assert stats["success_rate"] == 1.0
        assert "handlers" in stats
        assert len(stats["handlers"]) == len(coordinator.handlers)
    
    def test_reset_stats(self):
        """Test resetting statistics."""
        coordinator = RecoveryCoordinator()
        
        # Create some stats
        coordinator.recovery_stats["total_attempts"] = 10
        coordinator.recovery_stats["successful_recoveries"] = 5
        coordinator.handlers[0].recovery_attempts = 3
        
        coordinator.reset_stats()
        
        assert coordinator.recovery_stats["total_attempts"] == 0
        assert coordinator.recovery_stats["successful_recoveries"] == 0
        assert coordinator.handlers[0].recovery_attempts == 0


class TestDefaultRecoveryCoordinator:
    """Test default recovery coordinator."""
    
    def test_default_coordinator_exists(self):
        """Test that default coordinator exists."""
        assert default_recovery_coordinator is not None
        assert isinstance(default_recovery_coordinator, RecoveryCoordinator)
    
    def test_default_coordinator_has_handlers(self):
        """Test that default coordinator has handlers."""
        assert len(default_recovery_coordinator.handlers) > 0
    
    def test_default_coordinator_can_handle_errors(self):
        """Test that default coordinator can handle various errors."""
        auth_error = AuthenticationError("test")
        device_error = DeviceConnectionError("test")
        mapping_error = DPSMappingError("test")
        protocol_error = ProtocolError("test")
        network_error = NetworkError("test")
        
        auth_result = default_recovery_coordinator.recover(auth_error, {})
        device_result = default_recovery_coordinator.recover(device_error, {})
        mapping_result = default_recovery_coordinator.recover(mapping_error, {})
        protocol_result = default_recovery_coordinator.recover(protocol_error, {})
        network_result = default_recovery_coordinator.recover(network_error, {})
        
        assert isinstance(auth_result, RecoveryResult)
        assert isinstance(device_result, RecoveryResult)
        assert isinstance(mapping_result, RecoveryResult)
        assert isinstance(protocol_result, RecoveryResult)
        assert isinstance(network_result, RecoveryResult)


if __name__ == "__main__":
    pytest.main([__file__])