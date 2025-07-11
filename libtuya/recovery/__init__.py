"""
LibTuya Error Recovery System

This module provides comprehensive error recovery and health monitoring
capabilities for the libtuya system. It enables graceful degradation,
automatic recovery, and proactive health monitoring.

Key Components:
- Exception hierarchy for categorizing errors
- Retry strategies with exponential backoff and circuit breakers
- Error handlers for specific recovery scenarios
- System diagnostics and health monitoring
- Unified recovery management interface

Usage:
    from libtuya.recovery import RecoveryManager

    # Initialize recovery system
    recovery = RecoveryManager()

    # Enable recovery for operations
    try:
        device.turn_on()
    except DeviceConnectionError as e:
        recovery.recover_device_connection(e, device)
        device.turn_on()  # Retry after recovery

    # Start health monitoring
    await recovery.start_health_monitoring()
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Union

# Import diagnostics
from .diagnostics import (
    AuthenticationDiagnostics,
    BaseDiagnostic,
    DeviceDiagnostics,
    DiagnosticResult,
    HealthMonitor,
    HealthStatus,
    NetworkDiagnostics,
    SystemDiagnostics,
    default_health_monitor,
)

# Import error handlers
from .error_handlers import (
    AuthenticationRecovery,
    BaseRecoveryHandler,
    DeviceConnectionRecovery,
    DPSMappingRecovery,
    NetworkRecovery,
    ProtocolRecovery,
    RecoveryCoordinator,
    RecoveryResult,
    default_recovery_coordinator,
)

# Import all exception types
from .exceptions import (
    EXCEPTION_HIERARCHY,
    AuthenticationError,
    CapabilityMismatchError,
    CommandError,
    ConfigurationError,
    ConnectivityError,
    DeviceConnectionError,
    DeviceError,
    DNSError,
    DPSMappingError,
    FirmwareError,
    HardwareError,
    IPDiscoveryError,
    LocalKeyError,
    NetworkError,
    ProtocolError,
    QRCodeError,
    TimeoutError,
    TokenError,
    TuyaError,
    UnknownDeviceError,
    VersionDetectionError,
    get_error_category,
    is_retryable_error,
)

# Import retry strategies
from .retry_strategies import (
    CIRCUIT_BREAKER_CONFIGS,
    RETRY_CONFIGS,
    BackoffStrategy,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerState,
    ExponentialBackoff,
    FixedBackoff,
    LinearBackoff,
    RetryConfig,
    RetryManager,
    TimeoutManager,
    async_retry,
    default_retry_manager,
    retry,
)

logger = logging.getLogger(__name__)


class RecoveryManager:
    """
    Unified recovery management system for libtuya.

    This class provides a high-level interface for error recovery,
    health monitoring, and system diagnostics. It coordinates all
    recovery components and provides a "just works" experience.
    """

    def __init__(
        self,
        retry_manager: Optional[RetryManager] = None,
        recovery_coordinator: Optional[RecoveryCoordinator] = None,
        health_monitor: Optional[HealthMonitor] = None,
        enable_logging: bool = True,
    ):
        """
        Initialize the recovery manager.

        Args:
            retry_manager: Custom retry manager (uses default if None)
            recovery_coordinator: Custom recovery coordinator (uses default if None)
            health_monitor: Custom health monitor (uses default if None)
            enable_logging: Enable recovery logging
        """
        self.retry_manager = retry_manager or default_retry_manager
        self.recovery_coordinator = recovery_coordinator or default_recovery_coordinator
        self.health_monitor = health_monitor or default_health_monitor
        self.enable_logging = enable_logging

        # Recovery statistics
        self.recovery_stats = {
            "total_errors": 0,
            "successful_recoveries": 0,
            "failed_recoveries": 0,
            "fallback_used": 0,
            "start_time": time.time(),
        }

        # Health monitoring state
        self.health_monitoring_active = False
        self.health_check_interval = 300.0  # 5 minutes

        if self.enable_logging:
            self._setup_logging()

    def _setup_logging(self):
        """Setup recovery logging."""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

        # Set specific log levels
        logging.getLogger("libtuya.recovery").setLevel(logging.INFO)
        logging.getLogger("libtuya.recovery.diagnostics").setLevel(logging.WARNING)

    # === Error Recovery Methods ===

    def recover_from_error(
        self, error: Exception, context: Optional[Dict[str, Any]] = None
    ) -> RecoveryResult:
        """
        Recover from any error using appropriate handlers.

        Args:
            error: The error to recover from
            context: Additional context for recovery

        Returns:
            RecoveryResult indicating success or failure
        """
        self.recovery_stats["total_errors"] += 1

        if self.enable_logging:
            logger.info(f"Attempting recovery from {type(error).__name__}: {error}")

        # Attempt recovery
        result = self.recovery_coordinator.recover(error, context)

        # Update statistics
        if result.success:
            self.recovery_stats["successful_recoveries"] += 1
        else:
            self.recovery_stats["failed_recoveries"] += 1

        if result.fallback_used:
            self.recovery_stats["fallback_used"] += 1

        if self.enable_logging:
            logger.info(f"Recovery {'succeeded' if result.success else 'failed'}: {result.message}")

        return result

    def recover_authentication(
        self,
        error: AuthenticationError,
        auth_manager=None,
        user_code: Optional[str] = None,
    ) -> RecoveryResult:
        """
        Recover from authentication errors.

        Args:
            error: Authentication error
            auth_manager: Authentication manager instance
            user_code: User code for QR authentication

        Returns:
            RecoveryResult with recovery status
        """
        context = {"auth_manager": auth_manager, "user_code": user_code}

        return self.recover_from_error(error, context)

    def recover_device_connection(
        self,
        error: DeviceConnectionError,
        device=None,
        force_rediscovery: bool = False,
    ) -> RecoveryResult:
        """
        Recover from device connection errors.

        Args:
            error: Device connection error
            device: Device instance
            force_rediscovery: Force device rediscovery

        Returns:
            RecoveryResult with recovery status
        """
        context = {"device": device, "force_rediscovery": force_rediscovery}

        return self.recover_from_error(error, context)

    def recover_dps_mapping(
        self,
        error: DPSMappingError,
        device_info: Optional[Dict[str, Any]] = None,
    ) -> RecoveryResult:
        """
        Recover from DPS mapping errors.

        Args:
            error: DPS mapping error
            device_info: Device information

        Returns:
            RecoveryResult with recovery status and potentially recovered mapping
        """
        context = {"device_info": device_info}

        return self.recover_from_error(error, context)

    def recover_protocol_error(
        self,
        error: ProtocolError,
        device=None,
        suggested_version: Optional[str] = None,
    ) -> RecoveryResult:
        """
        Recover from protocol errors.

        Args:
            error: Protocol error
            device: Device instance
            suggested_version: Suggested protocol version to try

        Returns:
            RecoveryResult with recovery status
        """
        context = {"device": device, "suggested_version": suggested_version}

        return self.recover_from_error(error, context)

    # === Retry Management ===

    def with_retry(
        self,
        func,
        config: Optional[RetryConfig] = None,
        operation_name: Optional[str] = None,
        config_name: Optional[str] = None,
    ):
        """
        Execute a function with retry logic.

        Args:
            func: Function to execute
            config: Retry configuration
            operation_name: Name for logging and circuit breaker
            config_name: Name of pre-configured retry config

        Returns:
            Function result
        """
        retry_config = config
        if config_name and config_name in RETRY_CONFIGS:
            retry_config = RETRY_CONFIGS[config_name]
        if not retry_config:
            retry_config = RETRY_CONFIGS["network_operation"]

        return self.retry_manager.retry_sync(func, retry_config, operation_name=operation_name)

    async def with_async_retry(
        self,
        func,
        config: Optional[RetryConfig] = None,
        operation_name: Optional[str] = None,
        config_name: Optional[str] = None,
    ):
        """
        Execute an async function with retry logic.

        Args:
            func: Async function to execute
            config: Retry configuration
            operation_name: Name for logging and circuit breaker
            config_name: Name of pre-configured retry config

        Returns:
            Function result
        """
        retry_config = config
        if config_name and config_name in RETRY_CONFIGS:
            retry_config = RETRY_CONFIGS[config_name]
        if not retry_config:
            retry_config = RETRY_CONFIGS["network_operation"]

        return await self.retry_manager.retry_async(
            func, retry_config, operation_name=operation_name
        )

    # === Health Monitoring ===

    async def run_health_check(self) -> Dict[str, DiagnosticResult]:
        """
        Run a comprehensive health check.

        Returns:
            Dictionary of diagnostic results
        """
        if self.enable_logging:
            logger.info("Running comprehensive health check")

        return await self.health_monitor.run_all_diagnostics()

    async def start_health_monitoring(self, interval: Optional[float] = None):
        """
        Start continuous health monitoring.

        Args:
            interval: Check interval in seconds (uses default if None)
        """
        if interval:
            self.health_monitor.check_interval = interval

        if self.health_monitoring_active:
            logger.warning("Health monitoring is already active")
            return

        self.health_monitoring_active = True

        if self.enable_logging:
            logger.info(
                f"Starting health monitoring with {self.health_monitor.check_interval}s interval"
            )

        # Start monitoring in background
        asyncio.create_task(self.health_monitor.start_monitoring())

    def stop_health_monitoring(self):
        """Stop continuous health monitoring."""
        self.health_monitoring_active = False
        self.health_monitor.stop_monitoring()

        if self.enable_logging:
            logger.info("Health monitoring stopped")

    def get_health_status(self) -> Dict[str, Any]:
        """
        Get current system health status.

        Returns:
            Dictionary with health status information
        """
        return self.health_monitor.get_overall_health()

    def add_device_to_monitor(self, device_id: str, device_ip: str, local_key: str):
        """
        Add a device to health monitoring.

        Args:
            device_id: Device ID
            device_ip: Device IP address
            local_key: Device local key
        """
        # Find device diagnostics
        for diagnostic in self.health_monitor.diagnostics:
            if isinstance(diagnostic, DeviceDiagnostics):
                diagnostic.add_device(device_id, device_ip, local_key)
                break

    def set_auth_manager(self, auth_manager):
        """
        Set authentication manager for health monitoring.

        Args:
            auth_manager: Authentication manager instance
        """
        # Find authentication diagnostics
        for diagnostic in self.health_monitor.diagnostics:
            if isinstance(diagnostic, AuthenticationDiagnostics):
                diagnostic.set_auth_manager(auth_manager)
                break

    # === Statistics and Reporting ===

    def get_recovery_stats(self) -> Dict[str, Any]:
        """
        Get recovery statistics.

        Returns:
            Dictionary with recovery statistics
        """
        uptime = time.time() - self.recovery_stats["start_time"]
        total_attempts = self.recovery_stats["total_errors"]

        return {
            **self.recovery_stats,
            "uptime": uptime,
            "success_rate": (self.recovery_stats["successful_recoveries"] / max(total_attempts, 1)),
            "fallback_rate": (self.recovery_stats["fallback_used"] / max(total_attempts, 1)),
            "retry_stats": self.retry_manager.get_retry_stats(),
            "coordinator_stats": self.recovery_coordinator.get_recovery_stats(),
        }

    def get_diagnostic_stats(self) -> Dict[str, Any]:
        """
        Get diagnostic statistics.

        Returns:
            Dictionary with diagnostic statistics
        """
        return self.health_monitor.get_diagnostic_stats()

    def get_health_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent health check history.

        Args:
            limit: Number of recent checks to return

        Returns:
            List of health check results
        """
        return self.health_monitor.get_health_history(limit)

    def reset_stats(self):
        """Reset all statistics."""
        self.recovery_stats = {
            "total_errors": 0,
            "successful_recoveries": 0,
            "failed_recoveries": 0,
            "fallback_used": 0,
            "start_time": time.time(),
        }

        self.recovery_coordinator.reset_stats()

    # === Configuration ===

    def configure_retry(self, operation: str, config: RetryConfig):
        """
        Configure retry settings for a specific operation.

        Args:
            operation: Operation name
            config: Retry configuration
        """
        RETRY_CONFIGS[operation] = config

    def configure_circuit_breaker(self, operation: str, config: CircuitBreakerConfig):
        """
        Configure circuit breaker for a specific operation.

        Args:
            operation: Operation name
            config: Circuit breaker configuration
        """
        CIRCUIT_BREAKER_CONFIGS[operation] = config
        self.retry_manager.add_circuit_breaker(operation, config)

    def add_custom_handler(self, handler: BaseRecoveryHandler):
        """
        Add a custom recovery handler.

        Args:
            handler: Custom recovery handler
        """
        self.recovery_coordinator.add_handler(handler)

    def add_custom_diagnostic(self, diagnostic: BaseDiagnostic):
        """
        Add a custom diagnostic check.

        Args:
            diagnostic: Custom diagnostic
        """
        self.health_monitor.add_diagnostic(diagnostic)


