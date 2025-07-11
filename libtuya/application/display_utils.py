"""
Display Utilities - Terminal display components

This module extracts display logic from the CLI, providing reusable components
for terminal UI elements like QR codes and formatted output.
"""

from typing import Any, Dict, List, Optional, Tuple

import qrcode
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


class QRDisplayService:
    """Service for rendering QR codes in the terminal."""

    def __init__(self, console: Optional[Console] = None):
        """Initialize QR display service."""
        self.console = console or Console(highlight=False)

    def display_qr_code(
        self, qr_data: str, title: str = "Scan QR Code with Smart Life App"
    ) -> None:
        """
        Display QR code in terminal using half-block characters for compact rendering.

        Args:
            qr_data: The data to encode in the QR code
            title: Title to display above the QR code
        """
        # Create a compact QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.ERROR_CORRECT_L,
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
                bottom = matrix[i + 1][j] if i + 1 < len(matrix) else False

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
        self.console.print(
            Panel(
                qr_output,
                title=f"[bold blue]{title}[/bold blue]",
                border_style="blue",
            )
        )

        # Also show the QR code data as a clickable link for easier access
        self.console.print(f"\n[dim]QR Code Data: {qr_data}[/dim]")


class DisplayUtils:
    """General display utilities for terminal output."""

    def __init__(self, console: Optional[Console] = None):
        """Initialize display utilities."""
        self.console = console or Console(highlight=False)
        self.qr_service = QRDisplayService(self.console)

    def display_qr_code(
        self, qr_data: str, title: str = "Scan QR Code with Smart Life App"
    ) -> None:
        """Display QR code - delegates to QRDisplayService."""
        self.qr_service.display_qr_code(qr_data, title)

    def create_device_table(
        self, devices: List[Dict[str, Any]], include_details: bool = False
    ) -> Table:
        """
        Create a formatted table for device information.

        Args:
            devices: List of device data dictionaries
            include_details: Whether to include detailed device information

        Returns:
            Rich Table object ready for display
        """
        if include_details:
            table = Table(show_header=True, header_style="bold blue")
            table.add_column("Index", style="dim", width=6)
            table.add_column("Name", style="cyan")
            table.add_column("Type", style="green")
            table.add_column("Status", style="yellow")
            table.add_column("Connection", style="magenta")
            table.add_column("Last Seen", style="dim")
        else:
            table = Table(show_header=True, header_style="bold blue")
            table.add_column("Index", style="dim", width=6)
            table.add_column("Name", style="cyan")
            table.add_column("Type", style="green")
            table.add_column("Status", style="yellow")

        for device_data in devices:
            if include_details:
                table.add_row(
                    str(device_data.get("index", "")),
                    device_data.get("name", "Unknown"),
                    device_data.get("type", "Unknown"),
                    device_data.get("status", "Unknown"),
                    device_data.get("connection", "Unknown"),
                    device_data.get("last_seen", "Never"),
                )
            else:
                table.add_row(
                    str(device_data.get("index", "")),
                    device_data.get("name", "Unknown"),
                    device_data.get("type", "Unknown"),
                    device_data.get("status", "Unknown"),
                )

        return table

    def create_status_table(self, title: str, data: Dict[str, Any]) -> Table:
        """
        Create a formatted status table.

        Args:
            title: Table title
            data: Status data as key-value pairs

        Returns:
            Rich Table object ready for display
        """
        table = Table(title=title, show_header=True, header_style="bold blue")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="green")

        for key, value in data.items():
            table.add_row(str(key), str(value))

        return table

    def format_health_status(self, health_status: str) -> Tuple[str, str]:
        """
        Format health status with appropriate color and icon.

        Args:
            health_status: Raw health status string

        Returns:
            Tuple of (formatted_status, color)
        """
        if health_status.lower() in ["healthy", "good", "online"]:
            return "✅ Healthy", "green"
        elif health_status.lower() in ["warning", "degraded"]:
            return "⚠️ Warning", "yellow"
        elif health_status.lower() in ["error", "failed", "offline"]:
            return "❌ Error", "red"
        else:
            return f"ℹ️ {health_status}", "dim"

    def format_time_ago(self, timestamp_str: str) -> str:
        """
        Convert ISO timestamp to human-readable time ago format.

        Args:
            timestamp_str: ISO format timestamp string

        Returns:
            Human readable time ago string
        """
        if not timestamp_str:
            return "Never"

        try:
            from datetime import datetime, timezone

            # Parse the ISO timestamp
            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            diff = now - timestamp

            seconds = int(diff.total_seconds())
            if seconds < 60:
                return f"{seconds}s ago"
            elif seconds < 3600:
                minutes = seconds // 60
                return f"{minutes}m ago"
            elif seconds < 86400:
                hours = seconds // 3600
                return f"{hours}h ago"
            else:
                days = seconds // 86400
                return f"{days}d ago"
        except Exception:
            # If timestamp parsing fails, show "now" as fallback
            return "now"
