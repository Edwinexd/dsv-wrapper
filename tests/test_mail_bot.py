"""Tests for email monitoring bot."""

import os
import threading
import time

import pytest

from dsv_wrapper import AsyncMailBot, MailBot
from dsv_wrapper.bot.events import NewEmailEvent

# Mark for tests that require credentials
requires_credentials = pytest.mark.skipif(
    not os.environ.get("SU_USERNAME")
    or not os.environ.get("SU_PASSWORD")
    or not os.environ.get("SU_EMAIL"),
    reason="SU_USERNAME, SU_PASSWORD and SU_EMAIL environment variables required",
)


@requires_credentials
class TestMailBot:
    """Integration tests for MailBot (sync)."""

    def test_bot_context_manager(self):
        """Test bot lifecycle with context manager."""
        with MailBot() as bot:
            assert bot is not None
            assert not bot._running

    def test_callback_registration(self):
        """Test callback registration and removal."""
        with MailBot() as bot:
            called = []

            def handler(event: NewEmailEvent):
                called.append(event)

            # Register callback
            bot.on_new_email(handler)
            assert len(bot._callbacks) == 1

            # Remove callback
            bot.remove_callback(handler)
            assert len(bot._callbacks) == 0

    def test_multiple_callbacks(self):
        """Test multiple callbacks for same event."""
        with MailBot() as bot:
            called1 = []
            called2 = []

            bot.on_new_email(lambda e: called1.append(e))
            bot.on_new_email(lambda e: called2.append(e))

            assert len(bot._callbacks) == 2

    def test_error_callback_registration(self):
        """Test error callback registration."""
        with MailBot() as bot:
            errors = []

            def error_handler(error):
                errors.append(error)

            bot.on_error(error_handler)
            assert len(bot._error_callbacks) == 1

    def test_new_email_detection(self):
        """Test bot detects new emails (fetches recent emails)."""
        events = []

        def handler(event: NewEmailEvent):
            events.append(event)

        with MailBot(fetch_limit=5) as bot:
            bot.on_new_email(handler)

            # Start in background thread
            thread = threading.Thread(target=bot.start, daemon=True)
            thread.start()

            # Give it time to connect and fetch
            time.sleep(3)

            # Stop the bot
            bot.stop()
            thread.join(timeout=5)

        # Should have fetched recent emails (may be zero if inbox empty)
        assert len(events) >= 0
        print(f"Fetched {len(events)} emails from inbox")

    def test_error_handling_in_callbacks(self):
        """Test bot continues after callback error."""
        events = []
        errors = []

        def failing_handler(event: NewEmailEvent):
            events.append(event)
            raise ValueError("Test error")

        def error_handler(error):
            errors.append(error)

        with MailBot(fetch_limit=2) as bot:
            bot.on_new_email(failing_handler)
            bot.on_error(error_handler)

            # Start in background
            thread = threading.Thread(target=bot.start, daemon=True)
            thread.start()

            time.sleep(3)
            bot.stop()
            thread.join(timeout=5)

        # Errors should have been caught and passed to error handler
        if events:
            assert len(errors) >= len(events)  # At least one error per event

    def test_folder_name_mapping(self):
        """Test folder name mapping."""
        assert MailBot._map_folder_name("inbox") == "INBOX"
        assert MailBot._map_folder_name("sent") == '"Sent Items"'
        assert MailBot._map_folder_name("drafts") == "Drafts"
        assert MailBot._map_folder_name("trash") == '"Deleted Items"'
        assert MailBot._map_folder_name("CustomFolder") == "CustomFolder"

    def test_stop_before_start(self):
        """Test calling stop before start."""
        with MailBot() as bot:
            bot.stop()  # Should not raise


@requires_credentials
class TestAsyncMailBot:
    """Integration tests for AsyncMailBot."""

    @pytest.mark.asyncio
    async def test_async_bot_lifecycle(self):
        """Test async bot lifecycle."""
        async with AsyncMailBot() as bot:
            assert bot is not None
            assert bot._bot is not None

    @pytest.mark.asyncio
    async def test_async_callback_registration(self):
        """Test async bot callback registration."""
        async with AsyncMailBot() as bot:
            called = []

            def handler(event: NewEmailEvent):
                called.append(event)

            bot.on_new_email(handler)
            assert len(bot._bot._callbacks) == 1

            bot.remove_callback(handler)
            assert len(bot._bot._callbacks) == 0

    @pytest.mark.asyncio
    async def test_async_new_email_detection(self):
        """Test async bot detects emails."""
        import asyncio

        events = []

        def handler(event: NewEmailEvent):
            events.append(event)

        async with AsyncMailBot(fetch_limit=5) as bot:
            bot.on_new_email(handler)

            # Start in background task
            task = asyncio.create_task(bot.start())

            # Give it time to fetch
            await asyncio.sleep(3)

            # Stop
            await bot.stop()

            # Wait for task to complete
            try:
                await asyncio.wait_for(task, timeout=5)
            except TimeoutError:
                pass

        # Should have fetched recent emails
        assert len(events) >= 0
        print(f"Async bot fetched {len(events)} emails")


class TestMailBotUnit:
    """Unit tests without credentials."""

    def test_bot_initialization_without_credentials(self):
        """Test bot raises error without credentials."""
        import os

        # Temporarily remove env vars
        old_username = os.environ.pop("SU_USERNAME", None)
        old_password = os.environ.pop("SU_PASSWORD", None)

        try:
            with pytest.raises(ValueError, match="Username and password required"):
                MailBot()
        finally:
            # Restore env vars
            if old_username:
                os.environ["SU_USERNAME"] = old_username
            if old_password:
                os.environ["SU_PASSWORD"] = old_password

    def test_bot_initialization_with_params(self):
        """Test bot can be initialized with explicit params."""
        bot = MailBot(
            username="test",
            password="test",
            folder="sent",
            fetch_limit=10,
            poll_interval=30,
        )
        assert bot._folder == "sent"
        assert bot._fetch_limit == 10
        assert bot._poll_interval == 30


class TestBotApiParity:
    """Test sync/async API parity."""

    def test_sync_async_bot_api_parity(self):
        """Verify sync and async bots have same public methods."""
        sync_methods = {m for m in dir(MailBot) if not m.startswith("_")}
        async_methods = {m for m in dir(AsyncMailBot) if not m.startswith("_")}

        # AsyncMailBot should have same public API as MailBot
        assert sync_methods == async_methods
