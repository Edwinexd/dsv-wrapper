"""Daisy HTML parsing functions."""

import logging
import re
from datetime import date, datetime
from urllib.parse import urlparse

from bs4 import NavigableString

from ..exceptions import ParseError
from ..models import (
    CourseResponsibility,
    CourseStaff,
    DaisyCourse,
    RoomActivity,
    RoomCategory,
    RoomTime,
    Schedule,
    Semester,
    Staff,
    Student,
)
from ..utils import extract_text, parse_html, parse_time

logger = logging.getLogger(__name__)


def parse_schedule(html: str) -> Schedule:
    """Parse schedule HTML into Schedule object.

    Parses the Daisy schedule table (class='bgTabell') into a Schedule object.

    Args:
        html: HTML content from Daisy

    Returns:
        Schedule object with activities

    Raises:
        ParseError: If parsing fails
    """
    soup = parse_html(html)

    # Find the schedule table
    schedule_table = soup.find("table", {"class": "bgTabell"})
    if schedule_table is None:
        raise ParseError("Could not find schedule table (class='bgTabell')")

    rows = schedule_table.find_all("tr")
    if len(rows) < 3:
        raise ParseError("Schedule table has insufficient rows")

    # Extract room names from second row (first row is headers)
    room_names = [extract_text(td) for td in rows[1].find_all("td")[1:]]

    # Parse events for each room
    room_events = [[] for _ in room_names]
    room_offsets = [0] * len(room_names)

    for row in rows[2:]:
        cells = row.find_all("td")
        if not cells:
            continue

        time_slot = extract_text(cells[0])
        slicer = 0

        for i in range(len(room_names)):
            if room_offsets[i] > 0:
                # Continue previous event
                room_events[i].append((time_slot, room_events[i][-1][1]))
                room_offsets[i] -= 1
                continue

            if slicer + 1 >= len(cells):
                break

            cell = cells[slicer + 1]
            link = cell.find("a")
            if link and (cell.get("rowspan") or extract_text(cell)):
                # Extract event details
                event_text = extract_text(list(link.children)[0] if link.children else link)
                duration_span = cell.find("span", {"class": "mini"})

                if duration_span:
                    duration_text = extract_text(duration_span)
                    if ": " in duration_text:
                        duration = duration_text.split(": ")[1]
                        row_span = int(cell.get("rowspan") or 1)
                        start_hour = int(duration.split("-")[0].split(":")[0])
                        end_hour = start_hour + row_span

                        room_events[i].append((time_slot, event_text))
                        room_offsets[i] = row_span - 1

            slicer += 1

    # Convert to activities dict
    activities = {}
    for i, room_name in enumerate(room_names):
        activities[room_name] = []
        for time_slot, event in room_events[i]:
            if "-" in time_slot:
                try:
                    start_hour = int(time_slot.split("-")[0])
                    end_hour = int(time_slot.split("-")[1])
                    activities[room_name].append(
                        RoomActivity(
                            time_slot_start=RoomTime(start_hour),
                            time_slot_end=RoomTime(end_hour),
                            event=event,
                        )
                    )
                except (ValueError, KeyError) as e:
                    raise ParseError(f"Failed to parse activity time slot: {e}") from e

    # Extract metadata
    room_category_title = extract_text(rows[0].find_all("td")[1].find("b"))
    category_link = rows[0].find_all("td")[1].find("a")
    room_category_id = int(category_link.get("href").split("&")[1].split("=")[1])

    date_column = list(rows[0].find_all("td")[1].children)[2]
    date_match = re.findall(r"(\d{4})-(\d{2})-(\d{2})", str(date_column))[0]
    schedule_datetime = datetime(int(date_match[0]), int(date_match[1]), int(date_match[2]))

    return Schedule(
        activities=activities,
        room_category_title=room_category_title,
        room_category_id=room_category_id,
        room_category=RoomCategory(room_category_id),
        datetime=schedule_datetime,
    )


