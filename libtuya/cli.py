#!/usr/bin/env python3
"""
LibTuya CLI - Refactored thin wrapper

This is the refactored CLI that delegates all business logic to the core library
while maintaining the same user experience and command interface.
"""

import asyncio

import click
from rich.console import Console

from typing import Tuple

from libtuya.application import setup_logging
from libtuya.cli_core import CommandHandler, TuyaCLICore

console = Console(highlight=False)

# Global CLI core instance (initialized in main CLI)
cli_core = None
command_handler = None


def get_cli_core(verbose: bool = False) -> Tuple[TuyaCLICore, CommandHandler]:
    """Get or create CLI core instance."""
    global cli_core, command_handler
    if cli_core is None or command_handler is None:
        setup_logging(verbose=verbose)
        cli_core = TuyaCLICore(verbose=verbose, console=console)
        command_handler = CommandHandler(cli_core, console)
    return cli_core, command_handler


@click.group()
@click.version_option(version="1.0.0")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.pass_context
def cli(ctx, verbose: bool):
    """LibTuya CLI - Control your Tuya devices locally"""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    # Initialize CLI core with verbose setting
    get_cli_core(verbose=verbose)


@cli.command()
@click.option("--user-code", "-u", help="Unique user code for authentication")
@click.option("--json", "output_json", is_flag=True, help="Output result as JSON")
@click.option(
    "--force",
    is_flag=True,
    help="Force new user code even if already authenticated",
)
@click.pass_context
def login(ctx, user_code: str, output_json: bool, force: bool):
    """Authenticate with Tuya Smart Life app using QR code"""
    verbose = ctx.obj.get("verbose", False)
    core, _ = get_cli_core(verbose)

    # User code is required for authentication
    if not user_code:
        if output_json:
            import json
            error = {
                "success": False, 
                "error": "User code is required. Use --user-code or -u to provide it."
            }
            console.print(json.dumps(error))
            return
        else:
            console.print("[dim]Get your user code from the Smart Life app[/dim]")
            user_code = click.prompt("Enter user code")
            if not user_code.strip():
                console.print("[red]✗ User code cannot be empty[/red]")
                return

    async def run_login():
        await core.authenticate(
            user_code=user_code,
            force_new_user_code=force,
            output_json=output_json,
        )

    asyncio.run(run_login())


@cli.command()
@click.option("--json", "output_json", is_flag=True, help="Output result as JSON")
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose logging and show detailed device information",
)
@click.option("--cached", is_flag=True, help="Show cached devices without discovery")
@click.option(
    "--refresh",
    is_flag=True,
    help="Force fresh discovery even if cache exists",
)
@click.pass_context
def devices(ctx, output_json: bool, verbose: bool, cached: bool, refresh: bool):
    """List all available devices"""
    base_verbose = ctx.obj.get("verbose", False)
    effective_verbose = base_verbose or verbose
    core, handler = get_cli_core(effective_verbose)

    async def run_devices():
        await handler.handle_devices_command(
            output_json=output_json,
            verbose=effective_verbose,
            cached=cached,
            refresh=refresh,
        )

    asyncio.run(run_devices())


@cli.command()
@click.argument("device_id")
@click.argument(
    "action",
    type=click.Choice(
        ["on", "off", "brightness", "temperature", "color", "status"],
        case_sensitive=False,
    ),
)
@click.argument("value", required=False)
@click.option("--json", "output_json", is_flag=True, help="Output result as JSON")
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose logging and show detailed control information",
)
@click.pass_context
def control(
    ctx,
    device_id: str,
    action: str,
    value: str,
    output_json: bool,
    verbose: bool,
):
    """Control a device with specified action and optional value"""
    base_verbose = ctx.obj.get("verbose", False)
    effective_verbose = base_verbose or verbose
    core, _ = get_cli_core(effective_verbose)

    async def run_control():
        core.control_device(
            device_id=device_id,
            action=action,
            value=value,
            output_json=output_json,
        )

    asyncio.run(run_control())


@cli.command()
@click.argument("device_id")
@click.option("--json", "output_json", is_flag=True, help="Output result as JSON")
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose logging and show detailed diagnostic information",
)
@click.pass_context
def info(ctx, device_id: str, output_json: bool, verbose: bool):
    """Show detailed information about a device"""
    base_verbose = ctx.obj.get("verbose", False)
    effective_verbose = base_verbose or verbose
    core, handler = get_cli_core(effective_verbose)

    async def run_info():
        await handler.handle_info_command(
            device_id=device_id,
            output_json=output_json,
            verbose=effective_verbose,
        )

    asyncio.run(run_info())


