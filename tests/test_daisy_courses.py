"""Tests for the Daisy course/medverkande parsers and client methods.

Unit tests run against captured HTML fixtures in ``tests/fixtures/daisy/``.
Integration tests run against the live Daisy instance and require credentials.
"""

import logging
from datetime import date, datetime, time
from pathlib import Path

import httpx
import pytest

from dsv_wrapper import (
    AsyncDaisyClient,
    CourseExam,
    CourseResponsibility,
    CourseStaff,
    DaisyClient,
    DaisyCourse,
    ParseError,
    Semester,
    SyllabusCourse,
    TermSeason,
)
from dsv_wrapper.parsers.daisy import (
    parse_course_detail,
    parse_course_exams,
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
        assert course.unit == "ACT Agera i kommunikation med teknik"
        assert course.semester == Semester.from_label("VT2026")
        assert course.start_date == date(2026, 3, 23)
        assert course.end_date == date(2026, 6, 7)
        assert course.syllabus_url == (
            "https://utbildning.su.se/utbildning/sok-i-planarkiv/planarkiv?code=IB440C"
        )
        assert course.prerequisites.startswith("Som obligatorisk kurs: inget förkunskapskrav.")
        assert course.website is None

    def test_swedish_detail_all_fields(self):
        course = parse_course_detail(_load("momentinfo_7689_sv.html"), "7689", BASE)
        assert course.beteckning == "IDSV"
        assert course.name == "Introduktion till data- och systemvetenskap"
        assert course.semester == Semester.from_label("HT2026")
        assert course.unit == "ACT Agera i kommunikation med teknik"
        assert course.ects == 7.5
        assert course.level == "Grundnivå"
        assert course.start_date == date(2026, 8, 31)
        assert course.end_date == date(2026, 9, 30)
        assert course.language == "Svenska"
        assert course.prerequisites is None
        assert course.course_analysis_url == f"{BASE}/fil/visa?id=326360"
        assert course.course_analysis_semester == Semester.from_label("HT2025")
        assert course.last_updated == date(2026, 8, 26)
        assert course.aim.startswith("Efter avklarad kurs skall studenten kunna")
        assert "\n- datorarkitektur;\n" in course.aim
        assert course.aim.endswith("grundläggande färdigheter i programmering.")
        assert course.content.startswith("Kursen är en introduktion")
        assert course.instruction == "Undervisningen består av föreläsningar och handledning."
        assert course.examination.startswith("Kursen examineras genom tentamen")
        assert course.literature == [
            "J. Glenn Brookshear & Dennis Brylow. (2019). Computer Science - An Overview. "
            "13 uppl. Pearson. ISBN: 978-0-13-487546-0"
        ]
        assert course.courses == [
            SyllabusCourse(
                name="Introduktion till data- och systemvetenskap",
                code="IB130N",
                requirement="obligatorisk",
                level="Grundnivå",
                syllabus_url=(
                    "https://utbildning.su.se/utbildning/sok-i-planarkiv/planarkiv?code=IB130N"
                ),
            )
        ]
        assert course.syllabus_url == course.courses[0].syllabus_url

    def test_english_detail_all_fields(self):
        course = parse_course_detail(_load("momentinfo_7689_en.html"), "7689", BASE)
        assert course.beteckning == "IDSV"
        assert course.name == "Introduction to Computer and Systems Sciences"
        assert course.semester == Semester.from_label("HT2026")
        assert course.unit == "Act in Communication with Technology"
        assert course.ects == 7.5
        assert course.level == "First cycle"
        assert course.start_date == date(2026, 8, 31)
        assert course.end_date == date(2026, 9, 30)
        assert course.language == "Swedish"
        assert course.course_analysis_url == f"{BASE}/fil/visa?id=326360"
        assert course.course_analysis_semester == Semester.from_label("HT2025")
        assert course.last_updated == date(2026, 8, 26)
        assert course.aim.startswith("Upon successful completion of the course")
        assert course.instruction == (
            "Instruction is given in the form of lectures and supervision sessions."
        )
        assert course.examination.startswith("The course is examined through")
        assert len(course.literature) == 1
        assert [(c.code, c.requirement, c.level) for c in course.courses] == [
            ("IB130N", "compulsory", "First cycle")
        ]

    def test_language_independent_fields_match(self):
        """The Swedish and English pages agree on everything that isn't prose."""
        neutral = {
            "momenttillf_id", "beteckning", "ects", "semester", "start_date", "end_date",
            "info_url", "schedule_url", "participants_url", "syllabus_url",
            "course_analysis_url", "course_analysis_semester", "last_updated", "website",
        }  # fmt: skip
        sv = parse_course_detail(_load("momentinfo_7689_sv.html"), "7689", BASE)
        en = parse_course_detail(_load("momentinfo_7689_en.html"), "7689", BASE)
        assert sv.model_dump(include=neutral) == en.model_dump(include=neutral)

    def test_website_and_examination_subheadings(self):
        course = parse_course_detail(_load("momentinfo_7619_db.html"), "7619", BASE)
        assert course.unit == "Informationssystem"
        assert course.website == "https://nextilearn.dsv.su.se/course/view.php?id=415"
        assert course.start_date == date(2026, 2, 19)
        assert course.end_date == date(2026, 3, 22)
        # The "Enligt kursplanen" marker is dropped; real sub-headings are kept.
        assert course.examination.startswith("Kursen examineras genom tentamen")
        assert "\n\nPrecisering\n\nExamination enligt kursplanen\n" in course.examination

    def test_page_without_text_sections(self):
        """The English PROG2 page has no aim/content/instruction/examination."""
        course = parse_course_detail(_load("momentinfo_7620_en.html"), "7620", BASE)
        assert course.name == "Programming 2"
        assert course.aim is None
        assert course.examination is None
        assert len(course.literature) == 1

    def test_non_course_page_raises(self):
        with pytest.raises(ParseError):
            parse_course_detail("<html><body>Logga in</body></html>", "1", BASE)

    def test_malformed_dates_raise(self):
        html = _load("momentinfo_7689_sv.html").replace("2026-08-31 till", "i höst till")
        with pytest.raises(ParseError):
            parse_course_detail(html, "7689", BASE)


# ---------------------------------------------------------------------------
# Exam parser
# ---------------------------------------------------------------------------


class TestParseCourseExams:
    def test_idsv_exams_swedish(self):
        exams = parse_course_exams(_load("momentschema_7689_sv.html"))
        assert [(e.kind, e.date, e.start_time, e.end_time) for e in exams] == [
            ("Ordinarie tenta", date(2026, 9, 26), time(8), time(11)),
            ("Ordinarie tenta", date(2026, 9, 26), time(12), time(15)),
            ("Ordinarie tenta", date(2026, 9, 26), time(16), time(19)),
            ("Inlämningsuppgift", date(2026, 9, 30), None, None),
            ("Omtenta", date(2026, 12, 7), time(9), time(12)),
            ("Omtenta", date(2026, 12, 7), time(13), time(16)),
        ]
        first = exams[0]
        assert isinstance(first, CourseExam)
        assert first.examination == "Tentamen, 4 hp"
        assert first.ects == 4.0
        assert first.rooms[:3] == ["Aula NOD", "D1", "D2"]
        assert first.rooms[-1] == "T12"  # footnote asterisk stripped
        assert "G10:1" in first.rooms
        assert first.start == datetime(2026, 9, 26, 8, 0)
        assert first.end == datetime(2026, 9, 26, 11, 0)
        assert exams[2].rooms == ["DL40"]

        assignment = exams[3]
        assert assignment.examination == "Inlämningsuppgift, 3,5 hp"
        assert assignment.ects == 3.5
        assert assignment.rooms == []
        assert assignment.start is None and assignment.end is None

    def test_idsv_exams_english(self):
        """The English page has the same occasions; only names are translated."""
        sv = parse_course_exams(_load("momentschema_7689_sv.html"))
        en = parse_course_exams(_load("momentschema_7689_en.html"))
        neutral = {"ects", "date", "start_time", "end_time"}
        assert [e.model_dump(include=neutral) for e in en] == [
            e.model_dump(include=neutral) for e in sv
        ]
        assert en[0].examination == "Written exam, 4 hec"
        assert en[0].rooms[0] == "Auditorium NOD"
        assert en[3].examination == "Assignment, 3,5 hec"
        # Free-text kinds stay as entered; default ones are translated.
        assert [e.kind for e in en] == [
            "Ordinarie tenta",
            "Ordinarie tenta",
            "Ordinarie tenta",
            "Assignment",
            "Omtenta",
            "Omtenta",
        ]

    def test_db_exams_include_uppsamlingstenta(self):
        exams = parse_course_exams(_load("momentschema_7619_sv.html"))
        assert [(e.examination, e.kind, e.date) for e in exams] == [
            ("Projektarbete, 3,5 hp", "Projektarbete", date(2026, 3, 22)),
            ("Tentamen, 4 hp", "Ordinarie tenta", date(2026, 3, 22)),
            ("Tentamen, 4 hp", "Omtenta", date(2026, 5, 27)),
            ("Tentamen, 4 hp", "Uppsamlingstenta", date(2026, 8, 6)),
        ]
        assert exams[-1].rooms[-1] == "Lilla Hörsalen"

    def test_schedule_without_exam_table(self):
        html = _load("momentschema_7689_sv.html").replace(">Examinationer<", ">Annat<")
        assert parse_course_exams(html) == []

    def test_non_schedule_page_raises(self):
        with pytest.raises(ParseError):
            parse_course_exams("<html><body>404 Not Found</body></html>")

    def test_malformed_time_raises(self):
        html = _load("momentschema_7689_sv.html").replace("08:00-11:00", "förmiddag")
        with pytest.raises(ParseError):
            parse_course_exams(html)


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

    def test_english_participants(self):
        """The English page uses a *Contributors* heading and translated roles."""
        sv = parse_course_participants(_load("momentinfo_7689_sv.html"), BASE)
        en = parse_course_participants(_load("momentinfo_7689_en.html"), BASE)
        assert [(p.person_id, p.name) for p in en] == [(p.person_id, p.name) for p in sv]
        assert [p.name for p in en] == [
            "Peter Idestam-Almquist",
            "Edwin Sundberg",
            "Jozef Zbigniew Swiatycki",
            "Magnus Johansson",
        ]
        assert en[1].roles == ["Course assistant", "Teacher", "Lecturer"]
        assert sv[1].roles == ["Handledare", "Lektionsledare", "Föreläsare"]

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
        for method in (
            "get_courses",
            "get_course",
            "get_course_schedule_ical",
            "get_course_participants",
        ):
            assert hasattr(cls, method), f"{cls.__name__} missing {method}"


ICAL = """BEGIN:VCALENDAR\r
VERSION:2.0\r
BEGIN:VEVENT\r
UID:DAISY_schematillf_825062\r
LAST-MODIFIED:20260831T153138\r
DTSTART;TZID=Europe/Stockholm:20260323T130000\r
DTEND;TZID=Europe/Stockholm:20260323T144500\r
SUMMARY:Föreläsning 1 Aula NOD - PROG2\r
END:VEVENT\r
END:VCALENDAR\r
"""


def test_get_course_schedule_ical_uses_authenticated_client():
    request_seen = None

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal request_seen
        request_seen = request
        return httpx.Response(200, text=ICAL)

    client = DaisyClient(username="test", password="test")
    client._authenticated = True
    client._client.close()
    client._client = httpx.Client(transport=httpx.MockTransport(handle))
    try:
        calendar = client.get_course_schedule_ical(7620, language="en")
    finally:
        client._client.close()

    assert "UID:DAISY_schematillf_825062" in calendar
    assert request_seen is not None
    assert request_seen.url.path.endswith("/schema.CourseSegmentInstanceCalendarICS")
    assert dict(request_seen.url.params) == {"id": "7620", "daisy__lang": "en"}


def test_get_course_schedule_ical_rejects_non_calendar_response():
    client = DaisyClient(username="test", password="test")
    client._authenticated = True
    client._client.close()
    client._client = httpx.Client(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, text="login page"))
    )
    try:
        with pytest.raises(ParseError, match="iCalendar"):
            client.get_course_schedule_ical(7620)
    finally:
        client._client.close()


