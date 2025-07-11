"""
Command Handler - CLI command execution and formatting

This module handles the execution of specific CLI commands and formats their output.
"""

import json
import logging
from typing import Any, Dict, Optional

from rich.console import Console
from rich.table import Table

logger = logging.getLogger(__name__)


class CommandHandler:
    """Handles execution and formatting of CLI commands."""

    def __init__(self, cli_core, console: Optional[Console] = None):
        """Initialize command handler with CLI core reference."""
        self.cli_core = cli_core
        self.console = console or Console(highlight=False)

    async def handle_devices_command(
        self,
        output_json: bool = False,
        verbose: bool = False,
        cached: bool = False,
        refresh: bool = False,
    ) -> None:
        """
        Handle the devices command - list available devices.

        Args:
            output_json: Output as JSON
            verbose: Show detailed information
            cached: Show only cached devices
            refresh: Force refresh discovery
        """
        try:
            if cached and self.cli_core.cached_device_info:
                # Show cached devices
                await self._show_cached_devices(output_json=output_json, verbose=verbose)
            else:
                # Discover devices (respecting refresh flag)
                devices = await self.cli_core.discover_devices(
                    output_json=False, force_refresh=refresh
                )
                if devices:
                    await self._show_device_summary(output_json=output_json, verbose=verbose)
                elif output_json:
                    result = {"success": True, "devices": [], "count": 0}
                    self.console.print(json.dumps(result))
                else:
                    self.console.print("[yellow]No devices found[/yellow]")

        except Exception as e:
            logger.error(f"Devices command error: {e}")
            if output_json:
                error = {"success": False, "error": str(e)}
                self.console.print(json.dumps(error))
            else:
                self.console.print(f"[red]✗ Error listing devices: {e}[/red]")

    async def handle_info_command(
        self, device_id: str, output_json: bool = False, verbose: bool = False
    ) -> None:
        """
        Handle the info command - show detailed device information.

        Args:
            device_id: Device identifier
            output_json: Output as JSON
            verbose: Show verbose information
        """
        try:
            # Resolve device identifier
            resolved_device_id = self.cli_core.resolve_device_identifier(device_id)
            if not resolved_device_id:
                if output_json:
                    error = {
                        "success": False,
                        "error": f"Device '{device_id}' not found",
                    }
                    self.console.print(json.dumps(error))
                else:
                    self.console.print(f"[red]✗ Device '{device_id}' not found[/red]")
                return

            # Get device object
            if resolved_device_id not in self.cli_core.devices:
                device = await self.cli_core.device_manager.get_device(resolved_device_id)
                if not device:
                    if output_json:
                        error = {
                            "success": False,
                            "error": f"Could not load device {resolved_device_id}",
                        }
                        self.console.print(json.dumps(error))
                    else:
                        self.console.print(
                            f"[red]✗ Could not load device {resolved_device_id}[/red]"
                        )
                    return
                self.cli_core.devices[resolved_device_id] = device
            else:
                device = self.cli_core.devices[resolved_device_id]

            # Get device status and information
            status = await device.get_status()

            if output_json:
                device_info = {
                    "success": True,
                    "device": {
                        "id": device.id,
                        "name": device.name,
                        "category": device.category,
                        "status": status,
                        "capabilities": [cap.name for cap in device.get_capabilities()],
                        "local_key": getattr(device, "local_key", None),
                        "ip": getattr(device, "ip", None),
                    },
                }
                if verbose:
                    device_info["device"]["raw_device_info"] = getattr(device, "_device_info", {})

                self.console.print(json.dumps(device_info, indent=2))
            else:
                self._display_device_info(device, status, verbose)

        except Exception as e:
            logger.error(f"Info command error: {e}")
            if output_json:
                error = {"success": False, "error": str(e)}
                self.console.print(json.dumps(error))
            else:
                self.console.print(f"[red]✗ Error getting device info: {e}[/red]")

    async def handle_health_command(self, output_json: bool = False, verbose: bool = False) -> None:
        """
        Handle the health command - show system health status.

        Args:
            output_json: Output as JSON
            verbose: Show verbose information
        """
        try:
            health_data = {
                "authentication": (
                    "authenticated" if self.cli_core.session else "not_authenticated"
                ),
                "devices_cached": len(self.cli_core.cached_device_info),
                "devices_loaded": len(self.cli_core.devices),
                "session_valid": (
                    self.cli_core.session and not self.cli_core.session.is_expired
                    if self.cli_core.session
                    else False
                ),
            }

            if verbose and self.cli_core.session:
                health_data["session_info"] = {
                    "user_code": self.cli_core.session.user_code,
                    "uid": self.cli_core.session.uid,
                    "expires_at": self.cli_core.session.expires_at,
                }

            if output_json:
                result = {"success": True, "health": health_data}
                self.console.print(json.dumps(result, indent=2))
            else:
                self._display_health_status(health_data, verbose)

        except Exception as e:
            logger.error(f"Health command error: {e}")
            if output_json:
                error = {"success": False, "error": str(e)}
                self.console.print(json.dumps(error))
            else:
                self.console.print(f"[red]✗ Error checking health: {e}[/red]")

    async def _show_cached_devices(self, output_json: bool = False, verbose: bool = False) -> None:
        """Show cached devices without discovery."""
        if not self.cli_core.cached_device_info:
            if output_json:
                result = {
                    "success": True,
                    "devices": [],
                    "count": 0,
                    "source": "cache",
                }
                self.console.print(json.dumps(result))
            else:
                self.console.print("[yellow]No cached devices found[/yellow]")
                self.console.print("[dim]Run 'tuya devices --refresh' to discover devices[/dim]")
            return

        if output_json:
            devices_list = []
            for (
                device_id,
                device_info,
            ) in self.cli_core.cached_device_info.items():
                device_data = {
                    "id": device_id,
                    "name": device_info["name"],
                    "category": device_info["category"],
                    "index": device_info.get("index"),
                }
                devices_list.append(device_data)

            result = {
                "success": True,
                "devices": devices_list,
                "count": len(devices_list),
                "source": "cache",
            }
            self.console.print(json.dumps(result, indent=2))
        else:
            table = Table(show_header=True, header_style="bold blue")
            table.add_column("Index", style="dim", width=6)
            table.add_column("Name", style="cyan")
            table.add_column("Type", style="green")
            table.add_column("Status", style="yellow")

            for (
                device_id,
                device_info,
            ) in self.cli_core.cached_device_info.items():
                table.add_row(
                    str(device_info.get("index", "")),
                    device_info["name"],
                    self._get_category_display_name(device_info["category"]),
                    "[dim]cached[/dim]",
                )

            self.console.print(
                f"\n[bold]Cached Devices ({len(self.cli_core.cached_device_info)}):[/bold]"
            )
            self.console.print(table)
            self.console.print(
                "\n[dim]Note: Showing cached data. Use --refresh for live status.[/dim]"
            )

    async def _show_device_summary(self, output_json: bool = False, verbose: bool = False) -> None:
        """Show discovered devices summary."""
        if not self.cli_core.devices:
            return

        devices_list = list(self.cli_core.devices.values())

        if output_json:
            json_devices = []
            for device in devices_list:
                device_index = next(
                    (idx for idx, did in self.cli_core.device_indices.items() if did == device.id),
                    None,
                )
                device_data = {
                    "id": device.id,
                    "name": device.name,
                    "category": device.category,
                    "index": device_index,
                }
                if verbose:
                    # Add more details in verbose mode
                    device_data.update(
                        {
                            "capabilities": [cap.name for cap in device.get_capabilities()],
                            "local_key": getattr(device, "local_key", None),
                            "ip": getattr(device, "ip", None),
                        }
                    )
                json_devices.append(device_data)

            result = {
                "success": True,
                "devices": json_devices,
                "count": len(json_devices),
            }
            self.console.print(json.dumps(result, indent=2))
        else:
            table = self.cli_core.display_utils.create_device_table(
                [self._device_to_table_data(device) for device in devices_list],
                include_details=verbose,
            )

            self.console.print(f"\n[bold]Available Devices ({len(devices_list)}):[/bold]")
            self.console.print(table)
            self.console.print(
                f"\n[dim]Use: tuya control <device_name_or_number> <action> [value][/dim]"
            )

    def _device_to_table_data(self, device) -> Dict[str, Any]:
        """Convert device object to table data."""
        device_index = next(
            (idx for idx, did in self.cli_core.device_indices.items() if did == device.id),
            None,
        )
        # Get category name from device analysis (IntelligentDevice) or cached data (DeviceInfo)
        if hasattr(device, 'device_analysis') and device.device_analysis:
            category_name = device.device_analysis.category_name
        elif hasattr(device, 'category_name'):
            category_name = device.category_name
        else:
            category_name = device.category.title()
            
        return {
            "index": device_index,
            "name": device.name,
            "type": category_name,
            "status": "online",  # Could be enhanced with actual status
            "connection": "hybrid",  # Could show actual connection method
            "last_seen": "now",  # Could show actual last seen time
        }

    def _display_device_info(self, device, status: Dict[str, Any], verbose: bool) -> None:
        """Display device information in formatted table."""
        # Basic device info
        info_table = Table(show_header=True, header_style="bold blue")
        info_table.add_column("Property", style="cyan")
        info_table.add_column("Value", style="green")

        device_index = next(
            (idx for idx, did in self.cli_core.device_indices.items() if did == device.id),
            None,
        )

        info_table.add_row("Index", str(device_index) if device_index else "N/A")
        info_table.add_row("Name", device.name)
        info_table.add_row("ID", device.id)
        info_table.add_row("Category", self._get_category_display_name(device.category))
        info_table.add_row(
            "Capabilities",
            ", ".join([cap.name for cap in device.get_capabilities()]),
        )

        if hasattr(device, "local_key") and device.local_key:
            info_table.add_row(
                "Local Key",
                (device.local_key[:8] + "..." if len(device.local_key) > 8 else device.local_key),
            )
        if hasattr(device, "ip") and device.ip:
            info_table.add_row("IP Address", device.ip)

        self.console.print(f"\n[bold]{device.name} Information:[/bold]")
        self.console.print(info_table)

        # Status information
        if status:
            status_table = Table(show_header=True, header_style="bold blue")
            status_table.add_column("DPS", style="cyan")
            status_table.add_column("Value", style="green")

            for dps, value in status.items():
                status_table.add_row(str(dps), str(value))

            self.console.print(f"\n[bold]Current Status:[/bold]")
            self.console.print(status_table)

    def _display_health_status(self, health_data: Dict[str, Any], verbose: bool) -> None:
        """Display system health status."""
        health_table = Table(show_header=True, header_style="bold blue")
        health_table.add_column("Component", style="cyan")
        health_table.add_column("Status", style="green")

        # Authentication status
        auth_status, auth_color = self.cli_core.display_utils.format_health_status(
            "healthy" if health_data["authentication"] == "authenticated" else "error"
        )
        health_table.add_row("Authentication", f"[{auth_color}]{auth_status}[/{auth_color}]")

        # Session validity
        if health_data["session_valid"]:
            session_status, session_color = self.cli_core.display_utils.format_health_status(
                "healthy"
            )
        else:
            session_status, session_color = self.cli_core.display_utils.format_health_status(
                "error"
            )
        health_table.add_row("Session", f"[{session_color}]{session_status}[/{session_color}]")

        # Device counts
        health_table.add_row("Cached Devices", str(health_data["devices_cached"]))
        health_table.add_row("Loaded Devices", str(health_data["devices_loaded"]))

        self.console.print(f"\n[bold]System Health:[/bold]")
        self.console.print(health_table)

        if verbose and "session_info" in health_data:
            session_table = Table(show_header=True, header_style="bold blue")
            session_table.add_column("Property", style="cyan")
            session_table.add_column("Value", style="green")

            session_info = health_data["session_info"]
            session_table.add_row("User Code", session_info["user_code"])
            session_table.add_row("UID", session_info["uid"])
            session_table.add_row("Expires At", session_info["expires_at"])

            self.console.print(f"\n[bold]Session Details:[/bold]")
            self.console.print(session_table)

