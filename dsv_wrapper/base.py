"""Base classes for DSV wrapper clients."""

from typing import Optional

import aiohttp

from .auth import AsyncShibbolethAuth
from .auth.cache_backend import CacheBackend, MemoryCache, NullCache
from .utils import DEFAULT_HEADERS


class BaseAsyncClient:
    """Base class for async DSV clients."""

    def __init__(
        self,
        username: str,
        password: str,
        base_url: str,
        service: str,
        use_cache: bool = True,
        cache_backend: Optional[CacheBackend] = None,
        cache_ttl: int = 86400,
    ):
        """Initialize base async client.

        Args:
            username: SU username
            password: SU password
            base_url: Base URL for the service
            service: Service name for authentication
            use_cache: Whether to cache authentication cookies (default: True with MemoryCache)
            cache_backend: Custom cache backend (overrides use_cache if provided)
            cache_ttl: Cache time-to-live in seconds (default: 86400 = 24 hours)
        """
        self.username = username
        self.password = password
        self.base_url = base_url
        self.service = service

        # Determine cache backend
        if cache_backend is not None:
            _cache_backend = cache_backend
        elif use_cache:
            _cache_backend = MemoryCache()
        else:
            _cache_backend = NullCache()

        self.auth = AsyncShibbolethAuth(username, password, cache_backend=_cache_backend, cache_ttl=cache_ttl)
        self.session: Optional[aiohttp.ClientSession] = None
        self._authenticated = False

    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession(headers=DEFAULT_HEADERS)
        await self.auth.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
        await self.auth.__aexit__(exc_type, exc_val, exc_tb)

    async def _ensure_authenticated(self) -> None:
        """Ensure the client is authenticated."""
        if not self._authenticated:
            cookies = await self.auth.login(self.service)
            for name, value in cookies.items():
                self.session.cookie_jar.update_cookies({name: value})
            self._authenticated = True
