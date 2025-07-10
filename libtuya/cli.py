#!/usr/bin/env python3
"""
LibTuya CLI - Command-line interface for Tuya device control
"""

import asyncio
import json
import logging
import sys
import os
import time
from pathlib import Path
from typing import Optional
import click
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt
from rich.panel import Panel
import qrcode

from libtuya.auth import TuyaAuthenticator
from libtuya.auth.models import AuthSession
from libtuya.devices import DeviceManager
from libtuya.intelligence import DeviceIntelligence
from libtuya.dps import DPSMapper
from libtuya.recovery import RecoveryManager

console = Console()

# Session and device cache storage file paths
SESSION_FILE = Path.home() / ".libtuya" / "session.json"
DEVICE_CACHE_FILE = Path.home() / ".libtuya" / "device_cache.json"


class TuyaCLI:
    def __init__(self):
        # Reduce logging verbosity for cleaner user experience
        logging.getLogger("libtuya").setLevel(logging.WARNING)
        
        self.authenticator = TuyaAuthenticator()
        self.device_manager = DeviceManager()
        self.intelligence = DeviceIntelligence()
        self.dps_mapper = DPSMapper()
        self.recovery = RecoveryManager()
        self.session = None
        self.devices = {}
        self.device_indices = {}
        self.cached_device_info = {}
        
        # Try to load existing session and devices
        self._load_session()
        self._load_device_cache()
    
    def _load_session(self) -> bool:
        """Load authentication session from file."""
        try:
            if SESSION_FILE.exists():
                with open(SESSION_FILE, 'r') as f:
                    session_data = json.load(f)
                    session = AuthSession.from_dict(session_data)
                    
                    # Check if session is expired before trying to restore
                    if session.is_expired:
                        user_display = session.uid if session.uid else session.user_code
                        console.print(f"[dim]Session expired for user {user_display}[/dim]")
                        self._clear_session()
                        return False
                    
                    # Restore the session without network validation
                    self.session = session
                    self.authenticator._current_session = session
                    try:
                        self.authenticator._initialize_device_manager()
                    except Exception as e:
                        console.print(f"[dim]Could not initialize device manager: {e}[/dim]")
                        return False
                    
                    user_display = session.uid if session.uid else session.user_code
                    console.print(f"[dim]Loaded existing session for user {user_display}[/dim]")
                    return True
        except Exception as e:
            console.print(f"[dim]Could not load session: {e}[/dim]")
            return False
        return False
    
    def _save_session(self) -> None:
        """Save authentication session to file."""
        try:
            if self.session:
                # Ensure directory exists
                SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
                
                # Save session data
                with open(SESSION_FILE, 'w') as f:
                    json.dump(self.session.to_dict(), f, indent=2)
                
                user_display = self.session.uid if self.session.uid else self.session.user_code
                console.print(f"[dim]Session saved for user {user_display}[/dim]")
        except Exception as e:
            console.print(f"[yellow]Warning: Could not save session: {e}[/yellow]")
    
    def _clear_session(self) -> None:
        """Clear stored session file."""
        try:
            if SESSION_FILE.exists():
                SESSION_FILE.unlink()
                console.print("[dim]Session cleared[/dim]")
        except Exception as e:
            console.print(f"[yellow]Warning: Could not clear session: {e}[/yellow]")

    def _load_device_cache(self) -> None:
        """Load device cache from file."""
        try:
            if DEVICE_CACHE_FILE.exists():
                with open(DEVICE_CACHE_FILE, 'r') as f:
                    cache_data = json.load(f)
                    
                # Check if cache is still valid (not older than 1 hour)
                cache_time = cache_data.get('timestamp', 0)
                current_time = time.time()
                if current_time - cache_time < 3600:  # 1 hour
                    # Load device indices and basic info
                    self.device_indices = cache_data.get('device_indices', {})
                    self.cached_device_info = cache_data.get('device_info', {})
                    
                    # Convert string keys back to integers for device_indices
                    self.device_indices = {int(k): v for k, v in self.device_indices.items()}
                    
                    if self.cached_device_info:
                        console.print(f"[dim]Loaded {len(self.cached_device_info)} devices from cache[/dim]")
                else:
                    console.print("[dim]Device cache expired[/dim]")
                    self.device_indices = {}
                    self.cached_device_info = {}
            else:
                self.device_indices = {}
                self.cached_device_info = {}
        except Exception as e:
            console.print(f"[dim]Could not load device cache: {e}[/dim]")
            self.device_indices = {}
            self.cached_device_info = {}

    def _save_device_cache(self) -> None:
        """Save device cache to file."""
        try:
            if self.devices and hasattr(self, 'device_indices'):
                # Ensure directory exists
                DEVICE_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
                
                # Create cache data with device information
                cache_data = {
                    'timestamp': time.time(),
                    'device_indices': self.device_indices,
                    'device_info': {}
                }
                
                # Store basic device info for each device
                for device_id, device in self.devices.items():
                    cache_data['device_info'][device_id] = {
                        'id': device.id,
                        'name': device.name,
                        'category': device.category,
                        'product_name': device.device_info.product_name,
                        'ip': device.device_info.ip,
                        'local_key': device.device_info.local_key,
                        'online': device.is_online,
                    }
                
                with open(DEVICE_CACHE_FILE, 'w') as f:
                    json.dump(cache_data, f, indent=2)
                
                console.print(f"[dim]Cached {len(self.devices)} devices[/dim]")
        except Exception as e:
            console.print(f"[dim]Warning: Could not save device cache: {e}[/dim]")

    def display_qr_code(self, qr_data: str) -> None:
        """Display QR code in terminal"""
        # Create a compact QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=1,
            border=1,
        )
        qr.add_data(qr_data)
        qr.make(fit=True)

        # Get the QR code matrix
        matrix = qr.get_matrix()
        
        # Create a compact display using half-block characters
        output = []
        for i in range(0, len(matrix), 2):
            row = ""
            for j in range(len(matrix[i])):
                top = matrix[i][j]
                bottom = matrix[i+1][j] if i+1 < len(matrix) else False
                
                if top and bottom:
                    row += "█"  # Full block
                elif top:
                    row += "▀"  # Upper half block
                elif bottom:
                    row += "▄"  # Lower half block
                else:
                    row += " "  # Empty space
            output.append(row)
        
        qr_output = "\n".join(output)

        # Display with rich
        console.print(
            Panel(
                qr_output,
                title="[bold blue]Scan QR Code with Smart Life App[/bold blue]",
                border_style="blue",
            )
        )
        
        # Also show the QR code data as a clickable link for easier access
        console.print(f"\n[dim]QR Code Data: {qr_data}[/dim]")

    async def authenticate(self, user_code: Optional[str] = None) -> bool:
        """Authenticate with Tuya cloud"""
        if not user_code:
            user_code = Prompt.ask("Enter a unique user code", default="libtuya-cli")

        try:
            # Reduce logging verbosity during authentication
            libtuya_logger = logging.getLogger("libtuya")
            original_level = libtuya_logger.level
            libtuya_logger.setLevel(logging.ERROR)  # Only show errors

            try:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console,
                ) as progress:
                    task = progress.add_task("Generating QR code...", total=None)

                    self.authenticator.start_qr_auth(user_code)
                    progress.update(task, description="QR code generated")

                    # Extract the actual QR code data from the authenticator and format it properly for Smart Life app
                    token = self.authenticator._last_qr_data.qr_code if self.authenticator._last_qr_data else "NO_QR_DATA"
                    # Format the QR code data as expected by Smart Life app
                    qr_data = f"tuyaSmart--qrLogin?token={token}"
                    self.display_qr_code(qr_data)

                    console.print("\n[bold cyan]Instructions:[/bold cyan]")
                    console.print("1. Open Smart Life app on your phone")
                    console.print("2. Look for QR code login option (usually in profile/settings)")
                    console.print("3. Scan the QR code above")
                    console.print("4. Grant permissions when prompted")
                    console.print("\n[green]Press Enter after you've scanned the QR code...[/green]")
                    
                    progress.update(task, description="Waiting for you to scan...")
                    
                    # Wait for user to press Enter (safer approach for asyncio)
                    try:
                        await asyncio.get_event_loop().run_in_executor(None, lambda: input())
                    except EOFError:
                        pass  # Handle case where input is interrupted
                    
                    progress.update(task, description="Checking authentication...")

                    # Wait for authentication with longer timeout and faster polling
                    self.session = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: self.authenticator.wait_for_auth(timeout=600, poll_interval=1)
                    )

                    progress.update(task, description="Authentication successful!")
                    
            finally:
                # Restore original logging level
                libtuya_logger.setLevel(original_level)

            # Show user-friendly session info
            user_display = self.session.uid if self.session.uid else self.session.user_code
            console.print(f"[green]✓ Authenticated as: {user_display}[/green]")
            console.print(f"[dim]Session expires in: {self.session.expires_in_minutes} minutes[/dim]")
            
            # Save the session for future use
            self._save_session()
            return True

        except asyncio.TimeoutError:
            console.print("[red]✗ Authentication timed out. Please try again.[/red]")
            return False
        except Exception as e:
            console.print(f"[red]✗ Authentication failed: {str(e)}[/red]")
            return False

    async def discover_devices(self, output_json: bool = False) -> None:
        """Discover devices from Tuya cloud"""
        if not self.session and not self.authenticator.is_authenticated():
            if output_json:
                import json
                error = {"success": False, "error": "Authentication required", "message": "Please authenticate first"}
                console.print(json.dumps(error))
                return
            else:
                console.print("[red]✗ Please authenticate first[/red]")
                return

        try:
            # Temporarily reduce logging verbosity during discovery
            import logging
            libtuya_logger = logging.getLogger("libtuya")
            original_level = libtuya_logger.level
            libtuya_logger.setLevel(logging.WARNING)

            try:
                if not output_json:
                    with Progress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        console=console,
                    ) as progress:
                        task = progress.add_task("Discovering devices...", total=None)

                        device_infos = await asyncio.get_event_loop().run_in_executor(
                            None, self.authenticator.get_devices_with_keys
                        )
                        progress.update(task, description="Creating intelligent devices...")

                        self.devices = {}
                        for device_info in device_infos:
                            try:
                                # create_devices returns a list of devices (usually 1)
                                created_devices = self.device_manager.create_devices(
                                    device_info=device_info,
                                    intelligence=self.intelligence,
                                    dps_mapper=self.dps_mapper,
                                )
                                for device in created_devices:
                                    self.devices[device.id] = device
                            except Exception as e:
                                console.print(
                                    f"[yellow]⚠ Warning: Could not create device(s) for {device_info.name}: {str(e)}[/yellow]"
                                )

                        progress.update(task, description="Discovery complete!")
                else:
                    # Silent discovery for JSON output
                    device_infos = await asyncio.get_event_loop().run_in_executor(
                        None, self.authenticator.get_devices_with_keys
                    )

                    self.devices = {}
                    for device_info in device_infos:
                        try:
                            # create_devices returns a list of devices (usually 1)
                            created_devices = self.device_manager.create_devices(
                                device_info=device_info,
                                intelligence=self.intelligence,
                                dps_mapper=self.dps_mapper,
                            )
                            for device in created_devices:
                                self.devices[device.id] = device
                        except Exception:
                            # Silent failure for JSON mode
                            pass
            finally:
                # Restore original logging level
                libtuya_logger.setLevel(original_level)

            if not output_json:
                console.print(f"[green]✓ Discovered {len(self.devices)} devices[/green]")
                
                # Show a summary table of discovered devices
                if self.devices:
                    self._show_device_summary(output_json=False)
            
            # Save device cache for future use
            self._save_device_cache()

        except Exception as e:
            if output_json:
                import json
                error = {"success": False, "error": "Discovery failed", "message": str(e)}
                console.print(json.dumps(error))
            else:
                console.print(f"[red]✗ Device discovery failed: {str(e)}[/red]")

    def _show_device_summary(self, output_json: bool = False):
        """Show a summary table of discovered devices"""
        if output_json:
            import json
            devices_data = []
            sorted_devices = sorted(self.devices.values(), key=lambda d: (d.category, d.name))
            
            # Store device index mapping for easy reference
            self.device_indices = {}
            
            for i, device in enumerate(sorted_devices, 1):
                self.device_indices[i] = device.id
                
                device_data = {
                    "index": i,
                    "id": device.id,
                    "name": device.name,
                    "category": device.category,
                    "type": self._get_detailed_device_type(device),
                    "product": device.device_info.product_name,
                    "online": device.is_online,
                    "ip": device.device_info.ip or None,
                    "local_key": device.device_info.local_key[:8] + "..." if device.device_info.local_key else None,
                    "dps_mappings": len(device.dps_mappings) if hasattr(device, 'dps_mappings') else 0,
                    "protocol_version": getattr(device.device_info, 'protocol_version', None),
                    "uuid": device.device_info.uuid,
                    "support_local": getattr(device.device_info, 'support_local', False)
                }
                devices_data.append(device_data)
            
            result = {
                "success": True,
                "device_count": len(self.devices),
                "devices": devices_data
            }
            console.print(json.dumps(result))
        else:
            from rich.table import Table
            
            table = Table(title="Tuya Devices", show_header=True, header_style="bold blue")
            table.add_column("#", style="dim", justify="center", min_width=3)
            table.add_column("Name", style="white", min_width=25)
            table.add_column("Type", style="cyan", min_width=15)
            table.add_column("Product", style="yellow", min_width=20)
            table.add_column("Status", justify="center", min_width=8)
            table.add_column("IP Address", style="blue", min_width=15)
            table.add_column("Local Key", style="magenta", min_width=12)
            table.add_column("Control Method", style="green", min_width=15)
            
            # Sort devices by category then by name and assign indices
            sorted_devices = sorted(self.devices.values(), key=lambda d: (d.category, d.name))
            
            # Store device index mapping for easy reference
            self.device_indices = {}
            
            for i, device in enumerate(sorted_devices, 1):
                self.device_indices[i] = device.id
                
                device_type = self._get_detailed_device_type(device)
                product_name = device.device_info.product_name[:17] + "..." if len(device.device_info.product_name) > 20 else device.device_info.product_name
                status = "Online" if device.is_online else "Offline"
                status_style = "green" if device.is_online else "red"
                
                # Show actual IP address as reported by Tuya API
                ip_addr = device.device_info.ip or "Unknown"
                local_key = device.device_info.local_key[:8] + "..." if device.device_info.local_key else "No Key"
                
                # Determine control method
                control_method = device._determine_control_method() # Call the new method
                control_method_display = control_method.capitalize()
                control_method_style = "green" if control_method == "local" else "yellow"

                table.add_row(
                    str(i),
                    device.name,
                    device_type,
                    product_name,
                    f"[{status_style}]{status}[/{status_style}]",
                    ip_addr,
                    local_key,
                    f"[{control_method_style}]{control_method_display}[/{control_method_style}]" # New cell
                )
            
            console.print()
            console.print(table)
            console.print()
            console.print("[dim]💡 Tip: Use device numbers (1, 2, 3...) or names for easy control:[/dim]")
            console.print("[dim]   tuya control 1 on[/dim]")
            console.print("[dim]   tuya control \"Small Lamp\" brightness 75[/dim]")
            console.print()

    def _show_cached_devices(self, output_json: bool = False):
        """Show cached devices without full discovery"""
        if not self.cached_device_info:
            if output_json:
                import json
                result = {"success": True, "device_count": 0, "devices": [], "message": "No cached devices available"}
                console.print(json.dumps(result))
            else:
                console.print("[yellow]No cached devices available. Run 'tuya devices' to discover devices.[/yellow]")
            return
        
        if output_json:
            import json
            devices_data = []
            for i, device_id in enumerate(sorted(self.cached_device_info.keys()), 1):
                device_info = self.cached_device_info[device_id]
                devices_data.append({
                    "index": i,
                    "id": device_id,
                    "name": device_info['name'],
                    "type": self._get_category_display_name(device_info['category']),
                    "category": device_info['category'],
                    "product": device_info['product_name'],
                    "online": device_info['online'],
                    "cached": True
                })
            
            result = {
                "success": True,
                "device_count": len(self.cached_device_info),
                "devices": devices_data,
                "cached": True
            }
            console.print(json.dumps(result))
        else:
            from rich.table import Table
            
            table = Table(title="Tuya Devices", show_header=True, header_style="bold blue")
            table.add_column("#", style="dim", justify="center", min_width=3)
            table.add_column("Name", style="white", min_width=25)
            table.add_column("Type", style="cyan", min_width=15)
            table.add_column("Product", style="yellow", min_width=20)
            table.add_column("Status", justify="center", min_width=8)
            
            for i, device_id in enumerate(sorted(self.cached_device_info.keys()), 1):
                device_info = self.cached_device_info[device_id]
                status = "Online" if device_info['online'] else "Offline"
                status_style = "green" if device_info['online'] else "red"
                device_type = self._get_category_display_name(device_info['category'])
                product_name = device_info['product_name'][:17] + "..." if len(device_info['product_name']) > 20 else device_info['product_name']
                
                table.add_row(
                    str(i),
                    device_info['name'],
                    device_type,
                    product_name,
                    f"[{status_style}]{status}[/{status_style}]"
                )
            
            console.print()
            console.print(table)
            console.print()
            console.print("[dim]💡 Use device numbers or names for control: tuya control 1 on[/dim]")
            console.print("[dim]   Run 'tuya devices --refresh' for updated status[/dim]")
            console.print()

    def _get_category_display_name(self, category: str) -> str:
        """Get a human-readable display name for a device category"""
        category_names = {
            "dj": "Lights",
            "kg": "Switches", 
            "kt": "Air Conditioners",
            "qn": "Heaters/Thermostats",
            "pc": "Power Sockets",
            "pir": "PIR Sensors",
            "zndb": "Smart Locks",
            "cl": "Curtains/Covers",
            "fs": "Fans",
            "sp": "Cameras",
            "jsq": "Humidifiers",
            "kj": "Air Purifiers",
            "cjkg": "Scene Controllers",
        }
        return category_names.get(category, f"Unknown ({category})")

    def _get_detailed_device_type(self, device) -> str:
        """Get a detailed device type based on category and product name"""
        category = device.category
        product_name = device.device_info.product_name.lower()
        
        # Special handling for qn category (heaters/thermostats)
        if category == "qn":
            if "thermostat" in product_name or "temp" in product_name:
                return "Thermostat"
            elif "heater" in product_name or "radiator" in product_name:
                return "Heater"
            elif "valve" in product_name:
                return "Radiator Valve"
            else:
                # Try to guess from the device name
                device_name = device.name.lower()
                if "thermostat" in device_name or any(word in device_name for word in ["ac ", "hvac"]):
                    return "Thermostat"
                elif any(word in device_name for word in ["heater", "radiator", "heating"]):
                    return "Heater"
                else:
                    return "Climate Device"
        
        # Use the standard category names for other devices
        return self._get_category_display_name(category)
    
    def _resolve_device_identifier(self, identifier: str) -> Optional[str]:
        """
        Resolve a device identifier to a device ID.
        
        Args:
            identifier: Can be:
                - Device index number (1, 2, 3, etc.)
                - Full device ID  
                - Partial device name (case-insensitive)
                - Full device name (case-insensitive)
        
        Returns:
            Device ID if found, None otherwise
        """
        # Use cached device info if available, otherwise use full devices
        device_source = self.cached_device_info if self.cached_device_info else {}
        if not device_source and not self.devices:
            return None
            
        # Try as device index first
        try:
            index = int(identifier)
            if index in self.device_indices:
                return self.device_indices[index]
        except ValueError:
            pass
        
        # Try as exact device ID
        if self.devices and identifier in self.devices:
            return identifier
        elif identifier in device_source:
            return identifier
            
        # Try partial matching on device names (case-insensitive)
        identifier_lower = identifier.lower()
        matches = []
        
        # Search in cached device info first
        if device_source:
            for device_id, device_info in device_source.items():
                device_name_lower = device_info['name'].lower()
                # Exact name match
                if device_name_lower == identifier_lower:
                    return device_id
                # Partial name match
                elif identifier_lower in device_name_lower:
                    matches.append({'id': device_id, 'name': device_info['name']})
        
        # If no cached info, search in full devices
        elif self.devices:
            for device in self.devices.values():
                device_name_lower = device.name.lower()
                # Exact name match
                if device_name_lower == identifier_lower:
                    return device.id
                # Partial name match
                elif identifier_lower in device_name_lower:
                    matches.append({'id': device.id, 'name': device.name})
        
        # If we have exactly one partial match, use it
        if len(matches) == 1:
            return matches[0]['id']
            
        # If multiple matches, show them to the user
        if len(matches) > 1:
            console.print(f"[yellow]Multiple devices match '{identifier}':[/yellow]")
            for i, device in enumerate(matches, 1):
                console.print(f"  {i}. {device['name']}")
            console.print("[yellow]Please be more specific.[/yellow]")
            
        return None


    async def control_device(
        self, device_id: str, action: str, value: Optional[str] = None, output_json: bool = False
    ) -> None:
        """Control a specific device"""
        # Check if we have cached device info first
        if not self.cached_device_info and not self.devices:
            if output_json:
                import json
                error = {"success": False, "error": "No devices available", "message": "Run 'tuya devices' first"}
                console.print(json.dumps(error))
            else:
                console.print("[red]✗ No devices available. Run 'tuya devices' first.[/red]")
            return

        # Resolve device identifier using cached info
        resolved_device_id = self._resolve_device_identifier(device_id)
        if not resolved_device_id:
            if output_json:
                import json
                error = {"success": False, "error": "Device not found", "message": f"Device '{device_id}' not found"}
                console.print(json.dumps(error))
            else:
                console.print(f"[red]✗ Device '{device_id}' not found[/red]")
                console.print(f"[dim]Use device number, name, or partial name. Run 'tuya devices' to see available devices.[/dim]")
            return
        
        # If we only have cached info, we need to discover to get full device objects
        if not self.devices and self.cached_device_info:
            if not output_json:
                console.print("[dim]Loading full device information...[/dim]")
            await self.discover_devices(output_json=True)  # Silent discovery
            
            if not self.devices:
                if output_json:
                    import json
                    error = {"success": False, "error": "Device discovery failed", "message": "Could not load full device information"}
                    console.print(json.dumps(error))
                else:
                    console.print("[red]✗ Could not load full device information[/red]")
                return
            
        device = self.devices[resolved_device_id]

        try:
            result = {"success": False, "action": action, "device": device.name, "message": ""}
            
            # Execute action
            if action == "on":
                success = device.turn_on()
                result["success"] = success
                result["message"] = "Device turned on" if success else "Failed to turn on device"
            elif action == "off":
                success = device.turn_off()
                result["success"] = success
                result["message"] = "Device turned off" if success else "Failed to turn off device"
            elif action == "toggle":
                # For toggle, we need to get current status first
                try:
                    current_status = device.get_status()
                    # Try to determine current state and toggle
                    success = device.turn_off() if device.is_on else device.turn_on()
                    result["success"] = success
                    result["message"] = "Device toggled" if success else "Failed to toggle device"
                except:
                    result["success"] = False
                    result["message"] = "Failed to toggle device - could not determine current state"
            elif action == "status":
                try:
                    status = device.get_status()
                    result["success"] = True
                    
                    # Format the status for better readability
                    formatted_status = {
                        "online": status.online,
                        "last_update": status.last_update.isoformat() if status.last_update else None,
                        "capabilities": {}
                    }
                    
                    # Add raw DPS values for debugging
                    formatted_status["raw_dps"] = status.raw_dps
                    
                    # Add capability values with human-readable names
                    for cap_name, capability in status.capabilities.items():
                        formatted_status["capabilities"][cap_name] = {
                            "value": capability.current_value,
                            "dps": capability.dps_index,
                            "type": capability.data_type
                        }
                    
                    # Add any errors
                    if status.errors:
                        formatted_status["errors"] = status.errors
                    
                    result["status"] = formatted_status
                    result["message"] = "Status retrieved successfully"
                except Exception as e:
                    result["success"] = False
                    result["message"] = f"Failed to get status: {str(e)}"
            elif action == "brightness":
                if not value:
                    result["message"] = "Brightness value required"
                else:
                    try:
                        brightness = int(value)
                        if hasattr(device, "set_brightness_percentage"):
                            success = device.set_brightness_percentage(brightness)
                            result["success"] = success
                            result["brightness"] = brightness
                            result["message"] = f"Brightness set to {brightness}%" if success else f"Failed to set brightness to {brightness}%"
                        else:
                            result["message"] = "Device does not support brightness control"
                    except ValueError:
                        result["message"] = "Invalid brightness value - must be a number"
            elif action == "color":
                if not value:
                    result["message"] = "Color value required"
                else:
                    if hasattr(device, "set_color_hex"):
                        try:
                            success = device.set_color_hex(value)
                            result["success"] = success
                            result["color"] = value
                            result["message"] = f"Color set to {value}" if success else f"Failed to set color to {value}"
                        except Exception as e:
                            result["message"] = f"Failed to set color: {str(e)}"
                    else:
                        result["message"] = "Device does not support color control"
            else:
                result["message"] = f"Unknown action '{action}'"

            # Output result
            if output_json:
                import json
                console.print(json.dumps(result))
            else:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console,
                ) as progress:
                    task = progress.add_task(
                        f"Controlling {device.device_info.name}...", total=None
                    )
                    progress.update(task, description="Command executed!")
                
                if result["success"]:
                    if action == "status":
                        status_info = result.get('status', {})
                        console.print(f"[green]✓ Device Status for {device.name}[/green]")
                        console.print(f"[dim]Online:[/dim] {'Yes' if status_info.get('online') else 'No'}")
                        
                        if status_info.get('last_update'):
                            console.print(f"[dim]Last Update:[/dim] {status_info['last_update']}")
                        
                        # Show capabilities in a user-friendly way
                        capabilities = status_info.get('capabilities', {})
                        if capabilities:
                            console.print(f"[dim]Device State:[/dim]")
                            for cap_name, cap_info in capabilities.items():
                                value = cap_info.get('value')
                                if cap_name == 'switch' or cap_name == 'switch_1':
                                    display_value = "On" if value else "Off"
                                elif cap_name == 'brightness' and isinstance(value, (int, float)):
                                    display_value = f"{value}%"
                                elif cap_name == 'color_temp' and isinstance(value, (int, float)):
                                    display_value = f"{value}K"
                                else:
                                    display_value = str(value)
                                console.print(f"  • {cap_name.replace('_', ' ').title()}: {display_value}")
                        
                        # Show raw DPS for debugging if no capabilities found
                        raw_dps = status_info.get('raw_dps', {})
                        if not capabilities and raw_dps:
                            console.print(f"[dim]Raw DPS Values:[/dim]")
                            for dps, value in raw_dps.items():
                                console.print(f"  • DPS {dps}: {value}")
                        elif not capabilities and not raw_dps:
                            console.print(f"[yellow]No device state data available - device may be offline or not responding[/yellow]")
                        
                        # Show any errors
                        if status_info.get('errors'):
                            console.print(f"[yellow]Errors:[/yellow]")
                            for error in status_info['errors']:
                                console.print(f"  • {error}")
                    else:
                        console.print(f"[green]✓ {result['message']}[/green]")
                else:
                    console.print(f"[red]✗ {result['message']}[/red]")
                    
            if not result["success"] and action != "status" and not output_json:
                sys.exit(1)

        except Exception as e:
            if output_json:
                import json
                error = {"success": False, "error": "Control failed", "message": str(e)}
                console.print(json.dumps(error))
            else:
                # Try recovery if available
                try:
                    await self.recovery.recover_device_connection(e, device)
                    console.print(f"[yellow]⚠ Recovered from error, retrying...[/yellow]")
                    await self.control_device(device_id, action, value, output_json)
                except:
                    console.print(f"[red]✗ Control failed: {str(e)}[/red]")

    async def device_info(self, device_id: str, output_json: bool = False) -> None:
        """Show detailed device information"""
        if not self.devices:
            # Auto-discover devices if not available
            if not output_json:
                console.print("[dim]No devices loaded, discovering...[/dim]")
            await self.discover_devices(output_json=True)  # Silent discovery
            
            if not self.devices:
                if output_json:
                    import json
                    error = {"success": False, "error": "No devices available", "message": "Run 'tuya devices' first"}
                    console.print(json.dumps(error))
                else:
                    console.print("[red]✗ No devices available. Run 'tuya devices' first.[/red]")
                return

        # Resolve device identifier
        resolved_device_id = self._resolve_device_identifier(device_id)
        if not resolved_device_id:
            if output_json:
                import json
                error = {"success": False, "error": "Device not found", "message": f"Device '{device_id}' not found"}
                console.print(json.dumps(error))
            else:
                console.print(f"[red]✗ Device '{device_id}' not found[/red]")
                console.print(f"[dim]Use device number, name, or partial name. Run 'tuya devices' to see available devices.[/dim]")
            return
            
        device = self.devices[resolved_device_id]

        info = device.device_info

        # Create info panel
        info_text = f"""
[bold]Device Information[/bold]
Name: {info.name}
Device ID: {info.device_id}
Category: {info.category}
Local IP: {info.local_ip or 'Unknown'}
Protocol Version: {info.protocol_version or 'Auto-detect'}
Local Key: {info.local_key[:8]}...

[bold]Capabilities[/bold]
"""

        try:
            analysis = self.intelligence.analyze_device(info.category)
            for capability in analysis.capabilities:
                info_text += f"• {capability}\n"

            if analysis.has_quirks:
                info_text += f"\n[bold yellow]Device Quirks:[/bold yellow] Present"
        except:
            info_text += "• Could not analyze capabilities"

        if output_json:
            import json
            device_data = {
                "name": info.name,
                "device_id": info.id,
                "category": info.category,
                "type": self._get_detailed_device_type(device),
                "product": info.product_name,
                "online": device.is_online,
                "local_ip": getattr(info, 'ip', None),
                "protocol_version": getattr(info, 'protocol_version', None),
                "local_key": info.local_key[:8] + "..." if info.local_key else None,
                "dps_mappings": len(device.dps_mappings),
                "capabilities": []
            }
            
            try:
                analysis = self.intelligence.analyze_device(info.category)
                device_data["capabilities"] = analysis.capabilities
                device_data["has_quirks"] = analysis.has_quirks
            except:
                device_data["capabilities"] = []
                device_data["has_quirks"] = False
                
            console.print(json.dumps(device_data))
        else:
            console.print(
                Panel(
                    info_text,
                    title=f"[bold blue]{info.name}[/bold blue]",
                    border_style="blue",
                )
            )


