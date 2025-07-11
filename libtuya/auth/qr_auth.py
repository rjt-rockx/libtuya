"""
QR Code Authentication Flow for Tuya Cloud API.

This module implements the QR code-based authentication flow using the
tuya-device-sharing-sdk LoginControl class. It handles QR code generation,
user scanning, and OAuth-like token exchange.
"""

import logging
import time
import uuid
from typing import Any, Dict, Optional, Tuple

from .models import AuthenticationError, AuthSession, QRCodeData

logger = logging.getLogger(__name__)


class QRAuthenticator:
    """
    Handles QR code authentication flow for Tuya Cloud API.

    This class wraps the tuya-device-sharing-sdk LoginControl to provide
    a clean interface for QR code authentication with proper error handling
    and timeout management.
    """

    # Home Assistant client configuration
    CLIENT_ID = "HA_3y9q4ak7g4ephrvke"
    SCHEMA = "haauthorize"

    def __init__(self, endpoint: str = "https://apigw.iotbing.com"):
        """
        Initialize QR authenticator.

        Args:
            endpoint: API endpoint URL
        """
        self.endpoint = endpoint
        self.login_control = None
        self._current_qr_data: Optional[QRCodeData] = None
        self._current_session: Optional[AuthSession] = None

    def _ensure_login_control(self):
        """Ensure LoginControl is initialized."""
        if self.login_control is None:
            try:
                from tuya_sharing.user import LoginControl

                self.login_control = LoginControl()
            except ImportError:
                raise AuthenticationError(
                    "tuya-device-sharing-sdk not installed. Install with: pip install tuya-device-sharing-sdk",
                    "MISSING_DEPENDENCY",
                )

    def generate_qr_code(self, user_code: Optional[str] = None) -> QRCodeData:
        """
        Generate QR code for authentication.

        Args:
            user_code: User code required for authentication.

        Returns:
            QRCodeData containing QR code and polling token

        Raises:
            AuthenticationError: If QR code generation fails or user_code is None
        """
        self._ensure_login_control()

        if user_code is None:
            raise AuthenticationError(
                "User code is required for QR code generation",
                "USER_CODE_REQUIRED"
            )

        try:
            logger.info("Generating QR code for authentication")
            if self.login_control is None:
                raise AuthenticationError("LoginControl not initialized", "INIT_ERROR")
            response = self.login_control.qr_code(
                client_id=self.CLIENT_ID,
                schema=self.SCHEMA,
                user_code=user_code,
            )

            if not response.get("success", False):
                raise AuthenticationError(
                    f"Failed to generate QR code: {response.get('msg', 'Unknown error')}",
                    "QR_GENERATION_FAILED",
                    {"response": response},
                )

            result = response.get("result", {})
            qr_code = result.get("qrcode", "")

            # In the current API, the QR code itself is used as the token for polling
            token = qr_code

            if not qr_code:
                raise AuthenticationError(
                    "QR code response missing qrcode field",
                    "INVALID_QR_RESPONSE",
                    {"result": result},
                )

            qr_data = QRCodeData(
                qr_code=qr_code,
                token=token,
                expires_in=result.get("expires_in", 600),
            )

            self._current_qr_data = qr_data
            logger.info("QR code generated successfully")
            return qr_data

        except Exception as e:
            if isinstance(e, AuthenticationError):
                raise
            logger.error(f"Unexpected error generating QR code: {e}")
            raise AuthenticationError(
                f"Unexpected error generating QR code: {str(e)}",
                "QR_GENERATION_ERROR",
                {"exception": str(e)},
            )

    def check_login_status(
        self, qr_data: QRCodeData, user_code: str
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Check if user has completed authentication.

        Args:
            qr_data: QR code data with polling token
            user_code: User code used for QR generation

        Returns:
            Tuple of (success, token_info). token_info is None if not authenticated yet.

        Raises:
            AuthenticationError: If polling fails
        """
        self._ensure_login_control()

        try:
            logger.debug("Checking login status")
            if self.login_control is None:
                raise AuthenticationError("LoginControl not initialized", "INIT_ERROR")
            success, result = self.login_control.login_result(
                token=qr_data.token,
                client_id=self.CLIENT_ID,
                user_code=user_code,
            )

            if success:
                logger.info("Authentication successful")
                return True, result
            else:
                # Check if it's a temporary failure or permanent error
                error_msg = result.get("msg", "Unknown error")
                logger.debug(f"Login result: success={success}, msg='{error_msg}', full_result={result}")
                
                # Be more lenient about waiting states - most initial states should be treated as "waiting"
                # Only throw exceptions for clearly permanent failures
                if any(keyword in error_msg.lower() for keyword in [
                    "not scanned", "waiting", "pending", "未扫描", "等待", 
                    "scan", "please", "again", "try", "failed"  # "Login failed, please scan and try again!" should wait
                ]):
                    logger.debug("Still waiting for user to scan QR code")
                    return False, None
                else:
                    # Only throw for clearly terminal errors
                    if "expired" in error_msg.lower() or "invalid" in error_msg.lower():
                        logger.warning(f"Authentication failed: {error_msg}")
                        raise AuthenticationError(
                            f"Authentication failed: {error_msg}",
                            "AUTH_FAILED",
                            {"result": result},
                        )
                    else:
                        # Default to waiting for unknown states
                        logger.debug(f"Unknown status '{error_msg}' - treating as waiting")
                        return False, None

        except Exception as e:
            if isinstance(e, AuthenticationError):
                raise
            logger.error(f"Error checking login status: {e}")
            raise AuthenticationError(
                f"Error checking login status: {str(e)}",
                "LOGIN_CHECK_ERROR",
                {"exception": str(e)},
            )

    def wait_for_authentication(
        self,
        qr_data: QRCodeData,
        user_code: str,
        timeout: int = 300,
        poll_interval: int = 2,
    ) -> AuthSession:
        """
        Wait for user to complete authentication.

        Args:
            qr_data: QR code data with polling token
            user_code: User code used for QR generation
            timeout: Maximum time to wait in seconds
            poll_interval: Time between polling attempts in seconds

        Returns:
            AuthSession with authentication tokens

        Raises:
            AuthenticationError: If authentication fails or times out
        """
        logger.info(f"Waiting for authentication (timeout: {timeout}s)")
        start_time = time.time()

        while (time.time() - start_time) < timeout:
            try:
                success, token_info = self.check_login_status(qr_data, user_code)

                if success and token_info:
                    # Debug token info
                    expire_time_raw = token_info.get("expire_time", 0)
                    current_time = int(time.time() * 1000)
                    logger.info(
                        f"Token expire_time (raw): {expire_time_raw}, current_time: {current_time}"
                    )

                    # Convert expire_time from seconds-from-now to absolute timestamp in milliseconds
                    expire_time_absolute = current_time + (expire_time_raw * 1000)
                    logger.info(f"Token expire_time (absolute ms): {expire_time_absolute}")

                    # Create authentication session
                    session = AuthSession(
                        access_token=token_info.get("access_token", ""),
                        refresh_token=token_info.get("refresh_token", ""),
                        uid=token_info.get("uid", ""),
                        expire_time=expire_time_absolute,
                        t=token_info.get("t", 0),
                        client_id=self.CLIENT_ID,
                        user_code=user_code,
                        terminal_id=token_info.get("terminal_id", ""),
                    )

                    # Store endpoint if provided
                    if "endpoint" in token_info:
                        session.endpoint = token_info["endpoint"]

                    if not session.access_token:
                        raise AuthenticationError(
                            "Authentication response missing access token",
                            "INVALID_AUTH_RESPONSE",
                            {"token_info": token_info},
                        )

                    self._current_session = session
                    logger.info("Authentication completed successfully")
                    return session

                # Wait before next poll
                time.sleep(poll_interval)

            except AuthenticationError:
                raise
            except Exception as e:
                logger.error(f"Unexpected error during authentication wait: {e}")
                raise AuthenticationError(
                    f"Unexpected error during authentication: {str(e)}",
                    "AUTH_WAIT_ERROR",
                    {"exception": str(e)},
                )

        # Timeout reached
        logger.error("Authentication timeout reached")
        raise AuthenticationError(
            f"Authentication timeout after {timeout} seconds",
            "AUTH_TIMEOUT",
            {"timeout": timeout},
        )

    def authenticate_with_qr(
        self,
        user_code: Optional[str] = None,
        timeout: int = 300,
        poll_interval: int = 2,
    ) -> Tuple[QRCodeData, AuthSession]:
        """
        Complete QR code authentication flow.

        Args:
            user_code: Optional user code. If None, generates unique code.
            timeout: Maximum time to wait for authentication
            poll_interval: Time between polling attempts

        Returns:
            Tuple of (QRCodeData, AuthSession)

        Raises:
            AuthenticationError: If authentication fails
        """
        logger.info("Starting QR code authentication flow")

        # Generate user code if not provided
        if user_code is None:
            user_code = str(uuid.uuid4())

        # Generate QR code
        qr_data = self.generate_qr_code(user_code)

        # Wait for authentication
        session = self.wait_for_authentication(qr_data, user_code, timeout, poll_interval)

        logger.info("QR code authentication flow completed successfully")
        return qr_data, session

    def get_current_session(self) -> Optional[AuthSession]:
        """Get the current authentication session."""
        return self._current_session

    def get_current_qr_data(self) -> Optional[QRCodeData]:
        """Get the current QR code data."""
        return self._current_qr_data

    def format_qr_for_display(self, qr_data: QRCodeData) -> str:
        """
        Format QR code for user-friendly display.

        Args:
            qr_data: QR code data

        Returns:
            Formatted string for display
        """
        return f"""
╔══════════════════════════════════════════════════════════════════════════════════════╗
║                                 TUYA AUTHENTICATION                                  ║
╠══════════════════════════════════════════════════════════════════════════════════════╣
║                                                                                      ║
║  Please scan the QR code below with your Smart Life or Tuya Smart app:              ║
║                                                                                      ║
║  QR Code: {qr_data.qr_code:<63} ║
║                                                                                      ║
║  Instructions:                                                                       ║
║  1. Open Smart Life or Tuya Smart app on your phone                                 ║
║  2. Tap "Scan" or the QR code icon                                                   ║
║  3. Scan the QR code above                                                           ║
║  4. Grant permission when prompted                                                   ║
║                                                                                      ║
║  Waiting for authentication...                                                       ║
║                                                                                      ║
╚══════════════════════════════════════════════════════════════════════════════════════╝
"""
