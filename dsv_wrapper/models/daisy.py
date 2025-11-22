"""Pydantic models for Daisy system."""

from datetime import date, datetime, time
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class RoomCategory(str, Enum):
    """Room categories in Daisy."""

    GROUPA = "GROUPA"
    GROUPB = "GROUPB"
    GROUPC = "GROUPC"
    PERS = "PERS"
    PHDSEM = "PHDSEM"
    PROJEKT = "PROJEKT"


class InstitutionID(str, Enum):
    """Institution IDs in Daisy.

    Note: Daisy is DSV-only. The institution_id parameter exists in forms
    but DSV is the only supported value.
    """
    DSV = "4"


class RoomTime(BaseModel):
    """Time slot for room availability."""

    start: time
    end: time
    available: bool = True
    booking_url: Optional[str] = None

    model_config = {"frozen": True}


class Room(BaseModel):
    """Room model."""

    id: str
    name: str
    category: RoomCategory
    available_times: list[RoomTime] = Field(default_factory=list)
    capacity: Optional[int] = None
    description: Optional[str] = None

    model_config = {"frozen": True}


class BookingSlot(BaseModel):
    """Booking time slot."""

    room_id: str
    room_name: str
    date: date
    start_time: time
    end_time: time
    available: bool = True
    booking_url: Optional[str] = None

    model_config = {"frozen": True}

    @property
    def duration_hours(self) -> float:
        """Calculate duration in hours."""
        start_dt = datetime.combine(self.date, self.start_time)
        end_dt = datetime.combine(self.date, self.end_time)
        return (end_dt - start_dt).total_seconds() / 3600


class Schedule(BaseModel):
    """Schedule for a room category on a specific date."""

    category: RoomCategory
    date: date
    rooms: list[Room] = Field(default_factory=list)
    slots: list[BookingSlot] = Field(default_factory=list)

    model_config = {"frozen": True}


class ActivityType(str, Enum):
    """Activity types in room schedules."""

    LECTURE = "Föreläsning"
    SEMINAR = "Seminarium"
    EXERCISE = "Övning"
    EXAMINATION = "Tentamen"
    PROJECT = "Projektarbete"
    OTHER = "Övrigt"


class RoomActivity(BaseModel):
    """Activity scheduled in a room."""

    room_name: str
    course_code: Optional[str] = None
    course_name: Optional[str] = None
    activity_type: Optional[ActivityType] = None
    start_time: time
    end_time: time
    date: date
    teacher: Optional[str] = None
    students_count: Optional[int] = None

    model_config = {"frozen": True}


class Staff(BaseModel):
    """Staff/employee model for Daisy."""

    person_id: str
    name: str
    email: Optional[str] = None
    room: Optional[str] = None
    location: Optional[str] = None
    profile_url: Optional[str] = None
    profile_pic_url: Optional[str] = None
    units: list[str] = Field(default_factory=list)
    swedish_title: Optional[str] = None
    english_title: Optional[str] = None
    phone: Optional[str] = None

    model_config = {"frozen": True}
