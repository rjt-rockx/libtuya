"""
CommandExecutor - Handles command execution with hybrid local/cloud control.

This module provides the CommandExecutor class that executes device commands
with automatic scaling, fallback strategies, and comprehensive error handling.
"""

import logging
from typing import Any, Callable, Dict, List, Optional

from libtuya.auth.models import DeviceInfo
from libtuya.dps import DPSMappingInfo
from libtuya.recovery.retry_strategies import (
    default_retry_manager,
    device_operation_config,
)

logger = logging.getLogger(__name__)


class CommandExecutor:
    """
    Executes device commands with hybrid local/cloud control.

    This class handles:
    - Command execution with local-first, cloud-fallback strategy
    - Value scaling for different device types
    - Comprehensive error handling and retry logic
    - Cache invalidation after successful commands
    """

    def __init__(self, device_info: DeviceInfo, dps_mappings: Dict[str, DPSMappingInfo]):
        """
        Initialize command executor.

        Args:
            device_info: Device information from cloud discovery
            dps_mappings: DPS mapping information for capabilities
        """
        self.device_info = device_info
        self.dps_mappings = dps_mappings

        # Strategy functions (set by orchestrator)
        self._connection_manager = None
        self._capability_translator = None
        self._tinytuya_device = None
        self._cloud_command_func: Optional[Callable[[str, Any], bool]] = None
        self._cache_clear_func: Optional[Callable[[], None]] = None

        # Error tracking
        self.last_error: Optional[str] = None

    def set_dependencies(
        self,
        connection_manager,
        capability_translator,
        tinytuya_device,
        cloud_command_func: Callable[[str, Any], bool],
        cache_clear_func: Callable[[], None],
    ):
        """
        Set the required dependencies.

        Args:
            connection_manager: ConnectionManager instance
            capability_translator: CapabilityTranslator instance
            tinytuya_device: TinyTuya device instance
            cloud_command_func: Function to send cloud commands
            cache_clear_func: Function to clear caches after successful commands
        """
        self._connection_manager = connection_manager
        self._capability_translator = capability_translator
        self._tinytuya_device = tinytuya_device
        self._cloud_command_func = cloud_command_func
        self._cache_clear_func = cache_clear_func

    def set_capability(self, capability: str, value: Any) -> bool:
        """
        Set a device capability value using full hybrid logic (local first, cloud fallback).

        This method implements the complete hybrid control strategy:
        1. Determine optimal control method (local vs cloud)
        2. Attempt local control first if viable
        3. Automatic fallback to cloud on local failure
        4. Comprehensive error handling and recovery
        5. Status cache invalidation on success

        Args:
            capability: Capability name (e.g., "switch_led", "bright_value")
            value: Value to set

        Returns:
            True if successful, False otherwise
        """
        if not self._connection_manager or not self._capability_translator:
            raise RuntimeError("CommandExecutor dependencies not set")

        control_method = self._connection_manager.determine_control_method(use_cache=True)
        logger.debug(
            f"Attempting to set capability '{capability}' to '{value}' using {control_method} control for {self.device_info.id}"
        )

        # Track attempt for error reporting
        local_attempted = False
        cloud_attempted = False
        local_error = None
        cloud_error = None

        # 1. Try local control first if viable
        if control_method == "local":
            local_attempted = True
            try:
                success = self._execute_local_command(capability, value)
                if success:
                    logger.info(
                        f"Successfully set {capability} to {value} via local control for {self.device_info.id}."
                    )
                    # Clear caches on successful command
                    if self._cache_clear_func:
                        self._cache_clear_func()
                    return True
                else:
                    local_error = "Local control command failed - no response"

            except Exception as e:
                logger.warning(
                    f"Local control failed for {self.device_info.id} ({capability}={value}): {e}"
                )
                local_error = str(e)
                self.last_error = str(e)
                # Clear connection caches on local failure to force fresh evaluation
                self._connection_manager.clear_caches()

        # 2. Fallback to cloud control (either as primary method or fallback)
        cloud_attempted = True
        try:
            logger.debug(
                f"Attempting cloud control for {self.device_info.id} ({capability}={value})"
            )
            success = self._execute_cloud_command(capability, value)

            if success:
                logger.info(
                    f"Successfully set {capability} to {value} via cloud control for {self.device_info.id}."
                )
                # Clear status cache on successful command
                if self._cache_clear_func:
                    self._cache_clear_func()
                return True
            else:
                cloud_error = "Cloud command returned False"
                logger.error(
                    f"Cloud control failed for {self.device_info.id} ({capability}={value}): {cloud_error}"
                )

        except Exception as e:
            cloud_error = str(e)
            logger.error(
                f"Cloud control failed for {self.device_info.id} ({capability}={value}): {e}"
            )
            self.last_error = str(e)

        # 3. Both methods failed - comprehensive error reporting
        error_details = []
        if local_attempted:
            error_details.append(f"Local: {local_error}")
        if cloud_attempted:
            error_details.append(f"Cloud: {cloud_error}")

        final_error = f"All control methods failed for {capability}={value}. " + "; ".join(
            error_details
        )
        logger.error(final_error)
        self.last_error = final_error

        return False

    def _execute_local_command(self, capability: str, value: Any) -> bool:
        """
        Execute a command using local TinyTuya control.

        Args:
            capability: Capability name
            value: Value to set

        Returns:
            True if successful, False otherwise
        """
        # Get DPS mapping for capability
        mapping_info = self.dps_mappings.get(capability)
        if not mapping_info:
            logger.warning(
                f"Capability '{capability}' not found for device {self.device_info.id} for local control. Fallback to cloud."
            )
            raise ValueError(f"No DPS mapping for capability '{capability}'")

        # Scale value if needed
        if self._capability_translator is None:
            raise RuntimeError("Capability translator not initialized")
        scaled_value = self._capability_translator.scale_value(capability, value, mapping_info)

        # Set value via TinyTuya
        if self._tinytuya_device is None:
            raise RuntimeError("TinyTuya device not initialized for local control.")

        # Use retry manager for robust local control
        success = default_retry_manager.retry_sync(
            func=lambda: self._tinytuya_device.set_value(mapping_info.dps, scaled_value),
            config=device_operation_config,
            operation_name=f"local_set_{capability}_{self.device_info.id}",
        )

        if success is not None:  # TinyTuya set_value returns None on success
            logger.debug(
                f"Successfully set {capability} to {scaled_value} via local control for {self.device_info.id}."
            )
            return True
        else:
            raise RuntimeError("Local control command failed - no response")

    def _execute_cloud_command(self, capability: str, value: Any) -> bool:
        """
        Execute a command using cloud control.

        Args:
            capability: Capability name
            value: Value to set

        Returns:
            True if successful, False otherwise
        """
        if not self._cloud_command_func:
            raise RuntimeError("Cloud command function not set")

        return self._cloud_command_func(capability, value)

    def execute_multiple_capabilities(
        self, capabilities: Dict[str, Any], stop_on_first_failure: bool = False
    ) -> Dict[str, bool]:
        """
        Execute multiple capability changes in sequence.

        Args:
            capabilities: Dictionary of capability -> value pairs
            stop_on_first_failure: Whether to stop on first failure

        Returns:
            Dictionary of capability -> success status
        """
        results = {}

        for capability, value in capabilities.items():
            try:
                success = self.set_capability(capability, value)
                results[capability] = success

                if not success and stop_on_first_failure:
                    logger.warning(
                        f"Stopping multiple capability execution due to failure on {capability}"
                    )
                    break

            except Exception as e:
                logger.error(f"Failed to set capability {capability}: {e}")
                results[capability] = False

                if stop_on_first_failure:
                    logger.warning(
                        f"Stopping multiple capability execution due to exception on {capability}"
                    )
                    break

        return results

    def get_switch_capabilities(self) -> List[str]:
        """
        Get available switch capabilities for this device.

        Returns:
            List of switch capability names
        """
        if not self._capability_translator:
            return []

        return self._capability_translator.get_switch_capabilities()

    def get_brightness_capabilities(self) -> List[str]:
        """
        Get available brightness capabilities for this device.

        Returns:
            List of brightness capability names
        """
        if not self._capability_translator:
            return []

        return self._capability_translator.get_brightness_capabilities()

    def get_color_capabilities(self) -> List[str]:
        """
        Get available color capabilities for this device.

        Returns:
            List of color capability names
        """
        if not self._capability_translator:
            return []

        return self._capability_translator.get_color_capabilities()

    def get_color_temperature_capabilities(self) -> List[str]:
        """
        Get available color temperature capabilities for this device.

        Returns:
            List of color temperature capability names
        """
        if not self._capability_translator:
            return []

        return self._capability_translator.get_color_temperature_capabilities()

    def turn_on(self) -> bool:
        """
        Turn device on using hybrid control logic.

        This method attempts to turn the device on using the enhanced set_capability()
        method, which provides full hybrid control with local-first and cloud fallback.

        Returns:
            True if successful, False otherwise
        """
        logger.debug(f"Attempting to turn on device {self.device_info.id}")

        # Get switch capabilities from device intelligence (with fallbacks)
        switch_caps = self.get_switch_capabilities()

        for switch_cap in switch_caps:
            if switch_cap in self.dps_mappings:
                logger.debug(
                    f"Using switch capability '{switch_cap}' to turn on {self.device_info.id}"
                )
                success = self.set_capability(switch_cap, True)
                if success:
                    logger.info(
                        f"Successfully turned on device {self.device_info.id} using {switch_cap}"
                    )
                    return True
                else:
                    logger.warning(
                        f"Failed to turn on {self.device_info.id} using {switch_cap}, trying next capability"
                    )
                    continue

        # If no mapped capabilities worked, try cloud control with common switch capabilities
        logger.debug(
            f"No DPS-mapped switch capabilities worked for {self.device_info.id}, trying cloud control"
        )
        for switch_cap in switch_caps:
            try:
                success = self._execute_cloud_command(switch_cap, True)
                if success:
                    logger.info(
                        f"Successfully turned on device {self.device_info.id} using cloud control with {switch_cap}"
                    )
                    if self._cache_clear_func:
                        self._cache_clear_func()
                    return True
            except Exception as e:
                logger.debug(f"Cloud control failed for {switch_cap}: {e}")
                continue

        logger.error(
            f"Failed to turn on device {self.device_info.id} - no working switch capabilities found"
        )
        return False

    def turn_off(self) -> bool:
        """
        Turn device off using hybrid control logic.

        Returns:
            True if successful, False otherwise
        """
        logger.debug(f"Attempting to turn off device {self.device_info.id}")

        # Get switch capabilities from device intelligence (with fallbacks)
        switch_caps = self.get_switch_capabilities()

        for switch_cap in switch_caps:
            if switch_cap in self.dps_mappings:
                logger.debug(
                    f"Using switch capability '{switch_cap}' to turn off {self.device_info.id}"
                )
                success = self.set_capability(switch_cap, False)
                if success:
                    logger.info(
                        f"Successfully turned off device {self.device_info.id} using {switch_cap}"
                    )
                    return True
                else:
                    logger.warning(
                        f"Failed to turn off {self.device_info.id} using {switch_cap}, trying next capability"
                    )
                    continue

        # If no mapped capabilities worked, try cloud control with common switch capabilities
        logger.debug(
            f"No DPS-mapped switch capabilities worked for {self.device_info.id}, trying cloud control"
        )
        for switch_cap in switch_caps:
            try:
                success = self._execute_cloud_command(switch_cap, False)
                if success:
                    logger.info(
                        f"Successfully turned off device {self.device_info.id} using cloud control with {switch_cap}"
                    )
                    if self._cache_clear_func:
                        self._cache_clear_func()
                    return True
            except Exception as e:
                logger.debug(f"Cloud control failed for {switch_cap}: {e}")
                continue

        logger.error(
            f"Failed to turn off device {self.device_info.id} - no working switch capabilities found"
        )
        return False

    def toggle(self) -> bool:
        """
        Toggle device state using hybrid control logic.

        Returns:
            True if successful, False otherwise
        """
        logger.debug(f"Attempting to toggle device {self.device_info.id}")

        # Get current status to determine current state
        # This would require status retrieval, which we delegate to the orchestrator
        # For now, we'll just try to toggle the first available switch capability

        switch_caps = self.get_switch_capabilities()
        if not switch_caps:
            logger.error(f"No switch capabilities found for device {self.device_info.id}")
            return False

        # Try to toggle using the first available switch capability
        # In a real implementation, we'd check the current state first
        switch_cap = switch_caps[0]

        # For toggle, we'll need the current state - this requires coordination with the orchestrator
        # For now, we'll just attempt to turn on (this should be improved in the full integration)
        logger.warning(
            f"Toggle operation simplified - attempting turn on for {self.device_info.id}"
        )
        return self.turn_on()

    def get_execution_info(self) -> Dict[str, Any]:
        """
        Get information about command execution capabilities and status.

        Returns:
            Dictionary with execution status and capability information
        """
        return {
            "device_id": self.device_info.id,
            "device_name": self.device_info.name,
            "dps_mappings_count": len(self.dps_mappings),
            "available_capabilities": list(self.dps_mappings.keys()),
            "switch_capabilities": self.get_switch_capabilities(),
            "brightness_capabilities": self.get_brightness_capabilities(),
            "color_capabilities": self.get_color_capabilities(),
            "color_temperature_capabilities": self.get_color_temperature_capabilities(),
            "dependencies_set": all(
                [
                    self._connection_manager is not None,
                    self._capability_translator is not None,
                    self._tinytuya_device is not None,
                    self._cloud_command_func is not None,
                    self._cache_clear_func is not None,
                ]
            ),
            "last_error": self.last_error,
        }
