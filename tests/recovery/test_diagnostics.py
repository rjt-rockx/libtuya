"""
Tests for libtuya diagnostics and health monitoring.

This module tests all diagnostic components and health monitoring
functionality.
"""

import asyncio
import pytest
import time
from unittest.mock import Mock, patch, AsyncMock, MagicMock

from libtuya.recovery.diagnostics import (
    HealthStatus,
    DiagnosticResult,
    BaseDiagnostic,
    NetworkDiagnostics,
    DeviceDiagnostics,
    AuthenticationDiagnostics,
    SystemDiagnostics,
    HealthMonitor,
    default_health_monitor
)


class TestHealthStatus:
    """Test HealthStatus enum."""
    
    def test_health_status_values(self):
        """Test health status values."""
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.WARNING.value == "warning"
        assert HealthStatus.CRITICAL.value == "critical"
        assert HealthStatus.UNKNOWN.value == "unknown"


class TestDiagnosticResult:
    """Test DiagnosticResult class."""
    
    def test_diagnostic_result_creation(self):
        """Test diagnostic result creation."""
        result = DiagnosticResult(
            check_name="test_check",
            status=HealthStatus.HEALTHY,
            message="All good",
            details={"key": "value"},
            timestamp=time.time(),
            duration=1.5,
            recommendations=["Keep monitoring"]
        )
        
        assert result.check_name == "test_check"
        assert result.status == HealthStatus.HEALTHY
        assert result.message == "All good"
        assert result.details == {"key": "value"}
        assert result.recommendations == ["Keep monitoring"]
        assert result.duration == 1.5
    
    def test_diagnostic_result_defaults(self):
        """Test diagnostic result with defaults."""
        result = DiagnosticResult(
            check_name="test_check",
            status=HealthStatus.HEALTHY,
            message="All good",
            details=None,
            timestamp=time.time(),
            duration=1.5,
            recommendations=None
        )
        
        assert result.details == {}
        assert result.recommendations == []


