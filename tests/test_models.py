"""Tests for Pydantic models."""

import logging
from datetime import date, datetime, time

import pytest
from pydantic import ValidationError

from dsv_wrapper.models import (
    ActivityType,
    BookingSlot,
    Course,
    HandledningSession,
    QueueEntry,
    QueueStatus,
    Room,
    RoomActivity,
    RoomCategory,
    RoomTime,
    Schedule,
    Student,
    Teacher,
)

logger = logging.getLogger(__name__)


def test_room_category_enum():
    """Test RoomCategory enum values."""
    assert RoomCategory.BOOKABLE_GROUP_ROOMS.value == 68
    assert RoomCategory.COMPUTER_LABS.value == 66
    assert RoomCategory.TEACHING_ROOMS.value == 64


def test_room_time_model():
    """Test RoomTime enum."""
    room_time = RoomTime.NINE

    assert room_time.value == 9
    assert room_time.to_string() == "09:00"

    # Test comparison
    assert RoomTime.NINE < RoomTime.TEN
    assert RoomTime.TEN > RoomTime.NINE


def test_room_model():
    """Test Room enum."""
    room = Room.G10_1

    assert room.value == 633

    # Test from_name
    room2 = Room.from_name("G10:1")
    assert room2 == Room.G10_1


def test_booking_slot_model():
    """Test BookingSlot model."""
    slot = BookingSlot(
        room=Room.G10_1,
        from_time=RoomTime.NINE,
        to_time=RoomTime.TEN,
    )

    assert slot.room == Room.G10_1
    assert slot.from_time == RoomTime.NINE
    assert slot.to_time == RoomTime.TEN


def test_schedule_model():
    """Test Schedule model."""
    activities = {
        "G10:1": [
            RoomActivity(
                time_slot_start=RoomTime.NINE,
                time_slot_end=RoomTime.TEN,
                event="DA2005 - Introduction to Programming",
            )
        ]
    }

    schedule = Schedule(
        activities=activities,
        room_category_title="Bookable Group Rooms",
        room_category_id=68,
        room_category=RoomCategory.BOOKABLE_GROUP_ROOMS,
        datetime=datetime.now(),
    )

    assert schedule.room_category == RoomCategory.BOOKABLE_GROUP_ROOMS
    assert len(schedule.activities) == 1


def test_student_model():
    """Test Student model."""
    student = Student(
        username="johndoe",
        first_name="John",
        last_name="Doe",
        email="john.doe@student.su.se",
        program="Computer Science",
    )

    assert student.username == "johndoe"
    assert student.full_name == "John Doe"
    assert student.email == "john.doe@student.su.se"

    # Test without names
    student2 = Student(username="janedoe")
    assert student2.full_name == "janedoe"


def test_teacher_model():
    """Test Teacher model."""
    teacher = Teacher(
        username="profsmith",
        first_name="Jane",
        last_name="Smith",
        email="jane.smith@dsv.su.se",
        title="Professor",
        room="4542",
    )

    assert teacher.username == "profsmith"
    assert teacher.full_name == "Jane Smith"
    assert teacher.title == "Professor"
    assert teacher.room == "4542"


def test_course_model():
    """Test Course model."""
    teachers = [
        Teacher(username="prof1", first_name="John", last_name="Doe"),
        Teacher(username="prof2", first_name="Jane", last_name="Smith"),
    ]

    course = Course(
        code="DA2005",
        name="Introduction to Programming",
        credits=7.5,
        level="Undergraduate",
        teachers=teachers,
    )

    assert course.code == "DA2005"
    assert course.name == "Introduction to Programming"
    assert course.credits == 7.5
    assert len(course.teachers) == 2


def test_queue_status_enum():
    """Test QueueStatus enum."""
    assert QueueStatus.WAITING.value == "waiting"
    assert QueueStatus.IN_PROGRESS.value == "in_progress"
    assert QueueStatus.COMPLETED.value == "completed"


def test_queue_entry_model():
    """Test QueueEntry model."""
    student = Student(username="johndoe")

    entry = QueueEntry(
        student=student,
        position=1,
        status=QueueStatus.WAITING,
        timestamp=datetime.now(),
    )

    assert entry.student.username == "johndoe"
    assert entry.position == 1
    assert entry.status == QueueStatus.WAITING
    assert entry.room is None


def test_handledning_session_model():
    """Test HandledningSession model."""
    teacher = Teacher(username="profsmith")
    students = [
        QueueEntry(
            student=Student(username="student1"),
            position=1,
            status=QueueStatus.WAITING,
            timestamp=datetime.now(),
        ),
        QueueEntry(
            student=Student(username="student2"),
            position=2,
            status=QueueStatus.IN_PROGRESS,
            timestamp=datetime.now(),
        ),
    ]

    session = HandledningSession(
        course_code="DA2005",
        course_name="Introduction to Programming",
        teacher=teacher,
        date=date.today(),
        start_time=time(10, 0),
        end_time=time(12, 0),
        queue=students,
        is_active=True,
    )

    assert session.course_code == "DA2005"
    assert session.queue_length == 1  # Only waiting students
    assert len(session.queue) == 2
    assert session.is_active is True


def test_room_activity_model():
    """Test RoomActivity model."""
    activity = RoomActivity(
        time_slot_start=RoomTime.TEN,
        time_slot_end=RoomTime.TWELVE,
        event="DA2005 - Introduction to Programming",
    )

    assert activity.time_slot_start == RoomTime.TEN
    assert activity.time_slot_end == RoomTime.TWELVE
    assert activity.event == "DA2005 - Introduction to Programming"
