"""Tests for MailClient functionality."""

import asyncio
import os
import time

import pytest

from dsv_wrapper import (
    AsyncMailClient,
    BodyType,
    EmailAddress,
    EmailMessage,
    Importance,
    MailClient,
    MailFolder,
    SendEmailResult,
)

# Skip all tests if credentials not set
pytestmark = pytest.mark.skipif(
    not os.environ.get("SU_USERNAME") or not os.environ.get("SU_PASSWORD"),
    reason="SU_USERNAME and SU_PASSWORD environment variables required",
)


@pytest.fixture
def credentials():
    """Get credentials from environment."""
    return {
        "username": os.environ.get("SU_USERNAME"),
        "password": os.environ.get("SU_PASSWORD"),
    }


class TestMailClient:
    """Tests for synchronous MailClient."""

    def test_get_folder_inbox(self, credentials):
        """Test getting inbox folder info."""
        with MailClient(**credentials) as client:
            folder = client.get_folder("inbox")

            assert isinstance(folder, MailFolder)
            assert folder.id
            assert folder.name.lower() in ("inbox", "inkorgen")
            assert folder.total_count >= 0
            assert folder.unread_count >= 0

    def test_get_folder_sentitems(self, credentials):
        """Test getting sent items folder info."""
        with MailClient(**credentials) as client:
            folder = client.get_folder("sentitems")

            assert isinstance(folder, MailFolder)
            assert folder.id
            assert "sent" in folder.name.lower()
            assert folder.total_count >= 0

    def test_get_emails_inbox(self, credentials):
        """Test listing emails from inbox."""
        with MailClient(**credentials) as client:
            emails = client.get_emails("inbox", limit=5)

            assert isinstance(emails, list)
            # Inbox might be empty, but if it has emails they should be valid
            for email in emails:
                assert isinstance(email, EmailMessage)
                assert email.id
                assert email.change_key
                # Subject can be empty
                assert email.is_read in (True, False)

    def test_get_email_full_content(self, credentials):
        """Test getting full email content."""
        with MailClient(**credentials) as client:
            emails = client.get_emails("inbox", limit=1)

            if not emails:
                pytest.skip("No emails in inbox to test")

            email = emails[0]
            full_email = client.get_email(email.id, email.change_key)

            assert isinstance(full_email, EmailMessage)
            assert full_email.id == email.id
            assert full_email.subject == email.subject
            # Full email should have body
            assert full_email.body is not None
            assert full_email.body_type in (BodyType.TEXT, BodyType.HTML)

    def test_send_email_to_self(self, credentials):
        """Test sending email to self with AUTOMATEDTESTSEND pattern."""
        my_email = os.environ.get("SU_EMAIL", "edwinsu@dsv.su.se")

        timestamp = int(time.time())
        subject = f"AUTOMATEDTESTSEND - {timestamp}"

        with MailClient(**credentials) as client:
            result = client.send_email(
                to=my_email,
                subject=subject,
                body=f"Automated test email sent at {timestamp}. Safe to delete.",
                body_type=BodyType.TEXT,
                save_to_sent=True,
            )

            assert isinstance(result, SendEmailResult)
            assert result.success is True
            assert result.message_id is not None
            assert result.error is None

            # Clean up: delete from inbox and sent items
            time.sleep(2)
            for folder in ("inbox", "sentitems"):
                emails = client.get_emails(folder, limit=20)
                for email in emails:
                    if email.subject == subject:
                        client.delete_email(email.id, permanent=True)

    def test_send_email_html(self, credentials):
        """Test sending HTML email to self."""
        my_email = os.environ.get("SU_EMAIL", "edwinsu@dsv.su.se")

        timestamp = int(time.time())
        subject = f"AUTOMATEDTESTSEND - {timestamp}"

        with MailClient(**credentials) as client:
            result = client.send_email(
                to=my_email,
                subject=subject,
                body=f"<html><body><h1>Test</h1><p>Test at {timestamp}</p></body></html>",
                body_type=BodyType.HTML,
                save_to_sent=True,
            )

            assert result.success is True
            assert result.message_id is not None

            # Clean up: delete from inbox and sent items
            time.sleep(2)
            for folder in ("inbox", "sentitems"):
                emails = client.get_emails(folder, limit=20)
                for email in emails:
                    if email.subject == subject:
                        client.delete_email(email.id, permanent=True)

    def test_send_and_delete_email(self, credentials):
        """Test sending email and then deleting it from inbox."""
        my_email = os.environ.get("SU_EMAIL", "edwinsu@dsv.su.se")

        timestamp = int(time.time())
        subject = f"AUTOMATEDTESTSEND - {timestamp}"

        with MailClient(**credentials) as client:
            # Send the email
            result = client.send_email(
                to=my_email,
                subject=subject,
                body=f"Test email at {timestamp}. Will be deleted.",
                body_type=BodyType.TEXT,
                save_to_sent=True,
            )

            assert result.success is True

            # Wait a moment for email to arrive (undo send delay)
            time.sleep(2)

            # Find the email in inbox by subject
            emails = client.get_emails("inbox", limit=20)
            test_email = None
            for email in emails:
                if email.subject == subject:
                    test_email = email
                    break

            # Delete if found
            if test_email:
                deleted = client.delete_email(test_email.id, permanent=True)
                assert deleted is True

                # Also delete from sent items
                sent_emails = client.get_emails("sentitems", limit=20)
                for email in sent_emails:
                    if email.subject == subject:
                        client.delete_email(email.id, permanent=True)
                        break


