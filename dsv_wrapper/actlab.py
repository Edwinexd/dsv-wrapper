"""ACT Lab client for digital signage management."""

import logging
import os
import re
from pathlib import Path
from typing import Optional

import aiohttp
import requests

from .auth import AsyncShibbolethAuth, ShibbolethAuth
from .auth.cache_backend import CacheBackend
from .base import BaseAsyncClient
from .exceptions import AuthenticationError, DSVWrapperError
from .models.actlab import Show, Slide, SlideUploadResult
from .utils import DEFAULT_HEADERS, extract_attr, extract_text, parse_html

logger = logging.getLogger(__name__)

ACTLAB_BASE_URL = "https://www2.dsv.su.se/act-lab/admin/"


class ACTLabError(DSVWrapperError):
    """Base exception for ACT Lab errors."""

    pass


class SlideUploadError(ACTLabError):
    """Raised when slide upload fails."""

    pass


class ACTLabClient:
    """Synchronous client for ACT Lab digital signage system."""

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        cache_backend: Optional[CacheBackend] = None,
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

        self.auth = ShibbolethAuth(self.username, self.password, cache_backend=cache_backend, cache_ttl=cache_ttl)
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self._authenticated = False

        logger.debug(f"Initialized ACTLabClient for user: {self.username}")

    def _ensure_authenticated(self) -> None:
        """Ensure the client is authenticated."""
        if not self._authenticated:
            logger.info("Authenticating to ACT Lab admin")
            cookies = self.auth._login(service="actlab")
            self.session.cookies.update(cookies)
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
        response = self.session.get(ACTLAB_BASE_URL)
        response.raise_for_status()

        soup = parse_html(response.text)

        # Find upload form
        upload_form = soup.find("form", {"enctype": "multipart/form-data"})
        if not upload_form:
            raise SlideUploadError("Could not find upload form")

        # Get the form action URL (where to POST to)
        form_action_url = extract_attr(upload_form, "action") or ""
        if not form_action_url.startswith("http"):
            # Relative URL, make it absolute
            form_action_url = ACTLAB_BASE_URL.rstrip("/") + "/" + form_action_url.lstrip("/")

        # Get the action value from hidden input (action parameter in POST data)
        action_input = upload_form.find("input", {"name": "action"})
        action_value = extract_attr(action_input, "value") or "upload_file"

        max_file_size_input = upload_form.find("input", {"name": "MAX_FILE_SIZE"})
        max_file_size = extract_attr(max_file_size_input, "value") or "10000000"

        # Prepare upload data
        files = {"uploadfile": (file_path.name, open(file_path, "rb"), "image/png")}
        data = {
            "action": action_value,
            "filename": slide_name,
            "MAX_FILE_SIZE": max_file_size,
        }

        # Upload the file to the form's action URL
        logger.debug(f"Uploading file to {form_action_url} with MAX_FILE_SIZE={max_file_size}")
        response = self.session.post(form_action_url, files=files, data=data, allow_redirects=True)
        response.raise_for_status()

        # Get the new slide ID by fetching the page again and finding the max ID
        response = self.session.get(ACTLAB_BASE_URL)
        response.raise_for_status()

        # Find all slide IDs and get the maximum (newest upload)
        all_slide_ids = re.findall(r'<div class="slide"\s+id="(\d+)"', response.text)

        if not all_slide_ids:
            logger.warning("Slide uploaded but could not extract ID")
            return SlideUploadResult(success=True, message="Upload successful but ID not found")

        slide_id = max(all_slide_ids, key=int)
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
        response = self.session.post(action_url, data=data, allow_redirects=True)
        response.raise_for_status()

        logger.debug(f"Slide {slide_id} configured successfully")
        return True

    def add_slide_to_show(self, slide_id: str, show_id: str = "1", auto_delete: bool = True) -> bool:
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
        response = self.session.post(action_url, data=data, allow_redirects=True)
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
        response = self.session.post(action_url, data=data, allow_redirects=True)
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

        response = self.session.get(ACTLAB_BASE_URL)
        response.raise_for_status()

        soup = parse_html(response.text)
        slides = []

        slide_divs = soup.find_all("div", class_="slide")
        for slide_div in slide_divs:
            # Slide IDs are just numbers, not "slideXX"
            slide_id = extract_attr(slide_div, "id", "")

            if slide_id and slide_id.isdigit():
                name_elem = slide_div.find(class_="slide-name")
                name = extract_text(name_elem) if name_elem else f"Slide {slide_id}"

                slides.append(Slide(id=slide_id, name=name))

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

        response = self.session.get(ACTLAB_BASE_URL)
        response.raise_for_status()

        soup = parse_html(response.text)

        # Find the show div (show IDs are just numbers, not "showXX")
        show_div = soup.find("div", {"id": show_id, "class": "show"})
        if not show_div:
            logger.warning(f"Show {show_id} not found")
            return 0

        # Get all slides in the show
        slide_divs = show_div.find_all("div", class_="slide")
        slide_ids = []

        for slide_div in slide_divs:
            # Slide IDs are just numbers, not "slideXX"
            id_attr = extract_attr(slide_div, "id", "")
            if id_attr and id_attr.isdigit():
                slide_ids.append(id_attr)

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
        self.session.close()
        self.auth.__exit__(None, None, None)

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


