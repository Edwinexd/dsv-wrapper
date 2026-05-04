"""DSV Wrapper - Reusable Python package for accessing DSV systems."""

__version__ = "0.1.0"

# Main clients
from .actlab import ACTLabClient, AsyncACTLabClient

# Authentication
from .auth import AsyncShibbolethAuth, ServiceType, ShibbolethAuth
from .auth.cache_backend import CacheBackend, FileCache, MemoryCache, NullCache
from .clickmap import AsyncClickmapClient, ClickmapClient
from .client import AsyncDSVClient, DSVClient
from .daisy import AsyncDaisyClient, DaisyClient

# Exceptions
from .exceptions import (
    ACTLabError,
    AuthenticationError,
    BookingError,
    DSVWrapperError,
    HandledningError,
    InvalidTimeSlotError,
    NetworkError,
    ParseError,
    PresentationNotReadyError,
    QueueError,
    RoomNotAvailableError,
    SessionExpiredError,
    TranscriptNotReadyError,
    ValidationError,
)
from .handledning import AsyncHandledningClient, HandledningClient
from .mail import AsyncMailClient, MailClient

# Models
from .models import (
    ActivityType,
    BodyType,
    BookingSlot,
    Course,
    EmailAddress,
    EmailMessage,
    HandledningSession,
    Importance,
    InstitutionID,
    MailFolder,
    Placement,
    PlayCourse,
    Presentation,
    Presenter,
    QueueEntry,
    QueueStatus,
    Room,
    RoomActivity,
    RoomCategory,
    RoomTime,
    Schedule,
    SendEmailResult,
    Show,
    Slide,
    SlideUploadResult,
    Staff,
    Student,
    Teacher,
    TranscriptCue,
    VideoSource,
)
from .play import AsyncPlayClient, PlayClient

# Utilities
from .utils import (
    DEFAULT_HEADERS,
    DSV_SSO_TARGETS,
    DSV_URLS,
    build_url,
    extract_attr,
    extract_text,
    format_date_swedish,
    get_weekday_swedish,
    parse_date,
    parse_html,
    parse_swedish_date,
    parse_time,
    validate_time_slot,
)

__all__ = [
    # Version
    "__version__",
    # Main clients
    "DSVClient",
    "AsyncDSVClient",
    "DaisyClient",
    "AsyncDaisyClient",
    "HandledningClient",
    "AsyncHandledningClient",
    "ACTLabClient",
    "AsyncACTLabClient",
    "ClickmapClient",
    "AsyncClickmapClient",
    "PlayClient",
    "AsyncPlayClient",
    "MailClient",
    "AsyncMailClient",
    # Authentication
    "ShibbolethAuth",
    "AsyncShibbolethAuth",
    "ServiceType",
    "CacheBackend",
    "FileCache",
    "MemoryCache",
    "NullCache",
    # Models
    "InstitutionID",
    "Room",
    "RoomCategory",
    "RoomTime",
    "BookingSlot",
    "Schedule",
    "ActivityType",
    "RoomActivity",
    "Staff",
    "Student",
    "Teacher",
    "Course",
    "QueueStatus",
    "QueueEntry",
    "HandledningSession",
    "Slide",
    "Show",
    "SlideUploadResult",
    "Placement",
    "PlayCourse",
    "Presenter",
    "VideoSource",
    "Presentation",
    "TranscriptCue",
    "BodyType",
    "EmailAddress",
    "EmailMessage",
    "Importance",
    "MailFolder",
    "SendEmailResult",
    # Exceptions
    "ACTLabError",
    "DSVWrapperError",
    "AuthenticationError",
    "SessionExpiredError",
    "BookingError",
    "RoomNotAvailableError",
    "InvalidTimeSlotError",
    "ParseError",
    "PresentationNotReadyError",
    "TranscriptNotReadyError",
    "NetworkError",
    "HandledningError",
    "QueueError",
    "ValidationError",
    # Utilities
    "parse_html",
    "parse_time",
    "parse_date",
    "parse_swedish_date",
    "format_date_swedish",
    "get_weekday_swedish",
    "extract_text",
    "extract_attr",
    "build_url",
    "validate_time_slot",
    "DEFAULT_HEADERS",
    "DSV_SSO_TARGETS",
    "DSV_URLS",
]
