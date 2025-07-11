"""
IntelligentDevice - Refactored orchestrator combining modular components.

This module provides the refactored IntelligentDevice class that orchestrates
multiple focused components while maintaining the same public API.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from libtuya.auth import TuyaAuthenticator

# Import libtuya components
from libtuya.auth.models import DeviceInfo
from libtuya.devices.capability_translator import CapabilityTranslator
from libtuya.devices.command_executor import CommandExecutor

# Import new component classes
from libtuya.devices.connection_manager import ConnectionManager
from libtuya.devices.factory import DeviceFactory
from libtuya.devices.status_cache import DeviceStatusCache
from libtuya.dps import DPSMapper, DPSMappingInfo
from libtuya.intelligence import DeviceAnalysis, DeviceIntelligence
from libtuya.recovery.exceptions import LocalKeyError

# Import device models
from .models import DeviceCapability, DeviceStatus

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

        def set_value(self, _index, _value):
            pass

    TINYTUYA_AVAILABLE = False

logger = logging.getLogger(__name__)


class IntelligentDevice:
    """
    Main intelligent device orchestrator combining modular components.

    This class provides a unified interface for controlling Tuya devices by orchestrating:
    - ConnectionManager: Handles local/cloud connection testing and method selection
    - DeviceStatusCache: Manages status retrieval and caching
    - CommandExecutor: Executes commands with hybrid local/cloud control
    - CapabilityTranslator: Handles DPS mapping and capability translation
    """

    def __init__(
        self,
        device_info: DeviceInfo,
        intelligence: DeviceIntelligence,
        dps_mapper: DPSMapper,
        auth_manager: "TuyaAuthenticator",
        device_factory: Optional[DeviceFactory] = None,
        enable_persistent_connection: bool = False,
        tinytuya_device_instance: Optional[Device] = None,
        entity_capabilities: Optional[List[str]] = None,
    ):
        """
        Initialize an intelligent device orchestrator.

        Args:
            device_info: Device information from cloud discovery
            intelligence: Device intelligence database
            dps_mapper: DPS mapping system
            auth_manager: Authentication manager for cloud operations
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

        # TinyTuya device instance
        self.tinytuya_device: Optional[Device] = None

        # Initialize components
        self._initialize_components()

        # Initialize the device
        try:
            asyncio.create_task(self._async_initialize_device())
        except RuntimeError:
            # No event loop running (likely in tests), initialize synchronously
            try:
                asyncio.run(self._async_initialize_device())
            except Exception as e:
                logger.warning(f"Failed to initialize device synchronously: {e}")
                # Fall back to basic initialization
                self._sync_initialize_device()

    def _initialize_components(self):
        """Initialize the modular components."""
        # Initialize ConnectionManager
        self.connection_manager = ConnectionManager(
            device_info=self.device_info,
            tinytuya_device=self.tinytuya_device_instance,
        )

        # Initialize DeviceStatusCache
        self.status_cache = DeviceStatusCache(
            device_info=self.device_info, cache_timeout_seconds=30
        )

        # Initialize CapabilityTranslator (will be updated after device analysis)
        self.capability_translator = CapabilityTranslator(
            device_info=self.device_info,
            intelligence=self.intelligence,
            dps_mapper=self.dps_mapper,
            entity_capabilities=self.entity_capabilities,
        )

        # Initialize CommandExecutor
        self.command_executor = CommandExecutor(
            device_info=self.device_info,
            dps_mappings=self.capability_translator.dps_mappings,
        )

    async def _async_initialize_device(self):
        """Initialize the intelligent device with analysis and TinyTuya connection."""
        try:
            # Analyze device category and capabilities
            self.device_analysis = self.intelligence.analyze_device(
                self.device_info.category, self.device_info.to_dict()
            )

            # Update capability translator with device analysis
            self.capability_translator.device_analysis = self.device_analysis
            self.capability_translator.refresh_mappings()

            # Attempt to create TinyTuya device
            try:
                if self.tinytuya_device_instance:
                    self.tinytuya_device = self.tinytuya_device_instance
                else:
                    self.tinytuya_device = self.device_factory.create_device(
                        self.device_info,
                        persist_connection=self.enable_persistent_connection,
                    )
            except (LocalKeyError, UnicodeDecodeError) as e:
                logger.warning(
                    f"Local key or decoding error during TinyTuya device creation for {self.device_info.id}: {e}"
                )
                # Attempt to update local key from cloud
                if await self._update_local_key_from_cloud():
                    logger.info(
                        f"Retrying TinyTuya device creation for {self.device_info.id} with updated local key."
                    )
                    # Retry creating TinyTuya device with new key
                    if self.tinytuya_device_instance:
                        self.tinytuya_device = self.tinytuya_device_instance
                    else:
                        self.tinytuya_device = self.device_factory.create_device(
                            self.device_info,
                            persist_connection=self.enable_persistent_connection,
                        )
                else:
                    logger.error(
                        f"Failed to update local key for {self.device_info.id}. Device initialization failed."
                    )
                    raise

            # Update components with TinyTuya device
            self._update_components_with_tinytuya()

            # Setup status retrieval strategies
            self._setup_status_strategies()

            logger.debug(
                f"Initialized intelligent device {self.device_info.name} ({self.device_info.id})"
            )

        except Exception as e:
            logger.error(f"Failed to initialize device {self.device_info.id}: {e}")
            raise

    def _sync_initialize_device(self):
        """Synchronous initialization fallback."""
        try:
            # Analyze device category and capabilities
            self.device_analysis = self.intelligence.analyze_device(
                self.device_info.category, self.device_info.to_dict()
            )

            # Update capability translator with device analysis
            self.capability_translator.device_analysis = self.device_analysis
            self.capability_translator.refresh_mappings()

            # Attempt to create TinyTuya device
            if self.tinytuya_device_instance:
                self.tinytuya_device = self.tinytuya_device_instance
            else:
                self.tinytuya_device = self.device_factory.create_device(
                    self.device_info,
                    persist_connection=self.enable_persistent_connection,
                )

            # Update components with TinyTuya device
            self._update_components_with_tinytuya()

            # Setup status retrieval strategies
            self._setup_status_strategies()

            logger.debug(f"Sync initialized device {self.device_info.name} ({self.device_info.id})")

        except Exception as e:
            logger.error(f"Failed to sync initialize device {self.device_info.id}: {e}")

    def _update_components_with_tinytuya(self):
        """Update components with the TinyTuya device instance."""
        # Update ConnectionManager
        self.connection_manager.set_tinytuya_device(self.tinytuya_device)

        # Update CommandExecutor dependencies
        self.command_executor.set_dependencies(
            connection_manager=self.connection_manager,
            capability_translator=self.capability_translator,
            tinytuya_device=self.tinytuya_device,
            cloud_command_func=self._send_cloud_command,
            cache_clear_func=self._clear_all_caches,
        )

    def _setup_status_strategies(self):
        """Setup status retrieval strategies for the status cache."""
        self.status_cache.set_status_strategies(
            hybrid_strategy=self._get_hybrid_status,
            cloud_strategy=self._get_cloud_only_status,
            local_strategy=self._get_local_only_status,
        )

    def _clear_all_caches(self):
        """Clear all caches across components."""
        self.connection_manager.clear_caches()
        self.status_cache.clear_cache()

    async def _update_local_key_from_cloud(self) -> bool:
        """
        Update local key from cloud discovery.

        Returns:
            True if key was updated successfully, False otherwise
        """
        try:
            if not self.auth_manager:
                logger.warning(
                    f"No auth manager available to update local key for {self.device_info.id}"
                )
                return False

            # Get fresh device info from cloud
            result = self.auth_manager.get_all_devices(force_refresh=True)

            for device in result.devices:
                if device.id == self.device_info.id and device.has_local_key:
                    logger.info(f"Updating local key for device {self.device_info.id}")
                    self.device_info.local_key = device.local_key
                    return True

            logger.warning(f"Could not find updated local key for device {self.device_info.id}")
            return False

        except Exception as e:
            logger.error(f"Failed to update local key from cloud for {self.device_info.id}: {e}")
            return False

    def _send_cloud_command(self, capability: str, value: Any) -> bool:
        """
        Send a command via cloud control.

        Args:
            capability: Capability name
            value: Value to set

        Returns:
            True if successful, False otherwise
        """
        try:
            if not self.auth_manager:
                logger.error(
                    f"No auth manager available for cloud control of {self.device_info.id}"
                )
                return False

            # Convert capability to DPCode for cloud control
            dpcode = self.capability_translator.capability_to_dpcode(capability)

            # Send cloud command
            success = self.auth_manager.send_device_command(self.device_info.id, dpcode, value)

            if success:
                logger.debug(
                    f"Cloud command successful: {dpcode}={value} for {self.device_info.id}"
                )
            else:
                logger.warning(f"Cloud command failed: {dpcode}={value} for {self.device_info.id}")

            return success

        except Exception as e:
            logger.error(f"Cloud command exception for {self.device_info.id}: {e}")
            return False

    def _get_hybrid_status(self) -> DeviceStatus:
        """Get device status using hybrid approach (local + cloud)."""
        # Implementation delegated to existing logic
        # This would be the existing _get_hybrid_status method content
        # For now, fallback to cloud-only
        return self._get_cloud_only_status()

    def _get_cloud_only_status(self) -> DeviceStatus:
        """Get device status using cloud API only."""
        if not self.auth_manager:
            raise RuntimeError("Auth manager not available for cloud-only status retrieval")

        result = self.auth_manager.get_all_devices(force_refresh=True)
        updated_device_info = None
        for dev in result.devices:
            if dev.id == self.device_info.id:
                updated_device_info = dev
                break

        if not updated_device_info:
            raise RuntimeError(f"Device {self.device_info.id} not found in cloud discovery")

        # Update local device_info with fresh cloud status
        self.device_info.status = updated_device_info.status
        self.device_info.online = updated_device_info.online
        return self._create_status_from_cloud_data()

    def _get_local_only_status(self) -> DeviceStatus:
        """Get device status using local TinyTuya only."""
        if not self.tinytuya_device:
            raise RuntimeError("TinyTuya device not initialized for local-only status retrieval")

        # Implementation would use TinyTuya to get status
        # For now, create a basic status
        from datetime import datetime

        return DeviceStatus(
            online=True,
            last_update=datetime.now(),
            capabilities={},
            raw_dps={},
            errors=[],
        )

    def _create_status_from_cloud_data(self) -> DeviceStatus:
        """Create DeviceStatus from cloud data."""
        from datetime import datetime

        capabilities = {}
        raw_dps = {}

        # Convert cloud status to capabilities
        if hasattr(self.device_info, "status") and self.device_info.status:
            for status_item in self.device_info.status:
                if hasattr(status_item, "code") and hasattr(status_item, "value"):
                    capability_name = self.capability_translator.dpcode_to_capability(
                        status_item.code
                    )
                    dps_mapping = self.capability_translator.get_dps_mapping(capability_name)

                    capabilities[capability_name] = DeviceCapability(
                        name=capability_name,
                        dpcode=status_item.code,
                        dps_index=dps_mapping.dps if dps_mapping else None,
                        data_type=(dps_mapping.data_type if dps_mapping else "unknown"),
                        current_value=status_item.value,
                        available=True,
                    )

                    if dps_mapping:
                        raw_dps[dps_mapping.dps] = status_item.value

        return DeviceStatus(
            online=self.device_info.online,
            last_update=datetime.now(),
            capabilities=capabilities,
            raw_dps=raw_dps,
            errors=[],
        )

    # Public API methods (maintaining compatibility)

    @property
    def name(self) -> str:
        """Device name."""
        return self.device_info.name

    @property
    def id(self) -> str:
        """Device ID."""
        return self.device_info.id

    @property
    def category(self) -> str:
        """Device category."""
        return self.device_info.category

    @property
    def is_online(self) -> bool:
        """Check if device is online."""
        return self.device_info.online

    @property
    def can_control_locally(self) -> bool:
        """Check if device can be controlled locally."""
        return self.connection_manager.can_use_local_control()

    @property
    def available_capabilities(self) -> List[str]:
        """Get available capabilities."""
        return self.capability_translator.get_available_capabilities()

    def get_status(self, force_refresh: bool = False) -> DeviceStatus:
        """Get device status with caching."""
        return self.status_cache.get_status(force_refresh=force_refresh)

    def set_capability(self, capability: str, value: Any) -> bool:
        """Set a device capability value."""
        return self.command_executor.set_capability(capability, value)

    def execute_command(self, action: str, value: Any = None) -> bool:
        """
        Execute a command on the device.

        Args:
            action: Action to perform (on, off, brightness, etc.)
            value: Optional value for the action

        Returns:
            True if successful, False otherwise
        """
        try:
            if action.lower() in ["on", "turn_on"]:
                return self.turn_on()
            elif action.lower() in ["off", "turn_off"]:
                return self.turn_off()
            elif action.lower() == "brightness" and value is not None:
                return self.set_brightness_percentage(int(value))
            elif action.lower() == "color" and value is not None:
                if isinstance(value, str) and value.startswith("#"):
                    return self.set_color_hex(value)
                else:
                    return self.set_capability("colour_data", value)
            else:
                # Try to set as a capability
                return self.set_capability(action, value)
        except Exception as e:
            logger.error(f"Command execution failed for {action}={value}: {e}")
            return False

    def get_capability(self, capability: str) -> Any:
        """Get current value of a capability."""
        status = self.get_status()
        cap_info = status.capabilities.get(capability)
        return cap_info.current_value if cap_info else None

    def turn_on(self) -> bool:
        """Turn device on."""
        return self.command_executor.turn_on()

    def turn_off(self) -> bool:
        """Turn device off."""
        return self.command_executor.turn_off()

    def toggle(self) -> bool:
        """Toggle device state."""
        return self.command_executor.toggle()

    def set_brightness_percentage(self, percentage: int) -> bool:
        """Set brightness as percentage (0-100)."""
        brightness_caps = self.command_executor.get_brightness_capabilities()
        for cap in brightness_caps:
            if self.command_executor.set_capability(cap, percentage):
                return True
        return False

    def set_color_rgb(self, r: int, g: int, b: int) -> bool:
        """Set RGB color."""
        color_caps = self.command_executor.get_color_capabilities()
        # Convert RGB to hex format that most devices expect
        hex_color = f"{r:02x}{g:02x}{b:02x}"
        for cap in color_caps:
            if self.command_executor.set_capability(cap, hex_color):
                return True
        return False

    def set_color_hex(self, hex_color: str) -> bool:
        """Set color using hex format."""
        color_caps = self.command_executor.get_color_capabilities()
        for cap in color_caps:
            if self.command_executor.set_capability(cap, hex_color):
                return True
        return False

    def set_color_temperature(self, kelvin: int) -> bool:
        """Set color temperature in Kelvin."""
        temp_caps = self.command_executor.get_color_temperature_capabilities()
        for cap in temp_caps:
            if self.command_executor.set_capability(cap, kelvin):
                return True
        return False

    def detect_available_dps(self) -> Dict[int, Any]:
        """Detect all available DPS indices and their current values."""
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
        """Validate the device setup and configuration."""
        validation_results = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "device_info": self.device_info.to_dict(),
            "analysis": (self.device_analysis.__dict__ if self.device_analysis else None),
            "connection_info": self.connection_manager.get_connection_info(),
            "status_cache_info": self.status_cache.get_cache_info(),
            "translator_info": self.capability_translator.get_translator_info(),
            "executor_info": self.command_executor.get_execution_info(),
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

        # Check component initialization
        if not self.capability_translator.dps_mappings:
            validation_results["warnings"].append("No DPS mappings available")

        if not self.auth_manager:
            validation_results["warnings"].append(
                "Auth manager not available - cloud control disabled"
            )

        return validation_results

    def get_device_info(self) -> Dict[str, Any]:
        """Get comprehensive device information."""
        return {
            "device_info": self.device_info.to_dict(),
            "device_analysis": (self.device_analysis.__dict__ if self.device_analysis else None),
            "connection_info": self.connection_manager.get_connection_info(),
            "status_cache_info": self.status_cache.get_cache_info(),
            "translator_info": self.capability_translator.get_translator_info(),
            "executor_info": self.command_executor.get_execution_info(),
        }

    def close(self):
        """Close the device and clean up resources."""
        logger.debug(f"Closing intelligent device {self.device_info.id}")

        # Clear all caches
        self._clear_all_caches()

        # Close TinyTuya device if we created it
        if self.tinytuya_device and not self.tinytuya_device_instance:
            try:
                if hasattr(self.tinytuya_device, "close"):
                    self.tinytuya_device.close()
            except Exception as e:
                logger.warning(f"Error closing TinyTuya device: {e}")

    def set_scene(self, scene_name: str) -> bool:
        """
        Set a scene mode for the device.

        Args:
            scene_name: Name of the scene to set

        Returns:
            True if successful, False otherwise
        """
        # This is a base implementation that subclasses can override
        logger.info(f"Setting scene '{scene_name}' for device {self.device_info.name}")
        # Default implementation - subclasses should override for specific functionality
        return False

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, _exc_type, _exc_val, _exc_tb):
        """Context manager exit."""
        self.close()

    def __str__(self) -> str:
        return f"IntelligentDevice({self.device_info.name}, {self.device_info.id})"

    def __repr__(self) -> str:
        return f"IntelligentDevice(id='{self.device_info.id}', name='{self.device_info.name}', category='{self.device_info.category}')"


