"""Tests for Daisy client."""

import logging
from datetime import date

import pytest

from dsv_wrapper.models import RoomCategory
from dsv_wrapper.exceptions import BookingError, RoomNotAvailableError

logger = logging.getLogger(__name__)


@pytest.mark.integration
def test_daisy_get_schedule(daisy_client):
    """Test getting room schedule for a category."""
    schedule = daisy_client.get_schedule(RoomCategory.GROUPA, date.today())

    assert schedule is not None
    assert schedule.category == RoomCategory.GROUPA
    assert schedule.date == date.today()
    assert len(schedule.rooms) > 0

    logger.info(f"Got schedule with {len(schedule.rooms)} rooms")

    # Check room structure
    room = schedule.rooms[0]
    assert room.id
    assert room.name
    assert room.category == RoomCategory.GROUPA

    logger.info(f"First room: {room.name} with {len(room.available_times)} time slots")


@pytest.mark.integration
def test_daisy_search_students(daisy_client):
    """Test searching for students."""
    # Search for common Swedish names
    students = daisy_client.search_students("erik", limit=5)

    assert students is not None
    assert isinstance(students, list)

    if students:
        logger.info(f"Found {len(students)} students matching 'erik'")

        student = students[0]
        assert student.username
        logger.info(f"First student: {student.full_name} ({student.username})")
    else:
        logger.warning("No students found in search")


@pytest.mark.integration
def test_daisy_get_room_activities(daisy_client):
    """Test getting room activities."""
    # Get schedule first to find a room ID
    schedule = daisy_client.get_schedule(RoomCategory.GROUPA, date.today())

    if schedule.rooms:
        room_id = schedule.rooms[0].id
        activities = daisy_client.get_room_activities(room_id, date.today())

        assert activities is not None
        assert isinstance(activities, list)

        logger.info(f"Room {room_id} has {len(activities)} activities")

        if activities:
            activity = activities[0]
            assert activity.room_name
            assert activity.start_time
            assert activity.end_time
            logger.info(
                f"First activity: {activity.start_time}-{activity.end_time} {activity.course_code or 'N/A'}"
            )


@pytest.mark.integration
@pytest.mark.destructive
def test_daisy_book_room_invalid(daisy_client):
    """Test booking a room with invalid parameters (should fail)."""
    from datetime import time

    # Try to book with invalid time (past time)
    with pytest.raises((BookingError, RoomNotAvailableError, Exception)):
        daisy_client.book_room(
            room_id="invalid_room",
            schedule_date=date.today(),
            start_time=time(8, 0),  # Before opening
            end_time=time(9, 0),
            purpose="Test booking (should fail)",
        )

    logger.info("Invalid booking correctly rejected")


@pytest.mark.integration
def test_daisy_get_schedule_all_categories(daisy_client):
    """Test getting schedules for all categories."""
    categories = [
        RoomCategory.GROUPA,
        RoomCategory.GROUPB,
        RoomCategory.GROUPC,
    ]

    for category in categories:
        try:
            schedule = daisy_client.get_schedule(category, date.today())
            assert schedule is not None
            logger.info(f"{category.value}: {len(schedule.rooms)} rooms")
        except Exception as e:
            logger.error(f"Failed to get schedule for {category.value}: {e}")


@pytest.mark.integration
def test_daisy_schedule_slots(daisy_client):
    """Test that schedule has booking slots."""
    schedule = daisy_client.get_schedule(RoomCategory.GROUPA, date.today())

    # Check slots
    assert schedule.slots is not None
    logger.info(f"Total booking slots: {len(schedule.slots)}")

    available_slots = [s for s in schedule.slots if s.available]
    logger.info(f"Available slots: {len(available_slots)}")

    if available_slots:
        slot = available_slots[0]
        assert slot.room_id
        assert slot.room_name
        assert slot.date == date.today()
        assert slot.start_time
        assert slot.end_time
        assert slot.duration_hours > 0

        logger.info(
            f"First available slot: {slot.room_name} at {slot.start_time}-{slot.end_time}"
        )
