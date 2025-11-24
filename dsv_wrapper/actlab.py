"""ACT Lab client for digital signage management."""

import logging
import os
import re
from pathlib import Path
from typing import Optional

import aiohttp
import requests

from .auth import AsyncShibbolethAuth, ShibbolethAuth
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
        use_cache: bool = False,
    ):
        """Initialize ACT Lab client.

        Args:
            username: SU username (default: read from SU_USERNAME env var)
            password: SU password (default: read from SU_PASSWORD env var)
            use_cache: Whether to cache authentication cookies

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

        self.auth = ShibbolethAuth(self.username, self.password, use_cache=use_cache)
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self._authenticated = False

        logger.debug(f"Initialized ACTLabClient for user: {self.username}")

    def _ensure_authenticated(self) -> None:
        """Ensure the client is authenticated."""
        if not self._authenticated:
            logger.info("Authenticating to ACT Lab admin")
            cookies = self.auth.login(service="unified")
            self.session.cookies.update(cookies)
            self._authenticated = True
            logger.info("Successfully authenticated to ACT Lab")

    def upload_slide(
        self,
        file_path: str | Path,
        slide_name: str = "ACT Lab Slide",
        auto_delete: bool = True,
    ) -> SlideUploadResult:
        """Upload a slide image to ACT Lab.

        Args:
            file_path: Path to image file (PNG recommended)
            slide_name: Name for the slide
            auto_delete: Enable auto-delete when removed from show

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

        form_action = extract_attr(upload_form, "action") or ""
        max_file_size_input = upload_form.find("input", {"name": "MAX_FILE_SIZE"})
        max_file_size = extract_attr(max_file_size_input, "value") or "10000000"

        # Prepare upload data
        files = {"uploadfile": (file_path.name, open(file_path, "rb"), "image/png")}
        data = {
            "action": form_action,
            "filename": slide_name,
            "MAX_FILE_SIZE": max_file_size,
        }

        # Upload the file
        logger.debug(f"Uploading file with MAX_FILE_SIZE={max_file_size}")
        response = self.session.post(ACTLAB_BASE_URL, files=files, data=data)
        response.raise_for_status()

        # Parse response to get slide ID
        soup = parse_html(response.text)
        slides = soup.find_all("div", class_="slide")

        # Find the newly uploaded slide (usually the last one with matching name)
        slide_id = None
        for slide_div in reversed(slides):
            slide_id_match = re.search(r"slide(\d+)", extract_attr(slide_div, "id", ""))
            if slide_id_match:
                slide_id = slide_id_match.group(1)
                logger.info(f"Slide uploaded successfully with ID: {slide_id}")
                break

        if not slide_id:
            logger.warning("Slide uploaded but could not extract ID")
            return SlideUploadResult(success=True, message="Upload successful but ID not found")

        # Configure auto-delete if requested
        if auto_delete:
            self._configure_slide(slide_id, auto_delete=True)

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

        response = self.session.post(ACTLAB_BASE_URL, data=data)
        response.raise_for_status()

        logger.debug(f"Slide {slide_id} configured successfully")
        return True

    def add_slide_to_show(self, slide_id: str, show_id: str = "1") -> bool:
        """Add a slide to a show.

        Args:
            slide_id: Slide ID
            show_id: Show ID (default: 1 for Labbet)

        Returns:
            True if successful
        """
        self._ensure_authenticated()

        logger.info(f"Adding slide {slide_id} to show {show_id}")

        data = {"action": "add", "add": slide_id, "to": show_id}

        response = self.session.post(ACTLAB_BASE_URL, data=data)
        response.raise_for_status()

        logger.info(f"Slide {slide_id} added to show {show_id}")
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

        response = self.session.post(ACTLAB_BASE_URL, data=data)
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
            slide_id_attr = extract_attr(slide_div, "id", "")
            slide_id_match = re.search(r"slide(\d+)", slide_id_attr)

            if slide_id_match:
                slide_id = slide_id_match.group(1)
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

        # Find the show div
        show_div = soup.find("div", {"id": f"show{show_id}"})
        if not show_div:
            logger.warning(f"Show {show_id} not found")
            return 0

        # Get all slides in the show
        slide_divs = show_div.find_all("div", class_="slide")
        slide_ids = []

        for slide_div in slide_divs:
            slide_id_match = re.search(r"slide(\d+)", extract_attr(slide_div, "id", ""))
            if slide_id_match:
                slide_ids.append(slide_id_match.group(1))

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
        use_cache: bool = False,
    ):
        """Initialize async ACT Lab client.

        Args:
            username: SU username (default: read from SU_USERNAME env var)
            password: SU password (default: read from SU_PASSWORD env var)
            use_cache: Whether to cache authentication cookies

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
            service="unified",
            use_cache=use_cache,
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
            slide_id_attr = extract_attr(slide_div, "id", "")
            slide_id_match = re.search(r"slide(\d+)", slide_id_attr)

            if slide_id_match:
                slide_id = slide_id_match.group(1)
                name_elem = slide_div.find(class_="slide-name")
                name = extract_text(name_elem) if name_elem else f"Slide {slide_id}"

                slides.append(Slide(id=slide_id, name=name))

        logger.info(f"Found {len(slides)} slides")
        return slides

    async def add_slide_to_show(self, slide_id: str, show_id: str = "1") -> bool:
        """Add a slide to a show.

        Args:
            slide_id: Slide ID
            show_id: Show ID (default: 1 for Labbet)

        Returns:
            True if successful
        """
        await self._ensure_authenticated()

        logger.info(f"Adding slide {slide_id} to show {show_id}")

        data = {"action": "add", "add": slide_id, "to": show_id}

        async with self.session.post(ACTLAB_BASE_URL, data=data) as response:
            response.raise_for_status()

        logger.info(f"Slide {slide_id} added to show {show_id}")
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

        async with self.session.post(ACTLAB_BASE_URL, data=data) as response:
            response.raise_for_status()

        logger.info(f"Slide {slide_id} removed from show {show_id}")
        return True
