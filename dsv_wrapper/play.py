"""Play client for DSVPlay presentation/video platform."""

import logging
import os

import httpx

from .auth import AsyncShibbolethAuth, ShibbolethAuth
from .auth.cache_backend import CacheBackend
from .exceptions import AuthenticationError, NetworkError, ParseError
from .models.play import PlayCourse, Presentation, TranscriptCue
from .parsers.play import (
    parse_courses_from_html,
    parse_courses_from_tag_html,
    parse_playlist_id_from_html,
    parse_playlist_json,
    parse_presentation_ids_from_html,
    parse_presentation_json,
    parse_vtt,
)
from .utils import DEFAULT_HEADERS, DSV_URLS

logger = logging.getLogger(__name__)


class PlayClient:
    """Synchronous client for DSVPlay (play.dsv.su.se).

    DSVPlay is the video/presentation platform for DSV, hosting recorded lectures
    and presentations organized by course.
    """

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        cache_backend: CacheBackend | None = None,
        cache_ttl: int = 86400,
    ):
        """Initialize Play client.

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

        self.base_url = DSV_URLS["play"]
        self.auth = ShibbolethAuth(
            self.username, self.password, cache_backend=cache_backend, cache_ttl=cache_ttl
        )
        self._client = httpx.Client(headers=DEFAULT_HEADERS, follow_redirects=True)
        self._authenticated = False

        logger.debug(f"Initialized PlayClient for user: {self.username}")

    def _ensure_authenticated(self) -> None:
        """Ensure the client is authenticated."""
        if not self._authenticated:
            logger.debug("Authenticating to play...")
            self.auth._login("play")
            for cookie in self.auth._client.cookies.jar:
                self._client.cookies.set(
                    cookie.name, cookie.value, domain=cookie.domain, path=cookie.path
                )
            self._authenticated = True
            logger.debug("Successfully authenticated to play")

    def get_courses(self) -> list[PlayCourse]:
        """Get all courses the user has presentations in.

        Returns:
            List of PlayCourse objects with code and name

        Raises:
            NetworkError: If the request fails
            ParseError: If parsing fails
        """
        self._ensure_authenticated()

        url = f"{self.base_url}/user/all"
        logger.debug(f"Fetching courses from {url}")

        try:
            response = self._client.get(url, timeout=30)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise NetworkError(f"Failed to fetch courses: {e}") from e

        return parse_courses_from_html(response.text)

    def get_courses_by_tag(self, tag: str) -> list[PlayCourse]:
        """Get all courses that have at least one presentation tagged ``tag``.

        Unlike :meth:`get_courses`, this is not user-scoped: it reflects every
        course visible on ``/tag/{tag}``, including ones the authenticated user
        is not enrolled in. Unioning across broad tags like ``Lecture`` and
        ``Föreläsning`` yields a near-complete designation catalog.

        Args:
            tag: Tag name (e.g. ``"Lecture"`` or ``"Föreläsning"``). Non-ASCII
                characters are URL-encoded automatically.

        Returns:
            List of PlayCourse objects

        Raises:
            NetworkError: If the request fails
            ParseError: If parsing fails
        """
        self._ensure_authenticated()

        from urllib.parse import quote
        url = f"{self.base_url}/tag/{quote(tag)}"
        logger.debug(f"Fetching courses for tag {tag!r} from {url}")

        try:
            response = self._client.get(url, timeout=60)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise NetworkError(f"Failed to fetch tag page: {e}") from e

        return parse_courses_from_tag_html(response.text)

    def get_presentations(self, designation: str) -> list[Presentation]:
        """Get all presentations for a course designation.

        First tries to use the playlist endpoint (fast, single request).
        Falls back to extracting presentation IDs from the page and fetching
        each individually.

        Args:
            designation: Course designation code (e.g., 'PROG1', 'IDSV')

        Returns:
            List of Presentation objects (lightweight: id, title, thumb_url)

        Raises:
            NetworkError: If the request fails
            ParseError: If parsing fails
        """
        self._ensure_authenticated()

        url = f"{self.base_url}/designation/{designation}"
        logger.debug(f"Fetching presentations for {designation} from {url}")

        try:
            response = self._client.get(url, timeout=30)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise NetworkError(f"Failed to fetch designation page: {e}") from e

        html = response.text

        # Try playlist approach first (single request)
        playlist_id = parse_playlist_id_from_html(html)
        if playlist_id is not None:
            return self._get_playlist(playlist_id)

        # Fallback: extract UUIDs and fetch each presentation
        logger.debug("No playlist found, falling back to individual fetches")
        presentation_ids = parse_presentation_ids_from_html(html)
        presentations = []
        for pid in presentation_ids:
            try:
                presentations.append(self.get_presentation(pid))
            except (NetworkError, ParseError) as e:
                logger.warning(f"Failed to fetch presentation {pid}: {e}")

        return presentations

    def get_presentation(self, presentation_id: str) -> Presentation:
        """Get full presentation details including video sources and subtitles.

        Args:
            presentation_id: Presentation UUID

        Returns:
            Presentation object with sources, subtitles, and token

        Raises:
            NetworkError: If the request fails
            ParseError: If parsing fails
        """
        self._ensure_authenticated()

        url = f"{self.base_url}/presentation/{presentation_id}"
        logger.debug(f"Fetching presentation from {url}")

        try:
            response = self._client.get(url, timeout=30)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise NetworkError(f"Failed to fetch presentation: {e}") from e

        return parse_presentation_json(response.json())

    def get_transcript(self, presentation_id: str) -> list[TranscriptCue]:
        """Get the transcript (parsed VTT subtitles) for a presentation.

        Args:
            presentation_id: Presentation UUID

        Returns:
            List of TranscriptCue objects with timestamps and text

        Raises:
            NetworkError: If the request fails
            ParseError: If the VTT content is invalid or no subtitles available
        """
        presentation = self.get_presentation(presentation_id)

        if not presentation.subtitles:
            raise ParseError(f"Presentation {presentation_id} has no subtitles")

        # Use the first available subtitle track
        label = next(iter(presentation.subtitles))
        vtt_url = presentation.subtitles[label]
        token = presentation.token

        logger.debug(f"Fetching VTT from {vtt_url}")

        try:
            response = self._client.get(vtt_url, params={"token": token}, timeout=30)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise NetworkError(f"Failed to fetch VTT subtitles: {e}") from e

        if response.text.strip() == "Unauthorized":
            raise NetworkError("Failed to fetch VTT: unauthorized (token may be expired)")

        return parse_vtt(response.text)

    def get_transcript_text(self, presentation_id: str) -> str:
        """Get the transcript as plain text.

        Args:
            presentation_id: Presentation UUID

        Returns:
            Plain text transcript with cues joined by spaces

        Raises:
            NetworkError: If the request fails
            ParseError: If the VTT content is invalid or no subtitles available
        """
        cues = self.get_transcript(presentation_id)
        return " ".join(cue.text for cue in cues)

    def _get_playlist(self, playlist_id: int) -> list[Presentation]:
        """Fetch playlist and return as Presentation list.

        Args:
            playlist_id: Playlist ID

        Returns:
            List of lightweight Presentation objects
        """
        url = f"{self.base_url}/playlist/{playlist_id}"
        logger.debug(f"Fetching playlist from {url}")

        try:
            response = self._client.get(url, timeout=30)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise NetworkError(f"Failed to fetch playlist: {e}") from e

        return parse_playlist_json(response.json())

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


class AsyncPlayClient:
    """Asynchronous client for DSVPlay (play.dsv.su.se).

    DSVPlay is the video/presentation platform for DSV, hosting recorded lectures
    and presentations organized by course.
    """

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        cache_backend: CacheBackend | None = None,
        cache_ttl: int = 86400,
    ):
        """Initialize async Play client.

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

        self.base_url = DSV_URLS["play"]
        self.auth = AsyncShibbolethAuth(
            self.username, self.password, cache_backend=cache_backend, cache_ttl=cache_ttl
        )
        self._client: httpx.AsyncClient | None = None
        self._authenticated = False

        logger.debug(f"Initialized AsyncPlayClient for user: {self.username}")

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
            logger.debug("Authenticating to play...")
            await self.auth.login(service="play")
            for cookie in self.auth._sync_auth._client.cookies.jar:
                self._client.cookies.set(
                    cookie.name, cookie.value, domain=cookie.domain, path=cookie.path
                )
            self._authenticated = True
            logger.debug("Successfully authenticated to play")

    async def get_courses(self) -> list[PlayCourse]:
        """Get all courses the user has presentations in.

        Returns:
            List of PlayCourse objects with code and name

        Raises:
            NetworkError: If the request fails
            ParseError: If parsing fails
        """
        await self._ensure_authenticated()

        url = f"{self.base_url}/user/all"
        logger.debug(f"Fetching courses from {url}")

        try:
            response = await self._client.get(url, timeout=30)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise NetworkError(f"Failed to fetch courses: {e}") from e

        return parse_courses_from_html(response.text)

    async def get_courses_by_tag(self, tag: str) -> list[PlayCourse]:
        """Get all courses that have at least one presentation tagged ``tag``.

        Not user-scoped: reflects every course visible on ``/tag/{tag}``.
        See :meth:`PlayClient.get_courses_by_tag` for details.

        Args:
            tag: Tag name (e.g. ``"Lecture"`` or ``"Föreläsning"``).

        Returns:
            List of PlayCourse objects

        Raises:
            NetworkError: If the request fails
            ParseError: If parsing fails
        """
        await self._ensure_authenticated()

        from urllib.parse import quote
        url = f"{self.base_url}/tag/{quote(tag)}"
        logger.debug(f"Fetching courses for tag {tag!r} from {url}")

        try:
            response = await self._client.get(url, timeout=60)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise NetworkError(f"Failed to fetch tag page: {e}") from e

        return parse_courses_from_tag_html(response.text)

    async def get_presentations(self, designation: str) -> list[Presentation]:
        """Get all presentations for a course designation.

        First tries to use the playlist endpoint (fast, single request).
        Falls back to extracting presentation IDs from the page and fetching
        each individually.

        Args:
            designation: Course designation code (e.g., 'PROG1', 'IDSV')

        Returns:
            List of Presentation objects (lightweight: id, title, thumb_url)

        Raises:
            NetworkError: If the request fails
            ParseError: If parsing fails
        """
        await self._ensure_authenticated()

        url = f"{self.base_url}/designation/{designation}"
        logger.debug(f"Fetching presentations for {designation} from {url}")

        try:
            response = await self._client.get(url, timeout=30)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise NetworkError(f"Failed to fetch designation page: {e}") from e

        html = response.text

        # Try playlist approach first (single request)
        playlist_id = parse_playlist_id_from_html(html)
        if playlist_id is not None:
            return await self._get_playlist(playlist_id)

        # Fallback: extract UUIDs and fetch each presentation
        logger.debug("No playlist found, falling back to individual fetches")
        presentation_ids = parse_presentation_ids_from_html(html)
        presentations = []
        for pid in presentation_ids:
            try:
                presentations.append(await self.get_presentation(pid))
            except (NetworkError, ParseError) as e:
                logger.warning(f"Failed to fetch presentation {pid}: {e}")

        return presentations

    async def get_presentation(self, presentation_id: str) -> Presentation:
        """Get full presentation details including video sources and subtitles.

        Args:
            presentation_id: Presentation UUID

        Returns:
            Presentation object with sources, subtitles, and token

        Raises:
            NetworkError: If the request fails
            ParseError: If parsing fails
        """
        await self._ensure_authenticated()

        url = f"{self.base_url}/presentation/{presentation_id}"
        logger.debug(f"Fetching presentation from {url}")

        try:
            response = await self._client.get(url, timeout=30)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise NetworkError(f"Failed to fetch presentation: {e}") from e

        return parse_presentation_json(response.json())

    async def get_transcript(self, presentation_id: str) -> list[TranscriptCue]:
        """Get the transcript (parsed VTT subtitles) for a presentation.

        Args:
            presentation_id: Presentation UUID

        Returns:
            List of TranscriptCue objects with timestamps and text

        Raises:
            NetworkError: If the request fails
            ParseError: If the VTT content is invalid or no subtitles available
        """
        presentation = await self.get_presentation(presentation_id)

        if not presentation.subtitles:
            raise ParseError(f"Presentation {presentation_id} has no subtitles")

        label = next(iter(presentation.subtitles))
        vtt_url = presentation.subtitles[label]
        token = presentation.token

        logger.debug(f"Fetching VTT from {vtt_url}")

        try:
            response = await self._client.get(vtt_url, params={"token": token}, timeout=30)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise NetworkError(f"Failed to fetch VTT subtitles: {e}") from e

        if response.text.strip() == "Unauthorized":
            raise NetworkError("Failed to fetch VTT: unauthorized (token may be expired)")

        return parse_vtt(response.text)

    async def get_transcript_text(self, presentation_id: str) -> str:
        """Get the transcript as plain text.

        Args:
            presentation_id: Presentation UUID

        Returns:
            Plain text transcript with cues joined by spaces

        Raises:
            NetworkError: If the request fails
            ParseError: If the VTT content is invalid or no subtitles available
        """
        cues = await self.get_transcript(presentation_id)
        return " ".join(cue.text for cue in cues)

    async def _get_playlist(self, playlist_id: int) -> list[Presentation]:
        """Fetch playlist and return as Presentation list.

        Args:
            playlist_id: Playlist ID

        Returns:
            List of lightweight Presentation objects
        """
        url = f"{self.base_url}/playlist/{playlist_id}"
        logger.debug(f"Fetching playlist from {url}")

        try:
            response = await self._client.get(url, timeout=30)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise NetworkError(f"Failed to fetch playlist: {e}") from e

        return parse_playlist_json(response.json())