class TestBaseDiagnostic:
    """Test BaseDiagnostic functionality."""
    
    def test_base_diagnostic_abstract(self):
        """Test that BaseDiagnostic is abstract."""
        with pytest.raises(TypeError):
            BaseDiagnostic("test")
    
    def test_base_diagnostic_initialization(self):
        """Test BaseDiagnostic initialization."""
        class TestDiagnostic(BaseDiagnostic):
            async def run_check(self):
                return DiagnosticResult(
                    check_name=self.name,
                    status=HealthStatus.HEALTHY,
                    message="Test successful",
                    details={},
                    timestamp=0,
                    duration=0,
                    recommendations=[]
                )
        
        diagnostic = TestDiagnostic("test_diagnostic", timeout=15.0)
        
        assert diagnostic.name == "test_diagnostic"
        assert diagnostic.timeout == 15.0
        assert diagnostic.last_result is None
        assert diagnostic.run_count == 0
        assert diagnostic.failure_count == 0
    
    @pytest.mark.asyncio
    async def test_base_diagnostic_successful_run(self):
        """Test successful diagnostic run."""
        class TestDiagnostic(BaseDiagnostic):
            async def run_check(self):
                return DiagnosticResult(
                    check_name=self.name,
                    status=HealthStatus.HEALTHY,
                    message="Test successful",
                    details={},
                    timestamp=0,
                    duration=0,
                    recommendations=[]
                )
        
        diagnostic = TestDiagnostic("test_diagnostic")
        result = await diagnostic.run()
        
        assert result.status == HealthStatus.HEALTHY
        assert result.message == "Test successful"
        assert diagnostic.run_count == 1
        assert diagnostic.failure_count == 0
        assert diagnostic.last_result == result
    
    @pytest.mark.asyncio
    async def test_base_diagnostic_failed_run(self):
        """Test failed diagnostic run."""
        class TestDiagnostic(BaseDiagnostic):
            async def run_check(self):
                return DiagnosticResult(
                    check_name=self.name,
                    status=HealthStatus.CRITICAL,
                    message="Test failed",
                    details={},
                    timestamp=0,
                    duration=0,
                    recommendations=[]
                )
        
        diagnostic = TestDiagnostic("test_diagnostic")
        result = await diagnostic.run()
        
        assert result.status == HealthStatus.CRITICAL
        assert result.message == "Test failed"
        assert diagnostic.run_count == 1
        assert diagnostic.failure_count == 1
    
    @pytest.mark.asyncio
    async def test_base_diagnostic_timeout(self):
        """Test diagnostic timeout."""
        class TestDiagnostic(BaseDiagnostic):
            async def run_check(self):
                await asyncio.sleep(0.2)
                return DiagnosticResult(
                    check_name=self.name,
                    status=HealthStatus.HEALTHY,
                    message="Test successful",
                    details={},
                    timestamp=0,
                    duration=0,
                    recommendations=[]
                )
        
        diagnostic = TestDiagnostic("test_diagnostic", timeout=0.1)
        result = await diagnostic.run()
        
        assert result.status == HealthStatus.CRITICAL
        assert "timeout" in result.message.lower()
        assert diagnostic.run_count == 1
        assert diagnostic.failure_count == 1
    
    @pytest.mark.asyncio
    async def test_base_diagnostic_exception(self):
        """Test diagnostic exception handling."""
        class TestDiagnostic(BaseDiagnostic):
            async def run_check(self):
                raise ValueError("Test exception")
        
        diagnostic = TestDiagnostic("test_diagnostic")
        result = await diagnostic.run()
        
        assert result.status == HealthStatus.CRITICAL
        assert "failed" in result.message.lower()
        assert "ValueError" in result.details["error_type"]
        assert diagnostic.run_count == 1
        assert diagnostic.failure_count == 1
    
    def test_base_diagnostic_stats(self):
        """Test diagnostic statistics."""
        class TestDiagnostic(BaseDiagnostic):
            async def run_check(self):
                return DiagnosticResult(
                    check_name=self.name,
                    status=HealthStatus.HEALTHY,
                    message="Test successful",
                    details={},
                    timestamp=0,
                    duration=0,
                    recommendations=[]
                )
        
        diagnostic = TestDiagnostic("test_diagnostic")
        diagnostic.run_count = 10
        diagnostic.failure_count = 3
        diagnostic.last_result = DiagnosticResult(
            check_name="test_diagnostic",
            status=HealthStatus.WARNING,
            message="Test warning",
            details={},
            timestamp=time.time(),
            duration=0,
            recommendations=[]
        )
        
        stats = diagnostic.get_stats()
        
        assert stats["name"] == "test_diagnostic"
        assert stats["run_count"] == 10
        assert stats["failure_count"] == 3
        assert stats["success_rate"] == 0.7
        assert stats["last_status"] == "warning"
        assert stats["last_run"] is not None