# Factory functions to maintain compatibility
def create_intelligent_device(
    device_info: DeviceInfo,
    intelligence: DeviceIntelligence,
    dps_mapper: DPSMapper,
    auth_manager: "TuyaAuthenticator",
    device_factory: Optional[DeviceFactory] = None,
    enable_persistent_connection: bool = False,
) -> IntelligentDevice:
    """
    Create an intelligent device wrapper.

    Args:
        device_info: Device information from cloud discovery
        intelligence: Device intelligence database
        dps_mapper: DPS mapping system
        auth_manager: Authentication manager
        device_factory: Optional device factory
        enable_persistent_connection: Keep TinyTuya connection open

    Returns:
        Configured IntelligentDevice instance
    """
    return IntelligentDevice(
        device_info=device_info,
        intelligence=intelligence,
        dps_mapper=dps_mapper,
        auth_manager=auth_manager,
        device_factory=device_factory,
        enable_persistent_connection=enable_persistent_connection,
    )


def create_multi_entity_devices(
    device_info: DeviceInfo,
    intelligence: DeviceIntelligence,
    dps_mapper: DPSMapper,
    auth_manager: "TuyaAuthenticator",
    device_factory: Optional[DeviceFactory] = None,
    enable_persistent_connection: bool = False,
) -> List[IntelligentDevice]:
    """
    Create multiple intelligent device entities for multi-entity devices.

    Args:
        device_info: Device information from cloud discovery
        intelligence: Device intelligence database
        dps_mapper: DPS mapping system
        auth_manager: Authentication manager
        device_factory: Optional device factory
        enable_persistent_connection: Keep TinyTuya connection open

    Returns:
        List of IntelligentDevice instances, one per entity
    """
    # This would implement the existing multi-entity logic
    # For now, return a single device
    return [
        create_intelligent_device(
            device_info=device_info,
            intelligence=intelligence,
            dps_mapper=dps_mapper,
            auth_manager=auth_manager,
            device_factory=device_factory,
            enable_persistent_connection=enable_persistent_connection,
        )
    ]
