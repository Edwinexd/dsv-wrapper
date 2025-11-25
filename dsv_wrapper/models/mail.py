"""Pydantic models for Mail (SU webmail via OWA)."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class BodyType(str, Enum):
    """Email body type."""

    TEXT = "Text"
    HTML = "HTML"


class Importance(str, Enum):
    """Email importance level."""

    LOW = "Low"
    NORMAL = "Normal"
    HIGH = "High"


class EmailAddress(BaseModel):
    """Email address with optional display name."""

    email: str = Field(description="Email address")
    name: str = Field(default="", description="Display name")

    model_config = {"frozen": True}


class EmailMessage(BaseModel):
    """Email message from inbox or sent items."""

    id: str = Field(description="Message ID for API operations")
    change_key: str = Field(default="", description="Change key for updates")
    subject: str = Field(default="", description="Email subject")
    body: str = Field(default="", description="Email body content")
    body_type: BodyType = Field(default=BodyType.TEXT, description="Body content type")
    sender: EmailAddress | None = Field(default=None, description="Sender email address")
    recipients: list[EmailAddress] = Field(default_factory=list, description="To recipients")
    cc_recipients: list[EmailAddress] = Field(default_factory=list, description="CC recipients")
    received_at: datetime | None = Field(default=None, description="Date/time received")
    sent_at: datetime | None = Field(default=None, description="Date/time sent")
    is_read: bool = Field(default=False, description="Whether message has been read")
    has_attachments: bool = Field(default=False, description="Whether message has attachments")
    importance: Importance = Field(default=Importance.NORMAL, description="Message importance")

    model_config = {"frozen": True}


class MailFolder(BaseModel):
    """Email folder (inbox, sent, drafts, etc.)."""

    id: str = Field(description="Folder ID")
    name: str = Field(description="Folder display name")
    total_count: int = Field(default=0, description="Total messages in folder")
    unread_count: int = Field(default=0, description="Unread messages in folder")

    model_config = {"frozen": True}


class SendEmailResult(BaseModel):
    """Result of sending an email."""

    success: bool = Field(description="Whether send was successful")
    message_id: str | None = Field(default=None, description="ID of sent message")
    error: str | None = Field(default=None, description="Error message if failed")

    model_config = {"frozen": True}
