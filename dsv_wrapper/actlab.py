"""ACT Lab client for digital signage management."""

import logging
import os
from pathlib import Path

import httpx

from .auth import AsyncShibbolethAuth, ShibbolethAuth
from .auth.cache_backend import CacheBackend
from .exceptions import AuthenticationError
from .models.actlab import Slide, SlideUploadResult
from .parsers.actlab import (
    SlideUploadError,
    find_newest_slide_id,
    parse_show_slides,
    parse_slides,
    parse_upload_form,
)
from .utils import DEFAULT_HEADERS

logger = logging.getLogger(__name__)

ACTLAB_BASE_URL = "https://www2.dsv.su.se/act-lab/admin/"


class ACTLabClient:
    """Synchronous client for ACT Lab digital signage system."""

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        cache_backend: CacheBackend | None = None,
        cache_ttl: int = 86400,
    ):
        """Initialize ACT Lab client.

        Args:
            username: SU username (default: read from SU_USERNAME env var)
            password: SU password (default: read from SU_PASSWORD env var)
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

        self.auth = ShibbolethAuth(
            self.username, self.password, cache_backend=cache_backend, cache_ttl=cache_ttl
        )
        self._client = httpx.Client(headers=DEFAULT_HEADERS)
        self._authenticated = False

        logger.debug(f"Initialized ACTLabClient for user: {self.username}")

    def _ensure_authenticated(self) -> None:
        """Ensure the client is authenticated."""
        if not self._authenticated:
            logger.info("Authenticating to ACT Lab admin")
            cookies = self.auth._login(service="actlab")
            self._client.cookies.update(cookies)
            self._authenticated = True
            logger.info("Successfully authenticated to ACT Lab")

    def upload_slide(
        self,
        file_path: str | Path,
        slide_name: str = "ACT Lab Slide",
    ) -> SlideUploadResult:
        """Upload a slide image to ACT Lab.

        Args:
            file_path: Path to image file (PNG recommended)
            slide_name: Name for the slide

        Returns:
            SlideUploadResult with upload status

        Raises:
            SlideUploadError: If upload fails
        """
        self._ensure_authenticated()

        file_path = Path(file_path)
        if not file_path.exists():
            raise SlideUploadError(f"File not found: {file_path}")

        logger.info(f"Uploading slide: {slide_name} from {file_path}")

        # Get the admin page to extract form action and MAX_FILE_SIZE
        response = self._client.get(ACTLAB_BASE_URL)
        response.raise_for_status()

        form_action_url, action_value, max_file_size = parse_upload_form(
            response.text, ACTLAB_BASE_URL
        )

        # Prepare upload data
        files = {"uploadfile": (file_path.name, open(file_path, "rb"), "image/png")}
        data = {
            "action": action_value,
            "filename": slide_name,
            "MAX_FILE_SIZE": max_file_size,
        }

        # Upload the file to the form's action URL
        logger.debug(f"Uploading file to {form_action_url} with MAX_FILE_SIZE={max_file_size}")
        response = self._client.post(form_action_url, files=files, data=data, follow_redirects=True)
        response.raise_for_status()

        # Get the new slide ID by fetching the page again and finding the max ID
        response = self._client.get(ACTLAB_BASE_URL)
        response.raise_for_status()

        slide_id = find_newest_slide_id(response.text)

        if not slide_id:
            logger.warning("Slide uploaded but could not extract ID")
            return SlideUploadResult(success=True, message="Upload successful but ID not found")

        logger.info(f"Slide uploaded successfully with ID: {slide_id}")
        return SlideUploadResult(success=True, slide_id=slide_id, message="Upload successful")

    def _configure_slide(
        self,
        slide_id: str,
        show_id: str = "1",
        auto_delete: bool = True,
        start_time: str = "",
        end_time: str = "",
    ) -> bool:
        """Configure slide settings.

        Args:
            slide_id: Slide ID
            show_id: Show ID (default: 1 for Labbet)
            auto_delete: Enable auto-delete
            start_time: Start time for display
            end_time: End time for display

        Returns:
            True if configuration successful
        """
        logger.debug(f"Configuring slide {slide_id} with auto_delete={auto_delete}")

        data = {
            "action": "configure_slide",
            "showid": show_id,
            "slideid": slide_id,
            "starttime": start_time,
            "endtime": end_time,
        }

        if auto_delete:
            data["autodelete"] = "on"

        # POST to action.php, not the base URL
        action_url = ACTLAB_BASE_URL.rstrip("/") + "/action.php"
        response = self._client.post(action_url, data=data, follow_redirects=True)
        response.raise_for_status()

        logger.debug(f"Slide {slide_id} configured successfully")
        return True

    def add_slide_to_show(
        self, slide_id: str, show_id: str = "1", auto_delete: bool = True
    ) -> bool:
        """Add a slide to a show.

        Args:
            slide_id: Slide ID
            show_id: Show ID (default: 1 for Labbet)
            auto_delete: Enable auto-delete when removed from show (default: True)

        Returns:
            True if successful
        """
        self._ensure_authenticated()

        logger.info(f"Adding slide {slide_id} to show {show_id}")

        data = {"action": "add_slide_to_show", "add": slide_id, "to": show_id}

        # POST to action.php, not the base URL
        action_url = ACTLAB_BASE_URL.rstrip("/") + "/action.php"
        response = self._client.post(action_url, data=data, follow_redirects=True)
        response.raise_for_status()

        logger.info(f"Slide {slide_id} added to show {show_id}")

        # Configure auto-delete after adding to show
        if auto_delete:
            self._configure_slide(slide_id, show_id, auto_delete=True)

        return True

    def remove_slide_from_show(self, slide_id: str, show_id: str = "1") -> bool:
        """Remove a slide from a show.

        Args:
            slide_id: Slide ID
            show_id: Show ID (default: 1 for Labbet)

        Returns:
            True if successful
        """
        self._ensure_authenticated()

        logger.info(f"Removing slide {slide_id} from show {show_id}")

        data = {"action": "remove", "remove": slide_id, "from": show_id}

        # POST to action.php, not the base URL
        action_url = ACTLAB_BASE_URL.rstrip("/") + "/action.php"
        response = self._client.post(action_url, data=data, follow_redirects=True)
        response.raise_for_status()

        logger.info(f"Slide {slide_id} removed from show {show_id}")
        return True

    def get_slides(self) -> list[Slide]:
        """Get list of all available slides.

        Returns:
            List of Slide objects
        """
        self._ensure_authenticated()

        logger.debug("Fetching slides list")

        response = self._client.get(ACTLAB_BASE_URL)
        response.raise_for_status()

        slides = parse_slides(response.text)
        logger.info(f"Found {len(slides)} slides")
        return slides

    def cleanup_old_slides(self, show_id: str = "1", keep_latest: int = 1) -> int:
        """Remove old slides from a show, keeping only the latest N.

        Args:
            show_id: Show ID (default: 1 for Labbet)
            keep_latest: Number of latest slides to keep

        Returns:
            Number of slides removed
        """
        self._ensure_authenticated()

        logger.info(f"Cleaning up slides in show {show_id}, keeping latest {keep_latest}")

        response = self._client.get(ACTLAB_BASE_URL)
        response.raise_for_status()

        slide_ids = parse_show_slides(response.text, show_id)

        if not slide_ids:
            logger.warning(f"Show {show_id} not found or has no slides")
            return 0

        # Remove all but the latest N slides
        if len(slide_ids) > keep_latest:
            slides_to_remove = slide_ids[:-keep_latest]
            logger.info(f"Removing {len(slides_to_remove)} old slides")

            for slide_id in slides_to_remove:
                self.remove_slide_from_show(slide_id, show_id)

            return len(slides_to_remove)

        logger.info("No slides to remove")
        return 0

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


class AsyncACTLabClient:
    """Asynchronous client for ACT Lab digital signage system."""

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        cache_backend: CacheBackend | None = None,
        cache_ttl: int = 86400,
    ):
        """Initialize async ACT Lab client.

        Args:
            username: SU username (default: read from SU_USERNAME env var)
            password: SU password (default: read from SU_PASSWORD env var)
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

        self.auth = AsyncShibbolethAuth(
            self.username, self.password, cache_backend=cache_backend, cache_ttl=cache_ttl
        )
        self._client: httpx.AsyncClient | None = None
        self._authenticated = False

        logger.debug(f"Initialized AsyncACTLabClient for user: {self.username}")

    async def __aenter__(self):
        """Async context manager entry."""
        await self.auth.__aenter__()
        self._client = httpx.AsyncClient(headers=DEFAULT_HEADERS)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
        await self.auth.__aexit__(exc_type, exc_val, exc_tb)

    async def _ensure_authenticated(self) -> None:
        """Ensure the client is authenticated."""
        if not self._authenticated:
            logger.info("Authenticating to ACT Lab admin")
            await self.auth.login(service="actlab")
            # Copy cookies from auth client to this client (preserve domain/path)
            for cookie in self.auth._sync_auth._client.cookies.jar:
                self._client.cookies.set(
                    cookie.name, cookie.value, domain=cookie.domain, path=cookie.path
                )
            self._authenticated = True
            logger.info("Successfully authenticated to ACT Lab")

    async def get_slides(self) -> list[Slide]:
        """Get list of all available slides.

        Returns:
            List of Slide objects
        """
        await self._ensure_authenticated()

        logger.debug("Fetching slides list")

        response = await self._client.get(ACTLAB_BASE_URL)
        response.raise_for_status()

        slides = parse_slides(response.text)
        logger.info(f"Found {len(slides)} slides")
        return slides

    async def _configure_slide(
        self,
        slide_id: str,
        show_id: str = "1",
        auto_delete: bool = True,
        start_time: str = "",
        end_time: str = "",
    ) -> bool:
        """Configure slide settings.

        Args:
            slide_id: Slide ID
            show_id: Show ID (default: 1 for Labbet)
            auto_delete: Enable auto-delete
            start_time: Start time for display
            end_time: End time for display

        Returns:
            True if configuration successful
        """
        logger.debug(f"Configuring slide {slide_id} with auto_delete={auto_delete}")

        data = {
            "action": "configure_slide",
            "showid": show_id,
            "slideid": slide_id,
            "starttime": start_time,
            "endtime": end_time,
        }

        if auto_delete:
            data["autodelete"] = "on"

        # POST to action.php, not the base URL
        action_url = ACTLAB_BASE_URL.rstrip("/") + "/action.php"
        response = await self._client.post(action_url, data=data, follow_redirects=True)
        response.raise_for_status()

        logger.debug(f"Slide {slide_id} configured successfully")
        return True

    async def add_slide_to_show(
        self, slide_id: str, show_id: str = "1", auto_delete: bool = True
    ) -> bool:
        """Add a slide to a show.

        Args:
            slide_id: Slide ID
            show_id: Show ID (default: 1 for Labbet)
            auto_delete: Enable auto-delete when removed from show (default: True)

        Returns:
            True if successful
        """
        await self._ensure_authenticated()

        logger.info(f"Adding slide {slide_id} to show {show_id}")

        data = {"action": "add_slide_to_show", "add": slide_id, "to": show_id}

        # POST to action.php, not the base URL
        action_url = ACTLAB_BASE_URL.rstrip("/") + "/action.php"
        response = await self._client.post(action_url, data=data, follow_redirects=True)
        response.raise_for_status()

        logger.info(f"Slide {slide_id} added to show {show_id}")

        # Configure auto-delete after adding to show
        if auto_delete:
            await self._configure_slide(slide_id, show_id, auto_delete=True)

        return True

    async def remove_slide_from_show(self, slide_id: str, show_id: str = "1") -> bool:
        """Remove a slide from a show.

        Args:
            slide_id: Slide ID
            show_id: Show ID (default: 1 for Labbet)

        Returns:
            True if successful
        """
        await self._ensure_authenticated()

        logger.info(f"Removing slide {slide_id} from show {show_id}")

        data = {"action": "remove", "remove": slide_id, "from": show_id}

        # POST to action.php, not the base URL
        action_url = ACTLAB_BASE_URL.rstrip("/") + "/action.php"
        response = await self._client.post(action_url, data=data, follow_redirects=True)
        response.raise_for_status()

        logger.info(f"Slide {slide_id} removed from show {show_id}")
        return True

    async def upload_slide(
        self,
        file_path: str | Path,
        slide_name: str = "ACT Lab Slide",
    ) -> SlideUploadResult:
        """Upload a slide image to ACT Lab.

        Args:
            file_path: Path to image file (PNG recommended)
            slide_name: Name for the slide

        Returns:
            SlideUploadResult with upload status

        Raises:
            SlideUploadError: If upload fails
        """
        await self._ensure_authenticated()

        file_path = Path(file_path)
        if not file_path.exists():
            raise SlideUploadError(f"File not found: {file_path}")

        logger.info(f"Uploading slide: {slide_name} from {file_path}")

        # Get the admin page to extract form action and MAX_FILE_SIZE
        response = await self._client.get(ACTLAB_BASE_URL)
        response.raise_for_status()

        form_action_url, action_value, max_file_size = parse_upload_form(
            response.text, ACTLAB_BASE_URL
        )

        # Prepare upload data
        files = {"uploadfile": (file_path.name, open(file_path, "rb"), "image/png")}
        data = {
            "action": action_value,
            "filename": slide_name,
            "MAX_FILE_SIZE": max_file_size,
        }

        # Upload the file to the form's action URL
        logger.debug(f"Uploading file to {form_action_url} with MAX_FILE_SIZE={max_file_size}")
        response = await self._client.post(
            form_action_url, files=files, data=data, follow_redirects=True
        )
        response.raise_for_status()

        # Get the new slide ID by fetching the page again and finding the max ID
        response = await self._client.get(ACTLAB_BASE_URL)
        response.raise_for_status()

        slide_id = find_newest_slide_id(response.text)

        if not slide_id:
            logger.warning("Slide uploaded but could not extract ID")
            return SlideUploadResult(success=True, message="Upload successful but ID not found")

        logger.info(f"Slide uploaded successfully with ID: {slide_id}")
        return SlideUploadResult(success=True, slide_id=slide_id, message="Upload successful")

    async def cleanup_old_slides(self, show_id: str = "1", keep_latest: int = 1) -> int:
        """Remove old slides from a show, keeping only the latest N.

        Args:
            show_id: Show ID (default: 1 for Labbet)
            keep_latest: Number of latest slides to keep

        Returns:
            Number of slides removed
        """
        await self._ensure_authenticated()

        logger.info(f"Cleaning up slides in show {show_id}, keeping latest {keep_latest}")

        response = await self._client.get(ACTLAB_BASE_URL)
        response.raise_for_status()

        slide_ids = parse_show_slides(response.text, show_id)

        if not slide_ids:
            logger.warning(f"Show {show_id} not found or has no slides")
            return 0

        # Remove all but the latest N slides
        if len(slide_ids) > keep_latest:
            slides_to_remove = slide_ids[:-keep_latest]
            logger.info(f"Removing {len(slides_to_remove)} old slides")

            for slide_id in slides_to_remove:
                await self.remove_slide_from_show(slide_id, show_id)

            return len(slides_to_remove)

        logger.info("No slides to remove")
        return 0
