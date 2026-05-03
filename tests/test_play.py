"""Tests for Play client."""

import inspect
import logging

import pytest

from dsv_wrapper.exceptions import TranscriptNotReadyError
from dsv_wrapper.models.play import (
    PlayCourse,
    Presentation,
    TranscriptCue,
    VideoSource,
)
from dsv_wrapper.parsers.play import (
    parse_playlist_ids_from_html,
    parse_presentation_ids_from_html,
    parse_vtt,
)
from dsv_wrapper.play import AsyncPlayClient, PlayClient

logger = logging.getLogger(__name__)


@pytest.mark.integration
def test_play_get_courses(play_client):
    """Test getting courses from DSVPlay."""
    courses = play_client.get_courses()

    assert isinstance(courses, list)
    assert len(courses) > 0, "Should have at least one course"

    first = courses[0]
    assert isinstance(first, PlayCourse)
    assert first.code
    assert first.name

    logger.info(f"Retrieved {len(courses)} courses")
    for c in courses:
        logger.info(f"  {c.code}: {c.name}")


@pytest.mark.integration
def test_play_get_courses_by_tag(play_client):
    """Tag-based listing should cover courses the user isn't enrolled in."""
    courses = play_client.get_courses_by_tag("Lecture")

    assert isinstance(courses, list)
    assert len(courses) > 0, "Lecture tag should list many courses"

    first = courses[0]
    assert isinstance(first, PlayCourse)
    assert first.code
    assert first.name

    # The tag-based listing is global-ish; it should exceed the user-scoped list.
    user_courses = play_client.get_courses()
    assert len(courses) >= len(user_courses)

    logger.info(f"/tag/Lecture: {len(courses)} courses (user_courses={len(user_courses)})")


@pytest.mark.integration
def test_play_get_presentations(play_client):
    """Test getting presentations for a course."""
    courses = play_client.get_courses()
    assert len(courses) > 0

    designation = courses[0].code
    presentations = play_client.get_presentations(designation)

    assert isinstance(presentations, list)
    assert len(presentations) > 0, f"Should have presentations for {designation}"

    first = presentations[0]
    assert isinstance(first, Presentation)
    assert first.id
    assert first.title

    logger.info(f"Retrieved {len(presentations)} presentations for {designation}")


@pytest.mark.integration
def test_play_get_presentation(play_client):
    """Test getting full presentation details."""
    courses = play_client.get_courses()
    assert len(courses) > 0

    presentations = play_client.get_presentations(courses[0].code)
    assert len(presentations) > 0

    presentation = play_client.get_presentation(presentations[0].id)

    assert isinstance(presentation, Presentation)
    assert presentation.id == presentations[0].id
    assert presentation.title
    assert presentation.sources, "Should have video sources"
    assert presentation.token, "Should have a JWT token"

    # Check sources structure
    for name, source in presentation.sources.items():
        assert isinstance(source, VideoSource)
        assert source.url_720p or source.url_1080p, f"Source '{name}' should have video URL"

    logger.info(f"Presentation: {presentation.title}")
    logger.info(f"  Sources: {list(presentation.sources.keys())}")
    logger.info(f"  Subtitles: {list(presentation.subtitles.keys())}")


@pytest.mark.integration
def test_play_get_transcript(play_client):
    """Test getting transcript from a presentation with subtitles."""
    courses = play_client.get_courses()
    assert len(courses) > 0

    presentations = play_client.get_presentations(courses[0].code)
    assert len(presentations) > 0

    # Find a presentation with subtitles
    for p in presentations:
        full = play_client.get_presentation(p.id)
        if full.has_subtitles:
            cues = play_client.get_transcript(p.id)

            assert isinstance(cues, list)
            assert len(cues) > 0, "Should have at least one cue"

            first_cue = cues[0]
            assert isinstance(first_cue, TranscriptCue)
            assert first_cue.start_seconds >= 0
            assert first_cue.end_seconds > first_cue.start_seconds
            assert first_cue.text

            logger.info(f"Transcript for '{full.title}': {len(cues)} cues")
            logger.info(f"  First cue: [{first_cue.start_timestamp}] {first_cue.text[:80]}")
            return

    pytest.skip("No presentations with subtitles found")


@pytest.mark.integration
def test_play_get_transcript_text(play_client):
    """Test getting transcript as plain text."""
    courses = play_client.get_courses()
    assert len(courses) > 0

    presentations = play_client.get_presentations(courses[0].code)

    for p in presentations:
        full = play_client.get_presentation(p.id)
        if full.has_subtitles:
            text = play_client.get_transcript_text(p.id)

            assert isinstance(text, str)
            assert len(text) > 0

            logger.info(f"Transcript text ({len(text)} chars): {text[:200]}...")
            return

    pytest.skip("No presentations with subtitles found")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_async_play_get_courses(async_play_client):
    """Test getting courses with async client."""
    courses = await async_play_client.get_courses()

    assert isinstance(courses, list)
    assert len(courses) > 0

    logger.info(f"Async client retrieved {len(courses)} courses")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_async_play_get_presentations(async_play_client):
    """Test getting presentations with async client."""
    courses = await async_play_client.get_courses()
    assert len(courses) > 0

    presentations = await async_play_client.get_presentations(courses[0].code)
    assert isinstance(presentations, list)
    assert len(presentations) > 0

    logger.info(f"Async client retrieved {len(presentations)} presentations")