class TestNetworkDiagnostics:
    """Test NetworkDiagnostics class."""
    
    def test_network_diagnostics_initialization(self):
        """Test NetworkDiagnostics initialization."""
        diagnostic = NetworkDiagnostics()
        
        assert diagnostic.name == "Network"
        assert len(diagnostic.test_hosts) > 0
        assert "8.8.8.8" in diagnostic.test_hosts
        assert "openapi.tuyacn.com" in diagnostic.test_hosts
    
    @pytest.mark.asyncio
    async def test_network_diagnostics_run_check(self):
        """Test NetworkDiagnostics run_check method."""
        diagnostic = NetworkDiagnostics()
        
        # Mock all the check methods
        with patch.object(diagnostic, '_check_connectivity') as mock_connectivity, \
             patch.object(diagnostic, '_check_dns_resolution') as mock_dns, \
             patch.object(diagnostic, '_check_latency') as mock_latency, \
             patch.object(diagnostic, '_check_tuya_endpoints') as mock_tuya:
            
            mock_connectivity.return_value = {"internet_available": True}
            mock_dns.return_value = {"failures": 0}
            mock_latency.return_value = {"average_latency": 50}
            mock_tuya.return_value = {"failures": 0}
            
            result = await diagnostic.run_check()
            
            assert result.status == HealthStatus.HEALTHY
            assert "connectivity" in result.details
            assert "dns" in result.details
            assert "latency" in result.details
            assert "tuya_endpoints" in result.details
    
    @pytest.mark.asyncio
    async def test_network_diagnostics_no_internet(self):
        """Test NetworkDiagnostics with no internet."""
        diagnostic = NetworkDiagnostics()
        
        with patch.object(diagnostic, '_check_connectivity') as mock_connectivity, \
             patch.object(diagnostic, '_check_dns_resolution') as mock_dns, \
             patch.object(diagnostic, '_check_latency') as mock_latency, \
             patch.object(diagnostic, '_check_tuya_endpoints') as mock_tuya:
            
            mock_connectivity.return_value = {"internet_available": False}
            mock_dns.return_value = {"failures": 0}
            mock_latency.return_value = {"average_latency": 50}
            mock_tuya.return_value = {"failures": 0}
            
            result = await diagnostic.run_check()
            
            assert result.status == HealthStatus.CRITICAL
            assert "internet connection" in result.recommendations[0].lower()
    
    @pytest.mark.asyncio
    async def test_network_diagnostics_high_latency(self):
        """Test NetworkDiagnostics with high latency."""
        diagnostic = NetworkDiagnostics()
        
        with patch.object(diagnostic, '_check_connectivity') as mock_connectivity, \
             patch.object(diagnostic, '_check_dns_resolution') as mock_dns, \
             patch.object(diagnostic, '_check_latency') as mock_latency, \
             patch.object(diagnostic, '_check_tuya_endpoints') as mock_tuya:
            
            mock_connectivity.return_value = {"internet_available": True}
            mock_dns.return_value = {"failures": 0}
            mock_latency.return_value = {"average_latency": 1500}
            mock_tuya.return_value = {"failures": 0}
            
            result = await diagnostic.run_check()
            
            assert result.status == HealthStatus.WARNING
            assert any("latency" in rec.lower() for rec in result.recommendations)
    
    @pytest.mark.asyncio
    async def test_check_connectivity(self):
        """Test connectivity check."""
        diagnostic = NetworkDiagnostics()
        
        with patch('socket.socket') as mock_socket_class:
            mock_socket = Mock()
            mock_socket_class.return_value = mock_socket
            mock_socket.connect_ex.return_value = 0  # Success
            
            result = await diagnostic._check_connectivity()
            
            assert result["internet_available"] is True
            assert len(result["reachable_hosts"]) > 0
    
    @pytest.mark.asyncio
    async def test_check_dns_resolution(self):
        """Test DNS resolution check."""
        diagnostic = NetworkDiagnostics()
        
        with patch('socket.gethostbyname') as mock_gethostbyname:
            mock_gethostbyname.return_value = "1.2.3.4"
            
            result = await diagnostic._check_dns_resolution()
            
            assert result["successful_resolutions"] > 0
            assert result["failures"] == 0
    
    @pytest.mark.asyncio
    async def test_check_tuya_endpoints(self):
        """Test Tuya endpoints check."""
        diagnostic = NetworkDiagnostics()
        
        with patch('socket.socket') as mock_socket_class:
            mock_socket = Mock()
            mock_socket_class.return_value = mock_socket
            mock_socket.connect_ex.return_value = 0  # Success
            
            result = await diagnostic._check_tuya_endpoints()
            
            assert len(result["reachable_endpoints"]) > 0
            assert result["failures"] == 0
    
    def test_parse_ping_output(self):
        """Test ping output parsing."""
        diagnostic = NetworkDiagnostics()
        
        # Test Linux ping output
        linux_output = """
        PING 8.8.8.8 (8.8.8.8) 56(84) bytes of data.
        64 bytes from 8.8.8.8: icmp_seq=1 ttl=117 time=12.3 ms
        64 bytes from 8.8.8.8: icmp_seq=2 ttl=117 time=11.8 ms
        64 bytes from 8.8.8.8: icmp_seq=3 ttl=117 time=13.1 ms
        
        --- 8.8.8.8 ping statistics ---
        3 packets transmitted, 3 received, 0% packet loss, time 2004ms
        rtt min/avg/max/mdev = 11.8/12.4/13.1/0.6 ms
        """
        
        latency = diagnostic._parse_ping_output(linux_output)
        assert latency == 12.4
        
        # Test individual ping line
        ping_line = "64 bytes from 8.8.8.8: icmp_seq=1 ttl=117 time=15.5 ms"
        latency = diagnostic._parse_ping_output(ping_line)
        assert latency == 15.5


