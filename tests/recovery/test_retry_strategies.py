"""
Tests for libtuya retry strategies.

This module tests retry logic, backoff strategies, circuit breakers,
and timeout management.
"""

import asyncio
import pytest
import time
from unittest.mock import Mock, patch, AsyncMock

from libtuya.recovery.retry_strategies import (
    RetryConfig,
    BackoffStrategy,
    ExponentialBackoff,
    LinearBackoff,
    FixedBackoff,
    CustomBackoff,
    CircuitBreaker,
    CircuitBreakerState,
    CircuitBreakerConfig,
    TimeoutManager,
    RetryManager,
    default_retry_manager,
    retry,
    async_retry,
    RETRY_CONFIGS,
    CIRCUIT_BREAKER_CONFIGS
)
from libtuya.recovery.exceptions import TuyaError, NetworkError


class TestRetryConfig:
    """Test RetryConfig class."""
    
    def test_default_config(self):
        """Test default retry configuration."""
        config = RetryConfig()
        
        assert config.max_attempts == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0
        assert config.backoff_strategy == BackoffStrategy.EXPONENTIAL
        assert config.backoff_multiplier == 2.0
        assert config.jitter is True
        assert config.timeout is None
        assert config.retryable_exceptions is None
    
    def test_custom_config(self):
        """Test custom retry configuration."""
        config = RetryConfig(
            max_attempts=5,
            base_delay=2.0,
            max_delay=30.0,
            backoff_strategy=BackoffStrategy.LINEAR,
            backoff_multiplier=1.5,
            jitter=False,
            timeout=10.0,
            retryable_exceptions=[NetworkError]
        )
        
        assert config.max_attempts == 5
        assert config.base_delay == 2.0
        assert config.max_delay == 30.0
        assert config.backoff_strategy == BackoffStrategy.LINEAR
        assert config.backoff_multiplier == 1.5
        assert config.jitter is False
        assert config.timeout == 10.0
        assert config.retryable_exceptions == [NetworkError]


class TestBackoffCalculators:
    """Test backoff calculator classes."""
    
    def test_exponential_backoff(self):
        """Test exponential backoff calculation."""
        calculator = ExponentialBackoff(multiplier=2.0, jitter=False)
        
        assert calculator.calculate_delay(0, 1.0, 60.0) == 1.0
        assert calculator.calculate_delay(1, 1.0, 60.0) == 2.0
        assert calculator.calculate_delay(2, 1.0, 60.0) == 4.0
        assert calculator.calculate_delay(3, 1.0, 60.0) == 8.0
        
        # Test max delay
        assert calculator.calculate_delay(10, 1.0, 10.0) == 10.0
    
    def test_exponential_backoff_with_jitter(self):
        """Test exponential backoff with jitter."""
        calculator = ExponentialBackoff(multiplier=2.0, jitter=True)
        
        # With jitter, delay should be between 50% and 100% of calculated value
        delay = calculator.calculate_delay(1, 1.0, 60.0)
        assert 1.0 <= delay <= 2.0
    
    def test_linear_backoff(self):
        """Test linear backoff calculation."""
        calculator = LinearBackoff(increment=1.0, jitter=False)
        
        assert calculator.calculate_delay(0, 1.0, 60.0) == 1.0
        assert calculator.calculate_delay(1, 1.0, 60.0) == 2.0
        assert calculator.calculate_delay(2, 1.0, 60.0) == 3.0
        assert calculator.calculate_delay(3, 1.0, 60.0) == 4.0
        
        # Test max delay
        assert calculator.calculate_delay(100, 1.0, 5.0) == 5.0
    
    def test_linear_backoff_with_jitter(self):
        """Test linear backoff with jitter."""
        calculator = LinearBackoff(increment=1.0, jitter=True)
        
        # With jitter, delay should be between 80% and 120% of calculated value
        delay = calculator.calculate_delay(1, 1.0, 60.0)
        assert 1.6 <= delay <= 2.4
    
    def test_fixed_backoff(self):
        """Test fixed backoff calculation."""
        calculator = FixedBackoff(jitter=False)
        
        assert calculator.calculate_delay(0, 2.0, 60.0) == 2.0
        assert calculator.calculate_delay(1, 2.0, 60.0) == 2.0
        assert calculator.calculate_delay(10, 2.0, 60.0) == 2.0
    
    def test_fixed_backoff_with_jitter(self):
        """Test fixed backoff with jitter."""
        calculator = FixedBackoff(jitter=True)
        
        # With jitter, delay should be between 80% and 120% of base delay
        delay = calculator.calculate_delay(1, 2.0, 60.0)
        assert 1.6 <= delay <= 2.4
    
    def test_custom_backoff(self):
        """Test custom backoff calculation."""
        def custom_func(attempt, base_delay, max_delay):
            return min(base_delay * (attempt + 1), max_delay)
        
        calculator = CustomBackoff(custom_func)
        
        assert calculator.calculate_delay(0, 1.0, 60.0) == 1.0
        assert calculator.calculate_delay(1, 1.0, 60.0) == 2.0
        assert calculator.calculate_delay(2, 1.0, 60.0) == 3.0