@cli.command()
@click.option("--json", "output_json", is_flag=True, help="Output result as JSON")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.pass_context
def health(ctx, output_json: bool, verbose: bool):
    """Check system health and connectivity"""
    base_verbose = ctx.obj.get("verbose", False)
    effective_verbose = base_verbose or verbose
    core, handler = get_cli_core(effective_verbose)

    async def run_health():
        await handler.handle_health_command(output_json=output_json, verbose=effective_verbose)

    asyncio.run(run_health())


@cli.command()
@click.option("--json", "output_json", is_flag=True, help="Output result as JSON")
@click.pass_context
def logout(ctx, output_json: bool):
    """Clear authentication session"""
    verbose = ctx.obj.get("verbose", False)
    core, _ = get_cli_core(verbose)

    core.clear_session()

    if output_json:
        import json

        result = {"success": True, "message": "Logged out successfully"}
        console.print(json.dumps(result))
    else:
        console.print("[green]✓ Logged out successfully[/green]")


@cli.group()
def debug():
    """Debug commands for troubleshooting"""
    pass


@debug.command()
@click.argument("device_id")
@click.option("--json", "output_json", is_flag=True, help="Output result as JSON")
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose logging and show connection details",
)
@click.pass_context
def connection(ctx, device_id: str, output_json: bool, verbose: bool):
    """Debug device connection status"""
    base_verbose = ctx.obj.get("verbose", False)
    effective_verbose = base_verbose or verbose
    core, _ = get_cli_core(effective_verbose)

    # This would implement connection debugging
    # For now, show basic info
    if output_json:
        import json

        result = {
            "success": True,
            "message": "Debug connection not fully implemented",
        }
        console.print(json.dumps(result))
    else:
        console.print(
            f"[yellow]Debug connection for device {device_id} - feature in development[/yellow]"
        )


@debug.command()
@click.option("--json", "output_json", is_flag=True, help="Output result as JSON")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.pass_context
def stats(ctx, output_json: bool, verbose: bool):
    """Show usage statistics"""
    base_verbose = ctx.obj.get("verbose", False)
    effective_verbose = base_verbose or verbose

    if output_json:
        import json

        result = {"success": True, "stats": {"feature": "in_development"}}
        console.print(json.dumps(result))
    else:
        console.print("[yellow]Stats feature in development[/yellow]")


@debug.command()
@click.argument("device_id")
@click.option("--json", "output_json", is_flag=True, help="Output result as JSON")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.pass_context
def performance(ctx, device_id: str, output_json: bool, verbose: bool):
    """Test device performance and latency"""
    base_verbose = ctx.obj.get("verbose", False)
    effective_verbose = base_verbose or verbose

    if output_json:
        import json

        result = {
            "success": True,
            "message": "Performance testing not fully implemented",
        }
        console.print(json.dumps(result))
    else:
        console.print(
            f"[yellow]Performance testing for device {device_id} - feature in development[/yellow]"
        )


@debug.command()
@click.argument("device_id")
@click.option("--json", "output_json", is_flag=True, help="Output result as JSON")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.pass_context
def troubleshoot(ctx, device_id: str, output_json: bool, verbose: bool):
    """Run troubleshooting diagnostics for a device"""
    base_verbose = ctx.obj.get("verbose", False)
    effective_verbose = base_verbose or verbose

    if output_json:
        import json

        result = {
            "success": True,
            "message": "Troubleshooting not fully implemented",
        }
        console.print(json.dumps(result))
    else:
        console.print(
            f"[yellow]Troubleshooting for device {device_id} - feature in development[/yellow]"
        )


@cli.command()
@click.option(
    "--stats",
    is_flag=True,
    help="Show enhanced intelligence coverage statistics",
)
@click.option("--patterns", is_flag=True, help="Show enhanced DPS patterns")
@click.option("--capability", help="Show patterns for specific capability")
@click.pass_context
def intelligence(ctx, stats: bool, patterns: bool, capability: str):
    """Show device intelligence information"""
    verbose = ctx.obj.get("verbose", False)

    if stats or patterns or capability:
        console.print("[yellow]Intelligence command features in development[/yellow]")
    else:
        console.print("[yellow]Use --stats, --patterns, or --capability options[/yellow]")


def main():
    """Main entry point for the CLI"""
    cli()  # type: ignore


if __name__ == "__main__":
    main()
