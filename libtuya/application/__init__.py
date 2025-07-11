"""
Application Layer Module

This module contains application-level concerns that are too specific for the core library
but not specific to any particular interface (CLI, GUI, API).

Components:
- SessionManager: Persistent session storage and management
- DisplayUtils: Terminal display utilities (QR codes, formatting)
- LoggingConfig: Application logging configuration
"""

from .display_utils import DisplayUtils, QRDisplayService
from .logging_config import setup_logging
from .session_manager import SessionManager

__all__ = [
    "SessionManager",
    "DisplayUtils",
    "QRDisplayService",
    "setup_logging",
]
