"""
Logging Configuration - Application-level logging setup

This module extracts logging configuration from the CLI, providing a centralized
place to configure logging for different application contexts.
"""

import logging
from typing import Optional


class LoggingConfig:
    """Centralized logging configuration for libtuya applications."""

    # Core logger names that applications typically want to configure
    CORE_LOGGERS = [
        "libtuya",
        "libtuya.devices.intelligent_device",
        "libtuya.auth.manager",
        "libtuya.devices.connection_manager",
        "libtuya.devices.command_executor",
        "libtuya.application",
    ]

    @classmethod
    def setup_logging(cls, verbose: bool = False, level: Optional[int] = None) -> None:
        """
        Configure logging for libtuya applications.

        Args:
            verbose: Enable verbose/debug logging
            level: Specific logging level (overrides verbose)
        """
        if level is not None:
            target_level = level
        elif verbose:
            target_level = logging.DEBUG
        else:
            target_level = logging.WARNING

        # Configure core loggers
        for logger_name in cls.CORE_LOGGERS:
            logger = logging.getLogger(logger_name)
            logger.setLevel(target_level)

    @classmethod
    def setup_cli_logging(cls, verbose: bool = False) -> None:
        """
        Configure logging specifically for CLI usage.

        Args:
            verbose: Enable verbose logging for CLI operations
        """
        cls.setup_logging(verbose=verbose)

        # Add CLI-specific logging configuration if needed
        if verbose:
            # In verbose mode, show more detailed information
            formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        else:
            # In normal mode, minimal logging to console
            formatter = logging.Formatter("%(levelname)s: %(message)s")

        # Only add handler if none exists to avoid duplicates
        root_logger = logging.getLogger()
        if not root_logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(formatter)
            root_logger.addHandler(handler)

    @classmethod
    def silence_noisy_loggers(cls) -> None:
        """Silence known noisy third-party loggers."""
        noisy_loggers = [
            "urllib3.connectionpool",
            "requests.packages.urllib3.connectionpool",
            "aiohttp.access",
        ]

        for logger_name in noisy_loggers:
            logging.getLogger(logger_name).setLevel(logging.WARNING)


# Convenience function for backward compatibility
def setup_logging(verbose: bool = False, level: Optional[int] = None) -> None:
    """
    Setup logging for libtuya applications.

    Args:
        verbose: Enable verbose/debug logging
        level: Specific logging level (overrides verbose)
    """
    LoggingConfig.setup_logging(verbose=verbose, level=level)