@click.group()
@click.version_option(version="1.0.0")
def cli():
    """Tuya CLI - Control your Tuya smart devices"""
    pass


@cli.command()
@click.option("--user-code", "-u", help="Unique user code for authentication")
@click.option("--json", "output_json", is_flag=True, help="Output result as JSON")
def login(user_code: Optional[str], output_json: bool):
    """Authenticate with Tuya cloud via QR code"""
    tuya_cli = TuyaCLI()
    success = asyncio.run(tuya_cli.authenticate(user_code))
    
    if output_json:
        import json
        result = {"success": success, "authenticated": success}
        console.print(json.dumps(result))
    else:
        if success:
            console.print(
                "[green]Authentication successful! You can now run 'tuya devices' to see your devices.[/green]"
            )
        else:
            console.print("[red]Authentication failed. Please try again.[/red]")
            
    if not success and not output_json:
        sys.exit(1)


@cli.command()
@click.option("--json", "output_json", is_flag=True, help="Output result as JSON")
@click.option("--cached", is_flag=True, help="Show cached devices without discovery")
@click.option("--refresh", is_flag=True, help="Force fresh discovery even if cache exists")
def devices(output_json: bool, cached: bool, refresh: bool):
    """List Tuya devices using cached data when available
    
    By default, uses cached device data if available (refreshed every hour).
    Use --refresh to force fresh discovery or --cached to explicitly show cache status.
    """
    tuya_cli = TuyaCLI()
    
    # Check authentication first
    if not tuya_cli.session and not tuya_cli.authenticator.is_authenticated():
        if output_json:
            import json
            error = {"success": False, "error": "Authentication required", "message": "Please authenticate first"}
            console.print(json.dumps(error))
        else:
            console.print("[yellow]No devices found. Run 'tuya login' first and make sure you have devices in your Smart Life app.[/yellow]")
        return
    
    # If cached flag is used, show cached devices if available
    if cached and tuya_cli.cached_device_info:
        tuya_cli._show_cached_devices(output_json=output_json)
        return
    
    # If refresh is explicitly requested, always discover
    if refresh:
        asyncio.run(tuya_cli.discover_devices(output_json=output_json))
        return
    
    # If we have valid cached data and refresh wasn't requested, use cache
    if tuya_cli.cached_device_info:
        tuya_cli._show_cached_devices(output_json=output_json)
        return
    
    # No cache available, discover devices
    asyncio.run(tuya_cli.discover_devices(output_json=output_json))


