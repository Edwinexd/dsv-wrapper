"""Tests for the syllabus archive client.

Parsing tests run offline against responses captured from the live archive
(tests/fixtures/syllabus). The archive is public, so the integration tests
need network access but no credentials.
"""

import inspect
import json
from pathlib import Path

import httpx
import pytest

from dsv_wrapper import AsyncSyllabusClient, SyllabusClient, SyllabusNotFoundError
from dsv_wrapper.exceptions import ParseError
from dsv_wrapper.models import Semester
from dsv_wrapper.parsers.syllabus import parse_syllabus_archive
from dsv_wrapper.syllabus import _parse_response

FIXTURES = Path(__file__).parent / "fixtures" / "syllabus"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parse_multiple_versions_swedish():
    entry = parse_syllabus_archive(_load("IB440C_sv.json"))

    assert entry.code == "IB440C"
    assert entry.name == "Programmering 2"
    assert entry.education_type == "course"
    assert entry.ects == 7.5
    assert entry.is_discontinued is False
    assert entry.department and "data- och systemvetenskap" in entry.department.text
    assert [v.semester.label for v in entry.versions] == ["HT2020", "VT2015", "VT2013", "HT2011"]
    assert all(v.language == "sv" for v in entry.versions)
    assert entry.versions[0].pdf_url.endswith("/pdf/IB440C/HT2020")
    assert entry.versions[0].title == "Utbildningsplan Hösttermin 2020"
    assert entry.latest == entry.versions[0]


def test_parse_english_falls_back_to_swedish_pdfs():
    entry = parse_syllabus_archive(_load("IB440C_en.json"))

    by_label = {v.semester.label: v for v in entry.versions}
    assert by_label["HT2011"].language == "en"
    assert by_label["HT2011"].pdf_url.endswith("/HT2011/en")
    assert by_label["HT2020"].language == "sv"


def test_parse_discontinued():
    entry = parse_syllabus_archive(_load("DA1003_sv.json"))

    assert entry.is_discontinued is True
    assert entry.latest is not None


def test_latest_uses_semester_not_list_order():
    data = _load("IB440C_sv.json")
    data["syllabuses"].reverse()
    entry = parse_syllabus_archive(data)

    assert entry.latest.semester == Semester.from_label("HT2020")


def test_parse_literature_lists():
    data = _load("IB138N_sv.json")
    data["literatureList"] = [
        {"semester": "HT2026", "links": [{"text": "Litteraturlista", "href": "https://x/l.pdf"}]}
    ]
    entry = parse_syllabus_archive(data)

    assert entry.literature_lists[0].semester == "HT2026"
    assert entry.literature_lists[0].links[0].url == "https://x/l.pdf"


def test_parse_rejects_unknown_pdf_url():
    data = _load("IB138N_sv.json")
    data["syllabuses"] = [{"text": "x", "href": "https://example.com/plan.pdf"}]

    with pytest.raises(ParseError):
        parse_syllabus_archive(data)


def test_parse_rejects_non_entry():
    with pytest.raises(ParseError):
        parse_syllabus_archive({"errorMessage": "boom"})


def test_unknown_code_raises_not_found():
    body = (FIXTURES / "PROG2_notfound.txt").read_text(encoding="utf-8")
    response = httpx.Response(500, text=body, request=httpx.Request("GET", "https://x"))

    with pytest.raises(SyllabusNotFoundError):
        _parse_response(response, "PROG2")


def test_other_server_errors_propagate():
    response = httpx.Response(500, text="oops", request=httpx.Request("GET", "https://x"))

    with pytest.raises(httpx.HTTPStatusError):
        _parse_response(response, "IB440C")


def test_rejects_unsupported_language():
    with SyllabusClient() as client:
        with pytest.raises(ValueError):
            client.get_syllabus_archive("IB440C", language="de")


def test_sync_async_api_parity():
    def public(cls):
        return {
            name: inspect.signature(fn)
            for name, fn in inspect.getmembers(cls, predicate=inspect.isfunction)
            if not name.startswith("_") and name != "close"
        }

    sync_methods, async_methods = public(SyllabusClient), public(AsyncSyllabusClient)
    assert sync_methods.keys() == async_methods.keys()
    for name, sig in sync_methods.items():
        assert sig == async_methods[name], name


@pytest.mark.integration
def test_live_archive():
    with SyllabusClient() as client:
        entry = client.get_syllabus_archive("IB440C")
        assert entry.code == "IB440C"
        assert entry.versions

        with pytest.raises(SyllabusNotFoundError):
            client.get_syllabus_archive("PROG2")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_archive_async():
    async with AsyncSyllabusClient() as client:
        entry = await client.get_syllabus_archive("IB440C", language="en")
        assert entry.code == "IB440C"
        assert any(v.language == "en" for v in entry.versions)