def parse_students(html: str, base_url: str) -> list[Student]:
    """Parse a Daisy student search results page (``/sok/visastudent.jspa``).

    Columns observed: ``Efternamn``, ``Förnamn``, ``E-post``. The leading
    columns hold the personinfo icon (with the personID link) and an
    add-to-list icon. Username is *not* on the search page — fetch the
    student profile or call :meth:`Student.get_username` for that.
    """
    soup = parse_html(html)
    students: list[Student] = []

    for table in soup.find_all("table", class_="randig"):
        rows = table.find_all("tr")
        if not rows:
            continue
        headers = [
            _collapse_ws(c.get_text(" ", strip=True)) for c in rows[0].find_all(["th", "td"])
        ]
        wanted = {"Efternamn", "Förnamn", "E-post"}
        if not wanted.issubset(set(headers)):
            continue
        col_index = {h: i for i, h in enumerate(headers)}

        def _cell(cells, header: str, _idx=col_index):
            i = _idx.get(header)
            if i is None or i >= len(cells):
                return None
            return cells[i]

        for row in rows[1:]:
            cells = row.find_all("td")
            if not cells:
                continue
            link = row.find("a", href=lambda h: h and "studentinfo.jspa" in h and "personID" in h)
            person_id: str | None = None
            profile_url: str | None = None
            if link is not None:
                href = link["href"]
                m = _PERSON_ID_RE.search(href)
                if m:
                    person_id = m.group(1)
                    profile_url = href if href.startswith("http") else f"{base_url}{href}"

            last_cell = _cell(cells, "Efternamn")
            first_cell = _cell(cells, "Förnamn")
            email_cell = _cell(cells, "E-post")
            last_name = _collapse_ws(last_cell.get_text(" ", strip=True)) if last_cell else None
            first_name = _collapse_ws(first_cell.get_text(" ", strip=True)) if first_cell else None
            email = _collapse_ws(email_cell.get_text(" ", strip=True)) if email_cell else None
            email = email or None

            students.append(
                Student(
                    person_id=person_id,
                    first_name=first_name or None,
                    last_name=last_name or None,
                    email=email,
                    profile_url=profile_url,
                )
            )
        break  # only one randig table holds the results

    return students


def parse_student_details(person_id: str, html: str, base_url: str) -> Student:
    """Parse a Daisy student profile page (``/anstalld/student/studentinfo.jspa``).

    Extracts the SU username, name, contact information, and address.
    The page reuses the same label/value row convention as anstalld profiles.
    """
    soup = parse_html(html)

    name = ""
    name_div = soup.find("div", class_="fonsterrub")
    if name_div is not None:
        name = _collapse_ws(name_div.get_text(" ", strip=True))

    first_name = last_name = None
    if name:
        first_name, last_name = _split_name(name)

    username: str | None = None
    email: str | None = None
    phone: str | None = None
    program: str | None = None
    student_id: str | None = None
    address: str | None = None

    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        label = _collapse_ws(cells[0].get_text(" ", strip=True))
        if not label:
            continue
        value_cell = cells[1]
        value = _collapse_ws(value_cell.get_text(" ", strip=True))
        low = label.lower()

        if "användarnamn" in low:
            # Most students have one SU login; some have multiple realms.
            # Return the first one as the canonical username.
            parts = _split_list(value)
            username = parts[0] if parts else (value or None)
        elif "e-post" in low or low == "epost:":
            email = value or None
        elif "telefon" in low:
            phone = value or None
        elif "program" in low:
            program = value or None
        elif "personnummer" in low or "studentid" in low.replace("-", ""):
            student_id = value or None
        elif "adress" in low:
            raw_addr = value_cell.get_text("\n", strip=True)
            lines = [_collapse_ws(line) for line in raw_addr.splitlines() if line.strip()]
            address = "\n".join(lines) or None

    return Student(
        person_id=person_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
        student_id=student_id,
        program=program,
        profile_url=f"{base_url}/anstalld/student/studentinfo.jspa?personID={person_id}",
        address=address,
    )