class TestDeviceDiagnostics:
    """Test DeviceDiagnostics class."""
    
    def test_device_diagnostics_initialization(self):
        """Test DeviceDiagnostics initialization."""
        diagnostic = DeviceDiagnostics()
        
        assert diagnostic.name == "Device"
        assert len(diagnostic.devices_to_check) == 0
    
    def test_add_device(self):
        """Test adding device to diagnostics."""
        diagnostic = DeviceDiagnostics()
        
        diagnostic.add_device("DEV123", "192.168.1.100", "KEY123")
        
        assert len(diagnostic.devices_to_check) == 1
        assert diagnostic.devices_to_check[0]["device_id"] == "DEV123"
        assert diagnostic.devices_to_check[0]["device_ip"] == "192.168.1.100"
        assert diagnostic.devices_to_check[0]["local_key"] == "KEY123"
    
    @pytest.mark.asyncio
    async def test_device_diagnostics_no_devices(self):
        """Test DeviceDiagnostics with no devices."""
        diagnostic = DeviceDiagnostics()
        
        result = await diagnostic.run_check()
        
        assert result.status == HealthStatus.UNKNOWN
        assert "no devices" in result.message.lower()
        assert result.details["device_count"] == 0
    
    @pytest.mark.asyncio
    async def test_device_diagnostics_with_devices(self):
        """Test DeviceDiagnostics with devices."""
        diagnostic = DeviceDiagnostics()
        diagnostic.add_device("DEV123", "192.168.1.100", "KEY123")
        
        with patch.object(diagnostic, '_check_device_reachability') as mock_reach, \
             patch.object(diagnostic, '_check_protocol_versions') as mock_proto, \
             patch.object(diagnostic, '_check_device_responsiveness') as mock_resp:
            
            mock_reach.return_value = {"unreachable_devices": []}
            mock_proto.return_value = {"version_failures": []}
            mock_resp.return_value = {"unresponsive_devices": []}
            
            result = await diagnostic.run_check()
            
            assert result.status == HealthStatus.HEALTHY
            assert "1/1 devices healthy" in result.message
    
    @pytest.mark.asyncio
    async def test_device_diagnostics_unreachable_devices(self):
        """Test DeviceDiagnostics with unreachable devices."""
        diagnostic = DeviceDiagnostics()
        diagnostic.add_device("DEV123", "192.168.1.100", "KEY123")
        
        with patch.object(diagnostic, '_check_device_reachability') as mock_reach, \
             patch.object(diagnostic, '_check_protocol_versions') as mock_proto, \
             patch.object(diagnostic, '_check_device_responsiveness') as mock_resp:
            
            mock_reach.return_value = {"unreachable_devices": ["DEV123"]}
            mock_proto.return_value = {"version_failures": []}
            mock_resp.return_value = {"unresponsive_devices": []}
            
            result = await diagnostic.run_check()
            
            assert result.status == HealthStatus.CRITICAL
            assert "unreachable" in result.recommendations[0].lower()
    
    @pytest.mark.asyncio
    async def test_check_device_reachability(self):
        """Test device reachability check."""
        diagnostic = DeviceDiagnostics()
        diagnostic.add_device("DEV123", "192.168.1.100", "KEY123")
        
        with patch('socket.socket') as mock_socket_class:
            mock_socket = Mock()
            mock_socket_class.return_value = mock_socket
            mock_socket.connect_ex.return_value = 0  # Success
            
            result = await diagnostic._check_device_reachability()
            
            assert "DEV123" in result["reachable_devices"]
            assert len(result["unreachable_devices"]) == 0
    
    @pytest.mark.asyncio
    async def test_check_protocol_versions(self):
        """Test protocol version check."""
        diagnostic = DeviceDiagnostics()
        diagnostic.add_device("DEV123", "192.168.1.100", "KEY123")
        
        result = await diagnostic._check_protocol_versions()
        
        # This is a placeholder implementation
        assert "DEV123" in result["detected_versions"]
        assert result["detected_versions"]["DEV123"] == "3.3"
    
    @pytest.mark.asyncio
    async def test_check_device_responsiveness(self):
        """Test device responsiveness check."""
        diagnostic = DeviceDiagnostics()
        diagnostic.add_device("DEV123", "192.168.1.100", "KEY123")
        
        result = await diagnostic._check_device_responsiveness()
        
        # This is a placeholder implementation
        assert "DEV123" in result["responsive_devices"]
        assert result["response_times"]["DEV123"] == 100


