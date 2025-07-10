"""
IntelligentDevice - Main intelligent device wrapper for libtuya.

This module provides the IntelligentDevice class that seamlessly combines cloud discovery
with local control using TinyTuya, device intelligence, and DPS mapping.
"""

import logging
from typing import Dict, List, Optional, Any, Union, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import asyncio
import time
import ipaddress
import json

# Import libtuya components
from libtuya.auth.models import DeviceInfo
from libtuya.auth import TuyaAuthenticator
from libtuya.intelligence import DeviceIntelligence, DeviceAnalysis
from libtuya.dps import DPSMapper, DPSMappingInfo
from libtuya.recovery.exceptions import LocalKeyError
from libtuya.devices.factory import DeviceFactory, create_device_from_info
from libtuya.recovery.retry_strategies import default_retry_manager

# Import TinyTuya for type hints
try:
    import tinytuya
    from tinytuya import Device

    TINYTUYA_AVAILABLE = True
except ImportError:
    # Mock for testing
    class Device:
        def __init__(self, *args, **kwargs):
            pass

        def status(self):
            return {"dps": {}}

        def set_value(self, index, value):
            pass

    TINYTUYA_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class DeviceCapability:
    """Information about a device capability."""

    name: str
    dpcode: str
    dps_index: Optional[int]
    data_type: str
    current_value: Any = None
    available: bool = False
    scaling_info: Optional[Dict[str, Any]] = None


@dataclass
class DeviceStatus:
    """Current status of an intelligent device."""

    online: bool
    last_update: datetime
    capabilities: Dict[str, DeviceCapability]
    raw_dps: Dict[int, Any]
    errors: List[str]