def parse_activities(html: str, room_id: str, schedule_date: date) -> list[RoomActivity]:
    """Parse room activities from HTML.

    Args:
        html: HTML content
        room_id: Room ID
        schedule_date: Schedule date

    Returns:
        List of RoomActivity objects
    """
    soup = parse_html(html)
    activities = []

    activity_rows = soup.find_all("div", class_=re.compile(r"activity|event"))

    for activity_div in activity_rows:
        course_elem = activity_div.find(class_=re.compile(r"course"))
        time_elem = activity_div.find(class_=re.compile(r"time"))

        if not time_elem:
            continue

        time_text = extract_text(time_elem)
        time_match = re.search(r"(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})", time_text)

        if time_match:
            try:
                start_time = parse_time(time_match.group(1))
                end_time = parse_time(time_match.group(2))

                activity = RoomActivity(
                    room_name=room_id,
                    course_code=extract_text(course_elem) if course_elem else None,
                    start_time=start_time,
                    end_time=end_time,
                    date=schedule_date,
                )
                activities.append(activity)
            except ValueError as e:
                raise ParseError(f"Failed to parse activity times: {e}") from e

    return activities


def parse_staff_search(html: str, base_url: str) -> list[Staff]:
    """Parse staff search results.

    Args:
        html: HTML content from search results
        base_url: Base URL for constructing profile URLs

    Returns:
        List of Staff objects
    """
    soup = parse_html(html)
    staff_list = []

    tables = soup.find_all("table", class_="randig")
    for table in tables:
        rows = table.find_all("tr")

        for row in rows[1:]:  # Skip header
            cols = row.find_all("td")
            if len(cols) >= 2:
                profile_link = row.find("a", href=lambda x: x and "personID" in x)
                if profile_link:
                    href = profile_link.get("href")
                    if not href:
                        raise ParseError("Profile link found but missing href attribute")
                    person_id_match = re.search(r"personID=(\d+)", href)
                    if person_id_match:
                        person_id = person_id_match.group(1)
                        name = profile_link.get_text().strip()

                        staff = Staff(
                            person_id=person_id,
                            name=name,
                            profile_url=f"{base_url}{href}",
                        )
                        staff_list.append(staff)

    logger.info(f"Found {len(staff_list)} staff members")
    return staff_list


_LIST_SPLIT_RE = re.compile(r"\s*,\s*")
_WS_RE = re.compile(r"\s+")


def _split_list(value: str) -> list[str]:
    """Split a comma-separated cell value into trimmed non-empty entries."""
    return [item for item in (s.strip() for s in _LIST_SPLIT_RE.split(value)) if item]


def _collapse_ws(value: str) -> str:
    """Collapse internal whitespace runs to a single space."""
    return _WS_RE.sub(" ", value).strip()


def _label_matches(label: str, *needles: str) -> bool:
    """Case-insensitive label match against any of ``needles``."""
    low = label.lower()
    return any(n in low for n in needles)


def _parse_responsibility_row(label_cell, value_cell) -> CourseResponsibility | None:
    """Parse a Kurs-/delkursansvarig row into a CourseResponsibility.

    The label column contains the current semester wrapped in arrow links
    (e.g. ``<< VT2026 >>``); the value column lists course beteckningar.
    """
    label_text = _collapse_ws(label_cell.get_text(" ", strip=True))
    m = re.search(r"\b([VH]T)\s*(\d{4})\b", label_text)
    if not m:
        return None
    try:
        sem = Semester.from_label(m.group(1) + m.group(2))
    except ValueError:
        return None
    # Daisy renders beteckningar inside a single <b>…</b> text node with
    # newlines between them; split on whitespace to recover individual codes.
    raw = value_cell.get_text("\n", strip=True)
    beteckningar = [item for item in re.split(r"\s+", raw) if item]
    return CourseResponsibility(semester=sem, beteckningar=beteckningar)