class TestCircuitBreaker:
    """Test circuit breaker functionality."""
    
    def test_circuit_breaker_initial_state(self):
        """Test circuit breaker initial state."""
        config = CircuitBreakerConfig()
        breaker = CircuitBreaker(config)
        
        assert breaker.state == CircuitBreakerState.CLOSED
        assert breaker.failure_count == 0
        assert breaker.success_count == 0
        assert breaker.can_execute() is True
    
    def test_circuit_breaker_failure_threshold(self):
        """Test circuit breaker failure threshold."""
        config = CircuitBreakerConfig(failure_threshold=3)
        breaker = CircuitBreaker(config)
        
        # Record failures
        for i in range(2):
            breaker.record_failure()
            assert breaker.state == CircuitBreakerState.CLOSED
            assert breaker.can_execute() is True
        
        # Third failure should open the circuit
        breaker.record_failure()
        assert breaker.state == CircuitBreakerState.OPEN
        assert breaker.can_execute() is False
    
    def test_circuit_breaker_recovery(self):
        """Test circuit breaker recovery."""
        config = CircuitBreakerConfig(
            failure_threshold=2,
            recovery_timeout=0.1,
            success_threshold=2
        )
        breaker = CircuitBreaker(config)
        
        # Open the circuit
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitBreakerState.OPEN
        
        # Wait for recovery timeout
        time.sleep(0.2)
        
        # Should be able to execute (half-open state)
        assert breaker.can_execute() is True
        assert breaker.state == CircuitBreakerState.HALF_OPEN
        
        # Record success
        breaker.record_success()
        assert breaker.state == CircuitBreakerState.HALF_OPEN
        
        # Second success should close the circuit
        breaker.record_success()
        assert breaker.state == CircuitBreakerState.CLOSED
    
    def test_circuit_breaker_half_open_failure(self):
        """Test circuit breaker failure in half-open state."""
        config = CircuitBreakerConfig(
            failure_threshold=2,
            recovery_timeout=0.1
        )
        breaker = CircuitBreaker(config)
        
        # Open the circuit
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitBreakerState.OPEN
        
        # Wait for recovery timeout
        time.sleep(0.2)
        
        # Should be in half-open state
        assert breaker.can_execute() is True
        assert breaker.state == CircuitBreakerState.HALF_OPEN
        
        # Record failure - should go back to open
        breaker.record_failure()
        assert breaker.state == CircuitBreakerState.OPEN
        assert breaker.can_execute() is False
    
    def test_circuit_breaker_reset(self):
        """Test circuit breaker reset."""
        config = CircuitBreakerConfig(failure_threshold=2)
        breaker = CircuitBreaker(config)
        
        # Open the circuit
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitBreakerState.OPEN
        
        # Reset the circuit
        breaker.reset()
        assert breaker.state == CircuitBreakerState.CLOSED
        assert breaker.failure_count == 0
        assert breaker.success_count == 0
        assert breaker.can_execute() is True


