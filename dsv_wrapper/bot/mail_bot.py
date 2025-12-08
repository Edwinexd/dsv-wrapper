"""Event-driven email monitoring bot implementations."""

import asyncio
import logging
import os
import threading

from .events import BotError, ErrorCallback, NewEmailCallback, NewEmailEvent
from .idle_handler import IdleHandler

logger = logging.getLogger(__name__)


class MailBot:
    """Event-driven email monitoring bot (sync)."""

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        email_address: str | None = None,
        email_name: str | None = None,
        folder: str = "inbox",
        fetch_limit: int = 20,
        poll_interval: int = 60,
        enable_polling_fallback: bool = True,
    ):
        """Initialize the email monitoring bot.

        Args:
            username: SU username (default: SU_USERNAME env var)
            password: SU password (default: SU_PASSWORD env var)
            email_address: Email address for sender (default: SU_EMAIL env var)
            email_name: Display name for sender (default: SU_EMAIL_NAME env var)
            folder: Folder to monitor (default: inbox)
            fetch_limit: Number of recent emails to fetch per check (default: 20)
            poll_interval: Polling interval in seconds if IDLE unavailable (default: 60)
            enable_polling_fallback: Fall back to polling if IDLE not supported (default: True)
        """
        # Store credentials for MailClient usage
        self._mail_client_params = {
            "username": username,
            "password": password,
            "email_address": email_address,
            "email_name": email_name,
        }
        self._folder = folder
        self._fetch_limit = fetch_limit
        self._poll_interval = poll_interval
        self._enable_polling_fallback = enable_polling_fallback

        # Get credentials from env if not provided
        username = username or os.getenv("SU_USERNAME")
        password = password or os.getenv("SU_PASSWORD")
        email_address_for_login = email_address or os.getenv("SU_EMAIL")

        if not username or not password:
            raise ValueError(
                "Username and password required (set SU_USERNAME/SU_PASSWORD env vars)"
            )

        # IMAP IDLE handler
        self._idle_handler = IdleHandler(
            host="ebox.su.se",
            port=993,
            username=username,
            password=password,
            folder=self._map_folder_name(folder),
            email_address=email_address_for_login,
        )

        # Callbacks
        self._callbacks: list[NewEmailCallback] = []
        self._error_callbacks: list[ErrorCallback] = []
        self._callback_lock = threading.Lock()

        # Track seen emails to avoid duplicate events
        self._seen_email_ids: set[str] = set()

        # Persistent MailClient for fetching emails
        from ..mail import MailClient

        self._mail_client = MailClient(**self._mail_client_params)

        # Control
        self._stop_event = threading.Event()
        self._running = False

    def on_new_email(self, callback: NewEmailCallback) -> None:
        """Register callback for new email events.

        Args:
            callback: Function to call when new email arrives
        """
        with self._callback_lock:
            self._callbacks.append(callback)

    def on_error(self, callback: ErrorCallback) -> None:
        """Register callback for error events.

        Args:
            callback: Function to call when error occurs
        """
        with self._callback_lock:
            self._error_callbacks.append(callback)

    def remove_callback(self, callback: NewEmailCallback) -> None:
        """Remove a registered callback.

        Args:
            callback: Callback to remove
        """
        with self._callback_lock:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

    def start(self) -> None:
        """Start monitoring (blocking).

        This will block until stop() is called or an unrecoverable error occurs.
        """
        self._running = True
        self._stop_event.clear()

        try:
            # Connect MailClient for fetching emails
            self._mail_client.__enter__()

            # Connect IDLE handler
            self._idle_handler.connect()
        except Exception as e:
            self._emit_error(
                BotError(
                    error=e,
                    error_type=type(e).__name__,
                    message=f"Failed to connect: {e}",
                    recoverable=False,
                )
            )
            raise

        # Try IDLE, fall back to polling if not supported
        self._idle_handler.start_idle()

        if not self._idle_handler._idle_supported:
            if self._enable_polling_fallback:
                logger.warning(
                    f"IMAP IDLE not supported - falling back to polling "
                    f"every {self._poll_interval}s"
                )
                self._poll_loop()
            else:
                error = RuntimeError("IMAP IDLE not supported and polling disabled")
                self._emit_error(
                    BotError(
                        error=error,
                        error_type="RuntimeError",
                        message=str(error),
                        recoverable=False,
                    )
                )
                raise error
        else:
            self._idle_loop()

    def stop(self) -> None:
        """Stop monitoring."""
        logger.info("Stopping bot...")
        self._stop_event.set()
        self._idle_handler.stop_idle()
        self._running = False

    def _idle_loop(self) -> None:
        """Main IDLE monitoring loop."""
        logger.info("Starting IDLE monitoring loop")

        while not self._stop_event.is_set():
            try:
                # Check if IDLE is still supported before waiting
                if not self._idle_handler._idle_supported:
                    logger.warning("IDLE became unsupported, switching to polling mode")
                    if self._enable_polling_fallback:
                        self._poll_loop()
                    return

                has_update = self._idle_handler.wait_for_update(timeout=30)

                # Check again after wait (might have become unsupported during wait)
                if not self._idle_handler._idle_supported:
                    logger.warning("IDLE became unsupported, switching to polling mode")
                    if self._enable_polling_fallback:
                        self._poll_loop()
                    return

                if has_update:
                    logger.debug("IDLE notification received, processing emails")
                    self._process_new_emails()

            except ConnectionError as e:
                logger.error(f"Connection lost: {e}")
                self._emit_error(
                    BotError(
                        error=e,
                        error_type=type(e).__name__,
                        message=f"Connection lost: {e}",
                        recoverable=True,
                    )
                )
                try:
                    self._idle_handler.reconnect()
                except Exception as reconnect_error:  # noqa: BLE001 - Handle all reconnect errors
                    logger.error(f"Failed to reconnect: {reconnect_error}")
                    self._emit_error(
                        BotError(
                            error=reconnect_error,
                            error_type=type(reconnect_error).__name__,
                            message=f"Failed to reconnect: {reconnect_error}",
                            recoverable=False,
                        )
                    )
                    break

            except Exception as e:  # noqa: BLE001 - Catch-all for unexpected errors
                logger.error(f"Unexpected error in IDLE loop: {e}")
                self._emit_error(
                    BotError(
                        error=e,
                        error_type=type(e).__name__,
                        message=f"Unexpected error: {e}",
                        recoverable=False,
                    )
                )
                break

    def _poll_loop(self) -> None:
        """Polling fallback loop."""
        logger.info(f"Starting polling loop (interval: {self._poll_interval}s)")

        while not self._stop_event.is_set():
            try:
                self._process_new_emails()
            except Exception as e:  # noqa: BLE001 - Continue polling even on errors
                logger.error(f"Error processing emails: {e}")
                self._emit_error(
                    BotError(
                        error=e,
                        error_type=type(e).__name__,
                        message=f"Error processing emails: {e}",
                        recoverable=True,
                    )
                )

            # Sleep with interruptible wait
            self._stop_event.wait(timeout=self._poll_interval)

    def _process_new_emails(self) -> None:
        """Fetch recent emails and emit events for new ones only."""
        try:
            emails = self._mail_client.get_emails(self._folder, limit=self._fetch_limit)

            logger.debug(f"Fetched {len(emails)} recent emails")

            # Only emit events for emails we haven't seen before
            new_count = 0
            for email in emails:
                if email.id not in self._seen_email_ids:
                    self._seen_email_ids.add(email.id)
                    event = NewEmailEvent(
                        folder=self._folder,
                        email=email,
                    )
                    self._emit_event(event)
                    new_count += 1

            if new_count > 0:
                logger.debug(f"Emitted {new_count} new email events")

        except Exception as e:
            logger.error(f"Error fetching emails: {e}")
            raise

    def _emit_event(self, event: NewEmailEvent) -> None:
        """Deliver event to all callbacks."""
        with self._callback_lock:
            callbacks = self._callbacks.copy()

        for callback in callbacks:
            try:
                callback(event)
            except Exception as e:  # noqa: BLE001 - Must catch all callback errors
                logger.error(f"Callback error: {e}")
                self._emit_error(
                    BotError(
                        error=e,
                        error_type=type(e).__name__,
                        message=f"Callback error: {e}",
                        recoverable=True,
                    )
                )

    def _emit_error(self, error: BotError) -> None:
        """Deliver error to error callbacks."""
        with self._callback_lock:
            callbacks = self._error_callbacks.copy()

        for callback in callbacks:
            try:
                callback(error)
            except Exception as callback_error:  # noqa: BLE001 - Prevent error cascade
                # Don't cascade errors - just log
                logger.error(f"Error callback failed: {callback_error}")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
        self._idle_handler.disconnect()
        # Properly exit MailClient context manager
        self._mail_client.__exit__(exc_type, exc_val, exc_tb)

    @staticmethod
    def _map_folder_name(folder: str) -> str:
        """Map friendly folder name to IMAP folder.

        Args:
            folder: Friendly folder name (e.g., 'inbox', 'sent')

        Returns:
            IMAP folder name
        """
        mapping = {
            "inbox": "INBOX",
            "sent": '"Sent Items"',
            "sentitems": '"Sent Items"',
            "drafts": "Drafts",
            "trash": '"Deleted Items"',
            "deleteditems": '"Deleted Items"',
            "junk": '"Junk Email"',
            "junkemail": '"Junk Email"',
        }
        return mapping.get(folder.lower(), folder)