class TestAuthenticationDiagnostics:
    """Test AuthenticationDiagnostics class."""
    
    def test_authentication_diagnostics_initialization(self):
        """Test AuthenticationDiagnostics initialization."""
        diagnostic = AuthenticationDiagnostics()
        
        assert diagnostic.name == "Authentication"
        assert diagnostic.auth_manager is None
    
    def test_set_auth_manager(self):
        """Test setting authentication manager."""
        diagnostic = AuthenticationDiagnostics()
        auth_manager = Mock()
        
        diagnostic.set_auth_manager(auth_manager)
        
        assert diagnostic.auth_manager == auth_manager
    
    @pytest.mark.asyncio
    async def test_authentication_diagnostics_no_manager(self):
        """Test AuthenticationDiagnostics with no manager."""
        diagnostic = AuthenticationDiagnostics()
        
        result = await diagnostic.run_check()
        
        assert result.status == HealthStatus.UNKNOWN
        assert "no authentication manager" in result.message.lower()
    
    @pytest.mark.asyncio
    async def test_authentication_diagnostics_with_manager(self):
        """Test AuthenticationDiagnostics with manager."""
        diagnostic = AuthenticationDiagnostics()
        diagnostic.set_auth_manager(Mock())
        
        with patch.object(diagnostic, '_check_token_validity') as mock_token, \
             patch.object(diagnostic, '_check_api_connectivity') as mock_api, \
             patch.object(diagnostic, '_check_session_health') as mock_session:
            
            mock_token.return_value = {"valid": True, "expires_soon": False}
            mock_api.return_value = {"api_reachable": True}
            mock_session.return_value = {"session_errors": 0}
            
            result = await diagnostic.run_check()
            
            assert result.status == HealthStatus.HEALTHY
            assert "healthy" in result.message.lower()
    
    @pytest.mark.asyncio
    async def test_authentication_diagnostics_invalid_token(self):
        """Test AuthenticationDiagnostics with invalid token."""
        diagnostic = AuthenticationDiagnostics()
        diagnostic.set_auth_manager(Mock())
        
        with patch.object(diagnostic, '_check_token_validity') as mock_token, \
             patch.object(diagnostic, '_check_api_connectivity') as mock_api, \
             patch.object(diagnostic, '_check_session_health') as mock_session:
            
            mock_token.return_value = {"valid": False, "expires_soon": False}
            mock_api.return_value = {"api_reachable": True}
            mock_session.return_value = {"session_errors": 0}
            
            result = await diagnostic.run_check()
            
            assert result.status == HealthStatus.CRITICAL
            assert "invalid" in result.recommendations[0].lower()
    
    @pytest.mark.asyncio
    async def test_check_token_validity(self):
        """Test token validity check."""
        diagnostic = AuthenticationDiagnostics()
        diagnostic.set_auth_manager(Mock())
        
        result = await diagnostic._check_token_validity()
        
        # This is a placeholder implementation
        assert result["valid"] is True
        assert result["token_type"] == "bearer"
        assert result["expires_at"] is not None
    
    @pytest.mark.asyncio
    async def test_check_api_connectivity(self):
        """Test API connectivity check."""
        diagnostic = AuthenticationDiagnostics()
        diagnostic.set_auth_manager(Mock())
        
        result = await diagnostic._check_api_connectivity()
        
        # This is a placeholder implementation
        assert result["api_reachable"] is True
        assert result["response_time"] == 200
        assert result["api_version"] == "1.0"
    
    @pytest.mark.asyncio
    async def test_check_session_health(self):
        """Test session health check."""
        diagnostic = AuthenticationDiagnostics()
        diagnostic.set_auth_manager(Mock())
        
        result = await diagnostic._check_session_health()
        
        # This is a placeholder implementation
        assert result["active_sessions"] == 1
        assert result["session_errors"] == 0
        assert result["last_activity"] is not None


