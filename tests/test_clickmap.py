"""Tests for Clickmap client."""

import inspect
import logging

import pytest

from dsv_wrapper.clickmap import AsyncClickmapClient, ClickmapClient
from dsv_wrapper.models import Placement

logger = logging.getLogger(__name__)


@pytest.mark.integration
def test_clickmap_get_placements(clickmap_client):
    """Test getting all placements from clickmap."""
    placements = clickmap_client.get_placements()

    assert isinstance(placements, list)
    assert len(placements) > 0, "Should have at least some placements"

    # Check first placement structure
    first = placements[0]
    assert isinstance(first, Placement)
    assert first.id is not None
    assert first.place_name is not None
    assert isinstance(first.latitude, float)
    assert isinstance(first.longitude, float)

    logger.info(f"Retrieved {len(placements)} placements")


@pytest.mark.integration
def test_clickmap_search_placements(clickmap_client):
    """Test searching placements by name."""
    # First get all placements to find a valid search term
    all_placements = clickmap_client.get_placements()

    # Find one with a person name
    occupied = [p for p in all_placements if p.person_name]
    if not occupied:
        pytest.skip("No occupied placements to search for")

    # Search for first occupied placement's person
    search_term = occupied[0].person_name.split()[0]  # First name
    results = clickmap_client.search_placements(search_term)

    assert len(results) > 0, f"Should find at least one result for '{search_term}'"
    assert any(search_term.lower() in p.person_name.lower() for p in results)

    logger.info(f"Found {len(results)} placements matching '{search_term}'")


@pytest.mark.integration
def test_clickmap_get_occupied_placements(clickmap_client):
    """Test getting only occupied placements."""
    occupied = clickmap_client.get_occupied_placements()

    assert isinstance(occupied, list)
    assert all(p.is_occupied for p in occupied), "All placements should be occupied"
    assert all(p.person_name for p in occupied), "All placements should have person_name"

    logger.info(f"Found {len(occupied)} occupied placements")


@pytest.mark.integration
def test_clickmap_placement_model(clickmap_client):
    """Test Placement model properties."""
    placements = clickmap_client.get_placements()

    for p in placements[:5]:  # Check first 5
        # Verify model is frozen (immutable)
        assert p.model_config.get("frozen", False) is True

        # Test is_occupied property
        if p.person_name:
            assert p.is_occupied is True
        else:
            assert p.is_occupied is False

    logger.info("Placement model validation passed")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_async_clickmap_get_placements(async_clickmap_client):
    """Test getting placements with async client."""
    placements = await async_clickmap_client.get_placements()

    assert isinstance(placements, list)
    assert len(placements) > 0, "Should have at least some placements"

    logger.info(f"Async client retrieved {len(placements)} placements")


def test_sync_async_clickmap_api_parity():
    """Test that sync and async Clickmap clients have the same public API."""
    # Get all public methods from sync client (excluding magic methods and private methods)
    sync_methods = {
        name: method
        for name, method in inspect.getmembers(ClickmapClient, predicate=inspect.isfunction)
        if not name.startswith("_")
    }

    # Get all public methods from async client (excluding magic methods and private methods)
    async_methods = {
        name: method
        for name, method in inspect.getmembers(AsyncClickmapClient, predicate=inspect.isfunction)
        if not name.startswith("_")
    }

    # Check that async client has all the public methods from sync client
    missing_in_async = set(sync_methods.keys()) - set(async_methods.keys())

    # Filter out context manager methods which are intentionally different
    missing_in_async = {m for m in missing_in_async if m not in {"__enter__", "__exit__", "close"}}

    assert not missing_in_async, (
        f"Async Clickmap client is missing these public methods "
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
        "API parity check passed: sync and async Clickmap clients have matching public methods"
    )


def test_placement_model():
    """Test Placement model creation and properties."""
    placement = Placement(
        id="test-uuid-123",
        place_name="66109",
        person_name="Test Person",
        person_role="Developer",
        latitude=1.5,
        longitude=2.5,
        comment="Test comment",
    )

    assert placement.id == "test-uuid-123"
    assert placement.place_name == "66109"
    assert placement.person_name == "Test Person"
    assert placement.person_role == "Developer"
    assert placement.latitude == 1.5
    assert placement.longitude == 2.5
    assert placement.comment == "Test comment"
    assert placement.is_occupied is True

    # Test vacant placement
    vacant = Placement(
        id="test-uuid-456",
        place_name="66110",
        person_name="",
        latitude=1.0,
        longitude=2.0,
    )

    assert vacant.is_occupied is False

    logger.info("Placement model tests passed")
