"""
Tests for the main RecoveryManager and integration points.

This module tests the RecoveryManager class and its integration
with all recovery components.
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, patch, AsyncMock, MagicMock

from libtuya.recovery import (
    RecoveryManager,
    RecoveryContext,
    create_recovery_manager,
    with_recovery,
    TuyaError,
    AuthenticationError,
    DeviceConnectionError,
    DPSMappingError,
    ProtocolError,
    NetworkError,
    RetryConfig,
    CircuitBreakerConfig,
    RecoveryResult,
    HealthStatus,
    DiagnosticResult,
    BaseRecoveryHandler,
    BaseDiagnostic
)


class TestRecoveryManager:
    """Test RecoveryManager class."""
    
    def test_recovery_manager_initialization(self):
        """Test RecoveryManager initialization."""
        manager = RecoveryManager()
        
        assert manager.retry_manager is not None
        assert manager.recovery_coordinator is not None
        assert manager.health_monitor is not None
        assert manager.enable_logging is True
        assert manager.recovery_stats["total_errors"] == 0
        assert manager.recovery_stats["successful_recoveries"] == 0
        assert manager.recovery_stats["failed_recoveries"] == 0
        assert manager.recovery_stats["fallback_used"] == 0
    
    def test_recovery_manager_custom_components(self):
        """Test RecoveryManager with custom components."""
        retry_manager = Mock()
        recovery_coordinator = Mock()
        health_monitor = Mock()
        
        manager = RecoveryManager(
            retry_manager=retry_manager,
            recovery_coordinator=recovery_coordinator,
            health_monitor=health_monitor,
            enable_logging=False
        )
        
        assert manager.retry_manager == retry_manager
        assert manager.recovery_coordinator == recovery_coordinator
        assert manager.health_monitor == health_monitor
        assert manager.enable_logging is False
    
    def test_recover_from_error_success(self):
        """Test successful error recovery."""
        manager = RecoveryManager()
        
        with patch.object(manager.recovery_coordinator, 'recover') as mock_recover:
            mock_recover.return_value = RecoveryResult(
                success=True,
                message="Recovery successful",
                fallback_used=True
            )
            
            error = AuthenticationError("Test error")
            result = manager.recover_from_error(error)
            
            assert result.success is True
            assert result.message == "Recovery successful"
            assert result.fallback_used is True
            assert manager.recovery_stats["total_errors"] == 1
            assert manager.recovery_stats["successful_recoveries"] == 1
            assert manager.recovery_stats["fallback_used"] == 1
    
    def test_recover_from_error_failure(self):
        """Test failed error recovery."""
        manager = RecoveryManager()
        
        with patch.object(manager.recovery_coordinator, 'recover') as mock_recover:
            mock_recover.return_value = RecoveryResult(
                success=False,
                message="Recovery failed"
            )
            
            error = AuthenticationError("Test error")
            result = manager.recover_from_error(error)
            
            assert result.success is False
            assert result.message == "Recovery failed"
            assert manager.recovery_stats["total_errors"] == 1
            assert manager.recovery_stats["failed_recoveries"] == 1
    
    def test_recover_authentication(self):
        """Test authentication error recovery."""
        manager = RecoveryManager()
        
        with patch.object(manager, 'recover_from_error') as mock_recover:
            mock_recover.return_value = RecoveryResult(True, "Success")
            
            error = AuthenticationError("Auth error")
            auth_manager = Mock()
            
            result = manager.recover_authentication(
                error, auth_manager, user_code="USER123"
            )
            
            assert result.success is True
            mock_recover.assert_called_once()
            args, kwargs = mock_recover.call_args
            assert args[0] == error
            assert kwargs["context"]["auth_manager"] == auth_manager
            assert kwargs["context"]["user_code"] == "USER123"
    
    def test_recover_device_connection(self):
        """Test device connection error recovery."""
        manager = RecoveryManager()
        
        with patch.object(manager, 'recover_from_error') as mock_recover:
            mock_recover.return_value = RecoveryResult(True, "Success")
            
            error = DeviceConnectionError("Connection error")
            device = Mock()
            
            result = manager.recover_device_connection(
                error, device, force_rediscovery=True
            )
            
            assert result.success is True
            mock_recover.assert_called_once()
            args, kwargs = mock_recover.call_args
            assert args[0] == error
            assert kwargs["context"]["device"] == device
            assert kwargs["context"]["force_rediscovery"] is True
    
    def test_recover_dps_mapping(self):
        """Test DPS mapping error recovery."""
        manager = RecoveryManager()
        
        with patch.object(manager, 'recover_from_error') as mock_recover:
            mock_recover.return_value = RecoveryResult(True, "Success")
            
            error = DPSMappingError("Mapping error")
            device_info = {"model": "TEST123"}
            
            result = manager.recover_dps_mapping(error, device_info)
            
            assert result.success is True
            mock_recover.assert_called_once()
            args, kwargs = mock_recover.call_args
            assert args[0] == error
            assert kwargs["context"]["device_info"] == device_info
    
    def test_recover_protocol_error(self):
        """Test protocol error recovery."""
        manager = RecoveryManager()
        
        with patch.object(manager, 'recover_from_error') as mock_recover:
            mock_recover.return_value = RecoveryResult(True, "Success")
            
            error = ProtocolError("Protocol error")
            device = Mock()
            
            result = manager.recover_protocol_error(
                error, device, suggested_version="3.4"
            )
            
            assert result.success is True
            mock_recover.assert_called_once()
            args, kwargs = mock_recover.call_args
            assert args[0] == error
            assert kwargs["context"]["device"] == device
            assert kwargs["context"]["suggested_version"] == "3.4"
    
    def test_with_retry_default_config(self):
        """Test with_retry with default configuration."""
        manager = RecoveryManager()
        
        with patch.object(manager.retry_manager, 'retry_sync') as mock_retry:
            mock_retry.return_value = "success"
            
            def test_func():
                return "success"
            
            result = manager.with_retry(test_func)
            
            assert result == "success"
            mock_retry.assert_called_once()
    
    def test_with_retry_custom_config(self):
        """Test with_retry with custom configuration."""
        manager = RecoveryManager()
        
        with patch.object(manager.retry_manager, 'retry_sync') as mock_retry:
            mock_retry.return_value = "success"
            
            config = RetryConfig(max_attempts=5)
            
            def test_func():
                return "success"
            
            result = manager.with_retry(test_func, config=config)
            
            assert result == "success"
            mock_retry.assert_called_once()
            args, kwargs = mock_retry.call_args
            assert args[1] == config
    
    def test_with_retry_config_name(self):
        """Test with_retry with config name."""
        manager = RecoveryManager()
        
        with patch.object(manager.retry_manager, 'retry_sync') as mock_retry:
            mock_retry.return_value = "success"
            
            def test_func():
                return "success"
            
            result = manager.with_retry(test_func, config_name="authentication")
            
            assert result == "success"
            mock_retry.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_with_async_retry(self):
        """Test with_async_retry functionality."""
        manager = RecoveryManager()
        
        with patch.object(manager.retry_manager, 'retry_async') as mock_retry:
            mock_retry.return_value = "success"
            
            async def test_func():
                return "success"
            
            result = await manager.with_async_retry(test_func)
            
            assert result == "success"
            mock_retry.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_run_health_check(self):
        """Test running health check."""
        manager = RecoveryManager()
        
        with patch.object(manager.health_monitor, 'run_all_diagnostics') as mock_run:
            mock_result = {
                "Network": DiagnosticResult(
                    check_name="Network",
                    status=HealthStatus.HEALTHY,
                    message="Healthy",
                    details={},
                    timestamp=time.time(),
                    duration=1.0,
                    recommendations=[]
                )
            }
            mock_run.return_value = mock_result
            
            result = await manager.run_health_check()
            
            assert result == mock_result
            mock_run.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_start_health_monitoring(self):
        """Test starting health monitoring."""
        manager = RecoveryManager()
        
        with patch.object(manager.health_monitor, 'start_monitoring') as mock_start:
            mock_start.return_value = None
            
            # Mock to avoid actual monitoring
            manager.health_monitor.monitoring_active = False
            
            await manager.start_health_monitoring(interval=60.0)
            
            assert manager.health_monitor.check_interval == 60.0
            assert manager.health_monitoring_active is True
    
    def test_stop_health_monitoring(self):
        """Test stopping health monitoring."""
        manager = RecoveryManager()
        
        with patch.object(manager.health_monitor, 'stop_monitoring') as mock_stop:
            manager.health_monitoring_active = True
            
            manager.stop_health_monitoring()
            
            assert manager.health_monitoring_active is False
            mock_stop.assert_called_once()
    
    def test_get_health_status(self):
        """Test getting health status."""
        manager = RecoveryManager()
        
        with patch.object(manager.health_monitor, 'get_overall_health') as mock_health:
            mock_health.return_value = {
                "overall_status": "healthy",
                "last_check": time.time()
            }
            
            status = manager.get_health_status()
            
            assert status["overall_status"] == "healthy"
            mock_health.assert_called_once()
    
    def test_add_device_to_monitor(self):
        """Test adding device to monitoring."""
        manager = RecoveryManager()
        
        # Mock device diagnostic
        device_diagnostic = Mock()
        device_diagnostic.add_device = Mock()
        
        with patch.object(manager.health_monitor, 'diagnostics', [device_diagnostic]):
            with patch('libtuya.recovery.diagnostics.DeviceDiagnostics', lambda: device_diagnostic):
                manager.add_device_to_monitor("DEV123", "192.168.1.100", "KEY123")
                
                device_diagnostic.add_device.assert_called_once_with(
                    "DEV123", "192.168.1.100", "KEY123"
                )
    
    def test_set_auth_manager(self):
        """Test setting authentication manager."""
        manager = RecoveryManager()
        
        # Mock auth diagnostic
        auth_diagnostic = Mock()
        auth_diagnostic.set_auth_manager = Mock()
        
        with patch.object(manager.health_monitor, 'diagnostics', [auth_diagnostic]):
            with patch('libtuya.recovery.diagnostics.AuthenticationDiagnostics', lambda: auth_diagnostic):
                auth_manager = Mock()
                manager.set_auth_manager(auth_manager)
                
                auth_diagnostic.set_auth_manager.assert_called_once_with(auth_manager)
    
    def test_get_recovery_stats(self):
        """Test getting recovery statistics."""
        manager = RecoveryManager()
        
        # Set some stats
        manager.recovery_stats["total_errors"] = 10
        manager.recovery_stats["successful_recoveries"] = 7
        manager.recovery_stats["fallback_used"] = 3
        
        with patch.object(manager.retry_manager, 'get_retry_stats') as mock_retry_stats, \
             patch.object(manager.recovery_coordinator, 'get_recovery_stats') as mock_coord_stats:
            
            mock_retry_stats.return_value = {"retry_data": "test"}
            mock_coord_stats.return_value = {"coord_data": "test"}
            
            stats = manager.get_recovery_stats()
            
            assert stats["total_errors"] == 10
            assert stats["successful_recoveries"] == 7
            assert stats["fallback_used"] == 3
            assert stats["success_rate"] == 0.7
            assert stats["fallback_rate"] == 0.3
            assert "retry_stats" in stats
            assert "coordinator_stats" in stats
    
    def test_get_diagnostic_stats(self):
        """Test getting diagnostic statistics."""
        manager = RecoveryManager()
        
        with patch.object(manager.health_monitor, 'get_diagnostic_stats') as mock_stats:
            mock_stats.return_value = {"Network": {"run_count": 5}}
            
            stats = manager.get_diagnostic_stats()
            
            assert stats["Network"]["run_count"] == 5
            mock_stats.assert_called_once()
    
    def test_get_health_history(self):
        """Test getting health history."""
        manager = RecoveryManager()
        
        with patch.object(manager.health_monitor, 'get_health_history') as mock_history:
            mock_history.return_value = [{"timestamp": time.time()}]
            
            history = manager.get_health_history(limit=5)
            
            assert len(history) == 1
            mock_history.assert_called_once_with(5)
    
    def test_reset_stats(self):
        """Test resetting statistics."""
        manager = RecoveryManager()
        
        # Set some stats
        manager.recovery_stats["total_errors"] = 10
        manager.recovery_stats["successful_recoveries"] = 7
        
        with patch.object(manager.recovery_coordinator, 'reset_stats') as mock_reset:
            manager.reset_stats()
            
            assert manager.recovery_stats["total_errors"] == 0
            assert manager.recovery_stats["successful_recoveries"] == 0
            mock_reset.assert_called_once()
    
    def test_configure_retry(self):
        """Test configuring retry settings."""
        manager = RecoveryManager()
        
        config = RetryConfig(max_attempts=5)
        manager.configure_retry("test_operation", config)
        
        # Check that config was added to global configs
        from libtuya.recovery.retry_strategies import RETRY_CONFIGS
        assert RETRY_CONFIGS["test_operation"] == config
    
    def test_configure_circuit_breaker(self):
        """Test configuring circuit breaker."""
        manager = RecoveryManager()
        
        config = CircuitBreakerConfig(failure_threshold=3)
        
        with patch.object(manager.retry_manager, 'add_circuit_breaker') as mock_add:
            manager.configure_circuit_breaker("test_operation", config)
            
            mock_add.assert_called_once_with("test_operation", config)
    
    def test_add_custom_handler(self):
        """Test adding custom recovery handler."""
        manager = RecoveryManager()
        
        handler = Mock()
        
        with patch.object(manager.recovery_coordinator, 'add_handler') as mock_add:
            manager.add_custom_handler(handler)
            
            mock_add.assert_called_once_with(handler)
    
    def test_add_custom_diagnostic(self):
        """Test adding custom diagnostic."""
        manager = RecoveryManager()
        
        diagnostic = Mock()
        
        with patch.object(manager.health_monitor, 'add_diagnostic') as mock_add:
            manager.add_custom_diagnostic(diagnostic)
            
            mock_add.assert_called_once_with(diagnostic)


class TestRecoveryContext:
    """Test RecoveryContext context manager."""
    
    def test_recovery_context_initialization(self):
        """Test RecoveryContext initialization."""
        manager = RecoveryManager()
        context = RecoveryContext(manager)
        
        assert context.recovery_manager == manager
        assert context.context == {}
        assert context.auto_retry is True
    
    def test_recovery_context_with_custom_settings(self):
        """Test RecoveryContext with custom settings."""
        manager = RecoveryManager()
        custom_context = {"key": "value"}
        
        context = RecoveryContext(manager, custom_context, auto_retry=False)
        
        assert context.context == custom_context
        assert context.auto_retry is False
    
    def test_recovery_context_success(self):
        """Test RecoveryContext with successful operation."""
        manager = RecoveryManager()
        
        with RecoveryContext(manager) as ctx:
            # No exception should be raised
            pass
        
        # Should exit normally
        assert True
    
    def test_recovery_context_with_tuya_error_successful_recovery(self):
        """Test RecoveryContext with TuyaError and successful recovery."""
        manager = RecoveryManager()
        
        with patch.object(manager, 'recover_from_error') as mock_recover:
            mock_recover.return_value = RecoveryResult(success=True, message="Success")
            
            with RecoveryContext(manager) as ctx:
                raise TuyaError("Test error")
        
        # Exception should be suppressed
        mock_recover.assert_called_once()
    
    def test_recovery_context_with_tuya_error_failed_recovery_with_retry(self):
        """Test RecoveryContext with TuyaError and failed recovery with retry."""
        manager = RecoveryManager()
        
        with patch.object(manager, 'recover_from_error') as mock_recover:
            mock_recover.return_value = RecoveryResult(
                success=False, 
                message="Failed", 
                retry_recommended=True
            )
            
            with RecoveryContext(manager) as ctx:
                raise TuyaError("Test error")
        
        # Exception should be suppressed due to retry recommendation
        mock_recover.assert_called_once()
    
    def test_recovery_context_with_tuya_error_failed_recovery_no_retry(self):
        """Test RecoveryContext with TuyaError and failed recovery without retry."""
        manager = RecoveryManager()
        
        with patch.object(manager, 'recover_from_error') as mock_recover:
            mock_recover.return_value = RecoveryResult(
                success=False, 
                message="Failed", 
                retry_recommended=False
            )
            
            with pytest.raises(TuyaError):
                with RecoveryContext(manager) as ctx:
                    raise TuyaError("Test error")
        
        mock_recover.assert_called_once()
    
    def test_recovery_context_with_tuya_error_auto_retry_disabled(self):
        """Test RecoveryContext with TuyaError and auto-retry disabled."""
        manager = RecoveryManager()
        
        with patch.object(manager, 'recover_from_error') as mock_recover:
            mock_recover.return_value = RecoveryResult(
                success=False, 
                message="Failed", 
                retry_recommended=True
            )
            
            with pytest.raises(TuyaError):
                with RecoveryContext(manager, auto_retry=False) as ctx:
                    raise TuyaError("Test error")
        
        mock_recover.assert_called_once()
    
    def test_recovery_context_with_non_tuya_error(self):
        """Test RecoveryContext with non-TuyaError."""
        manager = RecoveryManager()
        
        with pytest.raises(ValueError):
            with RecoveryContext(manager) as ctx:
                raise ValueError("Non-Tuya error")
        
        # Should not attempt recovery for non-TuyaError


class TestUtilityFunctions:
    """Test utility functions."""
    
    def test_create_recovery_manager_default(self):
        """Test create_recovery_manager with defaults."""
        with patch('libtuya.recovery.asyncio.create_task') as mock_task:
            manager = create_recovery_manager()
            
            assert isinstance(manager, RecoveryManager)
            assert manager.enable_logging is True
            # Should create monitoring task
            mock_task.assert_called_once()
    
    def test_create_recovery_manager_custom(self):
        """Test create_recovery_manager with custom settings."""
        with patch('libtuya.recovery.asyncio.create_task') as mock_task:
            manager = create_recovery_manager(
                enable_health_monitoring=False,
                enable_logging=False
            )
            
            assert isinstance(manager, RecoveryManager)
            assert manager.enable_logging is False
            # Should not create monitoring task
            mock_task.assert_not_called()
    
    def test_with_recovery_default(self):
        """Test with_recovery with default manager."""
        context = with_recovery()
        
        assert isinstance(context, RecoveryContext)
        assert isinstance(context.recovery_manager, RecoveryManager)
        assert context.context == {}
        assert context.auto_retry is True
    
    def test_with_recovery_custom(self):
        """Test with_recovery with custom settings."""
        manager = RecoveryManager()
        custom_context = {"key": "value"}
        
        context = with_recovery(
            recovery_manager=manager,
            context=custom_context,
            auto_retry=False
        )
        
        assert context.recovery_manager == manager
        assert context.context == custom_context
        assert context.auto_retry is False


class TestIntegration:
    """Test integration between components."""
    
    def test_full_recovery_workflow(self):
        """Test complete recovery workflow."""
        manager = RecoveryManager()
        
        # Mock all components
        with patch.object(manager.recovery_coordinator, 'recover') as mock_recover:
            mock_recover.return_value = RecoveryResult(
                success=True,
                message="Recovery successful",
                recovered_data={"mapping": {1: "switch"}},
                fallback_used=True
            )
            
            # Test error recovery
            error = DPSMappingError("Unknown device")
            result = manager.recover_from_error(error)
            
            # Check results
            assert result.success is True
            assert result.fallback_used is True
            assert "mapping" in result.recovered_data
            
            # Check stats
            assert manager.recovery_stats["total_errors"] == 1
            assert manager.recovery_stats["successful_recoveries"] == 1
            assert manager.recovery_stats["fallback_used"] == 1
    
    def test_recovery_with_retry_integration(self):
        """Test recovery integrated with retry logic."""
        manager = RecoveryManager()
        
        call_count = 0
        
        def failing_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise NetworkError("Network error")
            return "success"
        
        with patch.object(manager.retry_manager, 'retry_sync') as mock_retry:
            mock_retry.side_effect = lambda func, config, **kwargs: func()
            
            # This would normally fail on first two attempts
            # but succeed on third with retry logic
            result = manager.with_retry(failing_function, config_name="network_operation")
            
            assert result == "success"
            mock_retry.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_health_monitoring_integration(self):
        """Test health monitoring integration."""
        manager = RecoveryManager()
        
        # Mock health monitor
        with patch.object(manager.health_monitor, 'run_all_diagnostics') as mock_run:
            mock_results = {
                "Network": DiagnosticResult(
                    check_name="Network",
                    status=HealthStatus.WARNING,
                    message="High latency",
                    details={"latency": 1000},
                    timestamp=time.time(),
                    duration=1.0,
                    recommendations=["Check network speed"]
                ),
                "Authentication": DiagnosticResult(
                    check_name="Authentication",
                    status=HealthStatus.HEALTHY,
                    message="All good",
                    details={},
                    timestamp=time.time(),
                    duration=0.5,
                    recommendations=[]
                )
            }
            mock_run.return_value = mock_results
            
            # Run health check
            results = await manager.run_health_check()
            
            assert len(results) == 2
            assert results["Network"].status == HealthStatus.WARNING
            assert results["Authentication"].status == HealthStatus.HEALTHY
            
            # Check overall health
            with patch.object(manager.health_monitor, 'get_overall_health') as mock_health:
                mock_health.return_value = {
                    "overall_status": "warning",
                    "last_check": time.time(),
                    "recommendations": ["Check network speed"]
                }
                
                health = manager.get_health_status()
                assert health["overall_status"] == "warning"
                assert "Check network speed" in health["recommendations"]


if __name__ == "__main__":
    pytest.main([__file__])