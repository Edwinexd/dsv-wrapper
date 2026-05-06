"""Tests for Play client."""

import inspect
import logging
import tempfile
from pathlib import Path

import pytest

from dsv_wrapper.exceptions import (
    ParseError,
    PresentationNotReadyError,
    TranscriptNotReadyError,
)
from dsv_wrapper.models.play import (
    PlayCourse,
    Presentation,
    TrackInfo,
    TranscriptCue,
    VideoSource,
)
from dsv_wrapper.parsers.play import (
    enumerate_track_descriptors,
    parse_playlist_ids_from_html,
    parse_presentation_ids_from_html,
    parse_presentation_json,
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


def test_not_ready_exception_hierarchy():
    """The "not ready yet" exception family must form a chain so callers can
    pick their granularity:

    * ``except TranscriptNotReadyError`` — only the captions-pending case
      (video sources are ready, subtitles aren't).
    * ``except PresentationNotReadyError`` — both the captions-pending case
      *and* the broader "recording itself not yet processed" case.
    * ``except ParseError`` — all parse failures including the above.
    """
    transcript_err = TranscriptNotReadyError("captions pending")
    presentation_err = PresentationNotReadyError("recording still encoding")

    # TranscriptNotReady is the most specific case.
    assert isinstance(transcript_err, PresentationNotReadyError)
    assert isinstance(transcript_err, ParseError)

    # PresentationNotReady is the broader case but does NOT imply transcript
    # specifically — code that only wants the captions-pending branch must
    # check the subclass.
    assert isinstance(presentation_err, ParseError)
    assert not isinstance(presentation_err, TranscriptNotReadyError)


def test_parse_presentation_json_non_dict_response_signals_not_ready():
    """When DSVPlay's ``/presentation/{uuid}`` endpoint returns something
    other than a JSON object (observed in production: a list), the recording
    is still being processed. The parser must surface that as the
    transient-retry exception, not a generic ``AttributeError`` from a
    ``.get()`` call on the wrong type.

    Regression guard: previously raised
    ``AttributeError: 'list' object has no attribute 'get'`` and the hourly
    transcript fetcher would mark the document as permanently failed.
    """
    with pytest.raises(PresentationNotReadyError):
        parse_presentation_json([])

    with pytest.raises(PresentationNotReadyError):
        parse_presentation_json([{"error": "still processing"}])

    with pytest.raises(PresentationNotReadyError):
        parse_presentation_json(None)


def test_parse_presentation_json_missing_id_signals_not_ready():
    """An object envelope without an ``id`` field is also "not ready" rather
    than a malformed-data ParseError; the latter would be swallowed-and-failed
    by callers, the former is retried on the next run.
    """
    with pytest.raises(PresentationNotReadyError):
        parse_presentation_json({})

    with pytest.raises(PresentationNotReadyError):
        parse_presentation_json({"title": "still encoding"})


def test_parse_presentation_json_handles_empty_collections_as_lists():
    """Livewire/Eloquent serialise empty collections as ``[]`` rather than
    ``{}``. ``sources`` and ``subtitles`` must tolerate that without raising.

    Sibling regression to ``test_parse_presentation_ids_empty_designation``.
    """
    presentation = parse_presentation_json(
        {
            "id": "abc-123",
            "title": "Empty collections",
            "sources": [],
            "subtitles": [],
            "thumb": "",
            "token": "jwt",
        }
    )

    assert presentation.id == "abc-123"
    assert presentation.sources == {}
    assert presentation.subtitles == {}
    assert presentation.has_subtitles is False


def test_parse_presentation_json_happy_path():
    """Sanity check that the not-ready guards didn't break the normal path."""
    presentation = parse_presentation_json(
        {
            "id": "abc-123",
            "title": "Lecture 1",
            "sources": {
                "main": {
                    "video": {"720": "https://e/720.mp4", "1080": "https://e/1080.mp4"},
                    "poster": "https://e/poster.jpg",
                    "playAudio": True,
                }
            },
            "subtitles": {"Generated": "https://e/subs.vtt"},
            "thumb": "https://e/thumb.jpg",
            "token": "jwt-token",
        }
    )

    assert presentation.id == "abc-123"
    assert presentation.title == "Lecture 1"
    assert "main" in presentation.sources
    assert presentation.sources["main"].url_1080p == "https://e/1080.mp4"
    assert presentation.subtitles == {"Generated": "https://e/subs.vtt"}
    assert presentation.token == "jwt-token"


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


def test_enumerate_track_descriptors_orders_sources_then_quality():
    """Track enumeration must be deterministic: source insertion order outer,
    720p before 1080p inner. Empty URLs are skipped so callers don't get
    holes in the index space.
    """
    presentation = Presentation(
        id="abc",
        title="t",
        sources={
            "main": VideoSource(
                url_720p="https://e/main-720.mp4",
                url_1080p="https://e/main-1080.mp4",
            ),
            "right": VideoSource(url_1080p="https://e/right-1080.mp4"),
            "left": VideoSource(url_720p="https://e/left-720.mp4"),
        },
        token="jwt",
    )

    descriptors = enumerate_track_descriptors(presentation)
    assert descriptors == [
        ("https://e/main-720.mp4", "main", 720),
        ("https://e/main-1080.mp4", "main", 1080),
        ("https://e/right-1080.mp4", "right", 1080),
        ("https://e/left-720.mp4", "left", 720),
    ]


def test_enumerate_track_descriptors_empty_sources():
    """A presentation with no sources yields no descriptors (not a crash)."""
    presentation = Presentation(id="abc", title="t")
    assert enumerate_track_descriptors(presentation) == []


def test_track_info_model_all_fields_optional():
    """All metadata fields except ``index`` are optional — populated only when
    cheaply available. Callers that need width/duration can probe the moov
    atom themselves via ``stream_track``.
    """
    track = TrackInfo(index=0)
    assert track.duration_seconds is None
    assert track.width is None
    assert track.height is None
    assert track.size_bytes is None
    assert track.mime_type is None

    full = TrackInfo(
        index=3,
        duration_seconds=1234.5,
        width=1920,
        height=1080,
        size_bytes=987654321,
        mime_type="video/mp4",
    )
    assert full.index == 3
    assert full.height == 1080
    assert full.size_bytes == 987654321


@pytest.mark.integration
def test_play_get_media_tracks(play_client):
    """Enumerate tracks for the first ready presentation we can find.

    Track indexes must be 0..N-1 with no gaps. ``size_bytes`` must come back
    populated (the play-store CDN reports ``content-length`` on HEAD).
    URLs must NOT leak into the returned model — TrackInfo has no URL field
    by design, but we sanity-check that none of the string fields contain
    the play-store hostname either.
    """
    courses = play_client.get_courses()

    presentation_id = None
    for c in courses[:5]:
        try:
            presentations = play_client.get_presentations(c.code)
        except (ParseError, PresentationNotReadyError):
            continue
        for p in presentations[:5]:
            try:
                full = play_client.get_presentation(p.id)
            except (ParseError, PresentationNotReadyError):
                continue
            if full.is_video_ready:
                presentation_id = p.id
                break
        if presentation_id:
            break

    if not presentation_id:
        pytest.skip("No ready presentations found")

    tracks = play_client.get_media_tracks(presentation_id)

    assert isinstance(tracks, list)
    assert len(tracks) > 0, "A ready presentation must expose at least one track"
    assert [t.index for t in tracks] == list(range(len(tracks)))

    for t in tracks:
        assert isinstance(t, TrackInfo)
        assert t.size_bytes is not None and t.size_bytes > 0
        assert t.mime_type == "video/mp4"
        assert t.height in (720, 1080)
        # Defensive: the contract is "no URLs in the return". TrackInfo has
        # no string fields that could carry one, but verify nothing slipped
        # into the model dump either.
        for v in t.model_dump().values():
            if isinstance(v, str):
                assert "play-store" not in v
                assert "https://" not in v

    logger.info(f"Presentation {presentation_id}: {len(tracks)} tracks")
    for t in tracks:
        logger.info(f"  idx={t.index} h={t.height} size={t.size_bytes} mime={t.mime_type}")


@pytest.mark.integration
def test_play_stream_track_range_returns_requested_slice(play_client):
    """``stream_track`` with a byte range must return exactly the requested
    number of bytes. This is the cheap moov-atom-probe path callers depend
    on for track selection without a full multi-GB download.
    """
    courses = play_client.get_courses()

    presentation_id = None
    for c in courses[:5]:
        try:
            presentations = play_client.get_presentations(c.code)
        except (ParseError, PresentationNotReadyError):
            continue
        for p in presentations[:5]:
            try:
                full = play_client.get_presentation(p.id)
            except (ParseError, PresentationNotReadyError):
                continue
            if full.is_video_ready:
                presentation_id = p.id
                break
        if presentation_id:
            break

    if not presentation_id:
        pytest.skip("No ready presentations found")

    tracks = play_client.get_media_tracks(presentation_id)
    assert tracks

    chunks = list(play_client.stream_track(presentation_id, 0, end_byte=2047))
    body = b"".join(chunks)
    assert len(body) == 2048

    # Mid-file slice should also work (tests the start_byte path, not just open-ended).
    mid_chunks = list(play_client.stream_track(presentation_id, 0, start_byte=1024, end_byte=2047))
    mid_body = b"".join(mid_chunks)
    assert len(mid_body) == 1024


@pytest.mark.integration
def test_play_download_track_writes_full_byte_count(play_client):
    """``download_track`` must write exactly ``size_bytes`` bytes to disk.

    To keep the test cheap we pick the smallest ready track in the user's
    catalog. Large recordings (multi-GB) make this skip-prone; the test is
    skipped if we can't find a track under 200 MB.
    """
    courses = play_client.get_courses()

    size_limit = 200 * 1024 * 1024
    target = None

    for c in courses[:5]:
        try:
            presentations = play_client.get_presentations(c.code)
        except (ParseError, PresentationNotReadyError):
            continue
        for p in presentations[:5]:
            try:
                full = play_client.get_presentation(p.id)
            except (ParseError, PresentationNotReadyError):
                continue
            if not full.is_video_ready:
                continue
            try:
                tracks = play_client.get_media_tracks(p.id)
            except (ParseError, PresentationNotReadyError):
                continue
            for t in tracks:
                if (
                    t.size_bytes
                    and t.size_bytes < size_limit
                    and (target is None or t.size_bytes < target[2])
                ):
                    target = (p.id, t.index, t.size_bytes)
            if target:
                break
        if target:
            break

    if not target:
        pytest.skip(f"No track under {size_limit // (1024 * 1024)} MB found")

    presentation_id, track_index, expected_size = target
    logger.info(f"Downloading {presentation_id} track {track_index} ({expected_size} bytes)")

    with tempfile.TemporaryDirectory() as tmpdir:
        dest = Path(tmpdir) / "track.mp4"
        play_client.download_track(presentation_id, track_index, dest)
        actual = dest.stat().st_size
        assert actual == expected_size, f"Downloaded size {actual} != HEAD size {expected_size}"


@pytest.mark.integration
def test_play_get_media_tracks_invalid_index(play_client):
    """An out-of-range track index must surface as ValueError, not a
    confusing ``KeyError`` or a stray HTTP 404 deeper in the stack.
    """
    courses = play_client.get_courses()

    presentation_id = None
    for c in courses[:5]:
        try:
            presentations = play_client.get_presentations(c.code)
        except (ParseError, PresentationNotReadyError):
            continue
        for p in presentations[:3]:
            try:
                full = play_client.get_presentation(p.id)
            except (ParseError, PresentationNotReadyError):
                continue
            if full.is_video_ready:
                presentation_id = p.id
                break
        if presentation_id:
            break

    if not presentation_id:
        pytest.skip("No ready presentations found")

    with pytest.raises(ValueError):
        list(play_client.stream_track(presentation_id, 999, end_byte=1023))
