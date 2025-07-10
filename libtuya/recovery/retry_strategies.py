"""
Retry strategies and backoff logic for libtuya error recovery.

This module provides comprehensive retry mechanisms including:
- Exponential backoff for network operations
- Linear backoff for device discovery
- Circuit breaker pattern for failing devices
- Timeout management for long operations
- Coordinated retry management
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union
from contextlib import contextmanager

from .exceptions import (
    TuyaError,
    NetworkError,
    DeviceConnectionError,
    is_retryable_error,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class BackoffStrategy(Enum):
    """Backoff strategy types."""

    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    FIXED = "fixed"
    CUSTOM = "custom"


@dataclass
class RetryConfig:
    """Configuration for retry operations."""

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    backoff_strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL
    backoff_multiplier: float = 2.0
    jitter: bool = True
    timeout: Optional[float] = None
    retryable_exceptions: Optional[List[type]] = None


class BackoffCalculator(ABC):
    """Abstract base class for backoff calculators."""

    @abstractmethod
    def calculate_delay(
        self, attempt: int, base_delay: float, max_delay: float
    ) -> float:
        """Calculate delay for the given attempt."""
        pass


class ExponentialBackoff(BackoffCalculator):
    """Exponential backoff calculator."""

    def __init__(self, multiplier: float = 2.0, jitter: bool = True):
        self.multiplier = multiplier
        self.jitter = jitter

    def calculate_delay(
        self, attempt: int, base_delay: float, max_delay: float
    ) -> float:
        """Calculate exponential backoff delay."""
        delay = base_delay * (self.multiplier**attempt)
        delay = min(delay, max_delay)

        if self.jitter:
            import random

            delay = delay * (0.5 + random.random() * 0.5)

        return delay


class LinearBackoff(BackoffCalculator):
    """Linear backoff calculator."""

    def __init__(self, increment: float = 1.0, jitter: bool = True):
        self.increment = increment
        self.jitter = jitter

    def calculate_delay(
        self, attempt: int, base_delay: float, max_delay: float
    ) -> float:
        """Calculate linear backoff delay."""
        delay = base_delay + (self.increment * attempt)
        delay = min(delay, max_delay)

        if self.jitter:
            import random

            delay = delay * (0.8 + random.random() * 0.4)

        return delay


class FixedBackoff(BackoffCalculator):
    """Fixed delay backoff calculator."""

    def __init__(self, jitter: bool = True):
        self.jitter = jitter

    def calculate_delay(
        self, attempt: int, base_delay: float, max_delay: float
    ) -> float:
        """Calculate fixed backoff delay."""
        delay = base_delay

        if self.jitter:
            import random

            delay = delay * (0.8 + random.random() * 0.4)

        return delay


class CustomBackoff(BackoffCalculator):
    """Custom backoff calculator."""

    def __init__(self, calculate_func: Callable[[int, float, float], float]):
        self.calculate_func = calculate_func

    def calculate_delay(
        self, attempt: int, base_delay: float, max_delay: float
    ) -> float:
        """Calculate custom backoff delay."""
        return self.calculate_func(attempt, base_delay, max_delay)


class CircuitBreakerState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    success_threshold: int = 3
    timeout: float = 10.0


class CircuitBreaker:
    """
    Circuit breaker implementation for failing operations.

    Prevents cascading failures by temporarily stopping calls to
    failing operations and allowing them to recover.
    """

    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
        self.next_attempt_time = 0

    def can_execute(self) -> bool:
        """Check if operation can be executed."""
        now = time.time()

        if self.state == CircuitBreakerState.CLOSED:
            return True
        elif self.state == CircuitBreakerState.OPEN:
            if now >= self.next_attempt_time:
                self.state = CircuitBreakerState.HALF_OPEN
                self.success_count = 0
                return True
            return False
        elif self.state == CircuitBreakerState.HALF_OPEN:
            return True

        return False

    def record_success(self):
        """Record a successful operation."""
        self.failure_count = 0

        if self.state == CircuitBreakerState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self.state = CircuitBreakerState.CLOSED
                self.success_count = 0

    def record_failure(self):
        """Record a failed operation."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitBreakerState.HALF_OPEN:
            self.state = CircuitBreakerState.OPEN
            self.next_attempt_time = time.time() + self.config.recovery_timeout
        elif self.failure_count >= self.config.failure_threshold:
            self.state = CircuitBreakerState.OPEN
            self.next_attempt_time = time.time() + self.config.recovery_timeout

    def get_state(self) -> CircuitBreakerState:
        """Get current circuit breaker state."""
        return self.state

    def reset(self):
        """Reset circuit breaker to closed state."""
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
        self.next_attempt_time = 0


