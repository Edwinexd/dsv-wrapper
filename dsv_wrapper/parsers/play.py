"""Parsing functions for DSVPlay (play.dsv.su.se)."""

import json
import logging
import re

from ..exceptions import ParseError
from ..models.play import (
    PlayCourse,
    Presentation,
    TranscriptCue,
    VideoSource,
)
from ..utils import parse_html

logger = logging.getLogger(__name__)


def _parse_courses_from_component(html: str, component_name: str) -> list[PlayCourse]:
    """Parse the `courses` filter of a named Livewire component.

    Many pages (user/all, tag/{tag}, study/all, ...) embed a Livewire component
    whose `data.courses` field is a dict of `{code: full_name}` for every
    course visible under that page's scope.

    Args:
        html: HTML content of the page
        component_name: Livewire component name (from snapshot's ``memo.name``),
            e.g. "my.user-presentations" or "search.tag-results"

    Returns:
        List of PlayCourse objects

    Raises:
        ParseError: If the component or its courses field is not found
    """
    soup = parse_html(html)

    for elem in soup.find_all(attrs={"wire:snapshot": True}):
        try:
            snap = json.loads(elem.get("wire:snapshot", "{}"))
        except json.JSONDecodeError:
            continue

        name = snap.get("memo", {}).get("name", "")
        if name != component_name:
            continue

        data = snap.get("data", {})
        courses_raw = data.get("courses", [[]])[0]

        if not isinstance(courses_raw, dict):
            continue

        courses = []
        for code, full_name in courses_raw.items():
            if code == "nocourse":
                continue
            courses.append(PlayCourse(code=code, name=full_name))

        logger.info(
            f"Parsed {len(courses)} courses from Livewire component {component_name!r}"
        )
        return courses

    raise ParseError(
        f"Could not find course data in Livewire component {component_name!r}"
    )


def parse_courses_from_html(html: str) -> list[PlayCourse]:
    """Parse courses from the /user/all page Livewire snapshot.

    Args:
        html: HTML content of the /user/all page

    Returns:
        List of PlayCourse objects

    Raises:
        ParseError: If parsing fails
    """
    return _parse_courses_from_component(html, "my.user-presentations")


def parse_courses_from_tag_html(html: str) -> list[PlayCourse]:
    """Parse courses from a /tag/{tag} page Livewire snapshot.

    The tag-results component's ``courses`` field enumerates every course that
    has at least one presentation matching the tag. Unioning across broad tags
    such as ``Lecture`` and ``Föreläsning`` yields a near-complete catalog of
    designations hosted on play.dsv.su.se.

    Args:
        html: HTML content of the /tag/{tag} page

    Returns:
        List of PlayCourse objects

    Raises:
        ParseError: If parsing fails
    """
    return _parse_courses_from_component(html, "search.tag-results")


def parse_playlist_id_from_html(html: str) -> int | None:
    """Parse playlist ID from /designation/{code} page Livewire snapshot.

    Args:
        html: HTML content of a designation page

    Returns:
        Playlist ID or None if not found
    """
    soup = parse_html(html)

    for elem in soup.find_all(attrs={"wire:snapshot": True}):
        try:
            snap = json.loads(elem.get("wire:snapshot", "{}"))
        except json.JSONDecodeError:
            continue

        name = snap.get("memo", {}).get("name", "")
        if name != "search.course-results":
            continue

        data = snap.get("data", {})
        videos = data.get("videos", [{}])

        if isinstance(videos[0], dict):
            for playlist_id in videos[0]:
                try:
                    return int(playlist_id)
                except (ValueError, TypeError):
                    continue

    return None


def parse_presentation_ids_from_html(html: str) -> list[str]:
    """Parse presentation UUIDs from /designation/{code} page Livewire snapshot.

    Args:
        html: HTML content of a designation page

    Returns:
        List of presentation UUIDs
    """
    soup = parse_html(html)

    for elem in soup.find_all(attrs={"wire:snapshot": True}):
        try:
            snap = json.loads(elem.get("wire:snapshot", "{}"))
        except json.JSONDecodeError:
            continue

        name = snap.get("memo", {}).get("name", "")
        if name != "search.course-results":
            continue

        data = snap.get("data", {})
        all_videos = data.get("allVideos", [None, {}])

        if len(all_videos) > 1 and isinstance(all_videos[1], dict):
            keys = all_videos[1].get("keys", {})
            return list(keys.values())

    return []