def test_sync_async_play_api_parity():
    """Test that sync and async Play clients have the same public API."""
    sync_methods = {
        name: method
        for name, method in inspect.getmembers(PlayClient, predicate=inspect.isfunction)
        if not name.startswith("_")
    }

    async_methods = {
        name: method
        for name, method in inspect.getmembers(AsyncPlayClient, predicate=inspect.isfunction)
        if not name.startswith("_")
    }

    missing_in_async = set(sync_methods.keys()) - set(async_methods.keys())
    missing_in_async = {m for m in missing_in_async if m not in {"__enter__", "__exit__", "close"}}

    assert not missing_in_async, (
        f"Async Play client is missing these public methods from sync client: {missing_in_async}"
    )

    for method_name in sync_methods:
        if method_name in {"__enter__", "__exit__", "close"}:
            continue

        if method_name in async_methods:
            sync_sig = inspect.signature(sync_methods[method_name])
            async_sig = inspect.signature(async_methods[method_name])

            sync_params = [p for p in sync_sig.parameters.values() if p.name != "self"]
            async_params = [p for p in async_sig.parameters.values() if p.name != "self"]

            sync_param_names = [p.name for p in sync_params]
            async_param_names = [p.name for p in async_params]

            assert sync_param_names == async_param_names, (
                f"Method '{method_name}' has different parameters:\n"
                f"  Sync: {sync_param_names}\n"
                f"  Async: {async_param_names}"
            )

    logger.info("API parity check passed: sync and async Play clients have matching public methods")


def test_vtt_parsing():
    """Test VTT transcript parsing."""
    vtt_content = """WEBVTT

00:00:00.000 --> 00:00:05.060
Hello world, this is a test
transcript line.

00:00:05.060 --> 00:00:11.280
Second line of the transcript
with multiple words.

00:00:11.280 --> 00:00:18.240
Third line.
"""

    cues = parse_vtt(vtt_content)

    assert len(cues) == 3

    assert cues[0].start_seconds == 0.0
    assert cues[0].end_seconds == 5.06
    assert cues[0].text == "Hello world, this is a test transcript line."

    assert cues[1].start_seconds == 5.06
    assert cues[1].end_seconds == 11.28
    assert cues[1].text == "Second line of the transcript with multiple words."

    assert cues[2].start_seconds == 11.28
    assert cues[2].end_seconds == 18.24
    assert cues[2].text == "Third line."


def test_presentation_model():
    """Test Presentation model properties."""
    source = VideoSource(
        url_720p="https://example.com/720.mp4",
        url_1080p="https://example.com/1080.mp4",
        poster_url="https://example.com/poster.jpg",
        play_audio=True,
    )

    presentation = Presentation(
        id="test-uuid",
        title="Test Presentation",
        sources={"main": source},
        subtitles={"Generated": "https://example.com/subs.vtt"},
        token="jwt-token",
    )

    assert presentation.has_subtitles is True
    assert presentation.video_url == "https://example.com/1080.mp4"
    assert presentation.is_video_ready is True
    assert presentation.is_processing is False

    # Test without subtitles
    no_subs = Presentation(id="test-2", title="No subs")
    assert no_subs.has_subtitles is False
    assert no_subs.video_url == ""
    assert no_subs.is_video_ready is False
    assert no_subs.is_processing is True

    # Sources present but transcript still pending (typical post-upload state)
    transcript_pending = Presentation(
        id="test-3",
        title="Sources only",
        sources={"main": source},
    )
    assert transcript_pending.is_video_ready is True
    assert transcript_pending.has_subtitles is False
    assert transcript_pending.is_processing is True

    # Empty source dict shouldn't be considered ready
    empty_source = VideoSource()
    not_ready = Presentation(id="test-4", title="Encoding", sources={"main": empty_source})
    assert not_ready.is_video_ready is False
    assert not_ready.is_processing is True


def test_transcript_not_ready_error_is_parse_error():
    """TranscriptNotReadyError must subclass ParseError so existing
    ``except ParseError`` blocks keep working, while callers who care about
    the transient state can catch the subclass specifically.
    """
    from dsv_wrapper.exceptions import ParseError

    err = TranscriptNotReadyError("not ready")
    assert isinstance(err, ParseError)


def test_parse_playlist_ids_returns_all_terms():
    """A multi-term designation exposes one playlist id per term; the parser
    must return all of them in page order (most-recent first), not just the
    latest.
    """
    import json

    snapshot = json.dumps(
        {
            "memo": {"name": "search.course-results"},
            "data": {
                "videos": [
                    {
                        "7620": [],
                        "7464": [],
                        "7292": [],
                    },
                    {"s": "arr"},
                ],
            },
        }
    ).replace('"', "&quot;")
    html = f'<div wire:snapshot="{snapshot}"></div>'

    assert parse_playlist_ids_from_html(html) == [7620, 7464, 7292]


def test_parse_playlist_ids_no_videos():
    """Pages without a course-results component yield an empty list."""
    assert parse_playlist_ids_from_html("<html></html>") == []


def test_parse_presentation_ids_empty_designation():
    """Empty/non-existent designation pages serialize `keys` as [] instead of {}.

    Previously this raised ``AttributeError: 'list' object has no attribute 'values'``.
    Regression guard: parsing should return an empty list without raising.
    """
    import json

    snapshot = json.dumps(
        {
            "memo": {"name": "search.course-results"},
            "data": {
                "allVideos": [
                    None,
                    {
                        "keys": [],  # empty collection -> list, not dict
                        "class": "Illuminate\\Database\\Eloquent\\Collection",
                        "modelClass": None,
                        "s": "elcln",
                    },
                ],
            },
        }
    ).replace('"', "&quot;")
    html = f'<div wire:snapshot="{snapshot}"></div>'

    assert parse_presentation_ids_from_html(html) == []


def test_transcript_cue_timestamps():
    """Test TranscriptCue timestamp formatting."""
    cue = TranscriptCue(start_seconds=3661.5, end_seconds=3665.123, text="test")

    assert cue.start_timestamp == "01:01:01.500"
    assert cue.end_timestamp == "01:01:05.123"
