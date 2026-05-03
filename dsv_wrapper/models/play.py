"""Pydantic models for DSVPlay (play.dsv.su.se) - presentation/video platform."""

from pydantic import BaseModel, Field


class PlayCourse(BaseModel):
    """A course on DSVPlay with associated presentations."""

    code: str = Field(description="Course designation code (e.g., 'PROG1', 'IDSV')")
    name: str = Field(description="Full course name (e.g., 'Programming 1')")

    model_config = {"frozen": True}


class Presenter(BaseModel):
    """A presenter/teacher associated with a presentation."""

    username: str = Field(description="SU username (e.g., 'edsu8469')")
    name: str = Field(description="Full name (e.g., 'Edwin Sundberg')")

    model_config = {"frozen": True}


class VideoSource(BaseModel):
    """Video source with quality variants and poster image."""

    url_720p: str = Field(default="", description="720p video URL")
    url_1080p: str = Field(default="", description="1080p video URL")
    poster_url: str = Field(default="", description="Poster/thumbnail image URL")
    play_audio: bool = Field(default=False, description="Whether this source plays audio")

    model_config = {"frozen": True}


class Presentation(BaseModel):
    """A presentation/video on DSVPlay.

    When retrieved via get_presentations(), only id/title/title_en/thumb_url/description
    are populated. Use get_presentation() to get full details including sources/subtitles/token.
    """

    id: str = Field(description="Unique identifier (UUID)")
    title: str = Field(description="Presentation title")
    title_en: str = Field(default="", description="English title (from playlist)")
    thumb_url: str = Field(default="", description="Thumbnail image URL")
    description: str = Field(default="", description="Presentation description")
    sources: dict[str, VideoSource] = Field(
        default_factory=dict, description="Video sources keyed by name (e.g., 'main', 'right')"
    )
    subtitles: dict[str, str] = Field(
        default_factory=dict, description="Subtitle tracks keyed by label (e.g., 'Generated')"
    )
    token: str = Field(default="", description="JWT token for accessing media files")

    model_config = {"frozen": True}

    @property
    def has_subtitles(self) -> bool:
        """Check if this presentation has subtitles available.

        DSVPlay generates subtitles asynchronously, so a freshly uploaded
        recording may have ``has_subtitles == False`` and only flip to True
        once auto-transcription finishes.
        """
        return bool(self.subtitles)

    @property
    def is_video_ready(self) -> bool:
        """Check if at least one video source has a playable URL.

        Newly uploaded presentations may have ``sources == {}`` while encoding
        is still in progress. Once any source exposes a 720p or 1080p URL, the
        video is considered ready to play.
        """
        return any(s.url_720p or s.url_1080p for s in self.sources.values())

    @property
    def is_processing(self) -> bool:
        """Check whether the recording is still being processed.

        True when the video has not finished encoding (no sources) or the
        transcript has not yet been generated (no subtitles). Callers fetching
        transcripts should treat this as a "not ready, retry later" signal
        rather than a permanent error.
        """
        return not (self.is_video_ready and self.has_subtitles)

    @property
    def video_url(self) -> str:
        """Get the best available video URL (prefers 1080p main source)."""
        main = self.sources.get("main")
        if main:
            return main.url_1080p or main.url_720p
        if self.sources:
            first = next(iter(self.sources.values()))
            return first.url_1080p or first.url_720p
        return ""


class TranscriptCue(BaseModel):
    """A single cue/entry from a WebVTT transcript."""

    start_seconds: float = Field(description="Start time in seconds")
    end_seconds: float = Field(description="End time in seconds")
    text: str = Field(description="Transcript text for this cue")

    model_config = {"frozen": True}

    @property
    def start_timestamp(self) -> str:
        """Format start time as HH:MM:SS.mmm."""
        return _format_timestamp(self.start_seconds)

    @property
    def end_timestamp(self) -> str:
        """Format end time as HH:MM:SS.mmm."""
        return _format_timestamp(self.end_seconds)


def _format_timestamp(seconds: float) -> str:
    """Format seconds as HH:MM:SS.mmm."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"
