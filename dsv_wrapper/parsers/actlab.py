"""ACT Lab HTML parsing functions."""

import re

from ..exceptions import DSVWrapperError
from ..models.actlab import Slide
from ..utils import extract_attr, extract_text, parse_html


class SlideUploadError(DSVWrapperError):
    """Raised when slide upload fails."""

    pass


def parse_slides(html: str) -> list[Slide]:
    """Parse slides from admin page HTML.

    Args:
        html: HTML content from ACT Lab admin page

    Returns:
        List of Slide objects
    """
    soup = parse_html(html)
    slides = []

    slide_divs = soup.find_all("div", class_="slide")
    for slide_div in slide_divs:
        slide_id = extract_attr(slide_div, "id", "")

        if slide_id and slide_id.isdigit():
            name_elem = slide_div.find(class_="slide-name")
            name = extract_text(name_elem) if name_elem else f"Slide {slide_id}"

            # Extract filename from the anchor tag href (e.g., "../uploads/180515-101811.png")
            filename = None
            anchor = slide_div.find("a", href=True)
            if anchor:
                href = anchor.get("href", "")
                if href:
                    filename = href.rsplit("/", 1)[-1]

            slides.append(Slide(id=slide_id, name=name, filename=filename))

    return slides


def parse_show_slides(html: str, show_id: str) -> list[str]:
    """Parse slide IDs from a specific show.

    Args:
        html: HTML content from ACT Lab admin page
        show_id: Show ID to get slides from

    Returns:
        List of slide IDs in the show
    """
    soup = parse_html(html)
    show_div = soup.find("div", {"id": show_id, "class": "show"})

    if not show_div:
        return []

    slide_divs = show_div.find_all("div", class_="slide")
    slide_ids = []

    for slide_div in slide_divs:
        id_attr = extract_attr(slide_div, "id", "")
        if id_attr and id_attr.isdigit():
            slide_ids.append(id_attr)

    return slide_ids


def parse_upload_form(html: str, base_url: str) -> tuple[str, str, str]:
    """Parse upload form details from HTML.

    Args:
        html: HTML content from ACT Lab admin page
        base_url: Base URL for ACT Lab admin

    Returns:
        Tuple of (form_action_url, action_value, max_file_size)

    Raises:
        SlideUploadError: If form not found or malformed
    """
    soup = parse_html(html)
    upload_form = soup.find("form", {"enctype": "multipart/form-data"})

    if not upload_form:
        raise SlideUploadError("Could not find upload form")

    form_action_url = extract_attr(upload_form, "action") or ""
    if not form_action_url.startswith("http"):
        form_action_url = base_url.rstrip("/") + "/" + form_action_url.lstrip("/")

    action_input = upload_form.find("input", {"name": "action"})
    action_value = extract_attr(action_input, "value") or "upload_file"

    max_file_size_input = upload_form.find("input", {"name": "MAX_FILE_SIZE"})
    max_file_size = extract_attr(max_file_size_input, "value") or "10000000"

    return form_action_url, action_value, max_file_size


def find_newest_slide_id(html: str) -> str | None:
    """Find the newest slide ID from HTML.

    Args:
        html: HTML content from ACT Lab admin page

    Returns:
        Newest slide ID or None if no slides found
    """
    all_slide_ids = re.findall(r'<div class="slide"\s+id="(\d+)"', html)

    if not all_slide_ids:
        return None

    return max(all_slide_ids, key=int)