class TestSystemDiagnostics:
    """Test SystemDiagnostics class."""
    
    def test_system_diagnostics_initialization(self):
        """Test SystemDiagnostics initialization."""
        diagnostic = SystemDiagnostics()
        
        assert diagnostic.name == "System"
        assert len(diagnostic.subsystem_diagnostics) == 0
    
    def test_add_subsystem(self):
        """Test adding subsystem diagnostic."""
        diagnostic = SystemDiagnostics()
        subsystem = Mock()
        
        diagnostic.add_subsystem(subsystem)
        
        assert len(diagnostic.subsystem_diagnostics) == 1
        assert diagnostic.subsystem_diagnostics[0] == subsystem
    
    @pytest.mark.asyncio
    async def test_system_diagnostics_run_check(self):
        """Test SystemDiagnostics run_check method."""
        diagnostic = SystemDiagnostics()
        
        with patch.object(diagnostic, '_check_system_resources') as mock_resources, \
             patch.object(diagnostic, '_check_python_environment') as mock_python, \
             patch.object(diagnostic, '_check_dependencies') as mock_deps, \
             patch.object(diagnostic, '_run_subsystem_diagnostics') as mock_subsystems:
            
            mock_resources.return_value = {"memory_usage": 50, "disk_usage": 70}
            mock_python.return_value = {"python_version": "3.9.0"}
            mock_deps.return_value = {"missing_dependencies": []}
            mock_subsystems.return_value = {}
            
            result = await diagnostic.run_check()
            
            assert result.status == HealthStatus.HEALTHY
            assert "system_resources" in result.details
            assert "python_environment" in result.details
            assert "dependencies" in result.details
            assert "subsystems" in result.details
    
    @pytest.mark.asyncio
    async def test_system_diagnostics_high_memory(self):
        """Test SystemDiagnostics with high memory usage."""
        diagnostic = SystemDiagnostics()
        
        with patch.object(diagnostic, '_check_system_resources') as mock_resources, \
             patch.object(diagnostic, '_check_python_environment') as mock_python, \
             patch.object(diagnostic, '_check_dependencies') as mock_deps, \
             patch.object(diagnostic, '_run_subsystem_diagnostics') as mock_subsystems:
            
            mock_resources.return_value = {"memory_usage": 95, "disk_usage": 70}
            mock_python.return_value = {"python_version": "3.9.0"}
            mock_deps.return_value = {"missing_dependencies": []}
            mock_subsystems.return_value = {}
            
            result = await diagnostic.run_check()
            
            assert result.status == HealthStatus.WARNING
            assert any("memory" in rec.lower() for rec in result.recommendations)
    
    @pytest.mark.asyncio
    async def test_system_diagnostics_missing_dependencies(self):
        """Test SystemDiagnostics with missing dependencies."""
        diagnostic = SystemDiagnostics()
        
        with patch.object(diagnostic, '_check_system_resources') as mock_resources, \
             patch.object(diagnostic, '_check_python_environment') as mock_python, \
             patch.object(diagnostic, '_check_dependencies') as mock_deps, \
             patch.object(diagnostic, '_run_subsystem_diagnostics') as mock_subsystems:
            
            mock_resources.return_value = {"memory_usage": 50, "disk_usage": 70}
            mock_python.return_value = {"python_version": "3.9.0"}
            mock_deps.return_value = {"missing_dependencies": ["missing_package"]}
            mock_subsystems.return_value = {}
            
            result = await diagnostic.run_check()
            
            assert result.status == HealthStatus.CRITICAL
            assert any("dependencies" in rec.lower() for rec in result.recommendations)
    
    @pytest.mark.asyncio
    async def test_check_system_resources(self):
        """Test system resources check."""
        diagnostic = SystemDiagnostics()
        
        # Test without psutil
        result = await diagnostic._check_system_resources()
        
        assert "error" in result
        assert "psutil" in result["error"]
    
    @pytest.mark.asyncio
    async def test_check_python_environment(self):
        """Test Python environment check."""
        diagnostic = SystemDiagnostics()
        
        result = await diagnostic._check_python_environment()
        
        assert "python_version" in result
        assert "platform" in result
        assert "architecture" in result
    
    @pytest.mark.asyncio
    async def test_check_dependencies(self):
        """Test dependencies check."""
        diagnostic = SystemDiagnostics()
        
        result = await diagnostic._check_dependencies()
        
        assert "installed_packages" in result
        assert "missing_dependencies" in result
        assert "version_conflicts" in result
        
        # Standard library modules should be installed
        assert "time" in result["installed_packages"]
        assert "logging" in result["installed_packages"]
    
    @pytest.mark.asyncio
    async def test_run_subsystem_diagnostics(self):
        """Test subsystem diagnostics run."""
        diagnostic = SystemDiagnostics()
        
        # Mock subsystem diagnostic
        mock_subsystem = Mock()
        mock_subsystem.name = "mock_subsystem"
        mock_result = Mock()
        mock_result.status = HealthStatus.HEALTHY
        mock_result.message = "Mock healthy"
        mock_result.recommendations = []
        mock_subsystem.run.return_value = mock_result
        
        diagnostic.add_subsystem(mock_subsystem)
        
        result = await diagnostic._run_subsystem_diagnostics()
        
        assert "mock_subsystem" in result
        assert result["mock_subsystem"]["status"] == "healthy"
        assert result["mock_subsystem"]["message"] == "Mock healthy"


