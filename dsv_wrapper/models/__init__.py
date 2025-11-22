"""Pydantic models for DSV systems.

This module exports all models from the system-specific submodules.
You can import from specific modules:
    from dsv_wrapper.models.daisy import RoomCategory, Room
    from dsv_wrapper.models.handledning import QueueStatus, QueueEntry
    from dsv_wrapper.models.actlab import Slide, Show
    from dsv_wrapper.models.common import Student, Teacher

Or from the main models module (backward compatible):
    from dsv_wrapper.models import RoomCategory, Room, Student, Teacher, Slide
"""

# Common models
from .common import Course, Student, Teacher

# Daisy models
from .daisy import (
    ActivityType,
    BookingSlot,
    InstitutionID,
    Room,
    RoomActivity,
    RoomCategory,
    RoomTime,
    Schedule,
    Staff,
)

# Handledning models
from .handledning import HandledningSession, QueueEntry, QueueStatus

# ACT Lab models
from .actlab import Show, Slide, SlideUploadResult

__all__ = [
    # Common models
    "Student",
    "Teacher",
    "Course",
    # Daisy models
    "InstitutionID",
    "RoomCategory",
    "RoomTime",
    "Room",
    "BookingSlot",
    "Schedule",
    "ActivityType",
    "RoomActivity",
    "Staff",
    # Handledning models
    "QueueStatus",
    "QueueEntry",
    "HandledningSession",
    # ACT Lab models
    "Slide",
    "Show",
    "SlideUploadResult",
]
