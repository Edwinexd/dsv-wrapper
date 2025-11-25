"""Mail client for SU webmail (mail.su.se) via OWA API."""

import asyncio
import logging
from datetime import datetime

import httpx

from .exceptions import AuthenticationError, NetworkError, ParseError
from .models.mail import (
    BodyType,
    EmailAddress,
    EmailMessage,
    Importance,
    MailFolder,
    SendEmailResult,
)
from .utils import extract_attr, parse_html

logger = logging.getLogger(__name__)

# Browser-like headers required for OWA authentication
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
)
_BROWSER_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,sv;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

_API_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json; charset=utf-8",
    "X-Requested-With": "XMLHttpRequest",
}


def _parse_datetime(value: str | None) -> datetime | None:
    """Parse an ISO datetime string from OWA API."""
    if not value:
        return None

    try:
        # Handle Z suffix
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _parse_email_address(data: dict | None) -> EmailAddress | None:
    """Parse an EmailAddress from OWA API response."""
    if not data:
        return None
    mailbox = data.get("Mailbox", data)
    email = mailbox.get("EmailAddress", "")
    name = mailbox.get("Name", "")
    if not email:
        return None
    return EmailAddress(email=email, name=name)


def _parse_email_message(data: dict, include_body: bool = False) -> EmailMessage:
    """Parse an EmailMessage from OWA API response."""
    item_id = data.get("ItemId", {})
    sender = _parse_email_address(data.get("From"))
    recipients = [
        addr
        for addr in (_parse_email_address(r) for r in data.get("ToRecipients", []))
        if addr is not None
    ]
    cc_recipients = [
        addr
        for addr in (_parse_email_address(r) for r in data.get("CcRecipients", []))
        if addr is not None
    ]

    body_data = data.get("Body", {})
    body = body_data.get("Value", "") if include_body else ""
    body_type_str = body_data.get("BodyType", "Text")
    body_type = BodyType.HTML if body_type_str == "HTML" else BodyType.TEXT

    importance_str = data.get("Importance", "Normal")
    importance = (
        Importance.HIGH
        if importance_str == "High"
        else (Importance.LOW if importance_str == "Low" else Importance.NORMAL)
    )

    # DateTimeReceived not always returned in list view, fall back to DateTimeSent
    received_at = _parse_datetime(data.get("DateTimeReceived"))
    if not received_at:
        received_at = _parse_datetime(data.get("DateTimeSent")) or _parse_datetime(
            data.get("DateTimeCreated")
        )

    return EmailMessage(
        id=item_id.get("Id", ""),
        change_key=item_id.get("ChangeKey", ""),
        subject=data.get("Subject", ""),
        body=body,
        body_type=body_type,
        sender=sender,
        recipients=recipients,
        cc_recipients=cc_recipients,
        received_at=received_at,
        sent_at=_parse_datetime(data.get("DateTimeSent")),
        is_read=data.get("IsRead", False),
        has_attachments=data.get("HasAttachments", False),
        importance=importance,
    )


def _follow_redirects(
    client: httpx.Client, response: httpx.Response, max_redirects: int = 15
) -> httpx.Response:
    """Follow HTTP redirects manually."""
    for _ in range(max_redirects):
        if response.status_code not in (301, 302, 303):
            break
        location = response.headers.get("Location")
        if not location:
            break
        if location.startswith("/"):
            base = f"{response.url.scheme}://{response.url.host}"
            location = base + location
        response = client.get(location)
    return response