@cli.command()
@click.argument("device_id")
@click.argument(
    "action",
    type=click.Choice(["on", "off", "toggle", "status", "brightness", "color"]),
)
@click.argument("value", required=False)
@click.option("--json", "output_json", is_flag=True, help="Output result as JSON")
def control(device_id: str, action: str, value: Optional[str], output_json: bool):
    """Control a device (on/off/toggle/status/brightness/color)
    
    DEVICE_ID can be:
    • Device number (1, 2, 3...) from 'tuya devices' command
    • Full or partial device name (case-insensitive)
    • Full device ID
    
    Examples:
    • tuya control 1 on
    • tuya control "Small Lamp" brightness 50
    • tuya control lamp toggle
    """
    tuya_cli = TuyaCLI()
    # Pass the output_json flag to the control method
    asyncio.run(tuya_cli.control_device(device_id, action, value, output_json))


@cli.command()
@click.argument("device_id")
@click.option("--json", "output_json", is_flag=True, help="Output result as JSON")
def info(device_id: str, output_json: bool):
    """Show detailed device information
    
    DEVICE_ID can be device number (from 'tuya devices'), name, or partial name.
    """
    tuya_cli = TuyaCLI()
    asyncio.run(tuya_cli.device_info(device_id, output_json))


@cli.command()
@click.option("--json", "output_json", is_flag=True, help="Output result as JSON")
def health(output_json: bool):
    """Check system health and connectivity"""
    tuya_cli = TuyaCLI()

    if not output_json:
        console.print("[bold]System Health Check[/bold]")

    # Check network connectivity
    console.print("• Network connectivity... ", end="")
    try:
        import socket

        socket.create_connection(("8.8.8.8", 53), timeout=3)
        console.print("[green]✓[/green]")
    except:
        console.print("[red]✗[/red]")

    # Check dependencies
    console.print("• Dependencies... ", end="")
    try:
        import tinytuya
        from tuya_sharing import Manager

        console.print("[green]✓[/green]")
    except ImportError as e:
        console.print(f"[red]✗ Missing: {e}[/red]")

    # Check authentication
    console.print("• Authentication... ", end="")
    if tuya_cli.session:
        console.print("[green]✓[/green]")
    else:
        console.print("[yellow]- Not authenticated[/yellow]")

    console.print("\n[green]Health check complete![/green]")


