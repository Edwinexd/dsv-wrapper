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


class PresentationNotReadyError(ParseError):
    """Raised when a Play presentation isn't ready for downstream consumption.

    DSVPlay processes uploads asynchronously: video encoding runs first, then
    auto-captioning. While a recording is still being processed the
    ``/presentation/{uuid}`` endpoint may return a response shape that doesn't
    match the normal "ready" envelope (for example, a list instead of the
    expected object). Callers should treat this as transient and retry later.

    Subclassed by :class:`TranscriptNotReadyError` for the more specific case
    where the video itself is ready but subtitles haven't been generated yet.
    Code that wants to handle either case the same way should catch this class.
    """

    pass


class TranscriptNotReadyError(PresentationNotReadyError):
    """Raised when a Play presentation's transcript is not yet available.

    DSVPlay generates transcripts asynchronously after a recording is uploaded.
    A presentation may have its video sources ready while its subtitles are
    still being processed. Callers should treat this as transient and retry
    later. Subclass of :class:`PresentationNotReadyError` (and transitively
    :class:`ParseError`) so existing ``except ParseError`` blocks keep working.
    """

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


class AmbiguousMatchError(DSVWrapperError):
    """Raised when a lookup expected a unique result but got 0 or >1 matches.

    Used by :meth:`dsv_wrapper.models.daisy.CourseStaff.get_person_id` when
    resolving a plain-text participant name through the student search:
    Daisy must return exactly one person for the resolution to be safe.
    """

    pass
