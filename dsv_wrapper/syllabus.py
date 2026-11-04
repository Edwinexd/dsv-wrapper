"""Client for the public SU course syllabus archive (planarkiv).

Daisy's course pages link each offering to
``utbildning.su.se/utbildning/sok-i-planarkiv/planarkiv?code=...``, an HTML
page that renders its list of syllabus PDFs client-side. The data behind it
comes from a Sitevision web app endpoint that returns JSON; this client calls
that endpoint directly. No authentication is needed.

The endpoint path embeds Sitevision page and portlet ids. They are stable
across deploys but change if SU rebuilds the archive page, in which case
requests start failing with 404 and :data:`SYLLABUS_ENDPOINT` needs updating
from the ``registerApp({applicationId:'courseSyllabusArchive'...})`` call in
the page's HTML.
"""

import logging
from typing import Literal

import httpx

from .exceptions import SyllabusNotFoundError
from .models.syllabus import SyllabusArchiveEntry
from .parsers import syllabus as syllabus_parsers
from .retry import create_async_client, create_client

logger = logging.getLogger(__name__)

SYLLABUS_BASE_URL = "https://utbildning.su.se"
SYLLABUS_ENDPOINT = "/appresource/4.3c7ac109192bd29899b16517/12.3c7ac109192bd29899b166a3/syllabus"

Language = Literal["sv", "en"]


def _validate_language(language: str) -> None:
    if language not in ("sv", "en"):
        raise ValueError(f"Unsupported language: {language!r} (expected 'sv' or 'en')")


def _parse_response(response: httpx.Response, code: str) -> SyllabusArchiveEntry:
    # Unknown codes surface as a 500 wrapping the upstream 404.
    if response.status_code >= 400 and "not found" in response.text.lower():
        raise SyllabusNotFoundError(f"No syllabus archive entry for code {code!r}")
    response.raise_for_status()
    return syllabus_parsers.parse_syllabus_archive(response.json())


class SyllabusClient:
    """Synchronous client for the SU syllabus archive."""

    def __init__(self, base_url: str = SYLLABUS_BASE_URL):
        self.base_url = base_url
        self._client = create_client(follow_redirects=True)

    def get_syllabus_archive(self, code: str, *, language: Language = "sv") -> SyllabusArchiveEntry:
        """Fetch a course's archive entry with every published syllabus version.

        Args:
            code: Ladok course code, e.g. ``"IB440C"`` (see
                :attr:`~dsv_wrapper.models.daisy.SyllabusCourse.code`).
            language: ``"sv"`` lists the Swedish PDFs. ``"en"`` lists the
                English PDF for versions that have one and the Swedish PDF
                otherwise; check :attr:`SyllabusVersion.language`.

        Raises:
            ValueError: If ``language`` is unsupported.
            SyllabusNotFoundError: If the archive has no entry for ``code``.
            ParseError: If the response has an unexpected shape.
        """
        _validate_language(language)
        response = self._client.get(
            f"{self.base_url}{SYLLABUS_ENDPOINT}",
            params={"code": code, "languageCode": language},
            headers={"Accept": "application/json"},
            timeout=15,
        )
        return _parse_response(response, code)

    def close(self) -> None:
        """Close the client session."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class AsyncSyllabusClient:
    """Asynchronous client for the SU syllabus archive.

    Must be used as an async context manager.
    """

    def __init__(self, base_url: str = SYLLABUS_BASE_URL):
        self.base_url = base_url
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = create_async_client(follow_redirects=True)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()

    async def get_syllabus_archive(
        self, code: str, *, language: Language = "sv"
    ) -> SyllabusArchiveEntry:
        """Async version of :meth:`SyllabusClient.get_syllabus_archive`."""
        _validate_language(language)
        response = await self._client.get(
            f"{self.base_url}{SYLLABUS_ENDPOINT}",
            params={"code": code, "languageCode": language},
            headers={"Accept": "application/json"},
            timeout=15,
        )
        return _parse_response(response, code)