def parse_staff_details(person_id: str, html: str, base_url: str) -> Staff:
    """Parse detailed staff information from a Daisy profile page.

    Populates the rich :class:`Staff` fields (usernames, address, office_hours,
    research areas, course responsibilities, …) in addition to the basics.

    Args:
        person_id: Person ID
        html: HTML content from profile page
        base_url: Base URL for constructing URLs

    Returns:
        Staff object with details
    """
    soup = parse_html(html)

    # Profile picture
    profile_pic_url = None
    img_tag = soup.find("img", src=lambda x: x and "daisy.Jpg" in x)
    if img_tag:
        pic_src = img_tag.get("src")
        if not pic_src:
            raise ParseError("Profile image tag found but missing src attribute")
        if pic_src.startswith("/"):
            parsed = urlparse(base_url)
            profile_pic_url = f"{parsed.scheme}://{parsed.netloc}{pic_src}"

    # Primary email (mailto link)
    email = None
    email_link = soup.find("a", href=lambda x: x and "mailto:" in x)
    if email_link:
        href = email_link.get("href")
        if not href:
            raise ParseError("Email link found but missing href attribute")
        email = href.replace("mailto:", "")

    # Name from div.fonsterrub (Daisy convention) or fallback h1.
    name = ""
    name_div = soup.find("div", class_="fonsterrub")
    if name_div:
        name = extract_text(name_div)
    if not name:
        h1_tag = soup.find("h1")
        if h1_tag:
            name = extract_text(h1_tag)

    # Walk every label/value <tr> across the profile.
    room: str | None = None
    location: str | None = None
    units: list[str] = []
    swedish_title: str | None = None
    english_title: str | None = None
    phone: str | None = None
    usernames: list[str] = []
    address: str | None = None
    home_phone: str | None = None
    alt_phone: str | None = None
    office_hours: str | None = None
    exam_systems: list[str] = []
    research_areas: list[str] = []
    website: str | None = None
    responsibilities: list[CourseResponsibility] = []

    seen_rows: set[int] = set()
    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        # Skip rows we've seen via a parent table iteration
        if id(row) in seen_rows:
            continue
        seen_rows.add(id(row))

        label = _collapse_ws(cells[0].get_text(" ", strip=True))
        if not label:
            continue
        value_cell = cells[1]
        value = _collapse_ws(value_cell.get_text(" ", strip=True))

        # Profile pages use the same template as the staff search, so the
        # same labels (E-post, Arbetsrum, etc.) appear here.
        if _label_matches(label, "kurs-/delkursansvarig"):
            entry = _parse_responsibility_row(cells[0], value_cell)
            if entry is not None:
                responsibilities.append(entry)
        elif _label_matches(label, "användarnamn"):
            usernames = _split_list(value)
        elif _label_matches(label, "arbetsrum"):
            room = value
        elif _label_matches(label, "arbetstelefon"):
            phone = value
        elif _label_matches(label, "hemtelefon"):
            home_phone = value
        elif _label_matches(label, "alternativ telefon"):
            alt_phone = value
        elif _label_matches(label, "adress"):
            # Preserve newline structure (street / postcode+city / country).
            raw_addr = value_cell.get_text("\n", strip=True)
            lines = [_collapse_ws(line) for line in raw_addr.splitlines() if line.strip()]
            address = "\n".join(lines) or None
        elif _label_matches(label, "mottagningstid"):
            office_hours = value
        elif _label_matches(label, "utbildad för examinationssystem"):
            exam_systems = _split_list(value)
        elif _label_matches(label, "enheter") or _label_matches(label, "units"):
            units = _split_list(value)
        elif _label_matches(label, "forskningsområden"):
            research_areas = _split_list(value)
        elif _label_matches(label, "webbsida"):
            website = value
        elif _label_matches(label, "lokal", "plats", "arbetsplats"):
            location = value
        elif _label_matches(label, "svensk") and "titel" in label.lower():
            swedish_title = value
        elif _label_matches(label, "engelsk", "english"):
            english_title = value
        elif _label_matches(label, "telefon", "phone") and phone is None:
            phone = value

    return Staff(
        person_id=person_id,
        name=name,
        email=email,
        room=room,
        location=location,
        profile_url=f"{base_url}/anstalld/anstalldinfo.jspa?personID={person_id}",
        profile_pic_url=profile_pic_url,
        units=units,
        swedish_title=swedish_title,
        english_title=english_title,
        phone=phone,
        usernames=usernames,
        address=address,
        home_phone=home_phone,
        alt_phone=alt_phone,
        office_hours=office_hours,
        exam_systems=exam_systems,
        research_areas=research_areas,
        website=website,
        course_responsibilities=responsibilities,
    )


