"""Handledning HTML parsing functions."""

import re
from datetime import date, datetime

from ..exceptions import ParseError
from ..models import HandledningSession, QueueEntry, QueueStatus, Student, Teacher
from ..utils import extract_text, parse_html, parse_time


def parse_teacher_sessions(html: str, default_username: str) -> list[HandledningSession]:
    """Parse teacher sessions from HTML.

    Args:
        html: HTML content
        default_username: Default username to use for teacher if not found in HTML

    Returns:
        List of HandledningSession objects
    """
    soup = parse_html(html)
    sessions = []

    session_divs = soup.find_all("div", class_=re.compile(r"session|handledning"))

    for session_div in session_divs:
        course_elem = session_div.find(class_=re.compile(r"course"))
        teacher_elem = session_div.find(class_=re.compile(r"teacher|lärare"))
        time_elem = session_div.find(class_=re.compile(r"time|tid"))
        room_elem = session_div.find(class_=re.compile(r"room|rum"))
        status_elem = session_div.find(class_=re.compile(r"status|active"))

        if not course_elem or not time_elem:
            continue

        course_text = extract_text(course_elem)
        course_match = re.match(r"([A-Z]{2}\d{4})\s*-?\s*(.*)", course_text)

        if course_match:
            course_code = course_match.group(1)
            course_name = course_match.group(2).strip()
        else:
            course_code = course_text
            course_name = ""

        time_text = extract_text(time_elem)
        time_match = re.search(r"(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})", time_text)

        if not time_match:
            continue

        try:
            start_time = parse_time(time_match.group(1))
            end_time = parse_time(time_match.group(2))
        except ValueError as e:
            raise ParseError(f"Failed to parse time from session: {e}") from e

        # Extract teacher info
        teacher_text = extract_text(teacher_elem) if teacher_elem else default_username
        teacher = Teacher(username=teacher_text)

        # Extract room
        room = extract_text(room_elem) if room_elem else None

        # Check if active
        is_active = False
        if status_elem:
            status_text = extract_text(status_elem).lower()
            is_active = "aktiv" in status_text or "active" in status_text

        # Queue will be empty - requires separate request
        queue = []

        session = HandledningSession(
            course_code=course_code,
            course_name=course_name,
            teacher=teacher,
            date=date.today(),
            start_time=start_time,
            end_time=end_time,
            room=room,
            queue=queue,
            is_active=is_active,
        )
        sessions.append(session)

    return sessions


def parse_queue(html: str) -> list[QueueEntry]:
    """Parse queue from HTML.

    Args:
        html: HTML content

    Returns:
        List of QueueEntry objects
    """
    soup = parse_html(html)
    queue = []

    queue_rows = soup.find_all("tr", class_=re.compile(r"queue-entry|student"))

    for i, row in enumerate(queue_rows, start=1):
        student_cell = row.find("td", class_=re.compile(r"student|name"))
        time_cell = row.find("td", class_=re.compile(r"time|timestamp"))
        status_cell = row.find("td", class_=re.compile(r"status"))
        room_cell = row.find("td", class_=re.compile(r"room"))

        if not student_cell:
            continue

        student_text = extract_text(student_cell)
        student = Student(username=student_text)

        # Parse timestamp
        timestamp = datetime.now()
        if time_cell:
            time_text = extract_text(time_cell)
            time_match = re.search(r"(\d{2}:\d{2})", time_text)
            if time_match:
                try:
                    queue_time = parse_time(time_match.group(1))
                    timestamp = datetime.combine(date.today(), queue_time)
                except ValueError as e:
                    raise ParseError(f"Failed to parse timestamp from queue entry: {e}") from e

        # Parse status
        status = QueueStatus.WAITING
        if status_cell:
            status_text = extract_text(status_cell).lower()
            if "pågår" in status_text or "progress" in status_text:
                status = QueueStatus.IN_PROGRESS
            elif "klar" in status_text or "completed" in status_text:
                status = QueueStatus.COMPLETED

        # Get room
        room = extract_text(room_cell) if room_cell else None

        entry = QueueEntry(
            student=student,
            position=i,
            status=status,
            timestamp=timestamp,
            room=room,
        )
        queue.append(entry)

    return queue
