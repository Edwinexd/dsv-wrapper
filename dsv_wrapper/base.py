"""Base classes for DSV wrapper clients."""

from typing import Optional

import aiohttp

from .auth import AsyncShibbolethAuth
from .auth.cache_backend import CacheBackend
from .utils import DEFAULT_HEADERS


class BaseAsyncClient:
    """Base class for async DSV clients."""

    def __init__(
        self,
        username: str,
        password: str,
        base_url: str,
        service: str,
        cache_backend: Optional[CacheBackend] = None,
        cache_ttl: int = 86400,
    ):
        """Initialize base async client.

        Args:
            username: SU username
            password: SU password
            base_url: Base URL for the service
            service: Service name for authentication
            cache_backend: Cache backend for authentication cookies (default: NullCache)
            cache_ttl: Cache time-to-live in seconds (default: 86400 = 24 hours)
        """
        self.username = username
        self.password = password
        self.base_url = base_url
        self.service = service

        self.auth = AsyncShibbolethAuth(username, password, cache_backend=cache_backend, cache_ttl=cache_ttl)
        self.session: Optional[aiohttp.ClientSession] = None
        self._authenticated = False

    async def __aenter__(self):
        """Async context manager entry."""
        await self.auth.__aenter__()
        # Create session - cookies will be transferred after login
        self.session = aiohttp.ClientSession(headers=DEFAULT_HEADERS)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
        await self.auth.__aexit__(exc_type, exc_val, exc_tb)

    async def _ensure_authenticated(self) -> None:
        """Ensure the client is authenticated."""
        if not self._authenticated:
            # Get cookies from sync auth (runs in thread pool)
            cookies_dict = await self.auth.login(self.service)

            # Transfer cookies from sync session to async session
            # We need to create SimpleCookie objects with proper domain/path
            from http.cookies import SimpleCookie, Morsel
            from yarl import URL

            for cookie in self.auth._sync_auth.session.cookies:
                # Create a SimpleCookie with this cookie
                simple_cookie = SimpleCookie()
                morsel = Morsel()
                morsel.set(cookie.name, cookie.value, cookie.value)
                morsel['domain'] = cookie.domain if cookie.domain else ''
                morsel['path'] = cookie.path if cookie.path else '/'
                simple_cookie[cookie.name] = morsel

                # Update the cookie jar with a URL that matches the domain
                url = URL(self.base_url)
                self.session.cookie_jar.update_cookies(simple_cookie, url)

            self._authenticated = True