class TestTimeoutManager:
    """Test timeout manager functionality."""
    
    def test_timeout_manager_default(self):
        """Test timeout manager with default timeout."""
        manager = TimeoutManager(default_timeout=10.0)
        
        assert manager.get_timeout("test_operation") == 10.0
    
    def test_timeout_manager_custom_timeout(self):
        """Test timeout manager with custom timeout."""
        manager = TimeoutManager(default_timeout=10.0)
        manager.set_timeout("test_operation", 5.0)
        
        assert manager.get_timeout("test_operation") == 5.0
        assert manager.get_timeout("other_operation") == 10.0
    
    def test_timeout_context(self):
        """Test timeout context manager."""
        manager = TimeoutManager(default_timeout=10.0)
        
        with manager.timeout_context("test_operation") as timeout:
            assert timeout == 10.0
        
        # Set custom timeout
        manager.set_timeout("test_operation", 5.0)
        
        with manager.timeout_context("test_operation") as timeout:
            assert timeout == 5.0


class TestRetryManager:
    """Test retry manager functionality."""
    
    def test_retry_manager_success(self):
        """Test retry manager with successful function."""
        manager = RetryManager()
        config = RetryConfig(max_attempts=3)
        
        mock_func = Mock(return_value="success")
        result = manager.retry_sync(mock_func, config)
        
        assert result == "success"
        assert mock_func.call_count == 1
    
    def test_retry_manager_failure_then_success(self):
        """Test retry manager with failure then success."""
        manager = RetryManager()
        config = RetryConfig(max_attempts=3, base_delay=0.01)
        
        mock_func = Mock(side_effect=[NetworkError("Network error"), "success"])
        result = manager.retry_sync(mock_func, config)
        
        assert result == "success"
        assert mock_func.call_count == 2
    
    def test_retry_manager_all_failures(self):
        """Test retry manager with all failures."""
        manager = RetryManager()
        config = RetryConfig(max_attempts=3, base_delay=0.01)
        
        mock_func = Mock(side_effect=NetworkError("Network error"))
        
        with pytest.raises(NetworkError):
            manager.retry_sync(mock_func, config)
        
        assert mock_func.call_count == 3
    
    def test_retry_manager_non_retryable_error(self):
        """Test retry manager with non-retryable error."""
        manager = RetryManager()
        config = RetryConfig(max_attempts=3)
        
        mock_func = Mock(side_effect=TuyaError("Non-retryable", retryable=False))
        
        with pytest.raises(TuyaError):
            manager.retry_sync(mock_func, config)
        
        assert mock_func.call_count == 1
    
    def test_retry_manager_with_circuit_breaker(self):
        """Test retry manager with circuit breaker."""
        manager = RetryManager()
        breaker_config = CircuitBreakerConfig(failure_threshold=2)
        manager.add_circuit_breaker("test_op", breaker_config)
        
        config = RetryConfig(max_attempts=3, base_delay=0.01)
        mock_func = Mock(side_effect=NetworkError("Network error"))
        
        # First few calls should work
        with pytest.raises(NetworkError):
            manager.retry_sync(mock_func, config, operation_name="test_op")
        
        # Should fail due to circuit breaker
        with pytest.raises(TuyaError) as exc_info:
            manager.retry_sync(mock_func, config, operation_name="test_op")
        
        assert "circuit breaker" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_retry_manager_async_success(self):
        """Test retry manager with async successful function."""
        manager = RetryManager()
        config = RetryConfig(max_attempts=3)
        
        mock_func = AsyncMock(return_value="success")
        result = await manager.retry_async(mock_func, config)
        
        assert result == "success"
        assert mock_func.call_count == 1
    
    @pytest.mark.asyncio
    async def test_retry_manager_async_failure_then_success(self):
        """Test retry manager with async failure then success."""
        manager = RetryManager()
        config = RetryConfig(max_attempts=3, base_delay=0.01)
        
        mock_func = AsyncMock(side_effect=[NetworkError("Network error"), "success"])
        result = await manager.retry_async(mock_func, config)
        
        assert result == "success"
        assert mock_func.call_count == 2
    
    @pytest.mark.asyncio
    async def test_retry_manager_async_timeout(self):
        """Test retry manager with async timeout."""
        manager = RetryManager()
        config = RetryConfig(max_attempts=2, timeout=0.1)
        
        async def slow_func():
            await asyncio.sleep(0.2)
            return "success"
        
        with pytest.raises(asyncio.TimeoutError):
            await manager.retry_async(slow_func, config)
    
    def test_retry_manager_stats(self):
        """Test retry manager statistics."""
        manager = RetryManager()
        breaker_config = CircuitBreakerConfig()
        manager.add_circuit_breaker("test_op", breaker_config)
        
        stats = manager.get_retry_stats()
        
        assert "circuit_breakers" in stats
        assert "total_circuit_breakers" in stats
        assert stats["total_circuit_breakers"] == 1
        assert "test_op" in stats["circuit_breakers"]


