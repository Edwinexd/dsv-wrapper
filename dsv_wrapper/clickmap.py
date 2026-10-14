"""Clickmap client for DSV office/workspace placement map."""

import logging

import httpx

from .auth.cache_backend import CacheBackend
from .base import BaseAsyncClient, BaseClient
from .exceptions import NetworkError
from .models import Placement
from .utils import DSV_URLS

logger = logging.getLogger(__name__)


class ClickmapClient(BaseClient):
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
        super().__init__(
            username,
            password,
            "clickmap",
            DSV_URLS["clickmap"],
            cache_backend=cache_backend,
            cache_ttl=cache_ttl,
        )

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
            response = self._client.get(url, timeout=60)
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


class AsyncClickmapClient(BaseAsyncClient):
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
        super().__init__(
            username,
            password,
            "clickmap",
            DSV_URLS["clickmap"],
            cache_backend=cache_backend,
            cache_ttl=cache_ttl,
        )

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
            response = await self._client.get(url, timeout=60)
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
