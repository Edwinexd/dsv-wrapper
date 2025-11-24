"""Daisy HTML parsing functions."""

import logging
import re
from datetime import date, datetime
from urllib.parse import urlparse

from ..exceptions import ParseError
from ..models import RoomActivity, RoomCategory, RoomTime, Schedule, Staff, Student
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


def parse_students(html: str) -> list[Student]:
    """Parse student search results.

    Args:
        html: HTML content from student search

    Returns:
        List of Student objects
    """
    soup = parse_html(html)
    students = []

    student_rows = soup.find_all("tr", class_=re.compile(r"student-row|student"))

    for row in student_rows:
        username_cell = row.find("td", class_=re.compile(r"username|user"))
        if username_cell is None:
            continue

        username = extract_text(username_cell)

        name_cell = row.find("td", class_=re.compile(r"name|full-name"))
        email_cell = row.find("td", class_=re.compile(r"email|mail"))
        program_cell = row.find("td", class_=re.compile(r"program|programme"))

        student = Student(
            username=username,
            first_name=extract_text(name_cell).split()[0] if name_cell else None,
            last_name=(" ".join(extract_text(name_cell).split()[1:]) if name_cell else None),
            email=extract_text(email_cell) if email_cell else None,
            program=extract_text(program_cell) if program_cell else None,
        )
        students.append(student)

    return students


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


def parse_staff_details(person_id: str, html: str, base_url: str) -> Staff:
    """Parse detailed staff information from profile page.

    Args:
        person_id: Person ID
        html: HTML content from profile page
        base_url: Base URL for constructing URLs

    Returns:
        Staff object with details
    """
    soup = parse_html(html)

    # Extract profile picture
    profile_pic_url = None
    img_tag = soup.find("img", src=lambda x: x and "daisy.Jpg" in x)
    if img_tag:
        pic_src = img_tag.get("src")
        if not pic_src:
            raise ParseError("Profile image tag found but missing src attribute")
        if pic_src.startswith("/"):
            parsed = urlparse(base_url)
            profile_pic_url = f"{parsed.scheme}://{parsed.netloc}{pic_src}"

    # Extract email
    email = None
    email_link = soup.find("a", href=lambda x: x and "mailto:" in x)
    if email_link:
        href = email_link.get("href")
        if not href:
            raise ParseError("Email link found but missing href attribute")
        email = href.replace("mailto:", "")

    # Extract name from page
    name = ""
    # Name is in div with class="fonsterrub"
    name_div = soup.find("div", class_="fonsterrub")
    if name_div:
        name = extract_text(name_div)
    # Fallback to h1 if fonsterrub not found
    if not name:
        h1_tag = soup.find("h1")
        if h1_tag:
            name = extract_text(h1_tag)

    # Extract room, location, units, titles from tables
    room = None
    location = None
    units = []
    swedish_title = None
    english_title = None
    phone = None

    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) >= 2:
                label = cells[0].get_text().strip().lower()
                value = cells[1].get_text().strip()

                if "rum" in label or "room" in label:
                    room = value
                elif "lokal" in label or "plats" in label or "arbetsplats" in label:
                    location = value
                elif "units" in label or "enhet" in label:
                    units = [u.strip() for u in value.split(",") if u.strip()]
                elif "svensk" in label and "titel" in label:
                    swedish_title = value
                elif "engelsk" in label or "english" in label:
                    english_title = value
                elif "telefon" in label or "phone" in label:
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
    )