class TestRetryDecorators:
    """Test retry decorators."""
    
    def test_retry_decorator_success(self):
        """Test retry decorator with successful function."""
        @retry(config=RetryConfig(max_attempts=3))
        def test_func():
            return "success"
        
        result = test_func()
        assert result == "success"
    
    def test_retry_decorator_with_config_name(self):
        """Test retry decorator with config name."""
        @retry(config_name="network_operation")
        def test_func():
            return "success"
        
        result = test_func()
        assert result == "success"
    
    def test_retry_decorator_failure_then_success(self):
        """Test retry decorator with failure then success."""
        call_count = 0
        
        @retry(config=RetryConfig(max_attempts=3, base_delay=0.01))
        def test_func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise NetworkError("Network error")
            return "success"
        
        result = test_func()
        assert result == "success"
        assert call_count == 2
    
    @pytest.mark.asyncio
    async def test_async_retry_decorator_success(self):
        """Test async retry decorator with successful function."""
        @async_retry(config=RetryConfig(max_attempts=3))
        async def test_func():
            return "success"
        
        result = await test_func()
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_async_retry_decorator_failure_then_success(self):
        """Test async retry decorator with failure then success."""
        call_count = 0
        
        @async_retry(config=RetryConfig(max_attempts=3, base_delay=0.01))
        async def test_func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise NetworkError("Network error")
            return "success"
        
        result = await test_func()
        assert result == "success"
        assert call_count == 2


class TestRetryConfigs:
    """Test pre-configured retry configurations."""
    
    def test_retry_configs_exist(self):
        """Test that pre-configured retry configs exist."""
        assert "authentication" in RETRY_CONFIGS
        assert "device_discovery" in RETRY_CONFIGS
        assert "device_connection" in RETRY_CONFIGS
        assert "device_command" in RETRY_CONFIGS
        assert "network_operation" in RETRY_CONFIGS
    
    def test_circuit_breaker_configs_exist(self):
        """Test that pre-configured circuit breaker configs exist."""
        assert "device_connection" in CIRCUIT_BREAKER_CONFIGS
        assert "authentication" in CIRCUIT_BREAKER_CONFIGS
        assert "device_command" in CIRCUIT_BREAKER_CONFIGS
    
    def test_default_retry_manager_has_circuit_breakers(self):
        """Test that default retry manager has circuit breakers."""
        stats = default_retry_manager.get_retry_stats()
        assert stats["total_circuit_breakers"] > 0
        assert "device_connection" in stats["circuit_breakers"]
        assert "authentication" in stats["circuit_breakers"]
        assert "device_command" in stats["circuit_breakers"]


if __name__ == "__main__":
    pytest.main([__file__])