"""Play client for DSVPlay presentation/video platform."""

import logging
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx

from .auth import AsyncShibbolethAuth, ShibbolethAuth
from .auth.cache_backend import CacheBackend
from .exceptions import (
    AuthenticationError,
    NetworkError,
    ParseError,
    TranscriptNotReadyError,
)
from .models.play import PlayCourse, Presentation, TrackInfo, TranscriptCue
from .parsers.play import (
    enumerate_track_descriptors,
    parse_courses_from_html,
    parse_courses_from_tag_html,
    parse_playlist_ids_from_html,
    parse_playlist_json,
    parse_presentation_ids_from_html,
    parse_presentation_json,
    parse_vtt,
)
from .utils import DEFAULT_HEADERS, DSV_URLS

# Streaming chunk size used for both downloads and range iteration. 1 MiB is
# large enough to amortise per-chunk Python overhead and small enough that an
# moov-atom probe (~2 MiB) costs at most a couple of chunks.
_TRACK_CHUNK_SIZE = 1024 * 1024


def _track_mime_type(url: str) -> str | None:
    """Derive a track's MIME type from its URL extension.

    The play-store CDN reports ``content-type: text/html`` on mp4 HEAD/GET
    responses, which is wrong, so we don't trust it and infer from the
    extension instead.
    """
    lowered = url.lower().split("?", 1)[0]
    if lowered.endswith(".mp4"):
        return "video/mp4"
    return None