class AsyncMailBot:
    """Event-driven email monitoring bot (async)."""

    def __init__(self, *args, **kwargs):
        """Initialize async bot.

        Args are passed through to MailBot.
        """
        self._bot = MailBot(*args, **kwargs)
        self._task: asyncio.Task | None = None

    def on_new_email(self, callback: NewEmailCallback) -> None:
        """Register callback for new email events.

        Args:
            callback: Sync function to call when new email arrives (will run in thread)
        """
        self._bot.on_new_email(callback)

    def on_error(self, callback: ErrorCallback) -> None:
        """Register callback for error events.

        Args:
            callback: Sync function to call when error occurs (will run in thread)
        """
        self._bot.on_error(callback)

    def remove_callback(self, callback: NewEmailCallback) -> None:
        """Remove a registered callback.

        Args:
            callback: Callback to remove
        """
        self._bot.remove_callback(callback)

    async def start(self) -> None:
        """Start monitoring (async, blocking).

        This will block until stop() is called or an unrecoverable error occurs.
        """
        await asyncio.to_thread(self._bot.start)

    async def stop(self) -> None:
        """Stop monitoring."""
        await asyncio.to_thread(self._bot.stop)

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()
        await asyncio.to_thread(self._bot._idle_handler.disconnect)
        await asyncio.to_thread(self._bot._mail_client.__exit__, exc_type, exc_val, exc_tb)
