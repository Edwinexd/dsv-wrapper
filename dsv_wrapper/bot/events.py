"""Event models for email monitoring bot."""

from collections.abc import Callable
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from ..models.mail import EmailMessage


class EventType(str, Enum):
    """Types of email events."""

    NEW_EMAIL = "new_email"


class MailEvent(BaseModel):
    """Base email event."""

    event_type: EventType
    folder: str
    timestamp: datetime = Field(default_factory=datetime.now)


class NewEmailEvent(MailEvent):
    """Event fired when new email arrives."""

    event_type: EventType = EventType.NEW_EMAIL
    email: EmailMessage

    model_config = {"frozen": True}


class BotError(BaseModel):
    """Error event from bot."""

    error: Exception
    error_type: str
    message: str
    timestamp: datetime = Field(default_factory=datetime.now)
    recoverable: bool = True

    model_config = {"frozen": True, "arbitrary_types_allowed": True}


# Callback type aliases
NewEmailCallback = Callable[[NewEmailEvent], None]
ErrorCallback = Callable[[BotError], None]
