"""
TuyaCLICore - Main CLI business logic orchestrator

This module contains the core business logic for CLI operations, extracted from
the monolithic cli.py. It coordinates between the various library components
while maintaining a clean interface for CLI commands.
"""

import json
import logging
from typing import Any, Dict, Optional

from rich.console import Console

from libtuya.application import DisplayUtils, SessionManager
from libtuya.auth import TuyaAuthenticator
from libtuya.devices import IntelligentDeviceRegistry
from libtuya.dps import DPSMapper
from libtuya.intelligence import DeviceIntelligence
from libtuya.intelligence.translator import ValueTranslator
from libtuya.recovery import RecoveryManager

from .device_resolver import DeviceResolver
from .value_parser import ValueParser

logger = logging.getLogger(__name__)


class TuyaCLICore:
    """Core business logic orchestrator for CLI operations."""

    def __init__(self, verbose: bool = False, console: Optional[Console] = None):
        """Initialize CLI core with required components."""
        self.verbose = verbose
        self.console = console or Console(highlight=False)

        # Initialize core library components
        self.authenticator = TuyaAuthenticator(token_callback=self._on_token_updated)
        self.device_manager = IntelligentDeviceRegistry(auth_manager=self.authenticator)
        self.intelligence = DeviceIntelligence()
        self.value_translator = ValueTranslator()
        self.dps_mapper = DPSMapper()
        self.recovery = RecoveryManager()

        # Initialize application layer components
        self.session_manager = SessionManager()
        self.display_utils = DisplayUtils(self.console)
        self.device_resolver = DeviceResolver(self.console)
        self.value_parser = ValueParser()

        # State management
        self.session = None
        self.devices = {}
        self.device_indices = {}
        self.cached_device_info = {}

        # Try to load existing session and devices
        self._load_session()
        self._load_device_cache()

    def _on_token_updated(self, token_info: dict) -> None:
        """Handle token updates by saving the session."""
        try:
            self._save_session()
        except Exception as e:
            self.console.print(f"[dim]Warning: Could not save updated session: {e}[/dim]")

    def _load_session(self) -> bool:
        """Load authentication session from persistent storage."""
        session = self.session_manager.load_session()
        if session:
            self.session = session
            self.authenticator._current_session = session
            try:
                self.authenticator._initialize_device_manager()
                return True
            except Exception as e:
                self.console.print(f"[dim]Could not initialize device manager: {e}[/dim]")
                return False
        return False

    def _save_session(self) -> None:
        """Save authentication session to persistent storage."""
        if self.session:
            success = self.session_manager.save_session(self.session)
            if not success:
                self.console.print("[yellow]Warning: Could not save session[/yellow]")

    def clear_session(self) -> None:
        """Clear stored session."""
        success = self.session_manager.clear_session()
        if success:
            self.console.print("[dim]Session cleared[/dim]")
        else:
            self.console.print("[yellow]Warning: Could not clear session[/yellow]")
        self.session = None

    def _load_device_cache(self) -> None:
        """Load device cache from persistent storage."""
        cache_data = self.session_manager.load_device_cache()
        self.device_indices = cache_data["device_indices"]
        self.cached_device_info = cache_data["device_info"]

        if self.cached_device_info and self.verbose:
            self.console.print(
                f"[dim]Loaded {len(self.cached_device_info)} devices from cache[/dim]"
            )

    def _save_device_cache(self) -> None:
        """Save device cache to persistent storage."""
        success = self.session_manager.save_device_cache(
            self.device_indices, self.cached_device_info
        )
        if not success and self.verbose:
            self.console.print("[yellow]Warning: Could not save device cache[/yellow]")

    def display_qr_code(self, qr_data: str) -> None:
        """Display QR code in terminal."""
        self.display_utils.display_qr_code(qr_data)

    async def authenticate(
        self,
        user_code: Optional[str] = None,
        force_new_user_code: bool = False,
        output_json: bool = False,
    ) -> bool:
        """
        Perform authentication with QR code scanning.

        Args:
            user_code: Optional user code to use
            force_new_user_code: Force generation of new user code
            output_json: Output result as JSON

        Returns:
            True if authentication successful, False otherwise
        """
        try:
            # Check if we already have a valid session
            if self.session and not self.session.is_expired and not force_new_user_code:
                user_display = self.session.uid if self.session.uid else self.session.user_code

                if output_json:
                    result = {
                        "success": True,
                        "message": f"Already authenticated as {user_display}",
                        "user_code": self.session.user_code,
                        "uid": self.session.uid,
                    }
                    self.console.print(json.dumps(result))
                else:
                    self.console.print(f"[green]✓ Already authenticated as {user_display}[/green]")
                    self.console.print("[dim]Use --force to get a new user code[/dim]")
                return True

            # Follow the proper HA flow: user code -> generate QR -> scan QR -> authenticate
            # Step 1: Generate QR code 
            self.authenticator.start_qr_auth(user_code=user_code)
            qr_data = self.authenticator._last_qr_data
            
            # Step 2: Display QR code to user
            if not output_json and qr_data:
                # Format QR code the same way as Home Assistant
                qr_code_url = f"tuyaSmart--qrLogin?token={qr_data.qr_code}"
                self.display_utils.display_qr_code(
                    qr_code_url, 
                    "Scan QR Code with Smart Life App to Complete Authentication"
                )
                self.console.print("\n[dim]Instructions:[/dim]")
                self.console.print("[dim]1. Open Smart Life or Tuya Smart app on your phone[/dim]")
                self.console.print("[dim]2. Tap 'Scan' or the QR code icon[/dim]")
                self.console.print("[dim]3. Scan the QR code above[/dim]")
                self.console.print("[dim]4. Grant permission when prompted[/dim]")
                self.console.print("\n[yellow]Waiting for authentication...[/yellow]")
            
            # Step 3: Wait for user to scan QR code
            result = self.authenticator.wait_for_auth(timeout=300)

            if result:
                # Save the session
                self.session = self.authenticator._current_session
                self._save_session()

                if output_json:
                    json_result = {
                        "success": True,
                        "message": "Authentication successful",
                        "user_code": (
                            getattr(self.session, "user_code", None) if self.session else None
                        ),
                        "uid": (getattr(self.session, "uid", None) if self.session else None),
                    }
                    self.console.print(json.dumps(json_result))
                else:
                    user_display = (
                        getattr(self.session, "uid", None)
                        if self.session and getattr(self.session, "uid", None)
                        else (
                            getattr(self.session, "user_code", "unknown")
                            if self.session
                            else "unknown"
                        )
                    )
                    self.console.print(
                        f"[green]✓ Authentication successful! Logged in as {user_display}[/green]"
                    )
                    self.console.print("[dim]Run 'tuya devices' to see your devices[/dim]")

                return True
            else:
                if output_json:
                    error_result = {
                        "success": False,
                        "error": "Authentication failed",
                    }
                    self.console.print(json.dumps(error_result))
                else:
                    self.console.print("[red]✗ Authentication failed[/red]")
                return False

        except Exception as e:
            logger.error(f"Authentication error: {e}")
            if output_json:
                error_result = {"success": False, "error": str(e)}
                self.console.print(json.dumps(error_result))
            else:
                self.console.print(f"[red]✗ Authentication error: {e}[/red]")
            return False

    async def discover_devices(
        self, output_json: bool = False, force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Discover and cache devices with fast listing (lazy device creation).

        Args:
            output_json: Output result as JSON
            force_refresh: Force fresh discovery even if cache exists

        Returns:
            Dictionary of discovered devices (DeviceInfo objects for fast listing)
        """
        try:
            if not self.session:
                if output_json:
                    error = {"success": False, "error": "Not authenticated"}
                    self.console.print(json.dumps(error))
                    return {}
                else:
                    self.console.print("[red]✗ Not authenticated. Run 'tuya login' first.[/red]")
                    return {}

            # Check if we should use cached devices or do fresh discovery
            if not force_refresh and self.cached_device_info:
                # Use cached device info to reconstruct DeviceInfo objects
                devices_info = []
                for device_id, cached_info in self.cached_device_info.items():
                    # Create minimal DeviceInfo from cached data
                    from libtuya.auth.models import DeviceInfo
                    device_info = DeviceInfo(
                        id=device_id,
                        name=cached_info["name"],
                        category=cached_info["category"],
                        online=cached_info.get("online", True),
                        local_key=cached_info.get("local_key", ""),
                        product_id=cached_info.get("product_id", ""),
                        product_name="",
                        ip=cached_info.get("ip", ""),
                        uuid=cached_info.get("uuid", ""),
                        asset_id=""
                    )
                    # Add cached category name for display
                    device_info.category_name = cached_info.get("category_name", cached_info["category"].title())
                    devices_info.append(device_info)
                
                if self.verbose:
                    self.console.print(f"[dim]Using cached device information for {len(devices_info)} devices[/dim]")
            else:
                # Perform device discovery and create IntelligentDevice objects for analysis
                devices_info = self.device_manager.discover_devices()
                
                # Create IntelligentDevice objects to get proper intelligence analysis
                intelligent_devices = []
                for device_info in devices_info:
                    try:
                        created_devices = self.device_manager.create_devices(device_info)
                        intelligent_devices.extend(created_devices)
                    except Exception as e:
                        logger.error(f"Failed to create device for {device_info.id}: {e}")
                
                # Store IntelligentDevice objects which contain full analysis
                self.devices = {device.id: device for device in intelligent_devices}
                
                # Update devices_info to point to the IntelligentDevice objects for consistent processing
                devices_info = intelligent_devices

            if devices_info:
                # Store devices for consistent access
                if not hasattr(devices_info[0], 'device_analysis'):
                    # For cached DeviceInfo objects, store them in self.devices
                    self.devices = {device_info.id: device_info for device_info in devices_info}

                # Update device indices and cache
                sorted_devices = sorted(devices_info, key=lambda d: d.name.lower())
                self.device_indices = self.device_resolver.update_device_indices(
                    sorted_devices, self.device_indices
                )

                # Update cached device info
                self.cached_device_info = {}
                for device in devices_info:
                    # Handle both IntelligentDevice (fresh discovery) and DeviceInfo (cached)
                    device_id = device.id if hasattr(device, 'id') else device.device_id
                    device_name = device.name
                    device_category = device.category if hasattr(device, 'category') else device.device_info.category
                    device_online = device.online if hasattr(device, 'online') else getattr(device.device_info, 'online', True)
                    
                    device_index = next(
                        (idx for idx, did in self.device_indices.items() if did == device_id),
                        None,
                    )
                    
                    # Get category name from intelligence analysis for IntelligentDevice objects
                    if hasattr(device, 'device_analysis') and device.device_analysis:
                        category_name = device.device_analysis.category_name
                    elif hasattr(device, 'category_name'):
                        category_name = device.category_name
                    else:
                        category_name = device_category.title()
                    
                    # Extract device info for caching
                    device_info_obj = device.device_info if hasattr(device, 'device_info') else device
                    
                    self.cached_device_info[device_id] = {
                        "name": device_name,
                        "category": device_category,
                        "category_name": category_name,
                        "index": device_index,
                        "online": device_online,
                        "ip": getattr(device_info_obj, 'ip', ''),
                        "local_key": getattr(device_info_obj, 'local_key', ''),
                        "product_id": getattr(device_info_obj, 'product_id', ''),
                        "uuid": getattr(device_info_obj, 'uuid', ''),
                    }

                self._save_device_cache()

                if not output_json:
                    self.console.print(f"[green]✓ Found {len(devices_info)} devices[/green]")

                return self.devices
            else:
                if output_json:
                    result = {"success": True, "devices": [], "count": 0}
                    self.console.print(json.dumps(result))
                else:
                    self.console.print("[yellow]No devices found[/yellow]")
                return {}

        except Exception as e:
            logger.error(f"Device discovery error: {e}")
            if output_json:
                error = {"success": False, "error": str(e)}
                self.console.print(json.dumps(error))
            else:
                self.console.print(f"[red]✗ Device discovery error: {e}[/red]")
            return {}

    def resolve_device_identifier(self, identifier: str) -> Optional[str]:
        """Resolve device identifier to device ID."""
        return self.device_resolver.resolve_device_identifier(
            identifier,
            self.device_indices,
            self.devices,
            self.cached_device_info,
        )

    def control_device(
        self,
        device_id: str,
        action: str,
        value: Optional[str] = None,
        output_json: bool = False,
    ) -> bool:
        """
        Control a device with the specified action and value.

        Args:
            device_id: Device identifier (ID, name, or index)
            action: Action to perform (on, off, brightness, etc.)
            value: Optional value for the action
            output_json: Output result as JSON

        Returns:
            True if control successful, False otherwise
        """
        try:
            # Ensure we have devices available
            if not self.cached_device_info and not self.devices:
                self.discover_devices(output_json=False)
                if not self.cached_device_info and not self.devices:
                    if output_json:
                        error = {
                            "success": False,
                            "error": "No devices available",
                        }
                        self.console.print(json.dumps(error))
                    else:
                        self.console.print(
                            "[red]✗ No devices available. Run 'tuya devices' first.[/red]"
                        )
                    return False

            # Resolve device identifier
            resolved_device_id = self.resolve_device_identifier(device_id)
            if not resolved_device_id:
                if output_json:
                    error = {
                        "success": False,
                        "error": f"Device '{device_id}' not found",
                    }
                    self.console.print(json.dumps(error))
                else:
                    self.console.print(f"[red]✗ Device '{device_id}' not found[/red]")
                return False

            # Get device object - lazy create IntelligentDevice when needed
            device = self.device_manager.get_device(resolved_device_id)
            if not device:
                # Device not in registry - create it lazily from DeviceInfo
                device_info = self.devices.get(resolved_device_id)
                if not device_info:
                    if output_json:
                        error = {
                            "success": False,
                            "error": f"Device {resolved_device_id} not found",
                        }
                        self.console.print(json.dumps(error))
                    else:
                        self.console.print(
                            f"[red]✗ Device {resolved_device_id} not found[/red]"
                        )
                    return False
                
                # Create IntelligentDevice lazily
                try:
                    created_devices = self.device_manager.create_devices(device_info)
                    device = created_devices[0] if created_devices else None
                    if not device:
                        if output_json:
                            error = {
                                "success": False,
                                "error": f"Could not create device {resolved_device_id}",
                            }
                            self.console.print(json.dumps(error))
                        else:
                            self.console.print(
                                f"[red]✗ Could not create device {resolved_device_id}[/red]"
                            )
                        return False
                except Exception as e:
                    if output_json:
                        error = {
                            "success": False,
                            "error": f"Device creation failed: {e}",
                        }
                        self.console.print(json.dumps(error))
                    else:
                        self.console.print(
                            f"[red]✗ Device creation failed: {e}[/red]"
                        )
                    return False

            # Validate input if value provided
            if value:
                is_valid, error_msg = self.value_parser.validate_input_format(value, action)
                if not is_valid:
                    if output_json:
                        error = {"success": False, "error": error_msg}
                        self.console.print(json.dumps(error))
                    else:
                        self.console.print(f"[red]✗ {error_msg}[/red]")
                    return False

            # Execute device control
            success = device.execute_command(action, value)

            if success:
                if output_json:
                    result = {
                        "success": True,
                        "device": device.name,
                        "action": action,
                        "value": value,
                    }
                    self.console.print(json.dumps(result))
                else:
                    value_part = f" to {value}" if value else ""
                    self.console.print(f"[green]✓ Set {device.name} {action}{value_part}[/green]")
                return True
            else:
                if output_json:
                    error = {
                        "success": False,
                        "error": f"Command failed on device {device.name}",
                    }
                    self.console.print(json.dumps(error))
                else:
                    self.console.print(f"[red]✗ Command failed on device {device.name}[/red]")
                return False

        except Exception as e:
            logger.error(f"Device control error: {e}")
            if output_json:
                error = {"success": False, "error": str(e)}
                self.console.print(json.dumps(error))
            else:
                self.console.print(f"[red]✗ Device control error: {e}[/red]")
            return False
