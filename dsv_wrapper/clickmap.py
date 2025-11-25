"""Clickmap client for DSV office/workspace placement map."""

import logging
import os

import httpx

from .auth import AsyncShibbolethAuth, ShibbolethAuth
from .auth.cache_backend import CacheBackend
from .exceptions import AuthenticationError, NetworkError
from .models import Placement
from .utils import DEFAULT_HEADERS, DSV_URLS

logger = logging.getLogger(__name__)


class ClickmapClient:
    """Synchronous client for Clickmap system.

    Clickmap provides a map of DSV office/workspace placements with person assignments.
    """

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        cache_backend: CacheBackend | None = None,
        cache_ttl: int = 86400,
    ):
        """Initialize Clickmap client.

        Args:
            username: SU username (default: read from SU_USERNAME env var)
            password: SU password (default: read from SU_PASSWORD env var)
            cache_backend: Cache backend for authentication cookies (default: NullCache)
            cache_ttl: Cache TTL in seconds (default: 86400 = 24 hours)

        Raises:
            AuthenticationError: If username/password not provided and not in env vars
        """
        self.username = username or os.environ.get("SU_USERNAME")
        self.password = password or os.environ.get("SU_PASSWORD")

        if not self.username or not self.password:
            raise AuthenticationError(
                "Username and password must be provided either as arguments or "
                "via SU_USERNAME and SU_PASSWORD environment variables"
            )

        self.base_url = DSV_URLS["clickmap"]
        self.auth = ShibbolethAuth(
            self.username, self.password, cache_backend=cache_backend, cache_ttl=cache_ttl
        )
        self._client = httpx.Client(headers=DEFAULT_HEADERS, follow_redirects=True)
        self._authenticated = False

        logger.debug(f"Initialized ClickmapClient for user: {self.username}")

    def _ensure_authenticated(self) -> None:
        """Ensure the client is authenticated."""
        if not self._authenticated:
            logger.debug("Authenticating to clickmap...")
            self.auth._login("clickmap")
            # Copy cookies from auth client to this client
            for cookie in self.auth._client.cookies.jar:
                self._client.cookies.set(
                    cookie.name, cookie.value, domain=cookie.domain, path=cookie.path
                )
            self._authenticated = True
            logger.debug("Successfully authenticated to clickmap")

    def get_placements(self) -> list[Placement]:
        """Get all workspace placements.

        Returns:
            List of Placement objects with person and location information

        Raises:
            NetworkError: If the request fails
        """
        self._ensure_authenticated()

        url = f"{self.base_url}/api/points"
        logger.debug(f"Fetching placements from {url}")

        try:
            response = self._client.get(url, timeout=30)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise NetworkError(f"Failed to fetch placements: {e}") from e

        data = response.json()
        logger.info(f"Retrieved {len(data)} placements")

        placements = []
        for point_id, values in data.items():
            placement = Placement(
                id=point_id,
                place_name=values.get("placeName", ""),
                person_name=values.get("personName", ""),
                person_role=values.get("personRole", ""),
                latitude=values.get("latitude", 0.0),
                longitude=values.get("longitude", 0.0),
                comment=values.get("comment", ""),
            )
            placements.append(placement)

        return placements

    def search_placements(self, query: str) -> list[Placement]:
        """Search placements by person name or place name.

        Args:
            query: Search query (case-insensitive)

        Returns:
            List of matching Placement objects
        """
        query_lower = query.lower()
        placements = self.get_placements()

        return [
            p
            for p in placements
            if query_lower in p.person_name.lower() or query_lower in p.place_name.lower()
        ]

    def get_placement_by_person(self, person_name: str) -> Placement | None:
        """Find a placement by exact person name.

        Args:
            person_name: Exact person name to search for

        Returns:
            Placement object if found, None otherwise
        """
        placements = self.get_placements()
        for p in placements:
            if p.person_name == person_name:
                return p
        return None

    def get_placement_by_place(self, place_name: str) -> Placement | None:
        """Find a placement by exact place name.

        Args:
            place_name: Exact place name to search for (e.g., '66109', '6:7')

        Returns:
            Placement object if found, None otherwise
        """
        placements = self.get_placements()
        for p in placements:
            if p.place_name == place_name:
                return p
        return None

    def get_occupied_placements(self) -> list[Placement]:
        """Get only placements that have a person assigned.

        Returns:
            List of Placement objects with person assignments
        """
        return [p for p in self.get_placements() if p.is_occupied]

    def get_vacant_placements(self) -> list[Placement]:
        """Get only placements without a person assigned.

        Returns:
            List of vacant Placement objects
        """
        return [p for p in self.get_placements() if not p.is_occupied]

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


