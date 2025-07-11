"""
System diagnostics and health checks for libtuya.

This module provides comprehensive diagnostic capabilities to proactively
identify issues and monitor system health across all components.
"""

import asyncio
import logging
import platform
import socket
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from .exceptions import (
    AuthenticationError,
    ConnectivityError,
    DeviceConnectionError,
    DNSError,
    NetworkError,
    TimeoutError,
    TuyaError,
)

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status levels."""

    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class DiagnosticResult:
    """Result of a diagnostic check."""

    check_name: str
    status: HealthStatus
    message: str
    details: Dict[str, Any]
    timestamp: float
    duration: float
    recommendations: List[str]

    def __post_init__(self):
        """Validate the diagnostic result."""
        if not isinstance(self.details, dict):
            self.details = {}
        if not isinstance(self.recommendations, list):
            self.recommendations = []


class BaseDiagnostic(ABC):
    """Base class for all diagnostic checks."""

    def __init__(self, name: str, timeout: float = 30.0):
        self.name = name
        self.timeout = timeout
        self.last_result: Optional[DiagnosticResult] = None
        self.run_count = 0
        self.failure_count = 0

    @abstractmethod
    async def run_check(self) -> DiagnosticResult:
        """Run the diagnostic check."""
        pass

    async def run(self) -> DiagnosticResult:
        """Run the diagnostic check with timeout and error handling."""
        start_time = time.time()
        self.run_count += 1

        try:
            # Run check with timeout
            result = await asyncio.wait_for(self.run_check(), timeout=self.timeout)
            result.timestamp = start_time
            result.duration = time.time() - start_time

            # Reset failure count on success
            if result.status == HealthStatus.HEALTHY:
                self.failure_count = 0
            else:
                self.failure_count += 1

            self.last_result = result
            return result

        except asyncio.TimeoutError:
            self.failure_count += 1
            result = DiagnosticResult(
                check_name=self.name,
                status=HealthStatus.CRITICAL,
                message=f"Diagnostic check timed out after {self.timeout}s",
                details={"timeout": self.timeout},
                timestamp=start_time,
                duration=time.time() - start_time,
                recommendations=["Increase timeout or check system performance"],
            )
            self.last_result = result
            return result

        except Exception as e:
            self.failure_count += 1
            result = DiagnosticResult(
                check_name=self.name,
                status=HealthStatus.CRITICAL,
                message=f"Diagnostic check failed: {e}",
                details={"error": str(e), "error_type": type(e).__name__},
                timestamp=start_time,
                duration=time.time() - start_time,
                recommendations=["Check system logs and configuration"],
            )
            self.last_result = result
            return result

    def get_stats(self) -> Dict[str, Any]:
        """Get diagnostic statistics."""
        return {
            "name": self.name,
            "run_count": self.run_count,
            "failure_count": self.failure_count,
            "success_rate": (self.run_count - self.failure_count) / max(self.run_count, 1),
            "last_status": (self.last_result.status.value if self.last_result else "never_run"),
            "last_run": (self.last_result.timestamp if self.last_result else None),
        }


class NetworkDiagnostics(BaseDiagnostic):
    """Network connectivity and performance diagnostics."""

    def __init__(self, timeout: float = 30.0):
        super().__init__("Network", timeout)
        self.test_hosts = [
            "8.8.8.8",  # Google DNS
            "1.1.1.1",  # Cloudflare DNS
            "openapi.tuyacn.com",  # Tuya China API
            "openapi.tuyaus.com",  # Tuya US API
            "openapi.tuyaeu.com",  # Tuya EU API
        ]

    async def run_check(self) -> DiagnosticResult:
        """Run network diagnostic checks."""
        details = {}
        recommendations = []
        overall_status = HealthStatus.HEALTHY

        # Check basic connectivity
        connectivity_results = await self._check_connectivity()
        details["connectivity"] = connectivity_results

        # Check DNS resolution
        dns_results = await self._check_dns_resolution()
        details["dns"] = dns_results

        # Check latency
        latency_results = await self._check_latency()
        details["latency"] = latency_results

        # Check Tuya API endpoints
        tuya_results = await self._check_tuya_endpoints()
        details["tuya_endpoints"] = tuya_results

        # Determine overall status
        if not connectivity_results["internet_available"]:
            overall_status = HealthStatus.CRITICAL
            recommendations.append("Check internet connection")
        elif dns_results["failures"] > 0:
            overall_status = HealthStatus.WARNING
            recommendations.append("Check DNS configuration")
        elif latency_results["average_latency"] > 1000:
            overall_status = HealthStatus.WARNING
            recommendations.append("High latency detected - check network performance")
        elif tuya_results["failures"] > 0:
            overall_status = HealthStatus.WARNING
            recommendations.append("Some Tuya endpoints are unreachable")

        # Generate message
        if overall_status == HealthStatus.HEALTHY:
            message = "All network checks passed"
        elif overall_status == HealthStatus.WARNING:
            message = f"Network issues detected: {len(recommendations)} warnings"
        else:
            message = "Critical network issues detected"

        return DiagnosticResult(
            check_name=self.name,
            status=overall_status,
            message=message,
            details=details,
            timestamp=0,  # Will be set by run()
            duration=0,  # Will be set by run()
            recommendations=recommendations,
        )

    async def _check_connectivity(self) -> Dict[str, Any]:
        """Check basic internet connectivity."""
        results = {
            "internet_available": False,
            "reachable_hosts": [],
            "unreachable_hosts": [],
        }

        for host in self.test_hosts:
            try:
                # Use socket to test connectivity
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                result = sock.connect_ex((host, 80 if not host.startswith("openapi") else 443))
                sock.close()

                if result == 0:
                    results["reachable_hosts"].append(host)
                    results["internet_available"] = True
                else:
                    results["unreachable_hosts"].append(host)

            except Exception as e:
                results["unreachable_hosts"].append(f"{host}: {e}")

        return results

    async def _check_dns_resolution(self) -> Dict[str, Any]:
        """Check DNS resolution."""
        results = {
            "successful_resolutions": 0,
            "failures": 0,
            "resolution_times": {},
            "failed_hosts": [],
        }

        dns_hosts = [host for host in self.test_hosts if not host.replace(".", "").isdigit()]

        for host in dns_hosts:
            try:
                start_time = time.time()
                socket.gethostbyname(host)
                resolution_time = (time.time() - start_time) * 1000  # Convert to ms

                results["successful_resolutions"] += 1
                results["resolution_times"][host] = resolution_time

            except Exception as e:
                results["failures"] += 1
                results["failed_hosts"].append(f"{host}: {e}")

        return results

    async def _check_latency(self) -> Dict[str, Any]:
        """Check network latency using ping."""
        results = {
            "ping_results": {},
            "average_latency": 0.0,
            "max_latency": 0.0,
            "min_latency": float("inf"),
            "failed_pings": [],
        }

        ping_hosts = ["8.8.8.8", "1.1.1.1"]
        total_latency = 0
        successful_pings = 0

        for host in ping_hosts:
            try:
                # Use system ping command
                if platform.system().lower() == "windows":
                    cmd = ["ping", "-n", "3", host]
                else:
                    cmd = ["ping", "-c", "3", host]

                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                stdout, stderr = await process.communicate()

                if process.returncode == 0:
                    # Parse ping output for latency
                    latency = self._parse_ping_output(stdout.decode())
                    if latency > 0:
                        results["ping_results"][host] = latency
                        total_latency += latency
                        successful_pings += 1
                        current_max = float(results["max_latency"])
                        current_min = float(results["min_latency"])
                        results["max_latency"] = max(current_max, latency)
                        results["min_latency"] = min(current_min, latency)
                else:
                    results["failed_pings"].append(f"{host}: ping failed")

            except Exception as e:
                results["failed_pings"].append(f"{host}: {e}")

        if successful_pings > 0:
            results["average_latency"] = total_latency / successful_pings
        else:
            results["min_latency"] = 0

        return results

    def _parse_ping_output(self, output: str) -> float:
        """Parse ping output to extract average latency."""
        try:
            lines = output.split("\n")
            for line in lines:
                if "avg" in line.lower() or "average" in line.lower():
                    # Extract number from patterns like "min/avg/max/mdev = 1.2/3.4/5.6/7.8 ms"
                    parts = line.split("=")
                    if len(parts) > 1:
                        numbers = parts[1].split("/")
                        if len(numbers) >= 2:
                            return float(numbers[1])
                elif "time=" in line:
                    # Extract from individual ping lines
                    time_part = line.split("time=")[1].split()[0]
                    return float(time_part.replace("ms", ""))
        except BaseException:
            pass
        return 0

    async def _check_tuya_endpoints(self) -> Dict[str, Any]:
        """Check Tuya API endpoint availability."""
        results = {
            "reachable_endpoints": [],
            "unreachable_endpoints": [],
            "failures": 0,
        }

        tuya_endpoints = [
            "openapi.tuyacn.com",
            "openapi.tuyaus.com",
            "openapi.tuyaeu.com",
        ]

        for endpoint in tuya_endpoints:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                result = sock.connect_ex((endpoint, 443))
                sock.close()

                if result == 0:
                    results["reachable_endpoints"].append(endpoint)
                else:
                    results["unreachable_endpoints"].append(endpoint)
                    results["failures"] += 1

            except Exception as e:
                results["unreachable_endpoints"].append(f"{endpoint}: {e}")
                results["failures"] += 1

        return results


class DeviceDiagnostics(BaseDiagnostic):
    """Device connectivity and communication diagnostics."""

    def __init__(self, timeout: float = 30.0):
        super().__init__("Device", timeout)
        self.devices_to_check = []

    def add_device(self, device_id: str, device_ip: str, local_key: str):
        """Add a device to check."""
        self.devices_to_check.append(
            {
                "device_id": device_id,
                "device_ip": device_ip,
                "local_key": local_key,
            }
        )

    async def run_check(self) -> DiagnosticResult:
        """Run device diagnostic checks."""
        details = {}
        recommendations = []
        overall_status = HealthStatus.HEALTHY

        if not self.devices_to_check:
            return DiagnosticResult(
                check_name=self.name,
                status=HealthStatus.UNKNOWN,
                message="No devices configured for diagnostics",
                details={"device_count": 0},
                timestamp=0,
                duration=0,
                recommendations=["Add devices to monitor"],
            )

        # Check device reachability
        reachability_results = await self._check_device_reachability()
        details["reachability"] = reachability_results

        # Check protocol versions
        protocol_results = await self._check_protocol_versions()
        details["protocol_versions"] = protocol_results

        # Check device responsiveness
        responsiveness_results = await self._check_device_responsiveness()
        details["responsiveness"] = responsiveness_results

        # Determine overall status
        total_devices = len(self.devices_to_check)
        unreachable_devices = len(reachability_results["unreachable_devices"])
        unresponsive_devices = len(responsiveness_results["unresponsive_devices"])

        if unreachable_devices > 0:
            if unreachable_devices == total_devices:
                overall_status = HealthStatus.CRITICAL
            else:
                overall_status = HealthStatus.WARNING
            recommendations.append(f"{unreachable_devices} devices unreachable")

        if unresponsive_devices > 0:
            if overall_status == HealthStatus.HEALTHY:
                overall_status = HealthStatus.WARNING
            recommendations.append(f"{unresponsive_devices} devices unresponsive")

        # Generate message
        healthy_devices = total_devices - unreachable_devices - unresponsive_devices
        message = f"{healthy_devices}/{total_devices} devices healthy"

        return DiagnosticResult(
            check_name=self.name,
            status=overall_status,
            message=message,
            details=details,
            timestamp=0,
            duration=0,
            recommendations=recommendations,
        )

    async def _check_device_reachability(self) -> Dict[str, Any]:
        """Check if devices are reachable on the network."""
        results = {
            "reachable_devices": [],
            "unreachable_devices": [],
            "ping_times": {},
        }

        for device in self.devices_to_check:
            device_id = device["device_id"]
            device_ip = device["device_ip"]

            try:
                # Use socket to test connectivity
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3)
                start_time = time.time()
                result = sock.connect_ex((device_ip, 6668))  # Common Tuya port
                ping_time = (time.time() - start_time) * 1000
                sock.close()

                if result == 0:
                    results["reachable_devices"].append(device_id)
                    results["ping_times"][device_id] = ping_time
                else:
                    results["unreachable_devices"].append(device_id)

            except Exception as e:
                results["unreachable_devices"].append(f"{device_id}: {e}")

        return results

    async def _check_protocol_versions(self) -> Dict[str, Any]:
        """Check device protocol versions."""
        results = {
            "detected_versions": {},
            "version_failures": [],
            "protocol_support": {"3.1": [], "3.3": [], "3.4": [], "3.5": []},
        }

        # Integrate with actual device communication
        for device in self.devices_to_check:
            device_id = device.get("device_id", "unknown")
            try:
                # Try to detect protocol version from device info
                protocol_version = device.get("protocol_version", "3.3")

                # If protocol version is not set, try to detect it
                if not protocol_version or protocol_version == "Auto":
                    protocol_version = await self._detect_device_protocol(device)

                results["detected_versions"][device_id] = protocol_version

                # Add to protocol support tracking
                if protocol_version in results["protocol_support"]:
                    results["protocol_support"][protocol_version].append(device_id)
                else:
                    # Unknown version
                    if "unknown" not in results["protocol_support"]:
                        results["protocol_support"]["unknown"] = []
                    results["protocol_support"]["unknown"].append(device_id)

            except Exception as e:
                results["version_failures"].append(f"{device_id}: {str(e)}")

        return results

    async def _detect_device_protocol(self, device: Dict[str, Any]) -> str:
        """Detect device protocol version by trying different versions."""
        device_id = device.get("device_id", "unknown")
        local_key = device.get("local_key")
        local_ip = device.get("local_ip")

        if not local_key or not local_ip:
            return "unknown"

        # Try common protocol versions in order of likelihood
        versions_to_try = ["3.3", "3.1", "3.4", "3.2"]

        for version in versions_to_try:
            try:
                # Create a temporary TinyTuya device to test protocol
                import tinytuya

                test_device = tinytuya.Device(
                    dev_id=device_id,
                    address=local_ip,
                    local_key=local_key,
                    version=version,
                )
                test_device.set_socketTimeout(5)

                # Try to get status with this protocol version
                status = test_device.status()
                if status and not status.get("Error"):
                    return version

            except Exception as e:
                logger.debug(f"Protocol {version} failed for device {device_id}: {e}")
                continue

        return "unknown"

    async def _check_device_responsiveness(self) -> Dict[str, Any]:
        """Check device responsiveness to commands."""
        results = {
            "responsive_devices": [],
            "unresponsive_devices": [],
            "response_times": {},
            "slow_devices": [],
            "fast_devices": [],
            "average_response_time": 0,
        }

        total_response_time = 0
        successful_responses = 0

        # Test actual device communication
        for device in self.devices_to_check:
            device_id = device.get("device_id", "unknown")
            try:
                # Measure response time for status request
                start_time = time.time()

                # Try to communicate with device
                response_time = await self._test_device_communication(device)

                if response_time is not None:
                    end_time = time.time()
                    actual_response_time = (end_time - start_time) * 1000  # Convert to ms

                    results["responsive_devices"].append(device_id)
                    results["response_times"][device_id] = actual_response_time

                    total_response_time += actual_response_time
                    successful_responses += 1

                    # Categorize response times
                    if actual_response_time < 500:  # Fast response < 500ms
                        results["fast_devices"].append(device_id)
                    elif actual_response_time > 2000:  # Slow response > 2s
                        results["slow_devices"].append(device_id)

                else:
                    results["unresponsive_devices"].append(device_id)

            except Exception as e:
                results["unresponsive_devices"].append(f"{device_id}: {str(e)}")

        # Calculate average response time
        if successful_responses > 0:
            results["average_response_time"] = total_response_time / successful_responses

        return results

    async def _test_device_communication(self, device: Dict[str, Any]) -> Optional[float]:
        """Test communication with a single device."""
        device_id = device.get("device_id", "unknown")
        local_key = device.get("local_key")
        local_ip = device.get("local_ip")
        protocol_version = device.get("protocol_version", "3.3")

        if not local_key or not local_ip:
            raise Exception("Missing local key or IP address")

        try:
            # Create TinyTuya device for testing
            import tinytuya

            test_device = tinytuya.Device(
                dev_id=device_id,
                address=local_ip,
                local_key=local_key,
                version=protocol_version,
            )
            test_device.set_socketTimeout(10)  # 10 second timeout

            # Send a simple status request
            start_time = time.time()
            status = test_device.status()
            response_time = (time.time() - start_time) * 1000  # Convert to ms

            # Check if we got a valid response
            if status and not status.get("Error"):
                return response_time
            else:
                # Try with heartbeat if status failed
                heartbeat_result = test_device.heartbeat()
                if heartbeat_result:
                    return response_time
                else:
                    return None

        except Exception as e:
            logger.debug(f"Device communication test failed for {device_id}: {e}")
            return None


class AuthenticationDiagnostics(BaseDiagnostic):
    """Authentication system diagnostics."""

    def __init__(self, timeout: float = 30.0):
        super().__init__("Authentication", timeout)
        self.auth_manager = None

    def set_auth_manager(self, auth_manager):
        """Set the authentication manager to check."""
        self.auth_manager = auth_manager

    async def run_check(self) -> DiagnosticResult:
        """Run authentication diagnostic checks."""
        details = {}
        recommendations = []
        overall_status = HealthStatus.HEALTHY

        if not self.auth_manager:
            return DiagnosticResult(
                check_name=self.name,
                status=HealthStatus.UNKNOWN,
                message="No authentication manager configured",
                details={},
                timestamp=0,
                duration=0,
                recommendations=["Configure authentication manager"],
            )

        # Check token validity
        token_results = await self._check_token_validity()
        details["token_validity"] = token_results

        # Check API endpoint connectivity
        api_results = await self._check_api_connectivity()
        details["api_connectivity"] = api_results

        # Check session health
        session_results = await self._check_session_health()
        details["session_health"] = session_results

        # Determine overall status
        if not token_results["valid"]:
            overall_status = HealthStatus.CRITICAL
            recommendations.append("Authentication token is invalid or expired")
        elif not api_results["api_reachable"]:
            overall_status = HealthStatus.CRITICAL
            recommendations.append("Tuya API endpoints are unreachable")
        elif token_results["expires_soon"]:
            overall_status = HealthStatus.WARNING
            recommendations.append("Authentication token expires soon")

        # Generate message
        if overall_status == HealthStatus.HEALTHY:
            message = "Authentication system healthy"
        elif overall_status == HealthStatus.WARNING:
            message = "Authentication warnings detected"
        else:
            message = "Authentication system critical issues"

        return DiagnosticResult(
            check_name=self.name,
            status=overall_status,
            message=message,
            details=details,
            timestamp=0,
            duration=0,
            recommendations=recommendations,
        )

    async def _check_token_validity(self) -> Dict[str, Any]:
        """Check authentication token validity."""
        results = {
            "valid": False,
            "expires_soon": False,
            "expires_at": None,
            "token_type": None,
            "uid": None,
            "expires_in_minutes": 0,
        }

        try:
            # Get current session from auth manager
            if hasattr(self.auth_manager, "get_session"):
                session = self.auth_manager.get_session()
                if session:
                    results["valid"] = not session.is_expired
                    results["token_type"] = session.token_type
                    results["uid"] = session.uid

                    # Calculate expiration time
                    current_time = time.time()
                    expires_at = session.t + (session.expires_in * 60)  # Convert to timestamp
                    results["expires_at"] = expires_at

                    # Check if expires soon (within 10 minutes)
                    expires_in_seconds = expires_at - current_time
                    results["expires_in_minutes"] = expires_in_seconds / 60
                    results["expires_soon"] = expires_in_seconds < 600  # 10 minutes

                else:
                    results["error"] = "No active session found"
            else:
                results["error"] = "Auth manager does not support session checking"

        except Exception as e:
            results["error"] = str(e)

        return results

    async def _check_api_connectivity(self) -> Dict[str, Any]:
        """Check Tuya API connectivity."""
        results = {
            "api_reachable": False,
            "response_time": 0,
            "api_endpoints": {},
            "successful_endpoints": [],
            "failed_endpoints": [],
        }

        # Test common Tuya API endpoints
        api_endpoints = [
            "https://apigw.iotbing.com",
            "https://openapi.tuyaus.com",
            "https://openapi.tuyacn.com",
            "https://openapi.tuyaeu.com",
            "https://openapi.tuyain.com",
        ]

        try:
            import aiohttp

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                for endpoint in api_endpoints:
                    try:
                        start_time = time.time()
                        async with session.get(f"{endpoint}/health", ssl=False) as response:
                            response_time = (time.time() - start_time) * 1000

                            if (
                                response.status == 200 or response.status == 404
                            ):  # 404 is OK for health endpoint
                                results["api_endpoints"][endpoint] = {
                                    "reachable": True,
                                    "response_time": response_time,
                                    "status_code": response.status,
                                }
                                results["successful_endpoints"].append(endpoint)
                                results["api_reachable"] = True

                                # Update best response time
                                if (
                                    results["response_time"] == 0
                                    or response_time < results["response_time"]
                                ):
                                    results["response_time"] = response_time

                            else:
                                results["api_endpoints"][endpoint] = {
                                    "reachable": False,
                                    "response_time": response_time,
                                    "status_code": response.status,
                                }
                                results["failed_endpoints"].append(
                                    f"{endpoint}: HTTP {response.status}"
                                )

                    except Exception as e:
                        results["api_endpoints"][endpoint] = {
                            "reachable": False,
                            "error": str(e),
                        }
                        results["failed_endpoints"].append(f"{endpoint}: {str(e)}")

        except ImportError:
            # Fallback to basic socket connectivity if aiohttp not available
            for endpoint in api_endpoints[:2]:  # Test first 2 endpoints only
                try:
                    import urllib.parse

                    parsed = urllib.parse.urlparse(endpoint)
                    host = parsed.hostname
                    port = parsed.port or (443 if parsed.scheme == "https" else 80)

                    start_time = time.time()
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(10)
                    result = sock.connect_ex((host, port))
                    sock.close()
                    response_time = (time.time() - start_time) * 1000

                    if result == 0:
                        results["api_endpoints"][endpoint] = {
                            "reachable": True,
                            "response_time": response_time,
                            "method": "socket",
                        }
                        results["successful_endpoints"].append(endpoint)
                        results["api_reachable"] = True

                        if (
                            results["response_time"] == 0
                            or response_time < results["response_time"]
                        ):
                            results["response_time"] = response_time
                    else:
                        results["api_endpoints"][endpoint] = {
                            "reachable": False,
                            "error": f"Socket error: {result}",
                        }
                        results["failed_endpoints"].append(f"{endpoint}: Socket error {result}")

                except Exception as e:
                    results["api_endpoints"][endpoint] = {
                        "reachable": False,
                        "error": str(e),
                    }
                    results["failed_endpoints"].append(f"{endpoint}: {str(e)}")

        except Exception as e:
            results["error"] = str(e)

        return results

    async def _check_session_health(self) -> Dict[str, Any]:
        """Check session health."""
        results = {
            "active_sessions": 0,
            "session_errors": 0,
            "last_activity": None,
            "device_manager_active": False,
            "device_count": 0,
        }

        try:
            # Check if we have an active session
            if hasattr(self.auth_manager, "get_session"):
                session = self.auth_manager.get_session()
                if session and not session.is_expired:
                    results["active_sessions"] = 1
                    results["last_activity"] = time.time()

                    # Check if device manager is active
                    if (
                        hasattr(self.auth_manager, "device_manager")
                        and self.auth_manager.device_manager
                    ):
                        results["device_manager_active"] = True

                        # Try to get device count if available
                        if hasattr(self.auth_manager, "get_devices_with_keys"):
                            try:
                                devices = self.auth_manager.get_devices_with_keys()
                                results["device_count"] = len(devices)
                            except Exception as e:
                                results["session_errors"] += 1
                                results["device_error"] = str(e)
                else:
                    results["session_errors"] += 1
                    results["session_status"] = "expired" if session else "none"
            else:
                results["session_errors"] += 1
                results["error"] = "Auth manager does not support session checking"

        except Exception as e:
            results["error"] = str(e)
            results["session_errors"] += 1

        return results


class SystemDiagnostics(BaseDiagnostic):
    """Overall system health diagnostics."""

    def __init__(self, timeout: float = 30.0):
        super().__init__("System", timeout)
        self.subsystem_diagnostics = []

    def add_subsystem(self, diagnostic: BaseDiagnostic):
        """Add a subsystem diagnostic."""
        self.subsystem_diagnostics.append(diagnostic)

    async def run_check(self) -> DiagnosticResult:
        """Run system diagnostic checks."""
        details = {}
        recommendations = []
        overall_status = HealthStatus.HEALTHY

        # Check system resources
        resource_results = await self._check_system_resources()
        details["system_resources"] = resource_results

        # Check Python environment
        python_results = await self._check_python_environment()
        details["python_environment"] = python_results

        # Check dependencies
        dependency_results = await self._check_dependencies()
        details["dependencies"] = dependency_results

        # Run all subsystem diagnostics
        subsystem_results = await self._run_subsystem_diagnostics()
        details["subsystems"] = subsystem_results

        # Determine overall status
        if resource_results["memory_usage"] > 90:
            overall_status = HealthStatus.WARNING
            recommendations.append("High memory usage detected")

        if resource_results["disk_usage"] > 95:
            overall_status = HealthStatus.CRITICAL
            recommendations.append("Critical disk usage")

        if dependency_results["missing_dependencies"]:
            overall_status = HealthStatus.CRITICAL
            recommendations.append("Missing required dependencies")

        # Check subsystem status
        critical_subsystems = [
            result
            for result in subsystem_results.values()
            if result.get("status") == HealthStatus.CRITICAL.value
        ]

        if critical_subsystems:
            overall_status = HealthStatus.CRITICAL
            recommendations.append(f"{len(critical_subsystems)} subsystems critical")

        # Generate message
        healthy_subsystems = len(
            [
                result
                for result in subsystem_results.values()
                if result.get("status") == HealthStatus.HEALTHY.value
            ]
        )
        total_subsystems = len(subsystem_results)

        message = f"System health: {healthy_subsystems}/{total_subsystems} subsystems healthy"

        return DiagnosticResult(
            check_name=self.name,
            status=overall_status,
            message=message,
            details=details,
            timestamp=0,
            duration=0,
            recommendations=recommendations,
        )

    async def _check_system_resources(self) -> Dict[str, Any]:
        """Check system resource usage."""
        results: Dict[str, Any] = {"memory_usage": 0.0, "disk_usage": 0.0, "cpu_usage": 0.0}

        try:
            import psutil

            # Memory usage
            memory = psutil.virtual_memory()
            results["memory_usage"] = memory.percent

            # Disk usage
            disk = psutil.disk_usage("/")
            results["disk_usage"] = (disk.used / disk.total) * 100

            # CPU usage
            results["cpu_usage"] = psutil.cpu_percent(interval=1)

        except ImportError:
            # psutil not available, use basic checks
            results["error"] = "psutil not available for detailed system monitoring"
        except Exception as e:
            results["error"] = str(e)

        return results

    async def _check_python_environment(self) -> Dict[str, Any]:
        """Check Python environment."""
        results: Dict[str, Any] = {
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "architecture": platform.architecture()[0],
        }

        try:
            import sys

            results["executable"] = sys.executable
            results["path"] = sys.path[:3]  # First 3 paths

        except Exception as e:
            results["error"] = str(e)

        return results

    async def _check_dependencies(self) -> Dict[str, Any]:
        """Check required dependencies."""
        results = {
            "installed_packages": [],
            "missing_dependencies": [],
            "version_conflicts": [],
        }

        required_packages = ["asyncio", "socket", "logging", "json", "time"]

        for package in required_packages:
            try:
                __import__(package)
                results["installed_packages"].append(package)
            except ImportError:
                results["missing_dependencies"].append(package)

        return results

    async def _run_subsystem_diagnostics(self) -> Dict[str, Any]:
        """Run all subsystem diagnostics."""
        results = {}

        for diagnostic in self.subsystem_diagnostics:
            try:
                result = await diagnostic.run()
                results[diagnostic.name] = {
                    "status": result.status.value,
                    "message": result.message,
                    "recommendations": result.recommendations,
                }
            except Exception as e:
                results[diagnostic.name] = {
                    "status": HealthStatus.CRITICAL.value,
                    "message": f"Diagnostic failed: {e}",
                    "recommendations": ["Check diagnostic configuration"],
                }

        return results


class HealthMonitor:
    """
    Comprehensive health monitoring system that coordinates all diagnostics.
    """

    def __init__(self, check_interval: float = 300.0):  # 5 minutes
        self.check_interval = check_interval
        self.diagnostics: List[BaseDiagnostic] = []
        self.monitoring_active = False
        self.health_history = []
        self.max_history_size = 100

        # Initialize default diagnostics
        self._initialize_default_diagnostics()

    def _initialize_default_diagnostics(self):
        """Initialize default diagnostic checks."""
        self.diagnostics = [
            NetworkDiagnostics(),
            DeviceDiagnostics(),
            AuthenticationDiagnostics(),
            SystemDiagnostics(),
        ]

        # Add subsystem diagnostics to system diagnostic
        system_diagnostic = self.diagnostics[-1]
        for diagnostic in self.diagnostics[:-1]:
            system_diagnostic.add_subsystem(diagnostic)

    def add_diagnostic(self, diagnostic: BaseDiagnostic):
        """Add a custom diagnostic check."""
        self.diagnostics.append(diagnostic)

    async def run_all_diagnostics(self) -> Dict[str, DiagnosticResult]:
        """Run all diagnostic checks."""
        results = {}

        logger.info("Running comprehensive health diagnostics")

        # Run diagnostics in parallel
        tasks = []
        for diagnostic in self.diagnostics:
            task = asyncio.create_task(diagnostic.run())
            tasks.append((diagnostic.name, task))

        # Wait for all tasks to complete
        for name, task in tasks:
            try:
                result = await task
                results[name] = result
                logger.debug(f"Diagnostic {name}: {result.status.value} - {result.message}")
            except Exception as e:
                logger.error(f"Diagnostic {name} failed: {e}")
                results[name] = DiagnosticResult(
                    check_name=name,
                    status=HealthStatus.CRITICAL,
                    message=f"Diagnostic execution failed: {e}",
                    details={"error": str(e)},
                    timestamp=time.time(),
                    duration=0,
                    recommendations=["Check diagnostic configuration"],
                )

        # Store in history
        self.health_history.append({"timestamp": time.time(), "results": results})

        # Trim history if needed
        if len(self.health_history) > self.max_history_size:
            self.health_history = self.health_history[-self.max_history_size :]

        return results

    async def start_monitoring(self):
        """Start continuous health monitoring."""
        if self.monitoring_active:
            logger.warning("Health monitoring is already active")
            return

        self.monitoring_active = True
        logger.info(f"Starting health monitoring with {self.check_interval}s interval")

        try:
            while self.monitoring_active:
                await self.run_all_diagnostics()
                await asyncio.sleep(self.check_interval)
        except Exception as e:
            logger.error(f"Health monitoring failed: {e}")
        finally:
            self.monitoring_active = False

    def stop_monitoring(self):
        """Stop continuous health monitoring."""
        self.monitoring_active = False
        logger.info("Stopping health monitoring")

    def get_overall_health(self) -> Dict[str, Any]:
        """Get overall system health summary."""
        if not self.health_history:
            return {
                "overall_status": HealthStatus.UNKNOWN.value,
                "message": "No health data available",
                "last_check": None,
            }

        latest_results = self.health_history[-1]["results"]

        # Determine overall status
        statuses = [result.status for result in latest_results.values()]

        if HealthStatus.CRITICAL in statuses:
            overall_status = HealthStatus.CRITICAL
        elif HealthStatus.WARNING in statuses:
            overall_status = HealthStatus.WARNING
        elif HealthStatus.UNKNOWN in statuses:
            overall_status = HealthStatus.UNKNOWN
        else:
            overall_status = HealthStatus.HEALTHY

        # Count status distribution
        status_counts = {}
        for status in statuses:
            status_counts[status.value] = status_counts.get(status.value, 0) + 1

        # Collect all recommendations
        all_recommendations = []
        for result in latest_results.values():
            all_recommendations.extend(result.recommendations)

        return {
            "overall_status": overall_status.value,
            "message": f"System health: {status_counts}",
            "last_check": self.health_history[-1]["timestamp"],
            "status_distribution": status_counts,
            "total_checks": len(latest_results),
            "recommendations": all_recommendations,
            "monitoring_active": self.monitoring_active,
        }

    def get_health_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent health check history."""
        return self.health_history[-limit:]

    def get_diagnostic_stats(self) -> Dict[str, Any]:
        """Get statistics for all diagnostics."""
        return {diagnostic.name: diagnostic.get_stats() for diagnostic in self.diagnostics}


# Global health monitor instance
default_health_monitor = HealthMonitor()
