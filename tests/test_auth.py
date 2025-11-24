"""Tests for authentication module."""

import logging

import pytest

from dsv_wrapper import NullCache, ShibbolethAuth
from dsv_wrapper.exceptions import AuthenticationError

logger = logging.getLogger(__name__)


@pytest.mark.integration
def test_shibboleth_auth_login(credentials):
    """Test basic Shibboleth authentication."""
    username, password = credentials

    auth = ShibbolethAuth(username=username, password=password, cache_backend=NullCache())

    # Login to daisy staff service
    cookies = auth._login(service="daisy_staff")

    assert cookies is not None
    assert len(cookies) > 0

    logger.info(f"Successfully authenticated with {len(cookies)} cookies")

    auth.__exit__(None, None, None)


@pytest.mark.integration
def test_shibboleth_auth_with_cache(credentials, tmp_path):
    """Test authentication with cookie caching."""
    username, password = credentials

    # Create cache in temporary directory
    from dsv_wrapper import FileCache
    cache = FileCache(cache_dir=tmp_path, default_ttl=3600)

    auth = ShibbolethAuth(username=username, password=password, cache_backend=cache)

    # First login (should hit the server)
    cookies1 = auth._login(service="daisy_staff")
    assert cookies1 is not None

    # Second login (should use cache)
    cookies2 = auth._login(service="daisy_staff")
    assert cookies2 is not None

    # Check cache was used
    cache_key = f"{username}_daisy_staff"
    assert cache.get(cache_key) is not None

    logger.info("Cookie caching working correctly")

    auth.__exit__(None, None, None)


@pytest.mark.integration
def test_shibboleth_auth_invalid_credentials():
    """Test authentication with invalid credentials."""
    auth = ShibbolethAuth(username="invalid_user", password="wrong_password", cache_backend=NullCache())

    with pytest.raises((AuthenticationError, Exception)):
        auth._login(service="daisy_staff")

    auth.__exit__(None, None, None)


@pytest.mark.integration
def test_shibboleth_auth_daisy_staff(credentials):
    """Test authentication to Daisy staff service."""
    username, password = credentials

    auth = ShibbolethAuth(username=username, password=password, cache_backend=NullCache())

    cookies = auth._login(service="daisy_staff")

    assert cookies is not None
    logger.info("Successfully authenticated to Daisy staff service")

    auth.__exit__(None, None, None)


@pytest.mark.integration
def test_shibboleth_auth_handledning(credentials):
    """Test authentication to Handledning service."""
    username, password = credentials

    auth = ShibbolethAuth(username=username, password=password, cache_backend=NullCache())

    cookies = auth._login(service="handledning")

    assert cookies is not None
    logger.info("Successfully authenticated to Handledning service")

    auth.__exit__(None, None, None)


def test_cookie_cache_operations(tmp_path):
    """Test cookie cache operations."""
    from requests.cookies import RequestsCookieJar
    from dsv_wrapper import FileCache

    cache = FileCache(cache_dir=tmp_path, default_ttl=3600)

    # Create test cookies
    cookies = RequestsCookieJar()
    cookies.set("test_cookie", "test_value", domain="example.com", path="/")

    # Test set
    cache.set("test_key", cookies)

    # Test get
    cached_cookies = cache.get("test_key")
    assert cached_cookies is not None
    assert "test_cookie" in cached_cookies

    # Test delete
    cache.delete("test_key")
    assert cache.get("test_key") is None

    logger.info("Cookie cache operations working correctly")


def test_cookie_cache_expiry(tmp_path):
    """Test cookie cache expiry."""
    from requests.cookies import RequestsCookieJar
    from dsv_wrapper import FileCache

    # Create cache with very short TTL (1 second)
    cache = FileCache(cache_dir=tmp_path, default_ttl=1)

    cookies = RequestsCookieJar()
    cookies.set("test_cookie", "test_value")

    cache.set("test_key", cookies)

    # Should be valid immediately
    assert cache.get("test_key") is not None

    # Wait for expiry
    import time

    time.sleep(2)  # Sleep for 2 seconds to ensure cache expired

    # Should be expired now
    assert cache.get("test_key") is None

    logger.info("Cookie cache expiry working correctly")