# ---------------------------------------------------------------------------
# Course (moment) search and detail parsers
# ---------------------------------------------------------------------------

_DATE_RANGE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})\s*--\s*(\d{4}-\d{2}-\d{2})")
_TERM_RE = re.compile(r"^([VH]T)(\d{4})$")
_RESULT_RANGE_RE = re.compile(r"Resultat\s+(\d+)\s+till\s+(\d+)\s+av\s+(\d+)")
_ECTS_RE = re.compile(r"([\d,.]+)")
_PERSON_ID_RE = re.compile(r"personID=(\d+)")
_MOMENTTILLF_RE = re.compile(r"momenttillfID=(\d+)")
_MOMENT_ID_RE = re.compile(r"[?&]id=(\d+)")


def _parse_ects(text: str) -> float | None:
    """Parse a Swedish ECTS number like '7,5' or '7.5' into a float."""
    if not text:
        return None
    m = _ECTS_RE.search(text.replace("\xa0", " "))
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return None


def _parse_date_range(text: str) -> tuple[date | None, date | None]:
    """Parse a ``YYYY-MM-DD -- YYYY-MM-DD`` cell."""
    m = _DATE_RANGE_RE.search(text)
    if not m:
        return None, None
    try:
        start = datetime.strptime(m.group(1), "%Y-%m-%d").date()
        end = datetime.strptime(m.group(2), "%Y-%m-%d").date()
    except ValueError:
        return None, None
    return start, end


def _parse_semester_cell(text: str) -> Semester | None:
    """Parse a 'VT2026'/'HT2025' table cell."""
    text = text.strip()
    m = _TERM_RE.match(text)
    if not m:
        return None
    try:
        return Semester.from_label(text)
    except ValueError:
        return None


def parse_course_search(
    html: str, base_url: str
) -> tuple[list[DaisyCourse], int | None, int | None, int | None]:
    """Parse a Daisy course search page (``/sok/sokmoment.jspa``).

    Returns a tuple ``(courses, range_from, range_to, total)`` where the trailing
    integers come from the "Resultat X till Y av Z" header. They are ``None``
    if the page does not include a result range (e.g. no hits).
    """
    soup = parse_html(html)

    # Locate the result range line; bail out cleanly on empty result pages.
    range_from = range_to = total = None
    for text in soup.stripped_strings:
        m = _RESULT_RANGE_RE.search(text)
        if m:
            range_from, range_to, total = (int(g) for g in m.groups())
            break

    courses: list[DaisyCourse] = []

    # The results table is the *second* <table> on the page (the first holds
    # the toolbar). Locate it by header row that contains "Beteckning".
    target_table = None
    for table in soup.find_all("table"):
        headers = [_collapse_ws(th.get_text(" ", strip=True)) for th in table.find_all("th")]
        if any("Beteckning" in h for h in headers):
            target_table = table
            break
    if target_table is None:
        return courses, range_from, range_to, total

    rows = target_table.find_all("tr")
    for row in rows[1:]:
        cells = row.find_all("td")
        # Layout: icon | icon | icon | name | hp | termin | tidsperiod | beteckning
        if len(cells) < 8:
            continue

        # icon column 0 holds the momentinfo link with the moment ID
        info_link = cells[0].find("a")
        schedule_link = cells[1].find("a")
        participants_link = cells[2].find("a")
        if info_link is None:
            continue
        info_href = info_link.get("href") or ""
        m = _MOMENT_ID_RE.search(info_href)
        if not m:
            continue
        momenttillf_id = m.group(1)

        name = _collapse_ws(cells[3].get_text(" ", strip=True))
        ects = _parse_ects(cells[4].get_text(strip=True))
        semester = _parse_semester_cell(cells[5].get_text(strip=True))
        start_date, end_date = _parse_date_range(cells[6].get_text(" ", strip=True))
        beteckning = _collapse_ws(cells[7].get_text(" ", strip=True))

        def _abs(href: str | None) -> str | None:
            if not href:
                return None
            if href.startswith("http"):
                return href
            return f"{base_url}{href}"

        courses.append(
            DaisyCourse(
                momenttillf_id=momenttillf_id,
                beteckning=beteckning,
                name=name,
                ects=ects,
                semester=semester,
                start_date=start_date,
                end_date=end_date,
                info_url=_abs(info_href),
                schedule_url=_abs(schedule_link.get("href") if schedule_link else None),
                participants_url=_abs(participants_link.get("href") if participants_link else None),
            )
        )

    return courses, range_from, range_to, total


