"""
Session Manager - Persistent session storage and management

This module extracts session persistence logic from the CLI, providing a clean
interface for managing authentication sessions across application restarts.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from libtuya.auth.models import AuthSession

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages persistent storage of authentication sessions."""

    def __init__(self, session_dir: Optional[Path] = None):
        """Initialize session manager with storage directory."""
        self.session_dir = session_dir or (Path.home() / ".libtuya")
        self.session_file = self.session_dir / "session.json"
        self.device_cache_file = self.session_dir / "device_cache.json"

        # Ensure directory exists
        self.session_dir.mkdir(parents=True, exist_ok=True)

    def load_session(self) -> Optional[AuthSession]:
        """
        Load authentication session from persistent storage.

        Returns:
            AuthSession if found and valid, None otherwise
        """
        try:
            if not self.session_file.exists():
                logger.debug("No session file found")
                return None

            with open(self.session_file, "r") as f:
                session_data = json.load(f)
                session = AuthSession.from_dict(session_data)

            if session.is_expired:
                user_display = session.uid if session.uid else session.user_code
                logger.info(f"Session expired for user {user_display}, will attempt refresh")
            else:
                user_display = session.uid if session.uid else session.user_code
                logger.debug(f"Session valid for user {user_display}")

            return session

        except Exception as e:
            logger.warning(f"Could not load session: {e}")
            return None

    def save_session(self, session: AuthSession) -> bool:
        """
        Save authentication session to persistent storage.

        Args:
            session: The session to save

        Returns:
            True if saved successfully, False otherwise
        """
        try:
            with open(self.session_file, "w") as f:
                json.dump(session.to_dict(), f, indent=2)

            user_display = session.uid if session.uid else session.user_code
            logger.debug(f"Session saved for user {user_display}")
            return True

        except Exception as e:
            logger.error(f"Could not save session: {e}")
            return False

    def clear_session(self) -> bool:
        """
        Clear stored session file.

        Returns:
            True if cleared successfully, False otherwise
        """
        try:
            if self.session_file.exists():
                self.session_file.unlink()
                logger.debug("Session cleared")
                return True
            return True

        except Exception as e:
            logger.error(f"Could not clear session: {e}")
            return False

    def load_device_cache(self) -> Dict[str, Any]:
        """
        Load device cache from persistent storage.

        Returns:
            Dictionary with device_indices and device_info, or empty dict
        """
        try:
            if not self.device_cache_file.exists():
                logger.debug("No device cache file found")
                return {"device_indices": {}, "device_info": {}}

            with open(self.device_cache_file, "r") as f:
                cache_data = json.load(f)

            # Convert string keys back to integers for device_indices
            device_indices = cache_data.get("device_indices", {})
            device_indices = {int(k): v for k, v in device_indices.items()}

            result = {
                "device_indices": device_indices,
                "device_info": cache_data.get("device_info", {}),
            }

            logger.debug(f"Loaded {len(result['device_info'])} devices from cache")
            return result

        except Exception as e:
            logger.warning(f"Could not load device cache: {e}")
            return {"device_indices": {}, "device_info": {}}

    def save_device_cache(
        self, device_indices: Dict[int, str], device_info: Dict[str, Dict]
    ) -> bool:
        """
        Save device cache to persistent storage.

        Args:
            device_indices: Mapping from index to device_id
            device_info: Device information keyed by device_id

        Returns:
            True if saved successfully, False otherwise
        """
        try:
            cache_data = {
                "device_indices": device_indices,
                "device_info": device_info,
                "last_updated": json.dumps(None),  # Placeholder for future timestamp
            }

            with open(self.device_cache_file, "w") as f:
                json.dump(cache_data, f, indent=2)

            logger.debug(f"Device cache saved with {len(device_info)} devices")
            return True

        except Exception as e:
            logger.error(f"Could not save device cache: {e}")
            return False

    def clear_device_cache(self) -> bool:
        """
        Clear device cache file.

        Returns:
            True if cleared successfully, False otherwise
        """
        try:
            if self.device_cache_file.exists():
                self.device_cache_file.unlink()
                logger.debug("Device cache cleared")
                return True
            return True

        except Exception as e:
            logger.error(f"Could not clear device cache: {e}")
            return False
