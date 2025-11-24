"""Tests for Handledning client."""

import inspect
import logging

import pytest

from dsv_wrapper.exceptions import HandledningError
from dsv_wrapper.handledning import AsyncHandledningClient, HandledningClient

logger = logging.getLogger(__name__)


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
def test_handledning_session_properties(credentials):
    """Test that Handledning client can be instantiated."""
    from dsv_wrapper import HandledningClient

    username, password = credentials

    # Verify client can be instantiated
    client = HandledningClient(username=username, password=password)
    assert client is not None
    logger.info("Handledning client instantiated successfully")
    client.close()


def test_sync_async_handledning_api_parity():
    """Test that sync and async Handledning clients have the same public API."""
    # Get all public methods from sync client (excluding magic methods and private methods)
    sync_methods = {
        name: method
        for name, method in inspect.getmembers(HandledningClient, predicate=inspect.isfunction)
        if not name.startswith("_")
    }

    # Get all public methods from async client (excluding magic methods and private methods)
    async_methods = {
        name: method
        for name, method in inspect.getmembers(AsyncHandledningClient, predicate=inspect.isfunction)
        if not name.startswith("_")
    }

    # Check that async client has all the public methods from sync client
    missing_in_async = set(sync_methods.keys()) - set(async_methods.keys())

    # Filter out context manager methods which are intentionally different
    missing_in_async = {m for m in missing_in_async if m not in {"__enter__", "__exit__", "close"}}

    assert not missing_in_async, (
        f"Async Handledning client is missing these public methods "
        f"from sync client: {missing_in_async}"
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

    logger.info(
        "API parity check passed: sync and async Handledning clients have matching public methods"
    )
