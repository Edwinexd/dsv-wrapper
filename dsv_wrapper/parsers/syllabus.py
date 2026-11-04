"""Parsing for the SU syllabus archive (planarkiv) JSON endpoint."""

import re
from typing import Any

from ..exceptions import ParseError
from ..models.daisy import Semester
from ..models.syllabus import (
    LiteratureList,
    SyllabusArchiveEntry,
    SyllabusLink,
    SyllabusVersion,
)

# https://albatross.it.su.se/api/education/educationplan/pdf/IB440C/HT2020[/en]
_PDF_URL_RE = re.compile(
    r"/educationplan/pdf/(?P<code>[^/]+)/(?P<term>(?:VT|HT)\d{4})(?P<en>/en)?/?$"
)
_CREDITS_RE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)")


def _parse_credits(raw: str | None) -> float | None:
    """'7.5 hp' / '7,5 hp' / '30 credits' to a float."""
    if not raw:
        return None
    m = _CREDITS_RE.match(raw)
    return float(m.group(1).replace(",", ".")) if m else None


def _parse_link(raw: Any) -> SyllabusLink | None:
    if not isinstance(raw, dict) or not raw.get("href"):
        return None
    return SyllabusLink(text=(raw.get("text") or "").strip(), url=raw["href"])


def parse_syllabus_version(raw: dict) -> SyllabusVersion:
    """Parse one ``syllabuses`` entry; semester and language come from the URL."""
    href = raw.get("href") or ""
    m = _PDF_URL_RE.search(href)
    if not m:
        raise ParseError(f"Unrecognised syllabus PDF URL: {href!r}")
    return SyllabusVersion(
        semester=Semester.from_label(m.group("term")),
        language="en" if m.group("en") else "sv",
        pdf_url=href,
        title=(raw.get("text") or "").strip(),
    )


def parse_syllabus_archive(data: Any) -> SyllabusArchiveEntry:
    """Parse the archive's ``/syllabus`` JSON response for one course code."""
    if not isinstance(data, dict) or not data.get("code"):
        raise ParseError(f"Unexpected syllabus archive response: {str(data)[:200]!r}")
    return SyllabusArchiveEntry(
        code=data["code"],
        name=(data.get("heading") or "").strip(),
        education_type=data.get("educationType") or "course",
        ects=_parse_credits(data.get("credits")),
        description=(data.get("description") or "").strip() or None,
        is_discontinued=bool(data.get("isDiscontinued")),
        department=_parse_link(data.get("department")),
        versions=[parse_syllabus_version(v) for v in data.get("syllabuses") or []],
        literature_lists=[
            LiteratureList(
                semester=(lit.get("semester") or "").strip(),
                links=[link for link in map(_parse_link, lit.get("links") or []) if link],
            )
            for lit in data.get("literatureList") or []
        ],
    )
