"""Tests for the Daisy course/medverkande parsers and client methods.

Unit tests run against captured HTML fixtures in ``tests/fixtures/daisy/``.
Integration tests run against the live Daisy instance and require credentials.
"""

import logging
from datetime import date
from pathlib import Path

import pytest

from dsv_wrapper import (
    AsyncDaisyClient,
    CourseResponsibility,
    CourseStaff,
    DaisyClient,
    DaisyCourse,
    Semester,
    TermSeason,
)
from dsv_wrapper.parsers.daisy import (
    parse_course_detail,
    parse_course_participants,
    parse_course_search,
    parse_staff_details,
)

logger = logging.getLogger(__name__)

FIXTURES = Path(__file__).parent / "fixtures" / "daisy"
BASE = "https://daisy.dsv.su.se"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text()


# ---------------------------------------------------------------------------
# Semester model
# ---------------------------------------------------------------------------


class TestSemester:
    def test_label_roundtrip(self):
        assert Semester.from_label("VT2026").label == "VT2026"
        assert Semester.from_label("ht2025").label == "HT2025"

    def test_termin_id_encoding(self):
        assert Semester(year=2026, season=TermSeason.VT).termin_id == "20261"
        assert Semester(year=2026, season=TermSeason.HT).termin_id == "20262"

    def test_from_termin_id(self):
        assert Semester.from_termin_id("20261") == Semester(year=2026, season=TermSeason.VT)
        assert Semester.from_termin_id(20262) == Semester(year=2026, season=TermSeason.HT)

    def test_invalid_label_raises(self):
        with pytest.raises(ValueError):
            Semester.from_label("XX2026")
        with pytest.raises(ValueError):
            Semester.from_label("VT")

    def test_invalid_termin_id_raises(self):
        with pytest.raises(ValueError):
            Semester.from_termin_id("2026")  # wrong length
        with pytest.raises(ValueError):
            Semester.from_termin_id("20263")  # invalid season digit


# ---------------------------------------------------------------------------
# Course search parser
# ---------------------------------------------------------------------------


class TestParseCourseSearch:
    def test_first_page_full(self):
        courses, rf, rt, total = parse_course_search(_load("sokmoment_vt2026_p1.html"), BASE)
        assert (rf, rt, total) == (1, 20, 70)
        assert len(courses) == 20
        alda = next(c for c in courses if c.beteckning == "ALDA")
        assert alda.name == "Algoritmer och datastrukturer"
        assert alda.ects == 7.5
        assert alda.semester == Semester.from_label("VT2026")
        assert alda.start_date == date(2026, 1, 19)
        assert alda.end_date == date(2026, 3, 22)
        assert alda.momenttillf_id.isdigit()
        assert alda.info_url and alda.info_url.startswith(BASE)
        assert alda.schedule_url and "Momentschema" in alda.schedule_url
        assert alda.participants_url and "momenttillfID" in alda.participants_url
        # PROG2 is on a later page; verify the parenthesised AB variants survive.
        wprog1 = next(c for c in courses if c.beteckning.startswith("WPROG1"))
        assert wprog1.beteckning == "WPROG1 (AB)"

    def test_last_page_partial(self):
        courses, rf, rt, total = parse_course_search(_load("sokmoment_vt2026_p4.html"), BASE)
        assert (rf, rt, total) == (61, 70, 70)
        assert len(courses) == 10


# ---------------------------------------------------------------------------
# Course detail parser
# ---------------------------------------------------------------------------


class TestParseCourseDetail:
    def test_prog2_detail(self):
        course = parse_course_detail(_load("momentinfo_7620.html"), "7620", BASE)
        assert isinstance(course, DaisyCourse)
        assert course.beteckning == "PROG2"
        assert course.name == "Programmering 2"
        assert course.ects == 7.5
        assert course.unit == "ACT"
        assert course.semester == Semester.from_label("VT2026")
        assert course.syllabus_url == (
            "https://utbildning.su.se/utbildning/sok-i-planarkiv/planarkiv?code=IB440C"
        )


# ---------------------------------------------------------------------------
# Participants parser
# ---------------------------------------------------------------------------