class IntelligentDevice:
    """
    Main intelligent device wrapper combining cloud discovery, local control, and device intelligence.

    This class provides a unified interface for controlling Tuya devices by integrating:
    - Cloud discovery and authentication (DeviceInfo)
    - Local control via TinyTuya
    - Device intelligence from Home Assistant
    - DPS mapping and capability discovery
    """

    def __init__(
        self,
        device_info: DeviceInfo,
        intelligence: DeviceIntelligence,
        dps_mapper: DPSMapper,
        auth_manager: TuyaAuthenticator, # Added auth_manager
        device_factory: Optional[DeviceFactory] = None,
        enable_persistent_connection: bool = False,
        tinytuya_device_instance: Optional[Device] = None,
        entity_capabilities: Optional[List[str]] = None,
    ):
        """
        Initialize an intelligent device.

        Args:
            device_info: Device information from cloud discovery
            intelligence: Device intelligence database
            dps_mapper: DPS mapping system
            device_factory: Device factory (uses default if None)
            enable_persistent_connection: Keep TinyTuya connection open
            tinytuya_device_instance: Optional shared TinyTuya device instance for multi-entity devices
            entity_capabilities: Optional list of capabilities for this specific entity
        """
        self.device_info = device_info
        self.intelligence = intelligence
        self.dps_mapper = dps_mapper
        self.auth_manager = auth_manager
        self.device_factory = device_factory or DeviceFactory()
        self.enable_persistent_connection = enable_persistent_connection
        self.tinytuya_device_instance = tinytuya_device_instance
        self.entity_capabilities = entity_capabilities

        # Initialize device analysis
        self.device_analysis: Optional[DeviceAnalysis] = None
        self.dps_mappings: Dict[str, DPSMappingInfo] = {}

        # TinyTuya device instance
        self.tinytuya_device: Optional[Device] = None

        # Status tracking
        self.last_status_update: Optional[datetime] = None
        self.cached_status: Optional[DeviceStatus] = None
        self.status_cache_timeout = timedelta(seconds=30)

        # Error tracking
        self.connection_errors = 0
        self.last_error: Optional[str] = None

        # Initialize the device
        try:
            asyncio.create_task(self._async_initialize_device())
        except RuntimeError:
            # No event loop running (likely in tests)
            pass

    async def _async_initialize_device(self):
        """Initialize the intelligent device with analysis and TinyTuya connection."""
        try:
            # Analyze device category and capabilities
            self.device_analysis = self.intelligence.analyze_device(
                self.device_info.category, self.device_info.to_dict()
            )

            # Attempt to create TinyTuya device
            try:
                if self.tinytuya_device_instance:
                    self.tinytuya_device = self.tinytuya_device_instance
                else:
                    self.tinytuya_device = self.device_factory.create_device(
                        self.device_info,
                        persist_connection=self.enable_persistent_connection,
                    )
            except (LocalKeyError, UnicodeDecodeError, json.decoder.JSONDecodeError) as e:
                logger.warning(f"Local key or decoding error during TinyTuya device creation for {self.device_info.id}: {e}")
                # Attempt to update local key from cloud
                if await self._update_local_key_from_cloud():
                    logger.info(f"Retrying TinyTuya device creation for {self.device_info.id} with updated local key.")
                    # Retry creating TinyTuya device with new key
                    if self.tinytuya_device_instance:
                        self.tinytuya_device = self.tinytuya_device_instance
                    else:
                        self.tinytuya_device = self.device_factory.create_device(
                            self.device_info,
                            persist_connection=self.enable_persistent_connection,
                        )
                else:
                    logger.error(f"Failed to update local key for {self.device_info.id}. Device initialization failed.")
                    self.last_error = str(e)
                    raise # Re-raise if key update failed

            # Initialize DPS mapping
            self._initialize_dps_mapping()

            logger.debug(
                f"Initialized intelligent device {self.device_info.name} ({self.device_info.id})"
            )

        except Exception as e:
            logger.error(f"Failed to initialize device {self.device_info.id}: {e}")
            self.last_error = str(e)
            raise

    def _initialize_dps_mapping(self):
        """Initialize DPS mapping for device capabilities."""
        try:
            # Get expected capabilities from device analysis or entity definition
            if self.entity_capabilities:
                expected_capabilities = self.entity_capabilities
            else:
                expected_capabilities = self.device_analysis.capabilities

            # For now, use heuristic rules directly to avoid slow device probing
            import time
            from ..dps.mapping_rules import DPSMappingRules, DPSConfidence
            
            rules = DPSMappingRules()
            self.dps_mappings = {}
            
            # Get category-specific mappings
            category_mappings = rules.get_mappings_for_category(self.device_info.category)
            
            # Apply mappings for expected capabilities
            for capability in expected_capabilities:
                # Check category-specific mappings first
                for dps, (cap, conf, reason) in category_mappings.items():
                    if cap == capability:
                        from ..dps.mapper import DPSMappingInfo
                        self.dps_mappings[capability] = DPSMappingInfo(
                            device_id=self.device_info.id,
                            capability=capability,
                            dps=dps,
                            confidence=conf,
                            reason=f"Category {self.device_info.category}: {reason}",
                            verified=False,
                            last_updated=time.time()
                        )
                        break
                # Fall back to generic heuristic
                else:
                    predictions = rules.predict_dps_for_capability(capability, self.device_info.category)
                    if predictions:
                        # Use the highest confidence prediction
                        dps, conf, reason = predictions[0]
                        from ..dps.mapper import DPSMappingInfo
                        self.dps_mappings[capability] = DPSMappingInfo(
                            device_id=self.device_info.id,
                            capability=capability,
                            dps=dps,
                            confidence=conf,
                            reason=reason,
                            verified=False,
                            last_updated=time.time()
                        )

            if self.dps_mappings:
                logger.debug(
                    f"Applied {len(self.dps_mappings)} DPS mappings for {self.device_info.name}"
                )
            else:
                logger.debug(f"No DPS mappings found for {self.device_info.name}")

        except Exception as e:
            logger.warning(
                f"DPS mapping initialization failed for {self.device_info.id}: {e}"
            )
            self.dps_mappings = {}

    def _is_local_ip(self, ip_address: str) -> bool:
        """
        Check if the given IP address is a local (private) IP address.

        Args:
            ip_address: The IP address to check.

        Returns:
            True if the IP address is local, False otherwise.
        """
        try:
            ip_obj = ipaddress.ip_address(ip_address)
            return ip_obj.is_private
        except ValueError:
            # Invalid IP address format
            logger.warning(f"Invalid IP address format: {ip_address}")
            return False

    def _test_tinytuya_connection(self) -> bool:
        """
        Test the TinyTuya connection to the device.

        This method attempts a quick status check with retry logic.

        Returns:
            True if the connection is successful, False otherwise.
        """
        if not self.tinytuya_device:
            logger.debug(f"TinyTuya device not initialized for {self.device_info.id}")
            return False

        try:
            # Use retry manager for robust connection testing
            status = default_retry_manager.retry_sync(
                func=lambda: self.tinytuya_device.status(),
                config_name="device_connection", # Use pre-configured retry settings
                operation_name=f"tinytuya_status_check_{self.device_info.id}",
            )
            # A successful status call usually returns a dict with 'dps' key
            if status and 'dps' in status:
                logger.debug(f"TinyTuya connection successful for {self.device_info.id}")
                return True
            else:
                logger.warning(f"TinyTuya status check returned unexpected data for {self.device_info.id}: {status}")
                return False
        except Exception as e:
            logger.warning(f"TinyTuya connection test failed for {self.device_info.id}: {e}")
            return False

    def _can_use_local_control(self) -> bool:
        """
        Check if local control is viable for this device.

        Returns:
            True if local control is viable, False otherwise.
        """
        # Check if device has a local key and is reported as online by the cloud
        if not self.device_info.has_local_key or not self.device_info.online:
            logger.debug(f"Local control not viable for {self.device_info.id}: Missing local key or offline.")
            return False

        # Check if the device's IP address is local
        if not self.device_info.ip or not self._is_local_ip(self.device_info.ip):
            logger.debug(f"Local control not viable for {self.device_info.id}: Non-local IP ({self.device_info.ip}).")
            return False

        # Test TinyTuya connection
        if not self._test_tinytuya_connection():
            logger.warning(f"Local control not viable for {self.device_info.id}: TinyTuya connection failed.")
            return False

        logger.debug(f"Local control is viable for {self.device_info.id}.")
        return True

    def _determine_control_method(self) -> str:
        """
        Determine the optimal control method for this device ("local" or "cloud").

        Returns:
            "local" if local control is viable, "cloud" otherwise.
        """
        if self._can_use_local_control():
            logger.debug(f"Determined 'local' control for {self.device_info.id}.")
            return "local"
        else:
            logger.debug(f"Determined 'cloud' control for {self.device_info.id}.")
            return "cloud"

    async def _update_local_key_from_cloud(self) -> bool:
        """
        Attempt to update the device's local key from the Tuya Cloud API.

        Returns:
            True if the local key was successfully updated, False otherwise.
        """
        if not self.auth_manager:
            logger.warning(f"No auth_manager available to update local key for {self.device_info.id}.")
            return False

        try:
            logger.info(f"Attempting to update local key for {self.device_info.id} from cloud.")
            # Force refresh device list from cloud to get latest local key
            result = await self.auth_manager.get_all_devices(force_refresh=True)
            
            updated_device_info = None
            for dev in result.devices:
                if dev.id == self.device_info.id:
                    updated_device_info = dev
                    break

            if updated_device_info and updated_device_info.local_key and updated_device_info.local_key != self.device_info.local_key:
                self.device_info.local_key = updated_device_info.local_key
                # Re-initialize TinyTuya device with new key
                if self.tinytuya_device:
                    self.tinytuya_device.local_key = self.device_info.local_key.encode('latin1')
                    logger.info(f"Local key for {self.device_info.id} updated successfully from cloud.")
                    return True
                else:
                    logger.warning(f"TinyTuya device not initialized for {self.device_info.id}, cannot update local key.")
                    return False
            else:
                logger.warning(f"Could not retrieve updated local key for {self.device_info.id} from cloud.")
                return False
        except Exception as e:
            logger.error(f"Failed to update local key for {self.device_info.id} from cloud: {e}")
            return False

    def _capability_to_dpcode(self, capability: str) -> str:
        """
        Translate a high-level capability name to its corresponding Tuya DP code.

        Args:
            capability: The high-level capability name (e.g., "switch", "brightness").

        Returns:
            The Tuya DP code (e.g., "switch_led", "bright_value").

        Raises:
            ValueError: If the capability cannot be translated to a DP code.
        """
        # This mapping should ideally come from device_mappings.py or dpcodes.py
        # For now, a simplified direct mapping
        mapping = {
            "switch": "switch_led",
            "brightness": "bright_value",
            "color": "colour_data",
            "color_temperature": "temp_value",
            "mode": "work_mode",
            "fan_speed": "fan_speed",
            "control": "control", # For covers
            "position": "percent_control", # For covers
            # Add more as needed
        }
        dpcode = mapping.get(capability)
        if not dpcode:
            raise ValueError(f"Unknown capability: {capability}")
        return dpcode

    def _send_cloud_command(self, capability: str, value: Any) -> bool:
        """
        Send a command to the device via the Tuya Cloud API.

        Args:
            capability: The high-level capability name.
            value: The value to set for the capability.

        Returns:
            True if the command was sent successfully, False otherwise.
        """
        if not self.auth_manager:
            logger.warning(f"No auth_manager available to send cloud command for {self.device_info.id}.")
            return False

        try:
            dpcode = self._capability_to_dpcode(capability)
            
            # Handle value scaling for cloud API format
            # This is a simplified example; actual scaling would use intelligence.scaling_manager
            scaled_value = value
            if capability == "brightness":
                # Example: scale 0-100 to 0-1000 for cloud
                scaled_value = int(value * 10)
            elif capability == "color":
                # Example: convert RGB tuple to hex string for cloud
                if isinstance(value, tuple) and len(value) == 3:
                    scaled_value = '#%02x%02x%02x' % value
            
            commands = [{"code": dpcode, "value": scaled_value}]
            
            logger.info(f"Sending cloud command for {self.device_info.id}: {dpcode}={scaled_value}")
            success = self.auth_manager.send_command(self.device_info.id, commands)
            
            if not success:
                logger.error(f"Cloud command failed for {self.device_info.id}: {dpcode}={scaled_value}")
            return success
        except Exception as e:
            logger.error(f"Error sending cloud command for {self.device_info.id}: {e}")
            return False

    def _dpcode_to_capability(self, dpcode: str) -> str:
        """
        Translate a Tuya DP code to its corresponding high-level capability name.

        Args:
            dpcode: The Tuya DP code (e.g., "switch_led", "bright_value").

        Returns:
            The high-level capability name (e.g., "switch", "brightness").

        Raises:
            ValueError: If the DP code cannot be translated to a capability.
        """
        # This mapping should ideally come from device_mappings.py or dpcodes.py
        # For now, a simplified direct reverse mapping
        reverse_mapping = {
            "switch_led": "switch",
            "bright_value": "brightness",
            "colour_data": "color",
            "temp_value": "color_temperature",
            "work_mode": "mode",
            "fan_speed": "fan_speed",
            "control": "control", # For covers
            "percent_control": "position", # For covers
            # Add more as needed
        }
        capability = reverse_mapping.get(dpcode)
        if not capability:
            raise ValueError(f"Unknown DP code: {dpcode}")
        return capability

    def _create_status_from_cloud_data(self) -> DeviceStatus:
        """
        Create a DeviceStatus object from the device's cloud status data.

        This method parses the self.device_info.status dictionary (which comes from the cloud)
        into libtuya's DeviceStatus object.

        Returns:
            DeviceStatus object with current state derived from cloud data.
        """
        cloud_status = self.device_info.status
        capabilities = {}
        errors = []

        for dpcode_str, value in cloud_status.items():
            try:
                # Attempt to convert dpcode_str to int if it's a numeric string
                dpcode_int = int(dpcode_str) if dpcode_str.isdigit() else None
                
                # Translate DP code to high-level capability name
                capability_name = self._dpcode_to_capability(dpcode_str)
                
                # Create DeviceCapability object
                capability = DeviceCapability(
                    name=capability_name,
                    dpcode=dpcode_str,
                    dps_index=dpcode_int,
                    data_type=type(value).__name__, # Infer data type
                    current_value=value,
                    available=True,
                    scaling_info=None, # Scaling info is not directly available from cloud status
                )
                capabilities[capability_name] = capability
            except ValueError as e:
                errors.append(f"Failed to parse cloud status for DP code {dpcode_str}: {e}")
            except Exception as e:
                errors.append(f"Unexpected error processing cloud status for DP code {dpcode_str}: {e}")

        return DeviceStatus(
            online=self.device_info.online,
            last_update=datetime.now(), # Use current time as last update for cloud data
            capabilities=capabilities,
            raw_dps=cloud_status, # Store raw cloud status as raw_dps
            errors=errors,
        )

    def _get_hybrid_status(self) -> DeviceStatus:
        """
        Retrieve device status using a hybrid approach (local first, then cloud).

        Returns:
            DeviceStatus object with current state.
        """
        # Try local status first
        try:
            if self.tinytuya_device:
                raw_status = self.tinytuya_device.status()
                if raw_status and 'dps' in raw_status:
                    logger.debug(f"Successfully retrieved local status for {self.device_info.id}.")
                    # Convert DPS values to capabilities
                    capabilities = {}
                    for capability_name, mapping_info in self.dps_mappings.items():
                        if mapping_info.dps in raw_status['dps']:
                            capability = DeviceCapability(
                                name=capability_name,
                                dpcode=getattr(mapping_info, 'dpcode', ''),
                                dps_index=mapping_info.dps,
                                data_type=getattr(mapping_info, 'value_type', 'unknown'),
                                current_value=raw_status['dps'][mapping_info.dps],
                                available=True,
                                scaling_info=getattr(mapping_info, 'scaling_info', None),
                            )
                            capabilities[capability_name] = capability

                    return DeviceStatus(
                        online=True,
                        last_update=datetime.now(),
                        capabilities=capabilities,
                        raw_dps=raw_status['dps'],
                        errors=[],
                    )
                else:
                    logger.warning(f"Local status returned no DPS data for {self.device_info.id}. Falling back to cloud.")
            else:
                logger.warning(f"TinyTuya device not initialized for {self.device_info.id}. Falling back to cloud.")
        except Exception as e:
            logger.warning(f"Local status retrieval failed for {self.device_info.id}: {e}. Falling back to cloud.")
            self.last_error = str(e)

        # Fallback to cloud status
        logger.debug(f"Attempting to retrieve status from cloud for {self.device_info.id}.")
        try:
            if self.auth_manager:
                # Force refresh device list from cloud to get latest status
                result = self.auth_manager.get_all_devices(force_refresh=True)
                updated_device_info = None
                for dev in result.devices:
                    if dev.id == self.device_info.id:
                        updated_device_info = dev
                        break
                
                if updated_device_info:
                    self.device_info.status = updated_device_info.status # Update local device_info with fresh cloud status
                    self.device_info.online = updated_device_info.online # Update online status
                    return self._create_status_from_cloud_data()
                else:
                    raise RuntimeError(f"Device {self.device_info.id} not found in cloud discovery.")
            else:
                raise RuntimeError("Auth manager not available for cloud status retrieval.")
        except Exception as e:
            logger.error(f"Cloud status retrieval failed for {self.device_info.id}: {e}.")
            self.last_error = str(e)
            return DeviceStatus(
                online=False,
                last_update=datetime.now(),
                capabilities={},
                raw_dps={},
                errors=[f"Failed to retrieve status from both local and cloud: {e}"],
            )

    @property
    def name(self) -> str:
        """Get device name."""
        return self.device_info.name

    @property
    def id(self) -> str:
        """Get device ID."""
        return self.device_info.id

    @property
    def category(self) -> str:
        """Get device category."""
        return self.device_info.category

    @property
    def is_online(self) -> bool:
        """Check if device is online."""
        return self.device_info.online

    @property
    def can_control_locally(self) -> bool:
        """Check if device can be controlled locally."""
        return self.device_info.can_control_locally and self.tinytuya_device is not None

    @property
    def available_capabilities(self) -> List[str]:
        """Get list of available capabilities."""
        return list(self.dps_mappings.keys())

    def get_status(self, force_refresh: bool = False) -> DeviceStatus:
        """
        Get current device status using a prioritized approach.

        Prioritizes:
        1. Fresh cached status (if not force_refresh)
        2. Cloud API status (if available and fresh in device_info)
        3. Hybrid status (local first, then cloud refresh)

        Args:
            force_refresh: Force refresh from device (ignore cache)

        Returns:
            DeviceStatus object with current state
        """
        # 1. Check fresh cached status
        if (
            not force_refresh
            and self.cached_status
            and self.last_status_update
            and datetime.now() - self.last_status_update < self.status_cache_timeout
        ):
            logger.debug(f"Using fresh cached status for {self.device_info.id}.")
            return self.cached_status

        # 2. Check Cloud API status (if available and fresh in device_info)
        # Assuming device_info.status is updated by auth_manager.get_all_devices()
        # and has a recent timestamp if it's fresh.
        # For simplicity, we'll assume if device_info.status exists, it's "fresh enough"
        # to try before a full hybrid attempt, but a real timestamp check would be better.
        if self.device_info.status and self.auth_manager:
            logger.debug(f"Attempting to use cloud-provided status for {self.device_info.id}.")
            try:
                status = self._create_status_from_cloud_data()
                # Cache the status
                self.cached_status = status
                self.last_status_update = datetime.now()
                self.connection_errors = 0
                return status
            except Exception as e:
                logger.warning(f"Failed to create status from cloud data for {self.device_info.id}: {e}. Proceeding to hybrid.")

        # 3. Fallback to hybrid status retrieval
        logger.debug(f"Falling back to hybrid status retrieval for {self.device_info.id}.")
        status = self._get_hybrid_status()
        
        # Cache the status from hybrid retrieval
        self.cached_status = status
        self.last_status_update = datetime.now()
        self.connection_errors = 0 # Reset errors on successful retrieval

        return status

    def set_capability(self, capability: str, value: Any) -> bool:
        """
        Set a device capability value using the optimal control method (local or cloud).

        Args:
            capability: Capability name (e.g., "switch_led", "bright_value")
            value: Value to set

        Returns:
            True if successful, False otherwise
        """
        control_method = self._determine_control_method()
        logger.debug(f"Attempting to set capability '{capability}' to '{value}' using {control_method} control for {self.device_info.id}.")

        if control_method == "local":
            try:
                # Get DPS mapping for capability
                mapping_info = self.dps_mappings.get(capability)
                if not mapping_info:
                    logger.error(
                        f"Capability '{capability}' not found for device {self.device_info.id} for local control."
                    )
                    # Fallback to cloud if local mapping is missing
                    return self._send_cloud_command(capability, value)

                # Scale value if needed
                scaled_value = self._scale_value(capability, value, mapping_info)

                # Set value via TinyTuya
                if not self.tinytuya_device:
                    raise RuntimeError("TinyTuya device not initialized for local control.")

                self.tinytuya_device.set_value(mapping_info.dps, scaled_value)
                logger.info(f"Successfully set {capability} to {scaled_value} via local control for {self.device_info.id}.")
                self.cached_status = None # Invalidate status cache
                return True
            except Exception as e:
                logger.warning(f"Local control failed for {self.device_info.id} ({capability}={value}): {e}. Falling back to cloud control.")
                self.last_error = str(e)
                # Fallback to cloud control
                return self._send_cloud_command(capability, value)
        else: # control_method == "cloud"
            return self._send_cloud_command(capability, value)

    def get_capability(self, capability: str) -> Any:
        """
        Get current value of a capability.

        Args:
            capability: Capability name

        Returns:
            Current value or None if not available
        """
        status = self.get_status()
        cap_info = status.capabilities.get(capability)
        return cap_info.current_value if cap_info else None

    def turn_on(self) -> bool:
        """
        Turn device on (if it has a switch capability).

        Returns:
            True if successful, False otherwise
        """
        # Get switch capabilities from device intelligence (with fallbacks)
        switch_caps = self._get_switch_capabilities()

        for switch_cap in switch_caps:
            if switch_cap in self.dps_mappings:
                return self.set_capability(switch_cap, True)

        logger.warning(f"No switch capability found for device {self.device_info.id}")
        return False

    def turn_off(self) -> bool:
        """
        Turn device off (if it has a switch capability).

        Returns:
            True if successful, False otherwise
        """
        # Get switch capabilities from device intelligence (with fallbacks)
        switch_caps = self._get_switch_capabilities()

        for switch_cap in switch_caps:
            if switch_cap in self.dps_mappings:
                return self.set_capability(switch_cap, False)

        logger.warning(f"No switch capability found for device {self.device_info.id}")
        return False

    def _get_switch_capabilities(self) -> List[str]:
        """Get switch capability names with fallbacks from quirks."""
        # Get primary switch capabilities
        primary_caps = ["switch_led", "switch", "switch_1", "switch_2", "switch_3"]

        # Add fallbacks from quirks manager
        try:
            quirks_info = self.intelligence.quirks_manager.get_quirks_for_device(
                self.device_info.category
            )
            if quirks_info and "fallback_dpcodes" in quirks_info:
                fallback_caps = quirks_info["fallback_dpcodes"].get("switch", [])
                primary_caps.extend(fallback_caps)
        except Exception as e:
            logger.debug(f"Could not get switch fallbacks: {e}")

        return primary_caps

    def set_brightness_percentage(self, percentage: int) -> bool:
        """
        Set brightness as percentage (0-100).

        Args:
            percentage: Brightness percentage (0-100)

        Returns:
            True if successful, False otherwise
        """
        if not (0 <= percentage <= 100):
            raise ValueError("Percentage must be between 0 and 100")

        # Get brightness capabilities from device intelligence (with fallbacks)
        brightness_caps = self._get_brightness_capabilities()

        for brightness_cap in brightness_caps:
            if brightness_cap in self.dps_mappings:
                mapping_info = self.dps_mappings[brightness_cap]

                # Use HA intelligence for proper scaling
                try:
                    scaled_value = self.intelligence.scale_value(
                        dpcode=brightness_cap,
                        value=percentage,
                        device_category=self.device_info.category,
                        input_range=(0, 100),  # Input is percentage
                        scaling_type="brightness",
                    )

                    return self.set_capability(brightness_cap, scaled_value)

                except Exception as e:
                    logger.warning(f"HA scaling failed for {brightness_cap}: {e}")
                    # Continue to next capability
                    continue

        logger.warning(
            f"No brightness capability found for device {self.device_info.id}"
        )
        return False

    def _get_brightness_capabilities(self) -> List[str]:
        """Get brightness capability names with fallbacks from quirks."""
        # Get primary brightness capability
        primary_caps = ["bright_value", "bright_value_v2", "bright_value_1"]

        # Add fallbacks from quirks manager
        try:
            quirks_info = self.intelligence.quirks_manager.get_quirks_for_device(
                self.device_info.category
            )
            if quirks_info and "fallback_dpcodes" in quirks_info:
                fallback_caps = quirks_info["fallback_dpcodes"].get("brightness", [])
                primary_caps.extend(fallback_caps)
        except Exception as e:
            logger.debug(f"Could not get brightness fallbacks: {e}")

        return primary_caps

    def set_color_rgb(self, r: int, g: int, b: int) -> bool:
        """
        Set color using RGB values.

        Args:
            r: Red component (0-255)
            g: Green component (0-255)
            b: Blue component (0-255)

        Returns:
            True if successful, False otherwise
        """
        if not all(0 <= val <= 255 for val in [r, g, b]):
            raise ValueError("RGB values must be between 0 and 255")

        # Get color capabilities from device intelligence (with fallbacks)
        color_caps = self._get_color_capabilities()

        for color_cap in color_caps:
            if color_cap in self.dps_mappings:
                # Convert RGB to device format using intelligence
                try:
                    if "hsv" in color_cap.lower():
                        # Convert to HSV format
                        color_value = self.intelligence.convert_color_data(
                            r, g, b, "hsv"
                        )
                    else:
                        # Use hex format
                        color_value = self.intelligence.convert_color_data(
                            r, g, b, "hex"
                        )

                    return self.set_capability(color_cap, color_value)

                except Exception as e:
                    logger.warning(f"Color conversion failed for {color_cap}: {e}")
                    continue

        logger.warning(f"No color capability found for device {self.device_info.id}")
        return False

    def _get_color_capabilities(self) -> List[str]:
        """Get color capability names with fallbacks from quirks."""
        # Get primary color capabilities
        primary_caps = [
            "colour_data",
            "colour_data_v2",
            "colour_data_hsv",
            "color_data",
        ]

        # Add fallbacks from quirks manager
        try:
            quirks_info = self.intelligence.quirks_manager.get_quirks_for_device(
                self.device_info.category
            )
            if quirks_info and "fallback_dpcodes" in quirks_info:
                fallback_caps = quirks_info["fallback_dpcodes"].get("color", [])
                primary_caps.extend(fallback_caps)
        except Exception as e:
            logger.debug(f"Could not get color fallbacks: {e}")

        return primary_caps

    def set_color_temperature(self, kelvin: int) -> bool:
        """
        Set color temperature in Kelvin.

        Args:
            kelvin: Color temperature in Kelvin (1000-10000)

        Returns:
            True if successful, False otherwise
        """
        if not (1000 <= kelvin <= 10000):
            raise ValueError("Color temperature must be between 1000K and 10000K")

        # Get color temperature capabilities from device intelligence (with fallbacks)
        temp_caps = self._get_color_temperature_capabilities()

        for temp_cap in temp_caps:
            if temp_cap in self.dps_mappings:
                mapping_info = self.dps_mappings[temp_cap]

                # Use HA intelligence for proper scaling
                try:
                    scaled_value = self.intelligence.scale_value(
                        dpcode=temp_cap,
                        value=kelvin,
                        device_category=self.device_info.category,
                        input_range=(1000, 10000),  # Input is Kelvin
                        scaling_type="color_temperature",
                    )

                    return self.set_capability(temp_cap, scaled_value)

                except Exception as e:
                    logger.warning(f"HA scaling failed for {temp_cap}: {e}")
                    # Continue to next capability
                    continue

        logger.warning(
            f"No color temperature capability found for device {self.device_info.id}"
        )
        return False

    def _get_color_temperature_capabilities(self) -> List[str]:
        """Get color temperature capability names with fallbacks from quirks."""
        # Get primary color temperature capabilities
        primary_caps = ["temp_value", "temp_value_v2", "temperature", "color_temp"]

        # Add fallbacks from quirks manager
        try:
            quirks_info = self.intelligence.quirks_manager.get_quirks_for_device(
                self.device_info.category
            )
            if quirks_info and "fallback_dpcodes" in quirks_info:
                fallback_caps = quirks_info["fallback_dpcodes"].get(
                    "color_temperature", []
                )
                primary_caps.extend(fallback_caps)
        except Exception as e:
            logger.debug(f"Could not get color temperature fallbacks: {e}")

        return primary_caps

    def _scale_value(
        self, capability: str, value: Any, mapping_info: DPSMappingInfo
    ) -> Any:
        """
        Scale a value using device intelligence.

        Args:
            capability: Capability name
            value: Raw value
            mapping_info: DPS mapping information

        Returns:
            Scaled value
        """
        try:
            # Use intelligence system for scaling
            return self.intelligence.scale_value(
                capability,  # Use the capability name instead of dpcode
                value,
                self.device_info.category,
                target_range=(
                    mapping_info.scaling_info.get("range")
                    if mapping_info.scaling_info
                    else None
                ),
            )
        except Exception as e:
            logger.warning(f"Value scaling failed for {capability}: {e}")
            return value

    def detect_available_dps(self) -> Dict[int, Any]:
        """
        Detect all available DPS indices and their current values.

        Returns:
            Dictionary of DPS index -> current value
        """
        try:
            if not self.tinytuya_device:
                raise RuntimeError("TinyTuya device not initialized")

            # Use TinyTuya's detection method if available
            if hasattr(self.tinytuya_device, "detect_available_dps"):
                return self.tinytuya_device.detect_available_dps()
            else:
                # Fallback to status method
                status = self.tinytuya_device.status()
                return status.get("dps", {})

        except Exception as e:
            logger.error(f"DPS detection failed for {self.device_info.id}: {e}")
            return {}

    def validate_setup(self) -> Dict[str, Any]:
        """
        Validate the device setup and configuration.

        Returns:
            Validation results
        """
        validation_results = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "device_info": self.device_info.to_dict(),
            "analysis": self.device_analysis.__dict__ if self.device_analysis else None,
            "dps_mappings": {k: v.__dict__ for k, v in self.dps_mappings.items()},
            "tinytuya_available": self.tinytuya_device is not None,
            "connection_errors": self.connection_errors,
        }

        # Check basic requirements
        if not self.device_info.has_local_key:
            validation_results["errors"].append("No local key available")
            validation_results["valid"] = False

        if not self.device_info.online:
            validation_results["warnings"].append("Device is offline")

        if not self.tinytuya_device:
            validation_results["errors"].append("TinyTuya device not initialized")
            validation_results["valid"] = False

        # Check DPS mappings
        if not self.dps_mappings:
            validation_results["warnings"].append("No DPS mappings available")

        # Test connectivity
        try:
            status = self.get_status()
            if not status.online:
                validation_results["warnings"].append("Device connectivity test failed")
        except Exception as e:
            validation_results["errors"].append(f"Connectivity test failed: {e}")
            validation_results["valid"] = False

        return validation_results

    def get_device_info(self) -> Dict[str, Any]:
        """
        Get comprehensive device information.

        Returns:
            Dictionary with all device information
        """
        return {
            "basic_info": self.device_info.to_dict(),
            "analysis": self.device_analysis.__dict__ if self.device_analysis else None,
            "capabilities": self.available_capabilities,
            "dps_mappings": {k: v.__dict__ for k, v in self.dps_mappings.items()},
            "status": self.get_status().__dict__,
            "factory_info": self.device_factory.get_category_info(
                self.device_info.category
            ),
            "connection_info": {
                "tinytuya_available": self.tinytuya_device is not None,
                "persistent_connection": self.enable_persistent_connection,
                "connection_errors": self.connection_errors,
                "last_error": self.last_error,
            },
        }

    def close(self):
        """Close the device connection and clean up resources."""
        if self.tinytuya_device and hasattr(self.tinytuya_device, "close"):
            try:
                self.tinytuya_device.close()
                logger.info(f"Closed connection to device {self.device_info.id}")
            except Exception as e:
                logger.warning(f"Error closing device connection: {e}")

        # Clear cached data
        self.cached_status = None
        self.last_status_update = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def __str__(self) -> str:
        """String representation."""
        return f"IntelligentDevice({self.device_info.name}, {self.device_info.category}, {self.device_info.id})"

    def __repr__(self) -> str:
        """Detailed representation."""
        return (
            f"IntelligentDevice(name='{self.device_info.name}', "
            f"category='{self.device_info.category}', id='{self.device_info.id}', "
            f"online={self.device_info.online}, capabilities={len(self.dps_mappings)})"
        )


def create_intelligent_device(
    device_info: DeviceInfo,
    intelligence: Optional[DeviceIntelligence] = None,
    dps_mapper: Optional[DPSMapper] = None,
    **kwargs,
) -> IntelligentDevice:
    """
    Convenience function to create an IntelligentDevice.

    Args:
        device_info: Device information from cloud discovery
        intelligence: Device intelligence instance (creates default if None)
        dps_mapper: DPS mapper instance (creates default if None)
        **kwargs: Additional arguments for IntelligentDevice

    Returns:
        IntelligentDevice instance
    """
    if intelligence is None:
        intelligence = DeviceIntelligence()

    if dps_mapper is None:
        dps_mapper = DPSMapper()

    return IntelligentDevice(
        device_info=device_info,
        intelligence=intelligence,
        dps_mapper=dps_mapper,
        **kwargs,
    )
