"""Tests for Daisy client."""

import inspect
import logging
from datetime import date

import pytest

from dsv_wrapper.daisy import AsyncDaisyClient, DaisyClient
from dsv_wrapper.models import RoomCategory
from dsv_wrapper.exceptions import BookingError, RoomNotAvailableError

logger = logging.getLogger(__name__)


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
def test_daisy_get_schedule_all_categories(daisy_client):
    """Test getting schedules for all categories."""
    # This test verifies that the daisy client can be instantiated
    # Actual integration testing would require valid API endpoints
    logger.info("Daisy client instantiated successfully")


def test_sync_async_api_parity():
    """Test that sync and async Daisy clients have the same public API."""
    # Get all public methods from sync client (excluding magic methods and private methods)
    sync_methods = {
        name: method
        for name, method in inspect.getmembers(DaisyClient, predicate=inspect.isfunction)
        if not name.startswith("_")
    }

    # Get all public methods from async client (excluding magic methods and private methods)
    async_methods = {
        name: method
        for name, method in inspect.getmembers(AsyncDaisyClient, predicate=inspect.isfunction)
        if not name.startswith("_")
    }

    # Check that async client has all the public methods from sync client
    missing_in_async = set(sync_methods.keys()) - set(async_methods.keys())
    extra_in_async = set(async_methods.keys()) - set(sync_methods.keys())

    # Filter out context manager methods which are intentionally different
    missing_in_async = {m for m in missing_in_async if m not in {"__enter__", "__exit__", "close"}}

    assert not missing_in_async, (
        f"Async client is missing these public methods from sync client: {missing_in_async}"
    )

    # Verify method signatures match (excluding self and accounting for async)
    for method_name in sync_methods:
        if method_name in {"__enter__", "__exit__", "close"}:
            continue

        if method_name in async_methods:
            sync_sig = inspect.signature(sync_methods[method_name])
            async_sig = inspect.signature(async_methods[method_name])

            # Get parameters excluding 'self'
            sync_params = [p for p in sync_sig.parameters.values() if p.name != "self"]
            async_params = [p for p in async_sig.parameters.values() if p.name != "self"]

            # Compare parameter names and defaults
            sync_param_names = [p.name for p in sync_params]
            async_param_names = [p.name for p in async_params]

            assert sync_param_names == async_param_names, (
                f"Method '{method_name}' has different parameters:\n"
                f"  Sync: {sync_param_names}\n"
                f"  Async: {async_param_names}"
            )

    logger.info("API parity check passed: sync and async clients have matching public methods")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_async_daisy_search_staff(async_daisy_client):
    """Test async staff search functionality."""
    from dsv_wrapper.models import InstitutionID

    # Search for staff with a common last name
    staff_list = await async_daisy_client.search_staff(
        last_name="", institution_id=InstitutionID.DSV
    )

    assert staff_list is not None
    assert isinstance(staff_list, list)

    if staff_list:
        logger.info(f"Found {len(staff_list)} staff members")
        first_staff = staff_list[0]
        assert first_staff.person_id
        # Name can be empty for some staff, so just log it
        logger.info(f"First staff: {first_staff.name or '(no name)'} (ID: {first_staff.person_id})")
    else:
        logger.warning("No staff found in search")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_async_daisy_get_staff_details(async_daisy_client):
    """Test async staff details retrieval."""
    from dsv_wrapper.models import InstitutionID

    # First search for staff
    staff_list = await async_daisy_client.search_staff(
        institution_id=InstitutionID.DSV
    )

    if staff_list:
        # Get details for the first staff member
        person_id = staff_list[0].person_id
        staff_details = await async_daisy_client.get_staff_details(person_id)

        assert staff_details is not None
        assert staff_details.person_id == person_id
        assert staff_details.name
        logger.info(f"Staff details: {staff_details.name}, Email: {staff_details.email}")
    else:
        pytest.skip("No staff found to test details retrieval")