class MailClient:
    """Synchronous client for SU webmail (mail.su.se) via OWA API.

    This client authenticates through the SU Shibboleth SSO system and uses
    the Outlook Web App (OWA) JSON API to send emails.

    Note: Due to OWA JSON API limitations, listing emails is not supported.
    You can get folder statistics and send emails.

    Note: If you have "Undo Send" enabled in OWA settings, sent emails will
    appear in drafts for 30 seconds before being actually sent.
    """

    def __init__(self, username: str, password: str, timeout: int = 30):
        """Initialize the mail client.

        Args:
            username: SU username (e.g., 'abcd1234')
            password: SU password
            timeout: Request timeout in seconds
        """
        self._username = username
        self._password = password
        self._timeout = timeout
        self._client: httpx.Client | None = None
        self._owa_base: str | None = None
        self._canary: str | None = None

    def __enter__(self) -> "MailClient":
        """Enter context manager and authenticate."""
        self._client = httpx.Client(
            headers=_BROWSER_HEADERS,
            follow_redirects=False,
            timeout=self._timeout,
        )
        self._authenticate()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context manager and close client."""
        if self._client:
            self._client.close()
            self._client = None

    def _authenticate(self) -> None:
        """Perform SSO authentication to OWA."""
        if not self._client:
            raise NetworkError("Client not initialized")

        logger.debug("Starting mail.su.se SSO authentication")

        # Step 1: Start SSO flow
        response = self._client.get("https://mail.su.se/owa/")
        response = _follow_redirects(self._client, response)
        soup = parse_html(response.text)

        # Step 2: Handle localStorage form (Shibboleth)
        form = soup.find("form")
        if form:
            action = extract_attr(form, "action")
            if action and "execution" in action:
                form_data = {}
                for inp in form.find_all("input"):
                    name = inp.get("name")
                    if name:
                        form_data[name] = inp.get("value", "")
                form_data["_eventId_proceed"] = ""

                if action.startswith("/"):
                    action = "https://idp.it.su.se" + action

                response = self._client.post(action, data=form_data)
                response = _follow_redirects(self._client, response)
                soup = parse_html(response.text)

        # Step 3: Submit login credentials
        login_form = soup.find("form", {"id": "login"})
        if not login_form:
            login_form = soup.find("form")

        if login_form and "j_username" in str(login_form):
            action = extract_attr(login_form, "action")
            form_data = {}
            for inp in login_form.find_all("input"):
                name = inp.get("name")
                if name:
                    form_data[name] = inp.get("value", "")

            form_data["j_username"] = self._username
            form_data["j_password"] = self._password
            form_data["_eventId_proceed"] = ""
            form_data.pop("_eventId_authn/SPNEGO", None)
            form_data.pop("_eventId_trySPNEGO", None)

            if action and action.startswith("/"):
                action = "https://idp.it.su.se" + action

            response = self._client.post(action, data=form_data)
            soup = parse_html(response.text)

            # Check for login error
            error = soup.find("p", class_="form-error")
            if error:
                raise AuthenticationError(f"Login failed: {error.get_text().strip()}")

            response = _follow_redirects(self._client, response)
            soup = parse_html(response.text)

        # Step 4: Handle SAML/WS-Fed forms until we reach OWA
        owa_reached = False
        for _ in range(10):
            form = soup.find("form", method="post")
            if not form:
                form = soup.find("form")
            if not form:
                break

            form_str = str(form)
            if "SAMLResponse" in form_str or "wresult" in form_str or "wa=" in form_str:
                action = extract_attr(form, "action")
                form_data = {}
                for inp in form.find_all("input"):
                    name = inp.get("name")
                    if name:
                        form_data[name] = inp.get("value", "")

                headers = {
                    **_BROWSER_HEADERS,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": f"{response.url.scheme}://{response.url.host}",
                    "Referer": str(response.url),
                }
                response = self._client.post(action, data=form_data, headers=headers)

                # Follow any redirects (including 302)
                if response.status_code in (301, 302, 303):
                    response = _follow_redirects(self._client, response)

                soup = parse_html(response.text)

                # Check if we've reached OWA
                url_str = str(response.url).lower()
                if ("owa" in url_str or "ebox" in url_str) and response.status_code == 200:
                    title = soup.find("title")
                    title_text = title.get_text() if title else ""
                    if title and "Working" not in title_text:
                        owa_reached = True
                        break
            else:
                break

        if not owa_reached:
            raise AuthenticationError("Failed to complete OWA authentication")

        # Get OWA base URL and canary token
        self._owa_base = f"{response.url.scheme}://{response.url.host}"
        self._canary = None
        for cookie in self._client.cookies.jar:
            if cookie.name == "X-OWA-CANARY":
                self._canary = cookie.value
                break

        if not self._canary:
            raise AuthenticationError("Failed to get OWA canary token")

        logger.info("Successfully authenticated to mail.su.se")

    def _api_request(self, action: str, body: dict, action_id: int = -1) -> dict:
        """Make an OWA API request."""
        if not self._client or not self._owa_base or not self._canary:
            raise NetworkError("Not authenticated")

        headers = {
            **_BROWSER_HEADERS,
            **_API_HEADERS,
            "X-OWA-CANARY": self._canary,
            "X-OWA-ActionName": action,
            "Action": action,
        }

        url = f"{self._owa_base}/owa/service.svc?action={action}&ID={action_id}&AC=1"
        response = self._client.post(url, headers=headers, json=body)

        if response.status_code == 440:
            raise AuthenticationError("Session expired")
        if response.status_code != 200:
            logger.error(f"API request failed: {response.text[:500]}")
            raise NetworkError(f"API request failed with status {response.status_code}")

        try:
            return response.json()
        except ValueError as e:
            raise ParseError(f"Failed to parse API response: {e}") from e

    def send_email(
        self,
        to: list[str] | str,
        subject: str,
        body: str,
        body_type: BodyType = BodyType.TEXT,
        cc: list[str] | None = None,
        save_to_sent: bool = True,
    ) -> SendEmailResult:
        """Send an email.

        Note: If you have "Undo Send" enabled in OWA settings, the email will
        appear in drafts for the configured delay before being sent.

        Args:
            to: Recipient email address(es)
            subject: Email subject
            body: Email body content
            body_type: Body content type (Text or HTML)
            cc: CC recipient email address(es)
            save_to_sent: Whether to save a copy to Sent Items

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
            # Step 1: Create draft without recipients
            # (OWA API doesn't save recipients in CreateItem, must use UpdateItem)
            data = self._api_request(
                "CreateItem",
                {
                    "Header": {"RequestServerVersion": "Exchange2013"},
                    "Body": {
                        "MessageDisposition": "SaveOnly",
                        "SavedItemFolderId": {
                            "__type": "TargetFolderId:#Exchange",
                            "BaseFolderId": {
                                "__type": "DistinguishedFolderId:#Exchange",
                                "Id": "drafts",
                            },
                        },
                        "Items": [
                            {
                                "ItemClass": "IPM.Note",
                                "Subject": subject,
                                "Body": {"BodyType": body_type.value, "Value": body},
                            }
                        ],
                    },
                },
                action_id=-2,
            )

            items = data.get("Body", {}).get("ResponseMessages", {}).get("Items", [])
            if not items:
                return SendEmailResult(success=False, error="No response from CreateItem")

            item = items[0]
            if item.get("ResponseCode") != "NoError":
                return SendEmailResult(success=False, error=item.get("ResponseCode"))

            created = item.get("Items", [{}])[0]
            item_id = created.get("ItemId", {}).get("Id")
            change_key = created.get("ItemId", {}).get("ChangeKey")

            if not item_id:
                return SendEmailResult(success=False, error="No item ID returned")

            # Step 2: Update draft to add recipients
            updates = [
                {
                    "__type": "SetItemField:#Exchange",
                    "Path": {"__type": "PropertyUri:#Exchange", "FieldURI": "ToRecipients"},
                    "Item": {
                        "__type": "Message:#Exchange",
                        "ToRecipients": [{"EmailAddress": addr} for addr in to],
                    },
                }
            ]

            if cc:
                updates.append(
                    {
                        "__type": "SetItemField:#Exchange",
                        "Path": {"__type": "PropertyUri:#Exchange", "FieldURI": "CcRecipients"},
                        "Item": {
                            "__type": "Message:#Exchange",
                            "CcRecipients": [{"EmailAddress": addr} for addr in cc],
                        },
                    }
                )

            data = self._api_request(
                "UpdateItem",
                {
                    "Header": {"RequestServerVersion": "Exchange2013"},
                    "Body": {
                        "MessageDisposition": "SaveOnly",
                        "ConflictResolution": "AlwaysOverwrite",
                        "ItemChanges": [
                            {
                                "ItemId": {
                                    "__type": "ItemId:#Exchange",
                                    "Id": item_id,
                                    "ChangeKey": change_key,
                                },
                                "Updates": updates,
                            }
                        ],
                    },
                },
                action_id=-3,
            )

            items = data.get("Body", {}).get("ResponseMessages", {}).get("Items", [])
            if not items or items[0].get("ResponseCode") != "NoError":
                err_code = items[0].get("ResponseCode") if items else "no response"
                return SendEmailResult(success=False, error=f"UpdateItem failed: {err_code}")

            # Get updated change key
            updated = items[0].get("Items", [{}])[0]
            change_key = updated.get("ItemId", {}).get("ChangeKey")

            # Step 3: Send the message
            send_body: dict = {
                "ItemIds": [
                    {
                        "__type": "ItemId:#Exchange",
                        "Id": item_id,
                        "ChangeKey": change_key,
                    }
                ],
            }

            if save_to_sent:
                send_body["SaveItemToFolder"] = True
                send_body["SavedItemFolderId"] = {
                    "__type": "TargetFolderId:#Exchange",
                    "BaseFolderId": {
                        "__type": "DistinguishedFolderId:#Exchange",
                        "Id": "sentitems",
                    },
                }

            data = self._api_request(
                "SendItem",
                {
                    "Header": {"RequestServerVersion": "Exchange2013"},
                    "Body": send_body,
                },
                action_id=-4,
            )

            items = data.get("Body", {}).get("ResponseMessages", {}).get("Items", [])
            if not items:
                return SendEmailResult(success=False, error="No response from SendItem")

            item = items[0]
            if item.get("ResponseCode") != "NoError":
                err = f"SendItem failed: {item.get('ResponseCode')}"
                return SendEmailResult(success=False, error=err)

            return SendEmailResult(success=True, message_id=item_id)

        except (NetworkError, ParseError) as e:
            return SendEmailResult(success=False, error=str(e))

    def get_folder(self, folder_name: str = "inbox") -> MailFolder:
        """Get folder information.

        Args:
            folder_name: Distinguished folder name ('inbox', 'drafts', 'sentitems', etc.)

        Returns:
            MailFolder with folder details
        """
        data = self._api_request(
            "GetFolder",
            {
                "Header": {"RequestServerVersion": "Exchange2013"},
                "Body": {
                    "FolderShape": {"BaseShape": "Default"},
                    "FolderIds": [{"__type": "DistinguishedFolderId:#Exchange", "Id": folder_name}],
                },
            },
        )

        items = data.get("Body", {}).get("ResponseMessages", {}).get("Items", [])
        if not items:
            raise ParseError("No folder response")

        item = items[0]
        if item.get("ResponseCode") != "NoError":
            raise ParseError(f"GetFolder failed: {item.get('ResponseCode')}")

        folders = item.get("Folders", [])
        if not folders:
            raise ParseError("No folder data")

        folder = folders[0]
        return MailFolder(
            id=folder.get("FolderId", {}).get("Id", ""),
            name=folder.get("DisplayName", folder_name),
            total_count=folder.get("TotalCount", 0),
            unread_count=folder.get("UnreadCount", 0),
        )

    def get_emails(self, folder_name: str = "inbox", limit: int = 50) -> list[EmailMessage]:
        """Get emails from a folder.

        Note: This returns email headers without body content. Use get_email()
        to retrieve full email content.

        Args:
            folder_name: Distinguished folder name ('inbox', 'drafts', 'sentitems', etc.)
            limit: Maximum number of emails to return (default 50)

        Returns:
            List of EmailMessage objects (without body content)
        """
        # First get the folder ID
        folder = self.get_folder(folder_name)

        # Then list items using the actual folder ID
        data = self._api_request(
            "FindItem",
            {
                "Header": {"RequestServerVersion": "Exchange2013"},
                "Body": {
                    "ItemShape": {"BaseShape": "Default"},
                    "ParentFolderIds": [{"__type": "FolderId:#Exchange", "Id": folder.id}],
                    "Traversal": "Shallow",
                },
            },
        )

        items = data.get("Body", {}).get("ResponseMessages", {}).get("Items", [])
        if not items:
            return []

        item = items[0]
        if item.get("ResponseCode") != "NoError":
            raise ParseError(f"FindItem failed: {item.get('ResponseCode')}")

        root = item.get("RootFolder", {})
        email_items = root.get("Items", [])

        # Parse emails (limit the result)
        emails = []
        for email_data in email_items[:limit]:
            emails.append(_parse_email_message(email_data, include_body=False))

        return emails

    def get_email(
        self, message_id: str, change_key: str = "", body_type: BodyType = BodyType.TEXT
    ) -> EmailMessage:
        """Get full email content by ID.

        Args:
            message_id: The email message ID
            change_key: Optional change key (improves performance if provided)
            body_type: Preferred body format (Text or HTML)

        Returns:
            EmailMessage with full content including body
        """
        item_id_obj: dict = {"__type": "ItemId:#Exchange", "Id": message_id}
        if change_key:
            item_id_obj["ChangeKey"] = change_key

        data = self._api_request(
            "GetItem",
            {
                "Header": {"RequestServerVersion": "Exchange2013"},
                "Body": {
                    "ItemShape": {
                        "BaseShape": "AllProperties",
                        "BodyType": body_type.value,
                    },
                    "ItemIds": [item_id_obj],
                },
            },
        )

        items = data.get("Body", {}).get("ResponseMessages", {}).get("Items", [])
        if not items:
            raise ParseError("No item response")

        item = items[0]
        if item.get("ResponseCode") != "NoError":
            raise ParseError(f"GetItem failed: {item.get('ResponseCode')}")

        email_items = item.get("Items", [])
        if not email_items:
            raise ParseError("No email data")

        return _parse_email_message(email_items[0], include_body=True)

    def delete_email(self, message_id: str, permanent: bool = False) -> bool:
        """Delete an email by ID.

        Args:
            message_id: The email message ID to delete
            permanent: If True, permanently delete. If False, move to Deleted Items.

        Returns:
            True if deletion was successful
        """
        delete_type = "HardDelete" if permanent else "MoveToDeletedItems"

        data = self._api_request(
            "DeleteItem",
            {
                "Header": {"RequestServerVersion": "Exchange2013"},
                "Body": {
                    "DeleteType": delete_type,
                    "ItemIds": [{"__type": "ItemId:#Exchange", "Id": message_id}],
                },
            },
        )

        items = data.get("Body", {}).get("ResponseMessages", {}).get("Items", [])
        if not items:
            return False

        item = items[0]
        return item.get("ResponseCode") == "NoError"


class AsyncMailClient:
    """Asynchronous client for SU webmail (mail.su.se) via OWA API.

    This is a thin async wrapper around MailClient using asyncio.to_thread().
    """

    def __init__(self, username: str, password: str, timeout: int = 30):
        """Initialize the async mail client.

        Args:
            username: SU username (e.g., 'abcd1234')
            password: SU password
            timeout: Request timeout in seconds
        """
        self._username = username
        self._password = password
        self._timeout = timeout
        self._sync_client: MailClient | None = None

    async def __aenter__(self) -> "AsyncMailClient":
        """Enter async context manager and authenticate."""
        self._sync_client = MailClient(self._username, self._password, self._timeout)
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

    async def delete_email(self, message_id: str, permanent: bool = False) -> bool:
        """Delete an email by ID."""
        if not self._sync_client:
            raise NetworkError("Client not initialized")
        return await asyncio.to_thread(self._sync_client.delete_email, message_id, permanent)
