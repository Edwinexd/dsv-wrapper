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
    assert RoomCategory.GROUPA.value == "GROUPA"
    assert RoomCategory.GROUPB.value == "GROUPB"
    assert RoomCategory.GROUPC.value == "GROUPC"


def test_room_time_model():
    """Test RoomTime model."""
    room_time = RoomTime(start=time(9, 0), end=time(10, 0), available=True)

    assert room_time.start == time(9, 0)
    assert room_time.end == time(10, 0)
    assert room_time.available is True
    assert room_time.booking_url is None

    # Test frozen (immutability)
    with pytest.raises(ValidationError):
        room_time.start = time(11, 0)


def test_room_model():
    """Test Room model."""
    times = [
        RoomTime(start=time(9, 0), end=time(10, 0), available=True),
        RoomTime(start=time(10, 0), end=time(11, 0), available=False),
    ]

    room = Room(
        id="123",
        name="Room A",
        category=RoomCategory.GROUPA,
        available_times=times,
        capacity=20,
    )

    assert room.id == "123"
    assert room.name == "Room A"
    assert room.category == RoomCategory.GROUPA
    assert len(room.available_times) == 2
    assert room.capacity == 20


def test_booking_slot_model():
    """Test BookingSlot model."""
    slot = BookingSlot(
        room_id="123",
        room_name="Room A",
        date=date(2024, 1, 15),
        start_time=time(9, 0),
        end_time=time(10, 0),
        available=True,
    )

    assert slot.room_id == "123"
    assert slot.duration_hours == 1.0

    # Test 30-minute duration
    slot2 = BookingSlot(
        room_id="456",
        room_name="Room B",
        date=date(2024, 1, 15),
        start_time=time(9, 0),
        end_time=time(9, 30),
    )

    assert slot2.duration_hours == 0.5


def test_schedule_model():
    """Test Schedule model."""
    rooms = [
        Room(id="1", name="Room 1", category=RoomCategory.GROUPA),
        Room(id="2", name="Room 2", category=RoomCategory.GROUPA),
    ]

    schedule = Schedule(
        category=RoomCategory.GROUPA,
        date=date.today(),
        rooms=rooms,
    )

    assert schedule.category == RoomCategory.GROUPA
    assert len(schedule.rooms) == 2
    assert len(schedule.slots) == 0


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
        room_name="Room 4542",
        course_code="DA2005",
        course_name="Introduction to Programming",
        activity_type=ActivityType.LECTURE,
        start_time=time(10, 0),
        end_time=time(12, 0),
        date=date.today(),
        teacher="Prof. Smith",
        students_count=25,
    )

    assert activity.room_name == "Room 4542"
    assert activity.course_code == "DA2005"
    assert activity.activity_type == ActivityType.LECTURE
    assert activity.students_count == 25
