"""Base classes for Shibboleth-authenticated DSV clients.

Owns what every service client shares: credential resolution, the
Shibboleth authenticator, the private retrying httpx client, lazy login with
cookie transfer, and closing/context-manager handling. Subclasses only add
service-specific methods.
"""

import logging
import os

import httpx

from .auth import AsyncShibbolethAuth, ShibbolethAuth
from .auth.cache_backend import CacheBackend
from .auth.shibboleth import ServiceType
from .exceptions import AuthenticationError
from .retry import create_async_client, create_client

logger = logging.getLogger(__name__)


def resolve_credentials(username: str | None, password: str | None) -> tuple[str, str]:
    """Return explicit credentials, falling back to SU_USERNAME/SU_PASSWORD.

    Raises:
        AuthenticationError: If username/password not provided and not in env vars
    """
    username = username or os.environ.get("SU_USERNAME")
    password = password or os.environ.get("SU_PASSWORD")
    if not username or not password:
        raise AuthenticationError(
            "Username and password must be provided either as arguments or "
            "via SU_USERNAME and SU_PASSWORD environment variables"
        )
    return username, password


def _copy_cookies(source: httpx.Cookies, target: httpx.Cookies) -> None:
    """Copy cookies preserving domain/path so they're sent to the right hosts."""
    for cookie in source.jar:
        target.set(cookie.name, cookie.value, domain=cookie.domain, path=cookie.path)


class BaseClient:
    """Base class for synchronous Shibboleth-authenticated clients."""

    def __init__(
        self,
        username: str | None,
        password: str | None,
        service: ServiceType,
        base_url: str,
        cache_backend: CacheBackend | None = None,
        cache_ttl: int = 86400,
        follow_redirects: bool = True,
    ):
        self.username, self.password = resolve_credentials(username, password)
        self.service = service
        self.base_url = base_url
        self.auth = ShibbolethAuth(
            self.username, self.password, cache_backend=cache_backend, cache_ttl=cache_ttl
        )
        self._client = create_client(follow_redirects=follow_redirects)
        self._authenticated = False

        logger.debug(f"Initialized {type(self).__name__} for user: {self.username}")

    def _ensure_authenticated(self) -> None:
        """Log in on first use and copy the session cookies to this client."""
        if self._authenticated:
            return
        logger.debug(f"Authenticating to {self.service}")
        self.auth._login(self.service)
        _copy_cookies(self.auth._client.cookies, self._client.cookies)
        self._authenticated = True

    def close(self) -> None:
        """Close the client session."""
        self._client.close()
        self.auth.__exit__(None, None, None)

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


class BaseAsyncClient:
    """Base class for asynchronous Shibboleth-authenticated clients.

    The httpx client is created in ``__aenter__``, so instances must be used
    as async context managers.
    """

    def __init__(
        self,
        username: str | None,
        password: str | None,
        service: ServiceType,
        base_url: str,
        cache_backend: CacheBackend | None = None,
        cache_ttl: int = 86400,
        follow_redirects: bool = True,
    ):
        self.username, self.password = resolve_credentials(username, password)
        self.service = service
        self.base_url = base_url
        self.auth = AsyncShibbolethAuth(
            self.username, self.password, cache_backend=cache_backend, cache_ttl=cache_ttl
        )
        self._follow_redirects = follow_redirects
        self._client: httpx.AsyncClient | None = None
        self._authenticated = False

        logger.debug(f"Initialized {type(self).__name__} for user: {self.username}")

    async def __aenter__(self):
        """Async context manager entry."""
        await self.auth.__aenter__()
        self._client = create_async_client(follow_redirects=self._follow_redirects)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
        await self.auth.__aexit__(exc_type, exc_val, exc_tb)

    async def _ensure_authenticated(self) -> None:
        """Log in on first use and copy the session cookies to this client."""
        if self._authenticated:
            return
        logger.debug(f"Authenticating to {self.service}")
        await self.auth.login(service=self.service)
        _copy_cookies(self.auth._sync_auth._client.cookies, self._client.cookies)
        self._authenticated = True
