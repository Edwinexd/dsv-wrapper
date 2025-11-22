"""Pytest configuration and fixtures for integration tests."""

import logging
import os

import pytest
from dotenv import load_dotenv

# Configure logging for tests
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Load environment variables
load_dotenv()


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers",
        "integration: mark test as integration test (requires live credentials)",
    )
    config.addinivalue_line(
        "markers", "destructive: mark test as potentially destructive (modifies data)"
    )


@pytest.fixture(scope="session")
def credentials():
    """Get credentials from environment variables.

    Returns:
        tuple: (username, password)

    Raises:
        pytest.skip: If credentials are not available
    """
    username = os.getenv("SU_USERNAME")
    password = os.getenv("SU_PASSWORD")

    if not username or not password:
        pytest.skip("SU_USERNAME and SU_PASSWORD environment variables not set")

    return username, password


@pytest.fixture
def daisy_client(credentials):
    """Create a Daisy client for testing.

    Args:
        credentials: Credentials fixture

    Returns:
        DaisyClient: Initialized client
    """
    from dsv_wrapper import DaisyClient

    username, password = credentials

    client = DaisyClient(
        username=username, password=password, service="daisy_staff", use_cache=False
    )

    yield client

    # Cleanup
    client.close()


@pytest.fixture
def handledning_client(credentials):
    """Create a Handledning client for testing.

    Args:
        credentials: Credentials fixture

    Returns:
        HandledningClient: Initialized client
    """
    from dsv_wrapper import HandledningClient

    username, password = credentials

    client = HandledningClient(username=username, password=password, use_cache=False)

    yield client

    # Cleanup
    client.close()


@pytest.fixture
def dsv_client(credentials):
    """Create a unified DSV client for testing.

    Args:
        credentials: Credentials fixture

    Returns:
        DSVClient: Initialized client
    """
    from dsv_wrapper import DSVClient

    username, password = credentials

    client = DSVClient(username=username, password=password, use_cache=False)

    yield client

    # Cleanup
    client.close()


@pytest.fixture
async def async_daisy_client(credentials):
    """Create an async Daisy client for testing.

    Args:
        credentials: Credentials fixture

    Returns:
        AsyncDaisyClient: Initialized client
    """
    from dsv_wrapper import AsyncDaisyClient

    username, password = credentials

    client = AsyncDaisyClient(
        username=username, password=password, service="daisy_staff", use_cache=False
    )

    async with client:
        yield client


@pytest.fixture
async def async_handledning_client(credentials):
    """Create an async Handledning client for testing.

    Args:
        credentials: Credentials fixture

    Returns:
        AsyncHandledningClient: Initialized client
    """
    from dsv_wrapper import AsyncHandledningClient

    username, password = credentials

    client = AsyncHandledningClient(username=username, password=password, use_cache=False)

    async with client:
        yield client