def parse_course_detail(html: str, momenttillf_id: str, base_url: str) -> DaisyCourse:
    """Parse the public ``/servlet/momentinfo.Momentinfo?id=…`` page.

    The page title encodes ``BETECKNING SEMESTER - Course name``. The body
    contains a "Namn / Enhet / Poäng" line and an external syllabus link in
    the "Kurser" section.
    """
    soup = parse_html(html)

    # Title pattern: "Daisy » PROG2 VT2026 - Programmering 2"
    raw_title = soup.title.get_text(strip=True) if soup.title else ""
    title = raw_title.split("»", 1)[-1].strip()
    beteckning: str = ""
    name: str = ""
    semester: Semester | None = None
    head, _, tail = title.partition(" - ")
    name = _collapse_ws(tail) if tail else ""
    if head:
        parts = head.split()
        if len(parts) >= 2 and _TERM_RE.match(parts[-1]):
            semester = _parse_semester_cell(parts[-1])
            beteckning = " ".join(parts[:-1])
        else:
            beteckning = head

    ects: float | None = None
    unit: str | None = None
    syllabus_url: str | None = None

    # The "Namn: ... Enhet: ... Poäng: 7,5 hp" line lives in a single <td>.
    for td in soup.find_all("td"):
        text = td.get_text(" ", strip=True)
        if "Poäng:" in text and "Enhet:" in text:
            m_poang = re.search(r"Poäng:\s*([\d,.]+)\s*hp", text)
            if m_poang:
                ects = _parse_ects(m_poang.group(1))
            m_enhet = re.search(r"Enhet:\s*([^\s]+)", text)
            if m_enhet:
                unit = m_enhet.group(1)
            # Also recover the name if we didn't have it.
            if not name:
                m_name = re.search(r"Namn:\s*(.*?)\s+Enhet:", text)
                if m_name:
                    name = _collapse_ws(m_name.group(1))
            break

    # Find external syllabus link (planarkiv)
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "planarkiv" in href and "utbildning.su.se" in href:
            syllabus_url = href
            break

    return DaisyCourse(
        momenttillf_id=momenttillf_id,
        beteckning=beteckning or "",
        name=name or "",
        ects=ects,
        semester=semester,
        info_url=f"{base_url}/servlet/momentinfo.Momentinfo?id={momenttillf_id}",
        schedule_url=f"{base_url}/servlet/schema.moment.Momentschema?id={momenttillf_id}",
        participants_url=f"{base_url}/anstalld/moment/momentNav.jspa?momenttillfID={momenttillf_id}&akt=mdv",
        syllabus_url=syllabus_url,
        unit=unit,
    )


def _split_name(full: str) -> tuple[str | None, str | None]:
    """Split a Swedish display name into (first_names, last_name).

    Daisy uses "FirstName(s) LastName" with no comma. Hyphenated first names
    (Andrés-Emilio) stay attached. Single-word inputs return ``(name, None)``
    so callers can detect that there's nothing to do a search with.
    """
    parts = [p for p in re.split(r"\s+", full.strip()) if p]
    if not parts:
        return None, None
    if len(parts) == 1:
        return parts[0], None
    return " ".join(parts[:-1]), parts[-1]


