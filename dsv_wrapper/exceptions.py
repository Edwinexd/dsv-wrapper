"""Custom exceptions for dsv-wrapper package."""


class DSVWrapperError(Exception):
    """Base exception for all dsv-wrapper errors."""

    pass


class AuthenticationError(DSVWrapperError):
    """Raised when authentication fails."""

    pass


class SessionExpiredError(AuthenticationError):
    """Raised when the session has expired and needs to be renewed."""

    pass


class BookingError(DSVWrapperError):
    """Base exception for booking-related errors."""

    pass


class RoomNotAvailableError(BookingError):
    """Raised when a room is not available for booking."""

    pass


class InvalidTimeSlotError(BookingError):
    """Raised when an invalid time slot is provided."""

    pass


class ParseError(DSVWrapperError):
    """Raised when HTML parsing fails."""

    pass


class NetworkError(DSVWrapperError):
    """Raised when a network request fails."""

    pass


class HandledningError(DSVWrapperError):
    """Base exception for Handledning-related errors."""

    pass


class QueueError(HandledningError):
    """Raised when queue operations fail."""

    pass


class ValidationError(DSVWrapperError):
    """Raised when data validation fails."""

    pass


class ACTLabError(DSVWrapperError):
    """Raised when ACT Lab operations fail."""

    pass
