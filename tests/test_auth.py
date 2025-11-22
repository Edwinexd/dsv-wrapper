"""Tests for authentication module."""

import logging

import pytest

from dsv_wrapper import CookieCache, ShibbolethAuth
from dsv_wrapper.exceptions import AuthenticationError

logger = logging.getLogger(__name__)


@pytest.mark.integration
def test_shibboleth_auth_login(credentials):
    """Test basic Shibboleth authentication."""
    username, password = credentials

    auth = ShibbolethAuth(username=username, password=password, use_cache=False)

    # Login to unified service
    cookies = auth.login(service="unified")

    assert cookies is not None
    assert len(cookies) > 0

    logger.info(f"Successfully authenticated with {len(cookies)} cookies")

    auth.__exit__(None, None, None)


@pytest.mark.integration
def test_shibboleth_auth_with_cache(credentials, tmp_path):
    """Test authentication with cookie caching."""
    username, password = credentials

    # Create cache in temporary directory
    cache = CookieCache(cache_dir=tmp_path, ttl_hours=1)

    auth = ShibbolethAuth(username=username, password=password, cache=cache, use_cache=True)

    # First login (should hit the server)
    cookies1 = auth.login(service="unified")
    assert cookies1 is not None

    # Second login (should use cache)
    cookies2 = auth.login(service="unified")
    assert cookies2 is not None

    # Check cache was used
    cache_key = f"{username}_unified"
    assert cache.is_valid(cache_key)

    logger.info("Cookie caching working correctly")

    auth.__exit__(None, None, None)


@pytest.mark.integration
def test_shibboleth_auth_invalid_credentials():
    """Test authentication with invalid credentials."""
    auth = ShibbolethAuth(username="invalid_user", password="wrong_password", use_cache=False)

    with pytest.raises((AuthenticationError, Exception)):
        auth.login(service="unified")

    auth.__exit__(None, None, None)


@pytest.mark.integration
def test_shibboleth_auth_daisy_staff(credentials):
    """Test authentication to Daisy staff service."""
    username, password = credentials

    auth = ShibbolethAuth(username=username, password=password, use_cache=False)

    cookies = auth.login(service="daisy_staff")

    assert cookies is not None
    logger.info("Successfully authenticated to Daisy staff service")

    auth.__exit__(None, None, None)


@pytest.mark.integration
def test_shibboleth_auth_handledning(credentials):
    """Test authentication to Handledning service."""
    username, password = credentials

    auth = ShibbolethAuth(username=username, password=password, use_cache=False)

    cookies = auth.login(service="handledning")

    assert cookies is not None
    logger.info("Successfully authenticated to Handledning service")

    auth.__exit__(None, None, None)


def test_cookie_cache_operations(tmp_path):
    """Test cookie cache operations."""
    from requests.cookies import RequestsCookieJar

    cache = CookieCache(cache_dir=tmp_path, ttl_hours=1)

    # Create test cookies
    cookies = RequestsCookieJar()
    cookies.set("test_cookie", "test_value", domain="example.com", path="/")

    # Test set
    cache.set("test_key", cookies)

    # Test get
    cached_cookies = cache.get("test_key")
    assert cached_cookies is not None
    assert "test_cookie" in cached_cookies

    # Test is_valid
    assert cache.is_valid("test_key")

    # Test delete
    cache.delete("test_key")
    assert not cache.is_valid("test_key")

    logger.info("Cookie cache operations working correctly")


def test_cookie_cache_expiry(tmp_path):
    """Test cookie cache expiry."""
    from requests.cookies import RequestsCookieJar

    # Create cache with very short TTL
    cache = CookieCache(cache_dir=tmp_path, ttl_hours=0.0001)  # ~0.36 seconds

    cookies = RequestsCookieJar()
    cookies.set("test_cookie", "test_value")

    cache.set("test_key", cookies)

    # Should be valid immediately
    assert cache.is_valid("test_key")

    # Wait for expiry
    import time

    time.sleep(1)

    # Should be expired now
    assert not cache.is_valid("test_key")

    logger.info("Cookie cache expiry working correctly")