class TestAsyncMailClient:
    """Tests for asynchronous AsyncMailClient."""

    @pytest.mark.asyncio
    async def test_async_get_folder(self, credentials):
        """Test async getting folder info."""
        async with AsyncMailClient(**credentials) as client:
            folder = await client.get_folder("inbox")

            assert isinstance(folder, MailFolder)
            assert folder.id
            assert folder.total_count >= 0

    @pytest.mark.asyncio
    async def test_async_get_emails(self, credentials):
        """Test async listing emails."""
        async with AsyncMailClient(**credentials) as client:
            emails = await client.get_emails("inbox", limit=3)

            assert isinstance(emails, list)
            for email in emails:
                assert isinstance(email, EmailMessage)

    @pytest.mark.asyncio
    async def test_async_send_email(self, credentials):
        """Test async sending email to self."""
        my_email = os.environ.get("SU_EMAIL", "edwinsu@dsv.su.se")

        timestamp = int(time.time())
        subject = f"AUTOMATEDTESTSEND - {timestamp}"

        async with AsyncMailClient(**credentials) as client:
            result = await client.send_email(
                to=my_email,
                subject=subject,
                body=f"Async automated test email at {timestamp}.",
                body_type=BodyType.TEXT,
            )

            assert result.success is True

            # Clean up: delete from inbox and sent items
            await asyncio.sleep(2)
            for folder in ("inbox", "sentitems"):
                emails = await client.get_emails(folder, limit=20)
                for email in emails:
                    if email.subject == subject:
                        await client.delete_email(email.id, permanent=True)


class TestMailModels:
    """Tests for mail-related models."""

    def test_email_address_model(self):
        """Test EmailAddress model."""
        addr = EmailAddress(email="test@example.com", name="Test User")
        assert addr.email == "test@example.com"
        assert addr.name == "Test User"

        # Frozen model - should raise ValidationError on assignment
        with pytest.raises((TypeError, ValueError)):
            addr.email = "other@example.com"

    def test_mail_folder_model(self):
        """Test MailFolder model."""
        folder = MailFolder(
            id="abc123",
            name="Inbox",
            total_count=100,
            unread_count=5,
        )
        assert folder.id == "abc123"
        assert folder.name == "Inbox"
        assert folder.total_count == 100
        assert folder.unread_count == 5

    def test_send_email_result_model(self):
        """Test SendEmailResult model."""
        # Success case
        result = SendEmailResult(success=True, message_id="msg123")
        assert result.success is True
        assert result.message_id == "msg123"
        assert result.error is None

        # Error case
        result = SendEmailResult(success=False, error="Failed to send")
        assert result.success is False
        assert result.message_id is None
        assert result.error == "Failed to send"

    def test_body_type_enum(self):
        """Test BodyType enum."""
        assert BodyType.TEXT.value == "Text"
        assert BodyType.HTML.value == "HTML"

    def test_importance_enum(self):
        """Test Importance enum."""
        assert Importance.LOW.value == "Low"
        assert Importance.NORMAL.value == "Normal"
        assert Importance.HIGH.value == "High"


class TestMailApiParity:
    """Test sync/async API parity."""

    def test_sync_async_mail_api_parity(self):
        """Verify sync and async clients have same public methods."""
        sync_methods = {
            m for m in dir(MailClient) if not m.startswith("_") and callable(getattr(MailClient, m))
        }
        async_methods = {
            m
            for m in dir(AsyncMailClient)
            if not m.startswith("_") and callable(getattr(AsyncMailClient, m))
        }

        # Both should have the same public methods
        assert sync_methods == async_methods, (
            f"API parity mismatch. "
            f"Sync only: {sync_methods - async_methods}, "
            f"Async only: {async_methods - sync_methods}"
        )