@pytest.mark.asyncio
async def test_async_get_course_schedule_ical():
    request_seen = None

    async def handle(request: httpx.Request) -> httpx.Response:
        nonlocal request_seen
        request_seen = request
        return httpx.Response(200, text=ICAL)

    client = AsyncDaisyClient(username="test", password="test")
    client._authenticated = True
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    try:
        calendar = await client.get_course_schedule_ical("7620")
    finally:
        await client._client.aclose()

    assert calendar.startswith("BEGIN:VCALENDAR")
    assert request_seen is not None
    assert request_seen.url.params["id"] == "7620"


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
    # The detail page carries the same period as the search result.
    assert (detail.start_date, detail.end_date) == (prog2.start_date, prog2.end_date)

    english = daisy_client.get_course(prog2.momenttillf_id, language="en")
    assert english.name == "Programming 2"
    assert (english.start_date, english.end_date) == (detail.start_date, detail.end_date)

    exams = daisy_client.get_course_exams(prog2.momenttillf_id)
    english_exams = daisy_client.get_course_exams(prog2.momenttillf_id, language="en")
    assert any(e.kind == "Ordinarie tenta" and e.start and e.rooms for e in exams)
    assert [(e.date, e.start_time) for e in english_exams] == [
        (e.date, e.start_time) for e in exams
    ]
    assert exams[0].examination != english_exams[0].examination

    with pytest.raises(ParseError):
        daisy_client.get_course_exams(99999999)

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
