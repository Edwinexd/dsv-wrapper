"""Mail client for SU webmail (ebox.su.se) via standard IMAP/SMTP protocols.

This implementation uses standard IMAP (port 993/SSL) and SMTP (port 587/STARTTLS)
instead of the fragile OWA JSON API.
"""

import asyncio
import email
import email.utils
import hashlib
import html
import imaplib
import logging
import os
import re
import smtplib
import ssl
from datetime import UTC, datetime
from email.header import decode_header
from email.message import EmailMessage as StdEmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .exceptions import AuthenticationError, NetworkError, ParseError, ValidationError
from .models.mail import (
    BodyType,
    EmailAddress,
    EmailMessage,
    Importance,
    MailFolder,
    SendEmailResult,
)

logger = logging.getLogger(__name__)

# ebox.su.se server configuration
_IMAP_HOST = "ebox.su.se"
_IMAP_PORT = 993
_SMTP_HOST = "ebox.su.se"
_SMTP_PORT = 587

# Folder name mapping from OWA-style to IMAP-style
# Note: Folder names with spaces are quoted for IMAP compatibility
_FOLDER_MAP = {
    "inbox": "INBOX",
    "sentitems": '"Sent Items"',
    "drafts": "Drafts",
    "deleteditems": '"Deleted Items"',
    "junkemail": '"Junk Email"',
    "outbox": "Outbox",
}


def _decode_header_value(value: str | None) -> str:
    """Decode MIME encoded header value."""
    if not value:
        return ""
    decoded_parts = []
    for part, encoding in decode_header(value):
        if isinstance(part, bytes):
            decoded_parts.append(part.decode(encoding or "utf-8", errors="replace"))
        else:
            decoded_parts.append(part)
    return "".join(decoded_parts)


def _parse_email_address_string(addr_string: str | None) -> EmailAddress | None:
    """Parse an email address from a header string like 'Name <email@example.com>'."""
    if not addr_string:
        return None
    name, email_addr = email.utils.parseaddr(addr_string)
    if not email_addr:
        return None
    return EmailAddress(email=email_addr, name=_decode_header_value(name))


def _parse_address_list(header_value: str | None) -> list[EmailAddress]:
    """Parse a comma-separated list of email addresses."""
    if not header_value:
        return []
    addresses = email.utils.getaddresses([header_value])
    result = []
    for name, email_addr in addresses:
        if email_addr:
            result.append(EmailAddress(email=email_addr, name=_decode_header_value(name)))
    return result


def _parse_imap_date(date_string: str | None) -> datetime | None:
    """Parse date from email headers."""
    if not date_string:
        return None
    parsed = email.utils.parsedate_to_datetime(date_string)
    return parsed


def _get_email_body(msg: StdEmailMessage, body_type: BodyType) -> tuple[str, BodyType]:
    """Extract body content from email message."""
    # For multipart messages, find the right part
    if msg.is_multipart():
        text_body = ""
        html_body = ""
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    text_body = payload.decode(charset, errors="replace")
            elif content_type == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    html_body = payload.decode(charset, errors="replace")

        # Return preferred body type if available
        if body_type == BodyType.HTML and html_body:
            return html_body, BodyType.HTML
        if text_body:
            return text_body, BodyType.TEXT
        if html_body:
            return html_body, BodyType.HTML
        return "", BodyType.TEXT
    else:
        # Single-part message
        payload = msg.get_payload(decode=True)
        if not payload:
            return "", BodyType.TEXT
        charset = msg.get_content_charset() or "utf-8"
        content = payload.decode(charset, errors="replace")
        content_type = msg.get_content_type()
        if content_type == "text/html":
            return content, BodyType.HTML
        return content, BodyType.TEXT


def _parse_importance(headers: StdEmailMessage) -> Importance:
    """Parse importance/priority from email headers."""
    importance = headers.get("Importance", "").lower()
    priority = headers.get("X-Priority", "")

    if importance == "high" or priority == "1":
        return Importance.HIGH
    if importance == "low" or priority == "5":
        return Importance.LOW
    return Importance.NORMAL