class TestParseCourseParticipants:
    def test_prog2_participants_includes_unlinked(self):
        """PROG2 momentinfo lists 3 linked staff plus 2 plain-text student-
        handledare under 'Handledare'. The unlinked ones come back with
        ``person_id=None`` — resolve them via :meth:`CourseStaff.get_person_id`."""
        parts = parse_course_participants(_load("momentinfo_7620.html"), BASE)
        assert [p.name for p in parts] == [
            "Isak Samsten",
            "Beatrice Åkerblom",
            "Edwin Sundberg",
            "Ekaterina Kershinskaia",
            "Andrés-Emilio Miranda",
        ]
        by_name = {p.name: p for p in parts}
        beatrice = by_name["Beatrice Åkerblom"]
        assert isinstance(beatrice, CourseStaff)
        assert beatrice.person_id == "221"
        assert beatrice.first_name == "Beatrice"
        assert beatrice.last_name == "Åkerblom"
        assert beatrice.roles == ["Kurs-/delkursansvarig"]
        assert beatrice.profile_url == f"{BASE}/anstalld/anstalldinfo.jspa?personID=221"

        ekaterina = by_name["Ekaterina Kershinskaia"]
        assert ekaterina.person_id is None
        assert ekaterina.profile_url is None
        assert ekaterina.first_name == "Ekaterina"
        assert ekaterina.last_name == "Kershinskaia"
        assert ekaterina.roles == ["Handledare"]

        # Hyphenated first names stay attached.
        andres = by_name["Andrés-Emilio Miranda"]
        assert andres.first_name == "Andrés-Emilio"
        assert andres.last_name == "Miranda"

    def test_db_participants_role_merging(self):
        """Databasmetodik has people listed under many role groups; we merge
        them so each person appears once with the full role list."""
        parts = parse_course_participants(_load("momentinfo_7619_db.html"), BASE)
        assert len(parts) == 8
        by_name = {p.name: p for p in parts}

        # Course-responsible is encoded as a regular role, not a flag
        ann = by_name["Ann Maria Dorotea Bergholtz"]
        assert ann.roles[0] == "Kurs-/delkursansvarig"
        for expected in (
            "Administration",
            "Handledare",
            "Examination",
            "Laborationsledare",
            "Föreläsare",
        ):
            assert expected in ann.roles

        # Martin Duneld is only under "Gästföreläsare" — single-role case.
        martin = by_name["Martin Duneld"]
        assert martin.roles == ["Gästföreläsare"]
        assert martin.person_id == "589"

    def test_returns_empty_list_when_section_missing(self):
        """A momentinfo page without a Medverkande section returns []."""
        assert parse_course_participants("<html><body></body></html>", BASE) == []


# ---------------------------------------------------------------------------
# Extended staff details parser
# ---------------------------------------------------------------------------


class TestParseStaffDetailsRich:
    def test_beatrice_profile_full_fields(self):
        staff = parse_staff_details("221", _load("anstalld_221.html"), BASE)

        # Basics still work
        assert staff.person_id == "221"
        assert "Beatrice" in staff.name and "Åkerblom" in staff.name
        assert staff.email == "beatrice@dsv.su.se"
        assert staff.room == "63102"
        assert staff.phone == "08-164988"
        assert staff.profile_pic_url == f"{BASE}/servlet/daisy.Jpg?id=221"
        assert staff.units == ["DSV", "ACT"]

        # New rich fields
        assert staff.usernames == [
            "bake@KTH.SE",
            "u1cn3zfl@KTH.SE",
            "beatrice@DSV.SU.SE",
            "beake@SU.SE",
        ]
        assert staff.home_phone == "0709383111"
        assert staff.alt_phone == "0709-383 111"
        assert staff.office_hours == "By appointment"
        assert staff.exam_systems == ["iExam"]
        assert staff.research_areas == ["Programvaruvetenskap"]
        assert staff.website == "http://www.dsv.su.se/~beatrice"

        # Address newlines are preserved
        assert staff.address is not None
        assert "BOHUSGATAN 23 LGH 4040" in staff.address
        assert "11667 STOCKHOLM" in staff.address
        assert "Sverige" in staff.address
        assert staff.address.count("\n") == 2

        # Course responsibilities flattened into beteckningar list
        assert staff.course_responsibilities == [
            CourseResponsibility(
                semester=Semester.from_label("VT2026"),
                beteckningar=["ALDA", "PARADIS", "PROG2"],
            )
        ]


# ---------------------------------------------------------------------------
# Client API parity for the new methods
# ---------------------------------------------------------------------------


def test_new_methods_on_both_clients():
    """Both sync and async clients expose the new course methods."""
    for cls in (DaisyClient, AsyncDaisyClient):
        for method in ("get_courses", "get_course", "get_course_participants"):
            assert hasattr(cls, method), f"{cls.__name__} missing {method}"


# ---------------------------------------------------------------------------
# Integration tests (live Daisy)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_daisy_get_courses_vt2026(daisy_client):
    """VT2026 currently has 70 DSV course offerings. The exact number may
    drift over time; assert a reasonable lower bound and shape instead."""
    courses = daisy_client.get_courses(Semester.from_label("VT2026"))
    assert len(courses) >= 50, f"Expected many courses for VT2026, got {len(courses)}"
    # Every entry should be on VT2026 with non-empty beteckning/name
    for c in courses:
        assert c.beteckning, c
        assert c.name, c
        assert c.semester == Semester.from_label("VT2026"), c
        assert c.momenttillf_id.isdigit()
    # PROG2 is a stable course code
    assert any(c.beteckning == "PROG2" for c in courses)


@pytest.mark.integration
def test_daisy_get_course_and_participants(daisy_client):
    courses = daisy_client.get_courses(
        Semester.from_label("VT2026"), beteckning="PROG2", max_pages=1
    )
    prog2 = next(c for c in courses if c.beteckning == "PROG2")

    detail = daisy_client.get_course(prog2.momenttillf_id)
    assert detail.beteckning == "PROG2"
    assert detail.ects == 7.5
    assert detail.unit  # DSV courses always have an owning unit

    parts = daisy_client.get_course_participants(prog2.momenttillf_id)
    assert parts, "PROG2 has medverkande in Daisy"
    # At least one must carry the Kurs-/delkursansvarig role.
    assert any("Kurs-/delkursansvarig" in p.roles for p in parts)
    # Roles are non-empty for every returned person.
    assert all(p.roles for p in parts)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_async_daisy_get_courses(async_daisy_client):
    courses = await async_daisy_client.get_courses(Semester.from_label("VT2026"), max_pages=1)
    assert courses, "async get_courses should return some courses"
    assert all(c.semester == Semester.from_label("VT2026") for c in courses)