class TimeoutManager:
    """Manages timeouts for operations."""

    def __init__(self, default_timeout: float = 30.0):
        self.default_timeout = default_timeout
        self.operation_timeouts: Dict[str, float] = {}

    def set_timeout(self, operation: str, timeout: float):
        """Set timeout for a specific operation."""
        self.operation_timeouts[operation] = timeout

    def get_timeout(self, operation: str) -> float:
        """Get timeout for an operation."""
        return self.operation_timeouts.get(operation, self.default_timeout)

    @contextmanager
    def timeout_context(self, operation: str):
        """Context manager for timeout operations."""
        timeout = self.get_timeout(operation)
        start_time = time.time()

        try:
            yield timeout
        finally:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                logger.warning(
                    f"Operation '{operation}' exceeded timeout: {elapsed:.2f}s > {timeout:.2f}s"
                )


class RetryManager:
    """
    Comprehensive retry manager that coordinates all retry strategies.

    Provides a unified interface for retrying operations with different
    backoff strategies, circuit breakers, and timeout management.
    """

    def __init__(self):
        self.backoff_calculators = {
            BackoffStrategy.EXPONENTIAL: ExponentialBackoff(),
            BackoffStrategy.LINEAR: LinearBackoff(),
            BackoffStrategy.FIXED: FixedBackoff(),
        }
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.timeout_manager = TimeoutManager()

    def add_circuit_breaker(self, name: str, config: CircuitBreakerConfig):
        """Add a circuit breaker for a specific operation."""
        self.circuit_breakers[name] = CircuitBreaker(config)

    def get_circuit_breaker(self, name: str) -> Optional[CircuitBreaker]:
        """Get circuit breaker by name."""
        return self.circuit_breakers.get(name)

    def retry_sync(
        self,
        func: Callable[..., T],
        config: RetryConfig,
        *args,
        operation_name: Optional[str] = None,
        **kwargs,
    ) -> T:
        """
        Retry a synchronous function with the given configuration.

        Args:
            func: Function to retry
            config: Retry configuration
            *args: Function arguments
            operation_name: Name for circuit breaker and logging
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            Exception: The last exception if all retries fail
        """
        operation_name = operation_name or func.__name__
        circuit_breaker = self.circuit_breakers.get(operation_name)

        # Check circuit breaker
        if circuit_breaker and not circuit_breaker.can_execute():
            raise TuyaError(
                f"Circuit breaker is open for operation '{operation_name}'",
                error_code="CIRCUIT_BREAKER_OPEN",
                retryable=False,
            )

        # Get backoff calculator
        backoff_calculator = self.backoff_calculators.get(config.backoff_strategy)
        if not backoff_calculator:
            backoff_calculator = self.backoff_calculators[BackoffStrategy.EXPONENTIAL]

        last_exception = None

        for attempt in range(config.max_attempts):
            try:
                # Execute with timeout
                with self.timeout_manager.timeout_context(operation_name):
                    if config.timeout:
                        # TODO: Implement timeout wrapper for sync functions
                        result = func(*args, **kwargs)
                    else:
                        result = func(*args, **kwargs)

                # Record success
                if circuit_breaker:
                    circuit_breaker.record_success()

                logger.debug(
                    f"Operation '{operation_name}' succeeded on attempt {attempt + 1}"
                )
                return result

            except Exception as e:
                last_exception = e

                # Check if error is retryable
                if not self._is_retryable(e, config):
                    logger.debug(
                        f"Operation '{operation_name}' failed with non-retryable error: {e}"
                    )
                    if circuit_breaker:
                        circuit_breaker.record_failure()
                    raise

                # Record failure
                if circuit_breaker:
                    circuit_breaker.record_failure()

                # Log attempt
                logger.debug(
                    f"Operation '{operation_name}' failed on attempt {attempt + 1}: {e}"
                )

                # Calculate delay if not the last attempt
                if attempt < config.max_attempts - 1:
                    delay = backoff_calculator.calculate_delay(
                        attempt, config.base_delay, config.max_delay
                    )
                    logger.debug(
                        f"Retrying operation '{operation_name}' in {delay:.2f}s"
                    )
                    time.sleep(delay)

        # All attempts failed
        logger.error(
            f"Operation '{operation_name}' failed after {config.max_attempts} attempts"
        )
        raise last_exception

    async def retry_async(
        self,
        func: Callable[..., T],
        config: RetryConfig,
        *args,
        operation_name: Optional[str] = None,
        **kwargs,
    ) -> T:
        """
        Retry an asynchronous function with the given configuration.

        Args:
            func: Async function to retry
            config: Retry configuration
            *args: Function arguments
            operation_name: Name for circuit breaker and logging
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            Exception: The last exception if all retries fail
        """
        operation_name = operation_name or func.__name__
        circuit_breaker = self.circuit_breakers.get(operation_name)

        # Check circuit breaker
        if circuit_breaker and not circuit_breaker.can_execute():
            raise TuyaError(
                f"Circuit breaker is open for operation '{operation_name}'",
                error_code="CIRCUIT_BREAKER_OPEN",
                retryable=False,
            )

        # Get backoff calculator
        backoff_calculator = self.backoff_calculators.get(config.backoff_strategy)
        if not backoff_calculator:
            backoff_calculator = self.backoff_calculators[BackoffStrategy.EXPONENTIAL]

        last_exception = None

        for attempt in range(config.max_attempts):
            try:
                # Execute with timeout
                if config.timeout:
                    result = await asyncio.wait_for(
                        func(*args, **kwargs), timeout=config.timeout
                    )
                else:
                    result = await func(*args, **kwargs)

                # Record success
                if circuit_breaker:
                    circuit_breaker.record_success()

                logger.debug(
                    f"Operation '{operation_name}' succeeded on attempt {attempt + 1}"
                )
                return result

            except Exception as e:
                last_exception = e

                # Check if error is retryable
                if not self._is_retryable(e, config):
                    logger.debug(
                        f"Operation '{operation_name}' failed with non-retryable error: {e}"
                    )
                    if circuit_breaker:
                        circuit_breaker.record_failure()
                    raise

                # Record failure
                if circuit_breaker:
                    circuit_breaker.record_failure()

                # Log attempt
                logger.debug(
                    f"Operation '{operation_name}' failed on attempt {attempt + 1}: {e}"
                )

                # Calculate delay if not the last attempt
                if attempt < config.max_attempts - 1:
                    delay = backoff_calculator.calculate_delay(
                        attempt, config.base_delay, config.max_delay
                    )
                    logger.debug(
                        f"Retrying operation '{operation_name}' in {delay:.2f}s"
                    )
                    await asyncio.sleep(delay)

        # All attempts failed
        logger.error(
            f"Operation '{operation_name}' failed after {config.max_attempts} attempts"
        )
        raise last_exception

    def _is_retryable(self, error: Exception, config: RetryConfig) -> bool:
        """Check if an error is retryable based on configuration."""
        # Check custom retryable exceptions
        if config.retryable_exceptions:
            if any(
                isinstance(error, exc_type) for exc_type in config.retryable_exceptions
            ):
                return True

        # Use global retryable check
        return is_retryable_error(error)

    def get_retry_stats(self) -> Dict[str, Any]:
        """Get retry statistics."""
        stats = {
            "circuit_breakers": {},
            "total_circuit_breakers": len(self.circuit_breakers),
        }

        for name, breaker in self.circuit_breakers.items():
            stats["circuit_breakers"][name] = {
                "state": breaker.state.value,
                "failure_count": breaker.failure_count,
                "success_count": breaker.success_count,
                "last_failure_time": breaker.last_failure_time,
                "next_attempt_time": breaker.next_attempt_time,
            }

        return stats