class AsyncACTLabClient(BaseAsyncClient):
    """Asynchronous client for ACT Lab digital signage system."""

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        cache_backend: Optional[CacheBackend] = None,
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
        username = username or os.environ.get("SU_USERNAME")
        password = password or os.environ.get("SU_PASSWORD")

        if not username or not password:
            raise AuthenticationError(
                "Username and password must be provided either as arguments or "
                "via SU_USERNAME and SU_PASSWORD environment variables"
            )

        super().__init__(
            username=username,
            password=password,
            base_url=ACTLAB_BASE_URL,
            service="actlab",
            cache_backend=cache_backend,
            cache_ttl=cache_ttl,
        )
        logger.debug(f"Initialized AsyncACTLabClient for user: {username}")

    async def get_slides(self) -> list[Slide]:
        """Get list of all available slides.

        Returns:
            List of Slide objects
        """
        await self._ensure_authenticated()

        logger.debug("Fetching slides list")

        async with self.session.get(ACTLAB_BASE_URL) as response:
            response.raise_for_status()
            html = await response.text()

        soup = parse_html(html)
        slides = []

        slide_divs = soup.find_all("div", class_="slide")
        for slide_div in slide_divs:
            # Slide IDs are just numbers, not "slideXX"
            slide_id = extract_attr(slide_div, "id", "")

            if slide_id and slide_id.isdigit():
                name_elem = slide_div.find(class_="slide-name")
                name = extract_text(name_elem) if name_elem else f"Slide {slide_id}"

                slides.append(Slide(id=slide_id, name=name))

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
        async with self.session.post(action_url, data=data, allow_redirects=True) as response:
            response.raise_for_status()

        logger.debug(f"Slide {slide_id} configured successfully")
        return True

    async def add_slide_to_show(self, slide_id: str, show_id: str = "1", auto_delete: bool = True) -> bool:
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
        async with self.session.post(action_url, data=data, allow_redirects=True) as response:
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
        async with self.session.post(action_url, data=data, allow_redirects=True) as response:
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
        async with self.session.get(ACTLAB_BASE_URL) as response:
            response.raise_for_status()
            html = await response.text()

        soup = parse_html(html)

        # Find upload form
        upload_form = soup.find("form", {"enctype": "multipart/form-data"})
        if not upload_form:
            raise SlideUploadError("Could not find upload form")

        # Get the form action URL (where to POST to)
        form_action_url = extract_attr(upload_form, "action") or ""
        if not form_action_url.startswith("http"):
            # Relative URL, make it absolute
            form_action_url = ACTLAB_BASE_URL.rstrip("/") + "/" + form_action_url.lstrip("/")

        # Get the action value from hidden input (action parameter in POST data)
        action_input = upload_form.find("input", {"name": "action"})
        action_value = extract_attr(action_input, "value") or "upload_file"

        max_file_size_input = upload_form.find("input", {"name": "MAX_FILE_SIZE"})
        max_file_size = extract_attr(max_file_size_input, "value") or "10000000"

        # Prepare upload data
        form_data = aiohttp.FormData()
        form_data.add_field("action", action_value)
        form_data.add_field("filename", slide_name)
        form_data.add_field("MAX_FILE_SIZE", max_file_size)
        form_data.add_field(
            "uploadfile",
            open(file_path, "rb"),
            filename=file_path.name,
            content_type="image/png",
        )

        # Upload the file to the form's action URL
        logger.debug(f"Uploading file to {form_action_url} with MAX_FILE_SIZE={max_file_size}")
        async with self.session.post(form_action_url, data=form_data, allow_redirects=True) as response:
            response.raise_for_status()

        # Get the new slide ID by fetching the page again and finding the max ID
        async with self.session.get(ACTLAB_BASE_URL) as response:
            response.raise_for_status()
            html = await response.text()

        # Find all slide IDs and get the maximum (newest upload)
        all_slide_ids = re.findall(r'<div class="slide"\s+id="(\d+)"', html)

        if not all_slide_ids:
            logger.warning("Slide uploaded but could not extract ID")
            return SlideUploadResult(success=True, message="Upload successful but ID not found")

        slide_id = max(all_slide_ids, key=int)
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

        async with self.session.get(ACTLAB_BASE_URL) as response:
            response.raise_for_status()
            html = await response.text()

        soup = parse_html(html)

        # Find the show div (show IDs are just numbers, not "showXX")
        show_div = soup.find("div", {"id": show_id, "class": "show"})
        if not show_div:
            logger.warning(f"Show {show_id} not found")
            return 0

        # Get all slides in the show
        slide_divs = show_div.find_all("div", class_="slide")
        slide_ids = []

        for slide_div in slide_divs:
            # Slide IDs are just numbers, not "slideXX"
            id_attr = extract_attr(slide_div, "id", "")
            if id_attr and id_attr.isdigit():
                slide_ids.append(id_attr)

        # Remove all but the latest N slides
        if len(slide_ids) > keep_latest:
            slides_to_remove = slide_ids[:-keep_latest]
            logger.info(f"Removing {len(slides_to_remove)} old slides")

            for slide_id in slides_to_remove:
                await self.remove_slide_from_show(slide_id, show_id)

            return len(slides_to_remove)

        logger.info("No slides to remove")
        return 0