# === Context Managers ===


class RecoveryContext:
    """Context manager for automatic error recovery."""

    def __init__(
        self,
        recovery_manager: RecoveryManager,
        context: Optional[Dict[str, Any]] = None,
        auto_retry: bool = True,
    ):
        self.recovery_manager = recovery_manager
        self.context = context or {}
        self.auto_retry = auto_retry

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type and issubclass(exc_type, TuyaError):
            # Attempt recovery
            result = self.recovery_manager.recover_from_error(exc_val, self.context)

            if result.success or (self.auto_retry and result.retry_recommended):
                # Suppress the exception if recovery succeeded or retry is recommended
                return True

        return False


# === Utility Functions ===


def create_recovery_manager(
    enable_health_monitoring: bool = True,
    health_check_interval: float = 300.0,
    enable_logging: bool = True,
) -> RecoveryManager:
    """
    Create a configured recovery manager.

    Args:
        enable_health_monitoring: Enable automatic health monitoring
        health_check_interval: Health check interval in seconds
        enable_logging: Enable recovery logging

    Returns:
        Configured RecoveryManager instance
    """
    manager = RecoveryManager(enable_logging=enable_logging)

    if enable_health_monitoring:
        asyncio.create_task(manager.start_health_monitoring(health_check_interval))

    return manager