def parse_presentation_json(data: dict) -> Presentation:
    """Parse presentation from /presentation/{uuid} JSON response.

    Args:
        data: JSON response dict

    Returns:
        Presentation object

    Raises:
        ParseError: If required fields are missing
    """
    presentation_id = data.get("id")
    if not presentation_id:
        raise ParseError("Presentation JSON missing 'id' field")

    title = data.get("title", "")

    # Parse sources
    sources = {}
    for source_name, source_data in data.get("sources", {}).items():
        if not isinstance(source_data, dict):
            continue

        video = source_data.get("video", {})
        sources[source_name] = VideoSource(
            url_720p=video.get("720", ""),
            url_1080p=video.get("1080", ""),
            poster_url=source_data.get("poster", ""),
            play_audio=source_data.get("playAudio", False),
        )

    # Parse subtitles
    subtitles = {}
    for label, url in data.get("subtitles", {}).items():
        subtitles[label] = url

    return Presentation(
        id=presentation_id,
        title=title,
        thumb_url=data.get("thumb", ""),
        sources=sources,
        subtitles=subtitles,
        token=data.get("token", ""),
    )


def parse_playlist_json(data: dict) -> list[Presentation]:
    """Parse playlist items from /playlist/{id} JSON response as Presentations.

    Args:
        data: JSON response dict with 'title' and 'items' fields

    Returns:
        List of Presentation objects (lightweight, without sources/subtitles/token)
    """
    presentations = []
    for item in data.get("items", []):
        presentations.append(
            Presentation(
                id=item.get("id", ""),
                title=item.get("title", ""),
                title_en=item.get("title_en", ""),
                thumb_url=item.get("thumb", ""),
                description=item.get("description") or "",
            )
        )

    logger.info(f"Parsed {len(presentations)} presentations from playlist")
    return presentations


def parse_vtt(vtt_text: str) -> list[TranscriptCue]:
    """Parse WebVTT subtitle file into transcript cues.

    Args:
        vtt_text: Raw WebVTT file content

    Returns:
        List of TranscriptCue objects

    Raises:
        ParseError: If the VTT content is invalid
    """
    if not vtt_text.strip().startswith("WEBVTT"):
        raise ParseError("Invalid VTT content: missing WEBVTT header")

    cues = []
    # Match timestamp lines and their text
    # Format: HH:MM:SS.mmm --> HH:MM:SS.mmm
    timestamp_pattern = re.compile(r"(\d{2}:\d{2}:\d{2}\.\d{3})\s+-->\s+(\d{2}:\d{2}:\d{2}\.\d{3})")

    lines = vtt_text.strip().split("\n")
    i = 0
    while i < len(lines):
        match = timestamp_pattern.match(lines[i].strip())
        if match:
            start = _parse_vtt_timestamp(match.group(1))
            end = _parse_vtt_timestamp(match.group(2))

            # Collect text lines until empty line or end
            text_lines = []
            i += 1
            while i < len(lines) and lines[i].strip():
                text_lines.append(lines[i].strip())
                i += 1

            text = " ".join(text_lines)
            if text:
                cues.append(
                    TranscriptCue(
                        start_seconds=start,
                        end_seconds=end,
                        text=text,
                    )
                )
        else:
            i += 1

    logger.info(f"Parsed {len(cues)} transcript cues from VTT")
    return cues


def _parse_vtt_timestamp(timestamp: str) -> float:
    """Parse VTT timestamp (HH:MM:SS.mmm) to seconds.

    Args:
        timestamp: Timestamp string

    Returns:
        Time in seconds
    """
    parts = timestamp.split(":")
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = float(parts[2])
    return hours * 3600 + minutes * 60 + seconds