def parse_course_participants(html: str, base_url: str) -> list[CourseStaff]:
    """Parse the role-grouped medverkande section from a momentinfo page.

    The public ``/servlet/momentinfo.Momentinfo?id=…`` page contains a row
    headed *Medverkande* whose body is one ``<div class="brodtext">`` per role
    group. Each group starts with ``<b>RoleName</b>`` and then ``<a>…</a>Name``
    entries (one per person). The same person frequently appears under
    multiple role groups; we merge them so each ``CourseStaff`` shows up
    exactly once with all their roles.

    Unlike ``akt=mdv``, this page is readable for any course, not just ones
    the authenticated user is teaching.
    """
    soup = parse_html(html)

    # The "Medverkande" section is delimited by a tabellRubrik header row
    # followed by a single <tr> whose <td> contains the brodtext role groups.
    # Find that <td> first.
    medverkande_td = None
    for tr in soup.find_all("tr"):
        rubrik = tr.find("td", class_=lambda c: c and "tabellRubrik" in c)
        if rubrik and "Medverkande" in rubrik.get_text(strip=True):
            nxt = tr.find_next_sibling("tr")
            if nxt is not None:
                td = nxt.find("td")
                if td is not None:
                    medverkande_td = td
            break
    if medverkande_td is None:
        return []

    # Walk each <div class="brodtext"> and parse its role + people.
    # A person may appear linked (with personID) or as plain text (typically
    # student-handledare). We key linked rows by ``person_id`` and unlinked
    # rows by ``name`` to merge across role groups.
    by_pid: dict[str, CourseStaff] = {}
    by_name: dict[str, CourseStaff] = {}
    order: list[tuple[str, str]] = []  # (kind, key); kind in {"pid","name"}

    def _add(key_kind: str, key: str, *, role: str, **fields) -> None:
        store = by_pid if key_kind == "pid" else by_name
        existing = store.get(key)
        if existing is None:
            store[key] = CourseStaff(roles=[role], **fields)
            order.append((key_kind, key))
        else:
            if role not in existing.roles:
                existing.roles.append(role)
            # Linked entries discovered later should backfill an unlinked one.
            for f, v in fields.items():
                if v is not None and getattr(existing, f) in (None, ""):
                    object.__setattr__(existing, f, v)

    for div in medverkande_td.find_all("div", class_="brodtext"):
        role_b = div.find("b")
        if role_b is None:
            continue
        role = _collapse_ws(role_b.get_text(" ", strip=True))
        if not role:
            continue

        # Iterate the contents of <div> in document order. After the leading
        # <b>Role</b>, names appear either as ``<a>…</a>NameText`` (linked)
        # or as bare text nodes (unlinked). <br/> tags separate entries.
        children = list(div.children)
        seen_role_marker = False
        i = 0
        while i < len(children):
            node = children[i]
            if not seen_role_marker:
                if getattr(node, "name", None) == "b":
                    seen_role_marker = True
                i += 1
                continue
            # Linked entry: <a href=…personID=…>(img)</a> followed by name text
            if getattr(node, "name", None) == "a":
                href = node.get("href") or ""
                m = _PERSON_ID_RE.search(href)
                next_text = ""
                if i + 1 < len(children):
                    nxt = children[i + 1]
                    if isinstance(nxt, NavigableString):
                        next_text = _collapse_ws(str(nxt))
                if m and next_text:
                    pid = m.group(1)
                    first, last = _split_name(next_text)
                    profile_url = href if href.startswith("http") else f"{base_url}{href}"
                    _add(
                        "pid",
                        pid,
                        role=role,
                        person_id=pid,
                        name=next_text,
                        first_name=first,
                        last_name=last,
                        profile_url=profile_url,
                    )
                    i += 2
                    continue
            # Plain-text name (unlinked student-handledare).
            if isinstance(node, NavigableString):
                text = _collapse_ws(str(node))
                if text:
                    first, last = _split_name(text)
                    if last is None:
                        # Single-token entries are not real names — skip.
                        i += 1
                        continue
                    _add(
                        "name",
                        text,
                        role=role,
                        name=text,
                        first_name=first,
                        last_name=last,
                    )
            i += 1

    out: list[CourseStaff] = []
    for kind, key in order:
        out.append(by_pid[key] if kind == "pid" else by_name[key])
    return out
