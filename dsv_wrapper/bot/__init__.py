"""Event-driven email monitoring bot for dsv_wrapper."""

from .events import BotError, ErrorCallback, EventType, NewEmailCallback, NewEmailEvent
from .mail_bot import AsyncMailBot, MailBot

__all__ = [
    "MailBot",
    "AsyncMailBot",
    "NewEmailEvent",
    "BotError",
    "EventType",
    "NewEmailCallback",
    "ErrorCallback",
]
