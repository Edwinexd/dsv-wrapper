"""Low-level IMAP IDLE handler using imap-tools."""

import logging
import time

from imap_tools import MailBox

logger = logging.getLogger(__name__)


class IdleHandler:
    """Low-level IMAP IDLE handler."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        folder: str = "INBOX",
        email_address: str | None = None,
        idle_timeout: int = 29 * 60,
    ):
        """Initialize IDLE handler.

        Args:
            host: IMAP server hostname
            port: IMAP server port
            username: IMAP username (raw, without winadsu prefix)
            password: IMAP password
            folder: IMAP folder to monitor (default: INBOX)
            email_address: Email address to determine function account login format
            idle_timeout: IDLE timeout in seconds (default: 29 minutes per RFC 2177)
        """
        self._host = host
        self._port = port
        self._raw_username = username
        self._password = password
        self._folder = folder
        self._email_address = email_address
        self._idle_timeout = idle_timeout
        self._mailbox: MailBox | None = None
        self._idle_supported = True
        self._backoff_attempts = 0
        self._max_backoff = 32  # Maximum backoff in seconds

        # Calculate login username using same logic as MailClient
        self._login_username = self._get_login_username()

    def _get_login_username(self) -> str:
        """Calculate IMAP login username using same logic as MailClient.

        Returns:
            Formatted login username (winadsu\\username or winadsu\\username\\mailbox.institution)
        """
        if not self._email_address or "@" not in self._email_address:
            # Personal account format
            return f"winadsu\\{self._raw_username}"

        # Extract mailbox name and institution from email
        local_part, domain = self._email_address.split("@", 1)
        institution = domain.split(".")[0]  # e.g., "dsv" from "dsv.su.se"

        # Check if this looks like a function account (not personal)
        if local_part.lower() != self._raw_username.lower():
            # Function account format
            logger.debug(f"Using function account IMAP login: {local_part}.{institution}")
            return f"winadsu\\{self._raw_username}\\{local_part}.{institution}"

        # Personal account format
        return f"winadsu\\{self._raw_username}"

    def connect(self) -> None:
        """Connect to IMAP server and select folder."""
        try:
            self._mailbox = MailBox(self._host, self._port)
            self._mailbox.login(self._login_username, self._password)
            self._mailbox.folder.set(self._folder)
            self._backoff_attempts = 0  # Reset backoff on successful connect
            logger.debug(f"Connected to {self._host}:{self._port}, folder: {self._folder}")
        except Exception as e:
            logger.error(f"Failed to connect to IMAP server: {e}")
            raise

    def start_idle(self) -> None:
        """Enter IDLE mode. Sets _idle_supported to False if unsupported."""
        if not self._mailbox:
            raise RuntimeError("Not connected - call connect() first")

        try:
            self._mailbox.idle.start()
            logger.debug("IDLE mode started")
        except Exception as e:  # noqa: BLE001 - imap-tools can raise various exceptions
            logger.warning(f"IMAP IDLE not supported: {e}")
            self._idle_supported = False

    def wait_for_update(self, timeout: int = 30) -> bool:
        """Wait for IDLE notification.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if update received, False if timeout or IDLE not supported
        """
        if not self._idle_supported:
            return False

        if not self._mailbox:
            raise RuntimeError("Not connected - call connect() first")

        try:
            responses = self._mailbox.idle.wait(timeout=timeout)
            if responses:
                logger.debug(f"IDLE notification received: {responses}")
                return True
            return False
        except Exception as e:  # noqa: BLE001 - Mark IDLE as unsupported on error
            logger.warning(f"IDLE wait failed: {e} - marking IDLE as unsupported")
            self._idle_supported = False
            return False

    def stop_idle(self) -> None:
        """Exit IDLE mode."""
        if self._idle_supported and self._mailbox:
            try:
                self._mailbox.idle.stop()
                logger.debug("IDLE mode stopped")
            except Exception as e:  # noqa: BLE001 - Cleanup code, catch all errors
                logger.warning(f"Error stopping IDLE: {e}")

    def reconnect(self) -> None:
        """Reconnect with exponential backoff."""
        # Calculate backoff: 1s, 2s, 4s, 8s, 16s, 32s (max)
        backoff = min(2**self._backoff_attempts, self._max_backoff)
        logger.info(f"Reconnecting in {backoff} seconds (attempt {self._backoff_attempts + 1})")

        time.sleep(backoff)
        self._backoff_attempts += 1

        # Disconnect if still connected
        if self._mailbox:
            try:
                self._mailbox.logout()
            except Exception:  # noqa: BLE001 - Cleanup code, ignore all errors
                pass  # Ignore errors during cleanup

        # Reconnect
        self.connect()

        # Restart IDLE if it was supported
        if self._idle_supported:
            self.start_idle()

    def disconnect(self) -> None:
        """Disconnect gracefully."""
        if self._mailbox:
            try:
                self._mailbox.logout()
                logger.debug("Disconnected from IMAP server")
            except Exception as e:  # noqa: BLE001 - Cleanup code, catch all errors
                logger.warning(f"Error during disconnect: {e}")
            finally:
                self._mailbox = None
