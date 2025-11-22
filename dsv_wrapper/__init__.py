"""DSV Wrapper - Reusable Python package for accessing DSV systems."""

__version__ = "0.1.0"

# Main clients
from .client import AsyncDSVClient, DSVClient
from .actlab import ACTLabClient, AsyncACTLabClient
from .daisy import AsyncDaisyClient, DaisyClient
from .handledning import AsyncHandledningClient, HandledningClient

# Authentication
from .auth import AsyncShibbolethAuth, ServiceType, ShibbolethAuth
from .auth.cache_backend import CacheBackend, FileCache, MemoryCache, NullCache

# Models
from .models import (
    ActivityType,
    BookingSlot,
    Course,
    HandledningSession,
    InstitutionID,
    QueueEntry,
    QueueStatus,
    Room,
    RoomActivity,
    RoomCategory,
    RoomTime,
    Schedule,
    Show,
    Slide,
    SlideUploadResult,
    Staff,
    Student,
    Teacher,
)

# Exceptions
from .exceptions import (
    AuthenticationError,
    BookingError,
    DSVWrapperError,
    HandledningError,
    InvalidTimeSlotError,
    NetworkError,
    ParseError,
    QueueError,
    RoomNotAvailableError,
    SessionExpiredError,
    ValidationError,
)

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
    # Exceptions
    "DSVWrapperError",
    "AuthenticationError",
    "SessionExpiredError",
    "BookingError",
    "RoomNotAvailableError",
    "InvalidTimeSlotError",
    "ParseError",
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
