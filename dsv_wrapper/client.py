"""Unified client for all DSV systems."""

import os
from typing import Optional

from .actlab import ACTLabClient, AsyncACTLabClient
from .auth.cache_backend import CacheBackend
from .daisy import AsyncDaisyClient, DaisyClient
from .exceptions import AuthenticationError
from .handledning import AsyncHandledningClient, HandledningClient


class DSVClient:
    """Unified synchronous client for all DSV systems."""

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        daisy_service: str = "daisy_staff",
        cache_backend: Optional[CacheBackend] = None,
        cache_ttl: int = 86400,
    ):
        """Initialize DSV unified client.

        Args:
            username: SU username (default: read from SU_USERNAME env var)
            password: SU password (default: read from SU_PASSWORD env var)
            daisy_service: Daisy service type (daisy_staff or daisy_student)
            cache_backend: Cache backend for authentication cookies (default: NullCache)
            cache_ttl: Cache TTL in seconds (default: 86400 = 24 hours)

        Raises:
            AuthenticationError: If username/password not provided and not in env vars
        """
        # Get credentials from env vars if not provided
        self.username = username or os.environ.get("SU_USERNAME")
        self.password = password or os.environ.get("SU_PASSWORD")

        if not self.username or not self.password:
            raise AuthenticationError(
                "Username and password must be provided either as arguments or "
                "via SU_USERNAME and SU_PASSWORD environment variables"
            )

        self.cache_backend = cache_backend
        self.cache_ttl = cache_ttl

        # Initialize clients
        self._daisy: Optional[DaisyClient] = None
        self._handledning: Optional[HandledningClient] = None
        self._actlab: Optional[ACTLabClient] = None
        self.daisy_service = daisy_service

    @property
    def daisy(self) -> DaisyClient:
        """Get Daisy client (lazy initialization).

        Returns:
            DaisyClient instance
        """
        if self._daisy is None:
            self._daisy = DaisyClient(
                username=self.username,
                password=self.password,
                service=self.daisy_service,
                cache_backend=self.cache_backend,
                cache_ttl=self.cache_ttl,
            )
        return self._daisy

    @property
    def handledning(self) -> HandledningClient:
        """Get Handledning client (lazy initialization).

        Returns:
            HandledningClient instance
        """
        if self._handledning is None:
            self._handledning = HandledningClient(
                username=self.username,
                password=self.password,
                mobile=False,
                cache_backend=self.cache_backend,
                cache_ttl=self.cache_ttl,
            )
        return self._handledning

    @property
    def actlab(self) -> ACTLabClient:
        """Get ACT Lab client (lazy initialization).

        Returns:
            ACTLabClient instance
        """
        if self._actlab is None:
            self._actlab = ACTLabClient(
                username=self.username,
                password=self.password,
                cache_backend=self.cache_backend,
                cache_ttl=self.cache_ttl,
            )
        return self._actlab

    def close(self) -> None:
        """Close all client sessions."""
        if self._daisy is not None:
            self._daisy.close()
        if self._handledning is not None:
            self._handledning.close()
        if self._actlab is not None:
            self._actlab.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


class AsyncDSVClient:
    """Unified asynchronous client for all DSV systems."""

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        daisy_service: str = "daisy_staff",
        cache_backend: Optional[CacheBackend] = None,
        cache_ttl: int = 86400,
    ):
        """Initialize async DSV unified client.

        Args:
            username: SU username (default: read from SU_USERNAME env var)
            password: SU password (default: read from SU_PASSWORD env var)
            daisy_service: Daisy service type (daisy_staff or daisy_student)
            cache_backend: Cache backend for authentication cookies (default: NullCache)
            cache_ttl: Cache TTL in seconds (default: 86400 = 24 hours)

        Raises:
            AuthenticationError: If username/password not provided and not in env vars
        """
        # Get credentials from env vars if not provided
        self.username = username or os.environ.get("SU_USERNAME")
        self.password = password or os.environ.get("SU_PASSWORD")

        if not self.username or not self.password:
            raise AuthenticationError(
                "Username and password must be provided either as arguments or "
                "via SU_USERNAME and SU_PASSWORD environment variables"
            )

        self.cache_backend = cache_backend
        self.cache_ttl = cache_ttl

        # Initialize clients
        self._daisy: Optional[AsyncDaisyClient] = None
        self._handledning: Optional[AsyncHandledningClient] = None
        self._actlab: Optional[AsyncACTLabClient] = None
        self.daisy_service = daisy_service

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._daisy is not None:
            await self._daisy.__aexit__(exc_type, exc_val, exc_tb)
        if self._handledning is not None:
            await self._handledning.__aexit__(exc_type, exc_val, exc_tb)
        if self._actlab is not None:
            await self._actlab.__aexit__(exc_type, exc_val, exc_tb)

    async def get_daisy(self) -> AsyncDaisyClient:
        """Get async Daisy client (lazy initialization).

        Returns:
            AsyncDaisyClient instance
        """
        if self._daisy is None:
            self._daisy = AsyncDaisyClient(
                username=self.username,
                password=self.password,
                service=self.daisy_service,
                cache_backend=self.cache_backend,
                cache_ttl=self.cache_ttl,
            )
            await self._daisy.__aenter__()
        return self._daisy

    async def get_handledning(self) -> AsyncHandledningClient:
        """Get async Handledning client (lazy initialization).

        Returns:
            AsyncHandledningClient instance
        """
        if self._handledning is None:
            self._handledning = AsyncHandledningClient(
                username=self.username,
                password=self.password,
                mobile=False,
                cache_backend=self.cache_backend,
                cache_ttl=self.cache_ttl,
            )
            await self._handledning.__aenter__()
        return self._handledning

    async def get_actlab(self) -> AsyncACTLabClient:
        """Get async ACT Lab client (lazy initialization).

        Returns:
            AsyncACTLabClient instance
        """
        if self._actlab is None:
            self._actlab = AsyncACTLabClient(
                username=self.username,
                password=self.password,
                cache_backend=self.cache_backend,
                cache_ttl=self.cache_ttl,
            )
            await self._actlab.__aenter__()
        return self._actlab