@cli.command()
@click.option("--json", "output_json", is_flag=True, help="Output result as JSON")
def logout(output_json: bool):
    """Clear stored authentication session"""
    tuya_cli = TuyaCLI()
    tuya_cli._clear_session()
    
    if output_json:
        import json
        result = {"success": True, "message": "Session cleared"}
        console.print(json.dumps(result))
    else:
        console.print("[green]✓ Session cleared[/green]")


@cli.command()
def debug_session():
    """Debug session loading and authentication state"""
    tuya_cli = TuyaCLI()
    
    console.print("[bold]Session Debug Information[/bold]")
    console.print(f"• Session file exists: {SESSION_FILE.exists()}")
    console.print(f"• Session loaded: {tuya_cli.session is not None}")
    console.print(f"• Authenticator authenticated: {tuya_cli.authenticator.is_authenticated()}")
    
    if tuya_cli.session:
        console.print(f"• Session UID: {tuya_cli.session.uid}")
        console.print(f"• Session expired: {tuya_cli.session.is_expired}")
        console.print(f"• Session expires in: {tuya_cli.session.expires_in_minutes} minutes")
    
    console.print(f"• Device manager initialized: {tuya_cli.authenticator.device_manager is not None}")
    
    if SESSION_FILE.exists():
        try:
            with open(SESSION_FILE, 'r') as f:
                session_data = json.load(f)
                console.print(f"• Session file UID: {session_data.get('uid', 'N/A')}")
                console.print(f"• Session file user_code: {session_data.get('user_code', 'N/A')}")
        except Exception as e:
            console.print(f"• Error reading session file: {e}")


def main():
    """Main CLI entry point"""
    cli()


if __name__ == "__main__":
    main()