# Pre-configured retry configurations for common operations
RETRY_CONFIGS = {
    "authentication": RetryConfig(
        max_attempts=3,
        base_delay=2.0,
        max_delay=30.0,
        backoff_strategy=BackoffStrategy.EXPONENTIAL,
        timeout=30.0,
    ),
    "device_discovery": RetryConfig(
        max_attempts=5,
        base_delay=1.0,
        max_delay=10.0,
        backoff_strategy=BackoffStrategy.LINEAR,
        timeout=15.0,
    ),
    "device_connection": RetryConfig(
        max_attempts=3,
        base_delay=1.0,
        max_delay=20.0,
        backoff_strategy=BackoffStrategy.EXPONENTIAL,
        timeout=10.0,
    ),
    "device_command": RetryConfig(
        max_attempts=2,
        base_delay=0.5,
        max_delay=5.0,
        backoff_strategy=BackoffStrategy.EXPONENTIAL,
        timeout=5.0,
    ),
    "network_operation": RetryConfig(
        max_attempts=3,
        base_delay=1.0,
        max_delay=15.0,
        backoff_strategy=BackoffStrategy.EXPONENTIAL,
        timeout=10.0,
    ),
}

# Pre-configured circuit breaker configurations
CIRCUIT_BREAKER_CONFIGS = {
    "device_connection": CircuitBreakerConfig(
        failure_threshold=3, recovery_timeout=30.0, success_threshold=2, timeout=10.0
    ),
    "authentication": CircuitBreakerConfig(
        failure_threshold=5, recovery_timeout=60.0, success_threshold=3, timeout=30.0
    ),
    "device_command": CircuitBreakerConfig(
        failure_threshold=2, recovery_timeout=10.0, success_threshold=1, timeout=5.0
    ),
}