class TestHealthMonitor:
    """Test HealthMonitor class."""
    
    def test_health_monitor_initialization(self):
        """Test HealthMonitor initialization."""
        monitor = HealthMonitor(check_interval=60.0)
        
        assert monitor.check_interval == 60.0
        assert len(monitor.diagnostics) == 4  # Default diagnostics
        assert monitor.monitoring_active is False
        assert len(monitor.health_history) == 0
    
    def test_add_diagnostic(self):
        """Test adding custom diagnostic."""
        monitor = HealthMonitor()
        initial_count = len(monitor.diagnostics)
        
        custom_diagnostic = Mock()
        monitor.add_diagnostic(custom_diagnostic)
        
        assert len(monitor.diagnostics) == initial_count + 1
        assert custom_diagnostic in monitor.diagnostics
    
    @pytest.mark.asyncio
    async def test_run_all_diagnostics(self):
        """Test running all diagnostics."""
        monitor = HealthMonitor()
        
        # Mock all diagnostics
        for diagnostic in monitor.diagnostics:
            mock_result = Mock()
            mock_result.status = HealthStatus.HEALTHY
            mock_result.message = "Mock healthy"
            diagnostic.run = AsyncMock(return_value=mock_result)
        
        results = await monitor.run_all_diagnostics()
        
        assert len(results) == len(monitor.diagnostics)
        assert len(monitor.health_history) == 1
        
        # Check that all diagnostics were run
        for diagnostic in monitor.diagnostics:
            diagnostic.run.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_run_all_diagnostics_with_failure(self):
        """Test running diagnostics with failure."""
        monitor = HealthMonitor()
        
        # Mock first diagnostic to fail
        monitor.diagnostics[0].run = AsyncMock(side_effect=Exception("Test failure"))
        
        # Mock other diagnostics to succeed
        for diagnostic in monitor.diagnostics[1:]:
            mock_result = Mock()
            mock_result.status = HealthStatus.HEALTHY
            mock_result.message = "Mock healthy"
            diagnostic.run = AsyncMock(return_value=mock_result)
        
        results = await monitor.run_all_diagnostics()
        
        assert len(results) == len(monitor.diagnostics)
        assert results[monitor.diagnostics[0].name].status == HealthStatus.CRITICAL
        assert "execution failed" in results[monitor.diagnostics[0].name].message.lower()
    
    @pytest.mark.asyncio
    async def test_start_monitoring(self):
        """Test starting monitoring."""
        monitor = HealthMonitor(check_interval=0.1)
        
        # Mock run_all_diagnostics to avoid actual diagnostics
        monitor.run_all_diagnostics = AsyncMock()
        
        # Start monitoring
        monitoring_task = asyncio.create_task(monitor.start_monitoring())
        
        # Wait a short time
        await asyncio.sleep(0.05)
        
        # Check that monitoring is active
        assert monitor.monitoring_active is True
        
        # Stop monitoring
        monitor.stop_monitoring()
        
        # Wait for task to complete
        await monitoring_task
        
        assert monitor.monitoring_active is False
    
    def test_stop_monitoring(self):
        """Test stopping monitoring."""
        monitor = HealthMonitor()
        monitor.monitoring_active = True
        
        monitor.stop_monitoring()
        
        assert monitor.monitoring_active is False
    
    def test_get_overall_health_no_history(self):
        """Test getting overall health with no history."""
        monitor = HealthMonitor()
        
        health = monitor.get_overall_health()
        
        assert health["overall_status"] == "unknown"
        assert health["last_check"] is None
    
    def test_get_overall_health_with_history(self):
        """Test getting overall health with history."""
        monitor = HealthMonitor()
        
        # Add mock history
        mock_result = Mock()
        mock_result.status = HealthStatus.HEALTHY
        mock_result.recommendations = []
        
        monitor.health_history.append({
            "timestamp": time.time(),
            "results": {"test": mock_result}
        })
        
        health = monitor.get_overall_health()
        
        assert health["overall_status"] == "healthy"
        assert health["last_check"] is not None
        assert health["total_checks"] == 1
    
    def test_get_health_history(self):
        """Test getting health history."""
        monitor = HealthMonitor()
        
        # Add mock history
        for i in range(15):
            monitor.health_history.append({
                "timestamp": time.time() + i,
                "results": {}
            })
        
        # Get limited history
        history = monitor.get_health_history(limit=5)
        
        assert len(history) == 5
        assert history[-1]["timestamp"] > history[0]["timestamp"]
    
    def test_get_diagnostic_stats(self):
        """Test getting diagnostic statistics."""
        monitor = HealthMonitor()
        
        # Mock diagnostic stats
        for diagnostic in monitor.diagnostics:
            diagnostic.get_stats = Mock(return_value={"name": diagnostic.name})
        
        stats = monitor.get_diagnostic_stats()
        
        assert len(stats) == len(monitor.diagnostics)
        for diagnostic in monitor.diagnostics:
            assert diagnostic.name in stats
            diagnostic.get_stats.assert_called_once()


class TestDefaultHealthMonitor:
    """Test default health monitor."""
    
    def test_default_health_monitor_exists(self):
        """Test that default health monitor exists."""
        assert default_health_monitor is not None
        assert isinstance(default_health_monitor, HealthMonitor)
    
    def test_default_health_monitor_has_diagnostics(self):
        """Test that default health monitor has diagnostics."""
        assert len(default_health_monitor.diagnostics) > 0
        
        # Check that all default diagnostics are present
        diagnostic_names = [d.name for d in default_health_monitor.diagnostics]
        assert "Network" in diagnostic_names
        assert "Device" in diagnostic_names
        assert "Authentication" in diagnostic_names
        assert "System" in diagnostic_names


if __name__ == "__main__":
    pytest.main([__file__])