def _has_attachments(msg: StdEmailMessage) -> bool:
    """Check if message has attachments."""
    if not msg.is_multipart():
        return False
    for part in msg.walk():
        content_disposition = part.get("Content-Disposition", "")
        if "attachment" in content_disposition:
            return True
    return False


def _html_to_plain_text(html_content: str) -> str:
    """Convert HTML content to plain text.

    This is a simple conversion that strips HTML tags and decodes entities.
    For more complex HTML, the output may not be perfect but will be readable.
    """
    # Remove script and style blocks
    text = re.sub(
        r"<(script|style)[^>]*>.*?</\1>", "", html_content, flags=re.IGNORECASE | re.DOTALL
    )

    # Replace common block elements with newlines
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</div>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</h[1-6]>", "\n\n", text, flags=re.IGNORECASE)

    # Remove all remaining HTML tags
    text = re.sub(r"<[^>]+>", "", text)

    # Decode HTML entities
    text = html.unescape(text)

    # Normalize whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()

    return text


class MailClient:
    """Synchronous client for SU webmail (ebox.su.se) via IMAP/SMTP.

    This client uses IMAP (port 993/SSL) for reading emails and
    SMTP (port 587/STARTTLS) for sending emails.

    Authentication uses the Windows AD domain format: winadsu\\username

    For function accounts (funktionskonto), use the function account's email
    address as the `email_address` parameter. Authentication is still done
    with your personal username and password.
    """

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        email_address: str | None = None,
        timeout: int = 30,
    ):
        """Initialize the mail client.

        Args:
            username: SU username (default: read from SU_USERNAME env var)
            password: SU password (default: read from SU_PASSWORD env var)
            email_address: The email address to use as the sender address
                (default: read from SU_EMAIL env var).
                For personal accounts, use your personal email address.
                For function accounts (funktionskonto), use the function account's email address.
            timeout: Request timeout in seconds

        Raises:
            AuthenticationError: If credentials or email not provided and not in env vars
        """
        # Get credentials from env vars if not provided
        self._username = username or os.environ.get("SU_USERNAME")
        self._password = password or os.environ.get("SU_PASSWORD")
        self._email_address = email_address or os.environ.get("SU_EMAIL")

        if not self._username or not self._password:
            raise AuthenticationError(
                "Username and password must be provided either as arguments or "
                "via SU_USERNAME and SU_PASSWORD environment variables"
            )
        if not self._email_address:
            raise AuthenticationError(
                "Email address must be provided either as an argument or "
                "via SU_EMAIL environment variable"
            )

        self._timeout = timeout
        self._imap: imaplib.IMAP4_SSL | None = None
        self._user_email: str | None = None

    def __enter__(self) -> "MailClient":
        """Enter context manager and connect to IMAP server."""
        self._connect_imap()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context manager and close connections."""
        self._disconnect_imap()

    def _connect_imap(self) -> None:
        """Connect and authenticate to IMAP server."""
        try:
            context = ssl.create_default_context()
            self._imap = imaplib.IMAP4_SSL(
                _IMAP_HOST, _IMAP_PORT, ssl_context=context, timeout=self._timeout
            )

            # Use Windows AD format for authentication
            login_username = f"winadsu\\{self._username}"
            self._imap.login(login_username, self._password)

            # Use the provided email address
            self._user_email = self._email_address

            logger.info("Successfully connected to ebox.su.se IMAP")

        except imaplib.IMAP4.error as e:
            error_msg = str(e)
            if "authentication failed" in error_msg.lower() or "login failed" in error_msg.lower():
                raise AuthenticationError(f"IMAP login failed: {error_msg}") from e
            raise NetworkError(f"IMAP connection failed: {error_msg}") from e
        except (OSError, TimeoutError) as e:
            raise NetworkError(f"Failed to connect to IMAP server: {e}") from e

    def _disconnect_imap(self) -> None:
        """Disconnect from IMAP server."""
        if self._imap:
            try:
                self._imap.logout()
            except (imaplib.IMAP4.error, OSError):
                pass  # Ignore errors during logout
            self._imap = None

    def _get_imap_folder(self, folder_name: str) -> str:
        """Convert OWA-style folder name to IMAP folder name."""
        return _FOLDER_MAP.get(folder_name.lower(), folder_name)

    def send_email(
        self,
        to: list[str] | str,
        subject: str,
        body: str,
        body_type: BodyType = BodyType.TEXT,
        cc: list[str] | None = None,
        save_to_sent: bool = True,
    ) -> SendEmailResult:
        """Send an email via SMTP.

        Args:
            to: Recipient email address(es)
            subject: Email subject
            body: Email body content
            body_type: Body content type (Text or HTML)
            cc: CC recipient email address(es)
            save_to_sent: Whether to save a copy to Sent Items (via IMAP APPEND)

        Returns:
            SendEmailResult with success status and message ID
        """
        # Normalize recipients
        if isinstance(to, str):
            to = [to]
        if cc is None:
            cc = []
        elif isinstance(cc, str):
            cc = [cc]

        try:
            # Create email message
            if body_type == BodyType.HTML:
                msg = MIMEMultipart("alternative")
                # Add plain text version (converted from HTML)
                plain_text = _html_to_plain_text(body)
                text_part = MIMEText(plain_text, "plain", "utf-8")
                html_part = MIMEText(body, "html", "utf-8")
                msg.attach(text_part)
                msg.attach(html_part)
            else:
                msg = MIMEText(body, "plain", "utf-8")

            # Set headers
            msg["From"] = self._user_email
            msg["To"] = ", ".join(to)
            msg["Subject"] = subject

            if cc:
                msg["Cc"] = ", ".join(cc)

            # Add Message-ID
            msg_id = email.utils.make_msgid(domain="dsv.su.se")
            msg["Message-ID"] = msg_id
            msg["Date"] = email.utils.formatdate(localtime=True)

            # Connect to SMTP and send
            context = ssl.create_default_context()
            with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=self._timeout) as smtp:
                smtp.starttls(context=context)
                login_username = f"winadsu\\{self._username}"
                smtp.login(login_username, self._password)

                all_recipients = to + cc
                smtp.sendmail(self._user_email, all_recipients, msg.as_string())

            # Optionally save to Sent Items via IMAP
            if save_to_sent and self._imap:
                try:
                    sent_folder = self._get_imap_folder("sentitems")
                    # Add to sent folder with current time (email was just sent)
                    sent_time = imaplib.Time2Internaldate(datetime.now(tz=UTC))
                    # Flags must be in parentheses for IMAP APPEND
                    self._imap.append(sent_folder, "(\\Seen)", sent_time, msg.as_bytes())
                except imaplib.IMAP4.error as e:
                    logger.warning(f"Failed to save to Sent Items: {e}")
                    # Don't fail the send if saving to sent fails

            # Generate a pseudo message ID for the result
            # (SMTP doesn't return a server-side ID)
            result_id = hashlib.sha256(msg_id.encode()).hexdigest()[:32]

            return SendEmailResult(success=True, message_id=result_id)

        except smtplib.SMTPAuthenticationError as e:
            return SendEmailResult(success=False, error=f"SMTP authentication failed: {e}")
        except smtplib.SMTPException as e:
            return SendEmailResult(success=False, error=f"SMTP error: {e}")
        except (OSError, TimeoutError) as e:
            return SendEmailResult(success=False, error=f"Network error: {e}")

    def get_folder(self, folder_name: str = "inbox") -> MailFolder:
        """Get folder information.

        Args:
            folder_name: Folder name ('inbox', 'drafts', 'sentitems', etc.)

        Returns:
            MailFolder with folder details
        """
        if not self._imap:
            raise NetworkError("IMAP not connected")

        imap_folder = self._get_imap_folder(folder_name)

        try:
            # Select folder to get counts
            status, data = self._imap.select(imap_folder, readonly=True)
            if status != "OK":
                raise ParseError(f"Failed to select folder: {imap_folder}")

            # Get total count
            total_count = int(data[0].decode())

            # Get unread count
            status, data = self._imap.search(None, "UNSEEN")
            if status != "OK":
                unread_count = 0
            else:
                unread_ids = data[0].split()
                unread_count = len(unread_ids)

            # Generate folder ID (IMAP doesn't have IDs, use hash of name)
            folder_id = hashlib.sha256(imap_folder.encode()).hexdigest()[:32]

            return MailFolder(
                id=folder_id,
                name=imap_folder,
                total_count=total_count,
                unread_count=unread_count,
            )

        except imaplib.IMAP4.error as e:
            raise ParseError(f"IMAP error getting folder: {e}") from e

    def get_emails(self, folder_name: str = "inbox", limit: int = 50) -> list[EmailMessage]:
        """Get emails from a folder.

        Note: This returns email headers without body content. Use get_email()
        to retrieve full email content.

        Args:
            folder_name: Folder name ('inbox', 'drafts', 'sentitems', etc.)
            limit: Maximum number of emails to return (default 50)

        Returns:
            List of EmailMessage objects (without body content)
        """
        if not self._imap:
            raise NetworkError("IMAP not connected")

        imap_folder = self._get_imap_folder(folder_name)

        try:
            status, data = self._imap.select(imap_folder, readonly=True)
            if status != "OK":
                raise ParseError(f"Failed to select folder: {imap_folder}")

            # Get all message IDs (try SORT first, fallback to SEARCH)
            msg_ids = []
            try:
                # SORT is not supported by all IMAP servers (e.g., Exchange)
                status, data = self._imap.sort("(REVERSE DATE)", "UTF-8", "ALL")
                if status == "OK":
                    msg_ids = data[0].split()
            except imaplib.IMAP4.error:
                pass  # SORT not supported, fall through to SEARCH

            if not msg_ids:
                # Fallback to SEARCH (results won't be sorted)
                status, data = self._imap.search(None, "ALL")
                if status == "OK" and data[0]:
                    msg_ids = data[0].split()
                    # Reverse to get newest first (higher sequence numbers = newer)
                    msg_ids = list(reversed(msg_ids))

            if not msg_ids:
                return []

            # Limit results
            msg_ids = msg_ids[:limit]

            emails = []
            for msg_id in msg_ids:
                # Fetch headers only (not body)
                status, data = self._imap.fetch(
                    msg_id, "(FLAGS BODY.PEEK[HEADER] INTERNALDATE)"
                )
                if status != "OK" or not data or not data[0]:
                    continue

                # Parse the response
                msg_data = data[0]
                if isinstance(msg_data, tuple) and len(msg_data) >= 2:
                    flags_info = msg_data[0].decode()
                    headers_raw = msg_data[1]

                    # Parse headers
                    msg = email.message_from_bytes(headers_raw)

                    # Check if read (\\Seen flag)
                    is_read = b"\\Seen" in flags_info.encode()

                    # Extract date
                    date_str = msg.get("Date")
                    received_at = _parse_imap_date(date_str)
                    sent_at = received_at

                    # Parse sender and recipients
                    sender = _parse_email_address_string(msg.get("From"))
                    recipients = _parse_address_list(msg.get("To"))
                    cc_recipients = _parse_address_list(msg.get("Cc"))

                    # Generate a unique ID from message ID or sequence number
                    message_id_header = msg.get("Message-ID", "")
                    if message_id_header:
                        email_id = hashlib.sha256(message_id_header.encode()).hexdigest()[:32]
                    else:
                        email_id = hashlib.sha256(
                            f"{imap_folder}:{msg_id.decode()}".encode()
                        ).hexdigest()[:32]

                    emails.append(
                        EmailMessage(
                            id=email_id,
                            change_key=msg_id.decode(),  # Use IMAP sequence number as change_key
                            subject=_decode_header_value(msg.get("Subject", "")),
                            body="",  # Don't fetch body in list view
                            body_type=BodyType.TEXT,
                            sender=sender,
                            recipients=recipients,
                            cc_recipients=cc_recipients,
                            received_at=received_at,
                            sent_at=sent_at,
                            is_read=is_read,
                            # has_attachments is False in list view - can't determine from
                            # headers alone. Use get_email() to get accurate attachment info.
                            has_attachments=False,
                            importance=_parse_importance(msg),
                        )
                    )

            return emails

        except imaplib.IMAP4.error as e:
            raise ParseError(f"IMAP error listing emails: {e}") from e

    def get_email(
        self, message_id: str, change_key: str = "", body_type: BodyType = BodyType.TEXT
    ) -> EmailMessage:
        """Get full email content by ID.

        Args:
            message_id: The email message ID (hash from get_emails)
            change_key: IMAP sequence number (from get_emails change_key field)
            body_type: Preferred body format (Text or HTML)

        Returns:
            EmailMessage with full content including body
        """
        if not self._imap:
            raise NetworkError("IMAP not connected")

        if not change_key:
            raise ParseError("change_key (IMAP sequence number) is required")

        try:
            # Fetch full message using the sequence number (change_key)
            status, data = self._imap.fetch(change_key.encode(), "(FLAGS RFC822)")
            if status != "OK" or not data or not data[0]:
                raise ParseError(f"Failed to fetch email: {message_id}")

            # Parse the response
            msg_data = data[0]
            if not isinstance(msg_data, tuple) or len(msg_data) < 2:
                raise ParseError("Invalid IMAP response format")

            flags_info = msg_data[0].decode()
            raw_email = msg_data[1]

            # Parse email
            msg = email.message_from_bytes(raw_email)

            # Check if read
            is_read = b"\\Seen" in flags_info.encode()

            # Get body
            body_content, actual_body_type = _get_email_body(msg, body_type)

            # Parse dates
            date_str = msg.get("Date")
            received_at = _parse_imap_date(date_str)
            sent_at = received_at

            # Parse sender and recipients
            sender = _parse_email_address_string(msg.get("From"))
            recipients = _parse_address_list(msg.get("To"))
            cc_recipients = _parse_address_list(msg.get("Cc"))

            return EmailMessage(
                id=message_id,
                change_key=change_key,
                subject=_decode_header_value(msg.get("Subject", "")),
                body=body_content,
                body_type=actual_body_type,
                sender=sender,
                recipients=recipients,
                cc_recipients=cc_recipients,
                received_at=received_at,
                sent_at=sent_at,
                is_read=is_read,
                has_attachments=_has_attachments(msg),
                importance=_parse_importance(msg),
            )

        except imaplib.IMAP4.error as e:
            raise ParseError(f"IMAP error fetching email: {e}") from e

    def delete_email(self, change_key: str, permanent: bool = False) -> None:
        """Delete an email using its IMAP sequence number.

        Note: Use the change_key field from EmailMessage returned by get_emails().
        The change_key contains the IMAP sequence number needed for deletion.

        Args:
            change_key: The IMAP sequence number from EmailMessage.change_key field.
            permanent: If True, permanently delete. If False, move to Deleted Items.

        Raises:
            NetworkError: If IMAP is not connected.
            ValidationError: If change_key is invalid.
            ParseError: If the IMAP operation fails.
        """
        if not self._imap:
            raise NetworkError("IMAP not connected")

        if not change_key or not change_key.isdigit():
            raise ValidationError(
                "delete_email requires a valid change_key (IMAP sequence number). "
                "Use the change_key field from EmailMessage returned by get_emails()."
            )

        try:
            seq_num = change_key.encode()  # IMAP expects bytes
            if permanent:
                # Mark as deleted and expunge
                self._imap.store(seq_num, "+FLAGS", "(\\Deleted)")
                self._imap.expunge()
            else:
                # Move to deleted items
                deleted_folder = self._get_imap_folder("deleteditems")
                self._imap.copy(seq_num, deleted_folder)
                self._imap.store(seq_num, "+FLAGS", "(\\Deleted)")
                self._imap.expunge()
        except imaplib.IMAP4.error as e:
            raise ParseError(f"Failed to delete email: {e}") from e


class AsyncMailClient:
    """Asynchronous client for SU webmail (ebox.su.se) via IMAP/SMTP.

    This is a thin async wrapper around MailClient using asyncio.to_thread().
    """

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        email_address: str | None = None,
        timeout: int = 30,
    ):
        """Initialize the async mail client.

        Args:
            username: SU username (default: read from SU_USERNAME env var)
            password: SU password (default: read from SU_PASSWORD env var)
            email_address: The email address to use as the sender address
                (default: read from SU_EMAIL env var).
                For personal accounts, use your personal email address.
                For function accounts (funktionskonto), use the function account's email address.
            timeout: Request timeout in seconds

        Raises:
            AuthenticationError: If credentials or email not provided and not in env vars
        """
        self._username = username
        self._password = password
        self._email_address = email_address
        self._timeout = timeout
        self._sync_client: MailClient | None = None

    async def __aenter__(self) -> "AsyncMailClient":
        """Enter async context manager and authenticate."""
        self._sync_client = MailClient(
            self._username, self._password, self._email_address, self._timeout
        )
        await asyncio.to_thread(self._sync_client.__enter__)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context manager and close client."""
        if self._sync_client:
            self._sync_client.__exit__(exc_type, exc_val, exc_tb)
            self._sync_client = None

    async def send_email(
        self,
        to: list[str] | str,
        subject: str,
        body: str,
        body_type: BodyType = BodyType.TEXT,
        cc: list[str] | None = None,
        save_to_sent: bool = True,
    ) -> SendEmailResult:
        """Send an email."""
        if not self._sync_client:
            raise NetworkError("Client not initialized")
        return await asyncio.to_thread(
            self._sync_client.send_email, to, subject, body, body_type, cc, save_to_sent
        )

    async def get_folder(self, folder_name: str = "inbox") -> MailFolder:
        """Get folder information."""
        if not self._sync_client:
            raise NetworkError("Client not initialized")
        return await asyncio.to_thread(self._sync_client.get_folder, folder_name)

    async def get_emails(self, folder_name: str = "inbox", limit: int = 50) -> list[EmailMessage]:
        """Get emails from a folder."""
        if not self._sync_client:
            raise NetworkError("Client not initialized")
        return await asyncio.to_thread(self._sync_client.get_emails, folder_name, limit)

    async def get_email(
        self, message_id: str, change_key: str = "", body_type: BodyType = BodyType.TEXT
    ) -> EmailMessage:
        """Get full email content by ID."""
        if not self._sync_client:
            raise NetworkError("Client not initialized")
        return await asyncio.to_thread(
            self._sync_client.get_email, message_id, change_key, body_type
        )

    async def delete_email(self, change_key: str, permanent: bool = False) -> None:
        """Delete an email using its IMAP sequence number.

        Note: Use the change_key field from EmailMessage returned by get_emails().

        Raises:
            NetworkError: If IMAP is not connected.
            ValidationError: If change_key is invalid.
            ParseError: If the IMAP operation fails.
        """
        if not self._sync_client:
            raise NetworkError("Client not initialized")
        await asyncio.to_thread(
            self._sync_client.delete_email, change_key, permanent
        )