def _build_range_header(start_byte: int, end_byte: int | None) -> str | None:
    """Build a ``Range`` header value, or ``None`` if no slicing is requested."""
    if start_byte == 0 and end_byte is None:
        return None
    if start_byte < 0:
        raise ValueError("start_byte must be non-negative")
    if end_byte is not None and end_byte < start_byte:
        raise ValueError("end_byte must be >= start_byte")
    end_part = "" if end_byte is None else str(end_byte)
    return f"bytes={start_byte}-{end_part}"


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

    def get_presentations(self, designation: str, terms: int | None = 1) -> list[Presentation]:
        """Get presentations for a course designation.

        Designations offered across multiple terms expose one playlist per
        term (most-recent first). By default only the current term's playlist
        is returned; pass ``terms=2`` to also include the previous term, or
        ``terms=None`` to aggregate every term.

        Args:
            designation: Course designation code (e.g., 'PROG1', 'IDSV')
            terms: Number of most-recent term playlists to include. Defaults
                to 1 (current term only). ``None`` means "all terms".

        Returns:
            List of lightweight Presentation objects (id, title, thumb_url),
            de-duplicated by id, in playlist order across the included terms.

        Raises:
            NetworkError: If the request fails
            ParseError: If parsing fails
            ValueError: If ``terms`` is not a positive integer or None
        """
        if terms is not None and terms < 1:
            raise ValueError("terms must be a positive integer or None")

        self._ensure_authenticated()

        url = f"{self.base_url}/designation/{designation}"
        logger.debug(f"Fetching presentations for {designation} from {url}")

        try:
            response = self._client.get(url, timeout=30)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise NetworkError(f"Failed to fetch designation page: {e}") from e

        html = response.text

        playlist_ids = parse_playlist_ids_from_html(html)
        if playlist_ids:
            selected = playlist_ids if terms is None else playlist_ids[:terms]
            seen: set[str] = set()
            presentations: list[Presentation] = []
            for pid in selected:
                for p in self._get_playlist(pid):
                    if p.id and p.id not in seen:
                        seen.add(p.id)
                        presentations.append(p)
            return presentations

        # Fallback: no playlists on the page (e.g. tag-only listing). Fetch
        # each presentation by UUID.
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
            TranscriptNotReadyError: If the recording exists but its transcript
                has not yet been generated. Callers should retry later. This
                is a subclass of ``ParseError`` for backwards compatibility.
            ParseError: If the VTT content is malformed
        """
        presentation = self.get_presentation(presentation_id)

        if not presentation.subtitles:
            raise TranscriptNotReadyError(
                f"Presentation {presentation_id} has no subtitles available "
                f"(is_video_ready={presentation.is_video_ready}); "
                "transcript may still be processing"
            )

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

    def get_media_tracks(self, presentation_uuid: str) -> list[TrackInfo]:
        """Enumerate mp4 tracks attached to a presentation.

        DSVPlay exposes one or more sources per presentation (e.g. ``main``,
        ``left``, ``right``, plus a ``Manual capture for ...`` composite),
        each encoded in 720p and 1080p. Every non-empty mp4 URL is surfaced
        as one ``TrackInfo``. The returned ``index`` is opaque and only
        meaningful when paired with the same ``presentation_uuid`` against
        :meth:`download_track` / :meth:`stream_track`; it must not be
        persisted across SSO sessions because the underlying URL embeds a
        short-lived JWT.

        ``size_bytes`` is populated by issuing one ``HEAD`` per track against
        ``play-store-prod.dsv.su.se``. ``mime_type`` is derived from the URL
        extension (the CDN itself misreports ``text/html`` for mp4 responses).
        ``height`` is taken from the encoded quality label (720/1080).
        ``width`` and ``duration_seconds`` are not published by the API and
        are returned as ``None``; callers that need them should probe the
        moov atom via :meth:`stream_track` with a small ``end_byte``.

        Args:
            presentation_uuid: Presentation UUID, as returned by
                :meth:`get_presentations`.

        Returns:
            Tracks in stable enumeration order, never containing URLs.

        Raises:
            NetworkError: If the presentation envelope or HEAD probe fails.
            ParseError: If the presentation envelope is malformed.
        """
        presentation = self.get_presentation(presentation_uuid)
        descriptors = enumerate_track_descriptors(presentation)

        tracks: list[TrackInfo] = []
        for index, (url, _source_name, height) in enumerate(descriptors):
            size_bytes = self._head_track_size(url, presentation.token)
            tracks.append(
                TrackInfo(
                    index=index,
                    duration_seconds=None,
                    width=None,
                    height=height,
                    size_bytes=size_bytes,
                    mime_type=_track_mime_type(url),
                )
            )
        return tracks

    def download_track(
        self,
        presentation_uuid: str,
        track_index: int,
        dest_path: "str | os.PathLike[str]",
    ) -> None:
        """Stream a track to disk via the existing SSO session.

        Writes are chunked at ~1 MiB so multi-GB recordings don't sit in
        memory. The destination file is opened in binary write mode and
        truncated; the parent directory must already exist.

        Args:
            presentation_uuid: Presentation UUID.
            track_index: Track index returned by :meth:`get_media_tracks`.
            dest_path: Local path to write the mp4 bytes to.

        Raises:
            NetworkError: If the presentation envelope or download fails.
            ValueError: If ``track_index`` is out of range.
            ParseError: If the presentation envelope is malformed.
        """
        url, token = self._resolve_track(presentation_uuid, track_index)

        dest = Path(dest_path)
        try:
            with self._client.stream("GET", url, params={"token": token}, timeout=None) as response:
                response.raise_for_status()
                with dest.open("wb") as f:
                    for chunk in response.iter_bytes(chunk_size=_TRACK_CHUNK_SIZE):
                        f.write(chunk)
        except httpx.HTTPError as e:
            raise NetworkError(f"Failed to download track {track_index}: {e}") from e

    def stream_track(
        self,
        presentation_uuid: str,
        track_index: int,
        *,
        start_byte: int = 0,
        end_byte: int | None = None,
    ) -> Iterator[bytes]:
        """Iterate over the bytes of a track, optionally as an HTTP byte range.

        The play-store-prod CDN honours ``Range:`` headers and returns
        ``206 Partial Content`` (verified against three real presentations on
        2026-05-06), so callers can do cheap moov-atom probes with
        ``end_byte`` set to a small value (~2 MiB) instead of paying for the
        full multi-GB download during track selection.

        ``start_byte`` defaults to 0 and ``end_byte`` to ``None`` (open-ended
        — i.e. the rest of the file). Both are inclusive byte offsets, matching
        the HTTP Range spec.

        Args:
            presentation_uuid: Presentation UUID.
            track_index: Track index returned by :meth:`get_media_tracks`.
            start_byte: Inclusive starting offset. Default 0.
            end_byte: Inclusive ending offset, or ``None`` for "to end".

        Yields:
            Successive ``bytes`` chunks of the requested slice.

        Raises:
            NetworkError: If the presentation envelope or stream fails.
            ValueError: If ``track_index`` is out of range or the byte
                offsets are invalid.
            ParseError: If the presentation envelope is malformed.
        """
        url, token = self._resolve_track(presentation_uuid, track_index)
        range_header = _build_range_header(start_byte, end_byte)
        headers = {"Range": range_header} if range_header else {}

        try:
            with self._client.stream(
                "GET",
                url,
                params={"token": token},
                headers=headers,
                timeout=None,
            ) as response:
                response.raise_for_status()
                yield from response.iter_bytes(chunk_size=_TRACK_CHUNK_SIZE)
        except httpx.HTTPError as e:
            raise NetworkError(f"Failed to stream track {track_index}: {e}") from e

    def _resolve_track(self, presentation_uuid: str, track_index: int) -> tuple[str, str]:
        """Look up the URL and JWT token for a track index, freshly each call.

        The token is short-lived, so we always re-fetch the presentation
        envelope rather than caching descriptors across calls.
        """
        presentation = self.get_presentation(presentation_uuid)
        descriptors = enumerate_track_descriptors(presentation)
        if track_index < 0 or track_index >= len(descriptors):
            raise ValueError(
                f"track_index {track_index} out of range "
                f"(presentation has {len(descriptors)} track(s))"
            )
        url = descriptors[track_index][0]
        return url, presentation.token

    def _head_track_size(self, url: str, token: str) -> int | None:
        """HEAD a track URL and return its content-length, or None if absent."""
        self._ensure_authenticated()
        try:
            response = self._client.head(url, params={"token": token}, timeout=30)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise NetworkError(f"Failed to probe track size: {e}") from e

        length = response.headers.get("content-length")
        if length is None:
            return None
        try:
            return int(length)
        except ValueError:
            return None

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

    async def get_presentations(
        self, designation: str, terms: int | None = 1
    ) -> list[Presentation]:
        """Get presentations for a course designation.

        See :meth:`PlayClient.get_presentations` for semantics.

        Args:
            designation: Course designation code (e.g., 'PROG1', 'IDSV')
            terms: Number of most-recent term playlists to include. Defaults
                to 1 (current term only). ``None`` means "all terms".

        Returns:
            List of lightweight Presentation objects, deduplicated by id.

        Raises:
            NetworkError: If the request fails
            ParseError: If parsing fails
            ValueError: If ``terms`` is not a positive integer or None
        """
        if terms is not None and terms < 1:
            raise ValueError("terms must be a positive integer or None")

        await self._ensure_authenticated()

        url = f"{self.base_url}/designation/{designation}"
        logger.debug(f"Fetching presentations for {designation} from {url}")

        try:
            response = await self._client.get(url, timeout=30)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise NetworkError(f"Failed to fetch designation page: {e}") from e

        html = response.text

        playlist_ids = parse_playlist_ids_from_html(html)
        if playlist_ids:
            selected = playlist_ids if terms is None else playlist_ids[:terms]
            seen: set[str] = set()
            presentations: list[Presentation] = []
            for pid in selected:
                for p in await self._get_playlist(pid):
                    if p.id and p.id not in seen:
                        seen.add(p.id)
                        presentations.append(p)
            return presentations

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
            TranscriptNotReadyError: If the recording exists but its transcript
                has not yet been generated. Callers should retry later. This
                is a subclass of ``ParseError`` for backwards compatibility.
            ParseError: If the VTT content is malformed
        """
        presentation = await self.get_presentation(presentation_id)

        if not presentation.subtitles:
            raise TranscriptNotReadyError(
                f"Presentation {presentation_id} has no subtitles available "
                f"(is_video_ready={presentation.is_video_ready}); "
                "transcript may still be processing"
            )

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

    async def get_media_tracks(self, presentation_uuid: str) -> list[TrackInfo]:
        """Async counterpart of :meth:`PlayClient.get_media_tracks`.

        See that method for the full contract. ``size_bytes`` is populated by
        sequential ``HEAD`` requests; we don't fan out in parallel because
        the project's stated scope is "no parallelism beyond what the client
        already does".
        """
        presentation = await self.get_presentation(presentation_uuid)
        descriptors = enumerate_track_descriptors(presentation)

        tracks: list[TrackInfo] = []
        for index, (url, _source_name, height) in enumerate(descriptors):
            size_bytes = await self._head_track_size(url, presentation.token)
            tracks.append(
                TrackInfo(
                    index=index,
                    duration_seconds=None,
                    width=None,
                    height=height,
                    size_bytes=size_bytes,
                    mime_type=_track_mime_type(url),
                )
            )
        return tracks

    async def download_track(
        self,
        presentation_uuid: str,
        track_index: int,
        dest_path: "str | os.PathLike[str]",
    ) -> None:
        """Async counterpart of :meth:`PlayClient.download_track`.

        See that method for the full contract.
        """
        url, token = await self._resolve_track(presentation_uuid, track_index)

        dest = Path(dest_path)
        try:
            async with self._client.stream(
                "GET", url, params={"token": token}, timeout=None
            ) as response:
                response.raise_for_status()
                with dest.open("wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=_TRACK_CHUNK_SIZE):
                        f.write(chunk)
        except httpx.HTTPError as e:
            raise NetworkError(f"Failed to download track {track_index}: {e}") from e

    async def stream_track(
        self,
        presentation_uuid: str,
        track_index: int,
        *,
        start_byte: int = 0,
        end_byte: int | None = None,
    ) -> AsyncIterator[bytes]:
        """Async counterpart of :meth:`PlayClient.stream_track`.

        See that method for the full contract, including notes on Range
        support against play-store-prod.dsv.su.se.
        """
        url, token = await self._resolve_track(presentation_uuid, track_index)
        range_header = _build_range_header(start_byte, end_byte)
        headers = {"Range": range_header} if range_header else {}

        try:
            async with self._client.stream(
                "GET",
                url,
                params={"token": token},
                headers=headers,
                timeout=None,
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes(chunk_size=_TRACK_CHUNK_SIZE):
                    yield chunk
        except httpx.HTTPError as e:
            raise NetworkError(f"Failed to stream track {track_index}: {e}") from e

    async def _resolve_track(self, presentation_uuid: str, track_index: int) -> tuple[str, str]:
        """Async counterpart of :meth:`PlayClient._resolve_track`."""
        presentation = await self.get_presentation(presentation_uuid)
        descriptors = enumerate_track_descriptors(presentation)
        if track_index < 0 or track_index >= len(descriptors):
            raise ValueError(
                f"track_index {track_index} out of range "
                f"(presentation has {len(descriptors)} track(s))"
            )
        url = descriptors[track_index][0]
        return url, presentation.token

    async def _head_track_size(self, url: str, token: str) -> int | None:
        """HEAD a track URL and return its content-length, or None if absent."""
        await self._ensure_authenticated()
        try:
            response = await self._client.head(url, params={"token": token}, timeout=30)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise NetworkError(f"Failed to probe track size: {e}") from e

        length = response.headers.get("content-length")
        if length is None:
            return None
        try:
            return int(length)
        except ValueError:
            return None

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