# Global retry manager instance
default_retry_manager = RetryManager()

# Add default circuit breakers
for name, config in CIRCUIT_BREAKER_CONFIGS.items():
    default_retry_manager.add_circuit_breaker(name, config)


def retry(
    config: Optional[RetryConfig] = None,
    operation_name: Optional[str] = None,
    config_name: Optional[str] = None,
):
    """
    Decorator for retrying functions.

    Args:
        config: Retry configuration
        operation_name: Name for circuit breaker and logging
        config_name: Name of pre-configured retry config

    Returns:
        Decorated function
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            retry_config = config
            if config_name and config_name in RETRY_CONFIGS:
                retry_config = RETRY_CONFIGS[config_name]
            if not retry_config:
                retry_config = RETRY_CONFIGS["network_operation"]

            return default_retry_manager.retry_sync(
                func, retry_config, *args, operation_name=operation_name, **kwargs
            )

        return wrapper

    return decorator


def async_retry(
    config: Optional[RetryConfig] = None,
    operation_name: Optional[str] = None,
    config_name: Optional[str] = None,
):
    """
    Decorator for retrying async functions.

    Args:
        config: Retry configuration
        operation_name: Name for circuit breaker and logging
        config_name: Name of pre-configured retry config

    Returns:
        Decorated async function
    """

    def decorator(func):
        async def wrapper(*args, **kwargs):
            retry_config = config
            if config_name and config_name in RETRY_CONFIGS:
                retry_config = RETRY_CONFIGS[config_name]
            if not retry_config:
                retry_config = RETRY_CONFIGS["network_operation"]

            return await default_retry_manager.retry_async(
                func, retry_config, *args, operation_name=operation_name, **kwargs
            )

        return wrapper

    return decorator
