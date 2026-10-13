import base64
import json

import pytest

from dsv_wrapper.exceptions import ParseError
from dsv_wrapper.models.play import Presentation, VideoSource
from dsv_wrapper.parsers.play import resolve_track_download


def presentation(payload):
    token = (
        "e30."
        + base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        + ".sig"
    )
    return Presentation(
        id="test",
        title="test",
        token=token,
        sources={
            "camera": VideoSource(url_720p="https://example.invalid/camera.mp4"),
            "slides": VideoSource(url_1080p="https://example.invalid/slides.mp4?x=1&token=old"),
        },
    )


def test_download_uses_selected_envelope_and_expiry():
    p = presentation({"exp": 1791798609})
    result = resolve_track_download(p, 1)
    assert result.source_name == "slides"
    assert result.height == 1080
    assert result.expires_at == 1791798609
    assert "x=1&token=" in result.url
    assert "old" not in result.url
    assert p.token not in repr(result)


@pytest.mark.parametrize("payload", [{}, {"exp": "1791798609"}, {"exp": True}, {"exp": 0}, []])
def test_invalid_deadline_fails(payload):
    with pytest.raises(ParseError):
        resolve_track_download(presentation(payload), 0)


@pytest.mark.parametrize("index", [-1, 2])
def test_invalid_track_index(index):
    with pytest.raises(ValueError):
        resolve_track_download(presentation({"exp": 10}), index)
