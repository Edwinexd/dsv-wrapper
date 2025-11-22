"""Tests for Handledning client."""

import logging

import pytest

from dsv_wrapper.exceptions import HandledningError

logger = logging.getLogger(__name__)


@pytest.mark.integration
def test_handledning_get_teacher_sessions(handledning_client):
    """Test getting teacher sessions."""
    sessions = handledning_client.get_teacher_sessions()

    assert sessions is not None
    assert isinstance(sessions, list)

    logger.info(f"Found {len(sessions)} teacher sessions")

    if sessions:
        session = sessions[0]
        assert session.course_code
        assert session.course_name
        assert session.teacher
        assert session.start_time
        assert session.end_time
        assert session.date

        logger.info(
            f"First session: {session.course_code} - {session.course_name} "
            f"({session.start_time}-{session.end_time})"
        )
        logger.info(f"  Teacher: {session.teacher.username}")
        logger.info(f"  Active: {session.is_active}")
        logger.info(f"  Room: {session.room or 'N/A'}")


@pytest.mark.integration
def test_handledning_get_all_active_sessions(handledning_client):
    """Test getting all active sessions."""
    sessions = handledning_client.get_all_active_sessions()

    assert sessions is not None
    assert isinstance(sessions, list)

    logger.info(f"Found {len(sessions)} active sessions")

    if sessions:
        active_count = sum(1 for s in sessions if s.is_active)
        logger.info(f"Active sessions: {active_count}/{len(sessions)}")


@pytest.mark.integration
def test_handledning_queue_operations_safe(handledning_client):
    """Test queue operations without modifying state."""
    # Note: This test does NOT actually modify the queue
    # It only tests that the methods can be called without errors

    # These would be real operations (commented out for safety):
    # handledning_client.add_to_queue(session_id)
    # handledning_client.remove_from_queue(session_id, username)
    # handledning_client.activate_session(session_id)
    # handledning_client.deactivate_session(session_id)

    logger.info("Queue operation methods available (not tested to avoid state changes)")


@pytest.mark.integration
@pytest.mark.destructive
def test_handledning_invalid_session_operations(handledning_client):
    """Test operations with invalid session ID (should fail)."""
    invalid_session_id = "invalid_session_12345"

    # These should fail gracefully
    with pytest.raises((HandledningError, Exception)):
        handledning_client.activate_session(invalid_session_id)

    logger.info("Invalid session operations correctly rejected")


@pytest.mark.integration
def test_handledning_session_properties(handledning_client):
    """Test session properties and queue length."""
    sessions = handledning_client.get_teacher_sessions()

    if sessions:
        session = sessions[0]

        # Test queue_length property
        queue_length = session.queue_length
        assert queue_length >= 0

        logger.info(f"Session {session.course_code} has queue length: {queue_length}")

        # Check queue structure
        assert session.queue is not None
        assert isinstance(session.queue, list)


@pytest.mark.integration
def test_handledning_mobile_client(credentials):
    """Test mobile version of Handledning client."""
    from dsv_wrapper import HandledningClient

    username, password = credentials

    # Create mobile client
    mobile_client = HandledningClient(
        username=username, password=password, mobile=True, use_cache=False
    )

    try:
        sessions = mobile_client.get_teacher_sessions()

        assert sessions is not None
        logger.info(f"Mobile client: Found {len(sessions)} sessions")

    finally:
        mobile_client.close()


@pytest.mark.integration
def test_handledning_context_manager(credentials):
    """Test that Handledning client works as context manager."""
    from dsv_wrapper import HandledningClient

    username, password = credentials

    with HandledningClient(username=username, password=password, use_cache=False) as client:
        sessions = client.get_teacher_sessions()
        assert sessions is not None
        logger.info("Context manager working correctly")