class AsyncClickmapClient:
    """Asynchronous client for Clickmap system.

    Clickmap provides a map of DSV office/workspace placements with person assignments.
    """

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        cache_backend: CacheBackend | None = None,
        cache_ttl: int = 86400,
    ):
        """Initialize async Clickmap client.

        Args:
            username: SU username (default: read from SU_USERNAME env var)
            password: SU password (default: read from SU_PASSWORD env var)
            cache_backend: Cache backend for authentication cookies (default: NullCache)
            cache_ttl: Cache TTL in seconds (default: 86400 = 24 hours)

        Raises:
            AuthenticationError: If username/password not provided and not in env vars
        """
        self.username = username or os.environ.get("SU_USERNAME")
        self.password = password or os.environ.get("SU_PASSWORD")

        if not self.username or not self.password:
            raise AuthenticationError(
                "Username and password must be provided either as arguments or "
                "via SU_USERNAME and SU_PASSWORD environment variables"
            )

        self.base_url = DSV_URLS["clickmap"]
        self.auth = AsyncShibbolethAuth(
            self.username, self.password, cache_backend=cache_backend, cache_ttl=cache_ttl
        )
        self._client: httpx.AsyncClient | None = None
        self._authenticated = False

        logger.debug(f"Initialized AsyncClickmapClient for user: {self.username}")

    async def __aenter__(self):
        """Async context manager entry."""
        await self.auth.__aenter__()
        self._client = httpx.AsyncClient(headers=DEFAULT_HEADERS, follow_redirects=True)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
        await self.auth.__aexit__(exc_type, exc_val, exc_tb)

    async def _ensure_authenticated(self) -> None:
        """Ensure the client is authenticated."""
        if not self._authenticated:
            logger.debug("Authenticating to clickmap...")
            await self.auth.login(service="clickmap")
            # Copy cookies from auth client to this client (preserve domain/path)
            for cookie in self.auth._sync_auth._client.cookies.jar:
                self._client.cookies.set(
                    cookie.name, cookie.value, domain=cookie.domain, path=cookie.path
                )
            self._authenticated = True
            logger.debug("Successfully authenticated to clickmap")

    async def get_placements(self) -> list[Placement]:
        """Get all workspace placements.

        Returns:
            List of Placement objects with person and location information

        Raises:
            NetworkError: If the request fails
        """
        await self._ensure_authenticated()

        url = f"{self.base_url}/api/points"
        logger.debug(f"Fetching placements from {url}")

        try:
            response = await self._client.get(url, timeout=30)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise NetworkError(f"Failed to fetch placements: {e}") from e

        data = response.json()
        logger.info(f"Retrieved {len(data)} placements")

        placements = []
        for point_id, values in data.items():
            placement = Placement(
                id=point_id,
                place_name=values.get("placeName", ""),
                person_name=values.get("personName", ""),
                person_role=values.get("personRole", ""),
                latitude=values.get("latitude", 0.0),
                longitude=values.get("longitude", 0.0),
                comment=values.get("comment", ""),
            )
            placements.append(placement)

        return placements

    async def search_placements(self, query: str) -> list[Placement]:
        """Search placements by person name or place name.

        Args:
            query: Search query (case-insensitive)

        Returns:
            List of matching Placement objects
        """
        query_lower = query.lower()
        placements = await self.get_placements()

        return [
            p
            for p in placements
            if query_lower in p.person_name.lower() or query_lower in p.place_name.lower()
        ]

    async def get_placement_by_person(self, person_name: str) -> Placement | None:
        """Find a placement by exact person name.

        Args:
            person_name: Exact person name to search for

        Returns:
            Placement object if found, None otherwise
        """
        placements = await self.get_placements()
        for p in placements:
            if p.person_name == person_name:
                return p
        return None

    async def get_placement_by_place(self, place_name: str) -> Placement | None:
        """Find a placement by exact place name.

        Args:
            place_name: Exact place name to search for (e.g., '66109', '6:7')

        Returns:
            Placement object if found, None otherwise
        """
        placements = await self.get_placements()
        for p in placements:
            if p.place_name == place_name:
                return p
        return None

    async def get_occupied_placements(self) -> list[Placement]:
        """Get only placements that have a person assigned.

        Returns:
            List of Placement objects with person assignments
        """
        placements = await self.get_placements()
        return [p for p in placements if p.is_occupied]

    async def get_vacant_placements(self) -> list[Placement]:
        """Get only placements without a person assigned.

        Returns:
            List of vacant Placement objects
        """
        placements = await self.get_placements()
        return [p for p in placements if not p.is_occupied]
