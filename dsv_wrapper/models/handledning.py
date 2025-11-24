"""Pydantic models for Handledning system."""

from datetime import date, datetime, time
from enum import Enum

from pydantic import BaseModel, Field

from .common import Student, Teacher


class QueueStatus(str, Enum):
    """Status of a student in the Handledning queue."""

    WAITING = "waiting"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class QueueEntry(BaseModel):
    """Entry in the Handledning queue."""

    student: Student
    position: int
    status: QueueStatus = QueueStatus.WAITING
    timestamp: datetime
    room: str | None = None
    note: str | None = None

    model_config = {"frozen": True}


class HandledningSession(BaseModel):
    """Handledning (lab supervision) session."""

    course_code: str
    course_name: str
    teacher: Teacher
    date: date
    start_time: time
    end_time: time
    room: str | None = None
    queue: list[QueueEntry] = Field(default_factory=list)
    max_students: int | None = None
    is_active: bool = False

    model_config = {"frozen": True}

    @property
    def queue_length(self) -> int:
        """Get current queue length."""
        return len([entry for entry in self.queue if entry.status == QueueStatus.WAITING])