def with_recovery(
    recovery_manager: Optional[RecoveryManager] = None,
    context: Optional[Dict[str, Any]] = None,
    auto_retry: bool = True,
):
    """
    Context manager for automatic error recovery.

    Args:
        recovery_manager: Recovery manager (uses default if None)
        context: Recovery context
        auto_retry: Enable automatic retry on recoverable errors

    Returns:
        RecoveryContext instance
    """
    manager = recovery_manager or RecoveryManager()
    return RecoveryContext(manager, context, auto_retry)


# === Module Exports ===

__all__ = [
    # Exception classes
    "TuyaError",
    "AuthenticationError",
    "QRCodeError",
    "TokenError",
    "DeviceConnectionError",
    "LocalKeyError",
    "IPDiscoveryError",
    "DPSMappingError",
    "UnknownDeviceError",
    "CapabilityMismatchError",
    "ProtocolError",
    "VersionDetectionError",
    "CommandError",
    "NetworkError",
    "ConnectivityError",
    "DNSError",
    "TimeoutError",
    "DeviceError",
    "HardwareError",
    "FirmwareError",
    "ConfigurationError",
    # Retry classes
    "RetryManager",
    "RetryConfig",
    "BackoffStrategy",
    "CircuitBreaker",
    "CircuitBreakerState",
    "CircuitBreakerConfig",
    "TimeoutManager",
    # Recovery classes
    "RecoveryResult",
    "BaseRecoveryHandler",
    "RecoveryCoordinator",
    # Diagnostic classes
    "HealthStatus",
    "DiagnosticResult",
    "BaseDiagnostic",
    "NetworkDiagnostics",
    "DeviceDiagnostics",
    "AuthenticationDiagnostics",
    "SystemDiagnostics",
    "HealthMonitor",
    # Main classes
    "RecoveryManager",
    "RecoveryContext",
    # Utility functions
    "create_recovery_manager",
    "with_recovery",
    "get_error_category",
    "is_retryable_error",
    # Decorators
    "retry",
    "async_retry",
    # Constants
    "RETRY_CONFIGS",
    "CIRCUIT_BREAKER_CONFIGS",
    "EXCEPTION_HIERARCHY",
    # Default instances
    "default_retry_manager",
    "default_recovery_coordinator",
    "default_health_monitor",
]
