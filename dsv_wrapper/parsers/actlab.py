"""ACT Lab HTML parsing functions."""

import re
from datetime import datetime

from ..exceptions import DSVWrapperError
from ..models.actlab import Slide
from ..utils import extract_attr, extract_text, parse_html


def parse_upload_time_from_filename(filename: str) -> datetime | None:
    """Parse upload time from ACT Lab filename.

    Filenames are formatted as YYMMDD-HHMMSS.ext (e.g., 180515-101811.png).

    Args:
        filename: The filename to parse

    Returns:
        datetime if parsing succeeds, None otherwise
    """
    match = re.match(r"(\d{6})-(\d{6})\.", filename)
    if not match:
        return None

    date_part = match.group(1)  # YYMMDD
    time_part = match.group(2)  # HHMMSS

    try:
        return datetime.strptime(f"{date_part}{time_part}", "%y%m%d%H%M%S")
    except ValueError:
        return None


class SlideUploadError(DSVWrapperError):
    """Raised when slide upload fails."""

    pass


def _parse_slide_div(slide_div, show_id: int | None = None) -> Slide | None:
    """Parse a single slide div element.

    Args:
        slide_div: BeautifulSoup element for the slide div
        show_id: Show ID if the slide is in a show, None otherwise

    Returns:
        Slide object or None if parsing fails
    """
    slide_id_str = extract_attr(slide_div, "id", "")

    if not slide_id_str or not slide_id_str.isdigit():
        return None

    slide_id = int(slide_id_str)
    name_elem = slide_div.find(class_="slide-name")
    name = extract_text(name_elem) if name_elem else f"Slide {slide_id}"

    # Extract filename from the anchor tag href (e.g., "../uploads/180515-101811.png")
    filename = None
    upload_time = None
    anchor = slide_div.find("a", href=True)
    if anchor:
        href = anchor.get("href", "")
        if href:
            filename = href.rsplit("/", 1)[-1]
            upload_time = parse_upload_time_from_filename(filename)

    # Extract auto_delete from the settings form checkbox
    auto_delete = False
    form = slide_div.find("form", class_="settingsform")
    if form:
        autodelete_input = form.find("input", {"name": "autodelete"})
        if autodelete_input:
            auto_delete = autodelete_input.has_attr("checked")

    return Slide(
        id=slide_id,
        name=name,
        filename=filename,
        upload_time=upload_time,
        show_id=show_id,
        auto_delete=auto_delete,
    )


def parse_slides(html: str) -> list[Slide]:
    """Parse slides from admin page HTML.

    Args:
        html: HTML content from ACT Lab admin page

    Returns:
        List of Slide objects
    """
    soup = parse_html(html)
    slides = []
    seen_ids = set()

    # First, parse slides from shows (these have show_id set)
    show_divs = soup.find_all("div", class_="show")
    for show_div in show_divs:
        show_id_str = extract_attr(show_div, "id", "")
        if show_id_str and show_id_str.isdigit():
            show_id = int(show_id_str)
            slide_divs = show_div.find_all("div", class_="slide")
            for slide_div in slide_divs:
                slide = _parse_slide_div(slide_div, show_id=show_id)
                if slide and slide.id not in seen_ids:
                    slides.append(slide)
                    seen_ids.add(slide.id)

    # Then, parse slides from the general slides container (no show_id)
    slides_container = soup.find("div", id="slides")
    if slides_container:
        slide_divs = slides_container.find_all("div", class_="slide", recursive=False)
        for slide_div in slide_divs:
            slide = _parse_slide_div(slide_div, show_id=None)
            if slide and slide.id not in seen_ids:
                slides.append(slide)
                seen_ids.add(slide.id)

    return slides


def parse_show_slides(html: str, show_id: int) -> list[int]:
    """Parse slide IDs from a specific show.

    Args:
        html: HTML content from ACT Lab admin page
        show_id: Show ID to get slides from

    Returns:
        List of slide IDs in the show
    """
    soup = parse_html(html)
    show_div = soup.find("div", {"id": str(show_id), "class": "show"})

    if not show_div:
        return []

    slide_divs = show_div.find_all("div", class_="slide")
    slide_ids = []

    for slide_div in slide_divs:
        id_attr = extract_attr(slide_div, "id", "")
        if id_attr and id_attr.isdigit():
            slide_ids.append(int(id_attr))

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


def find_newest_slide_id(html: str) -> int | None:
    """Find the newest slide ID from HTML.

    Args:
        html: HTML content from ACT Lab admin page

    Returns:
        Newest slide ID or None if no slides found
    """
    all_slide_ids = re.findall(r'<div class="slide"\s+id="(\d+)"', html)

    if not all_slide_ids:
        return None

    return max(int(sid) for sid in all_slide_ids)


def parse_error_message(html: str) -> str | None:
    """Parse error message from ACT Lab admin page.

    Args:
        html: HTML content from ACT Lab admin page

    Returns:
        Error message if found, None otherwise
    """
    soup = parse_html(html)
    error_div = soup.find("div", class_="error")
    if error_div and "visible" in error_div.get("class", []):
        return extract_text(error_div)
    return None
