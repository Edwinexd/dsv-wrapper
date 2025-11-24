"""Handledning client for lab supervision queue management."""

import os
import re
from datetime import date, datetime, time
from typing import Optional

import aiohttp
import requests

from .auth import AsyncShibbolethAuth, ShibbolethAuth
from .auth.cache_backend import CacheBackend
from .base import BaseAsyncClient
from .exceptions import AuthenticationError, HandledningError, ParseError, QueueError
from .models import (
    HandledningSession,
    QueueEntry,
    QueueStatus,
    Student,
    Teacher,
)
from .utils import (
    DEFAULT_HEADERS,
    DSV_URLS,
    build_url,
    extract_attr,
    extract_text,
    parse_html,
    parse_time,
)


class HandledningClient:
    """Synchronous client for Handledning system."""

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        mobile: bool = False,
        cache_backend: Optional[CacheBackend] = None,
        cache_ttl: int = 86400,
    ):
        """Initialize Handledning client.

        Args:
            username: SU username (default: read from SU_USERNAME env var)
            password: SU password (default: read from SU_PASSWORD env var)
            mobile: Use mobile version (default: False for desktop)
            cache_backend: Cache backend for authentication cookies (default: NullCache)
            cache_ttl: Cache TTL in seconds (default: 86400 = 24 hours)

        Raises:
            AuthenticationError: If username/password not provided and not in env vars
        """
        # Get credentials from env vars if not provided
        self.username = username or os.environ.get("SU_USERNAME")
        self.password = password or os.environ.get("SU_PASSWORD")

        if not self.username or not self.password:
            raise AuthenticationError(
                "Username and password must be provided either as arguments or "
                "via SU_USERNAME and SU_PASSWORD environment variables"
            )
        self.mobile = mobile
        self.base_url = DSV_URLS["handledning_mobile" if mobile else "handledning_desktop"]
        self.auth = ShibbolethAuth(self.username, self.password, cache_backend=cache_backend, cache_ttl=cache_ttl)
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self._authenticated = False

    def _ensure_authenticated(self) -> None:
        """Ensure the client is authenticated."""
        if not self._authenticated:
            cookies = self.auth._login("handledning")
            self.session.cookies.update(cookies)
            self._authenticated = True

    def get_teacher_sessions(
        self, teacher_username: Optional[str] = None
    ) -> list[HandledningSession]:
        """Get all active sessions for a teacher.

        Args:
            teacher_username: Teacher username (default: current user)

        Returns:
            List of HandledningSession objects
        """
        self._ensure_authenticated()

        if teacher_username is None:
            teacher_username = self.username

        url = build_url(self.base_url, "teacher", teacher_username)
        response = self.session.get(url)
        response.raise_for_status()

        return self._parse_teacher_sessions(response.text)

    def _parse_teacher_sessions(self, html: str) -> list[HandledningSession]:
        """Parse teacher sessions from HTML.

        Args:
            html: HTML content

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
                raise ParseError(f"Failed to parse time from queue entry: {e}")

            # Extract teacher info
            teacher_text = extract_text(teacher_elem) if teacher_elem else self.username
            teacher = Teacher(username=teacher_text)

            # Extract room
            room = extract_text(room_elem) if room_elem else None

            # Check if active
            is_active = False
            if status_elem:
                status_text = extract_text(status_elem).lower()
                is_active = "aktiv" in status_text or "active" in status_text

            # Get queue for this session (requires another request)
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

    def get_queue(self, session_id: str) -> list[QueueEntry]:
        """Get the queue for a specific session.

        Args:
            session_id: Session ID

        Returns:
            List of QueueEntry objects
        """
        self._ensure_authenticated()

        url = build_url(self.base_url, "queue", session_id)
        response = self.session.get(url)
        response.raise_for_status()

        return self._parse_queue(response.text)

    def _parse_queue(self, html: str) -> list[QueueEntry]:
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
                        raise ParseError(f"Failed to parse timestamp from queue entry: {e}")

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

    def add_to_queue(self, session_id: str, student_username: Optional[str] = None) -> bool:
        """Add a student to the queue.

        Args:
            session_id: Session ID
            student_username: Student username (default: current user)

        Returns:
            True if successfully added

        Raises:
            QueueError: If adding to queue fails
        """
        self._ensure_authenticated()

        if student_username is None:
            student_username = self.username

        url = build_url(self.base_url, "queue", session_id, "add")
        data = {"student": student_username}

        response = self.session.post(url, data=data)

        if not response.ok:
            raise QueueError(f"Failed to add to queue: {response.status_code}")

        # Check for error messages
        soup = parse_html(response.text)
        error_elem = soup.find("div", class_=re.compile(r"error|alert-danger"))

        if error_elem:
            raise QueueError(f"Failed to add to queue: {extract_text(error_elem)}")

        return True

    def remove_from_queue(self, session_id: str, student_username: str) -> bool:
        """Remove a student from the queue.

        Args:
            session_id: Session ID
            student_username: Student username

        Returns:
            True if successfully removed

        Raises:
            QueueError: If removal fails
        """
        self._ensure_authenticated()

        url = build_url(self.base_url, "queue", session_id, "remove")
        data = {"student": student_username}

        response = self.session.post(url, data=data)

        if not response.ok:
            raise QueueError(f"Failed to remove from queue: {response.status_code}")

        return True

    def activate_session(self, session_id: str) -> bool:
        """Activate a session (teacher only).

        Args:
            session_id: Session ID

        Returns:
            True if successfully activated

        Raises:
            HandledningError: If activation fails
        """
        self._ensure_authenticated()

        url = build_url(self.base_url, "session", session_id, "activate")

        response = self.session.post(url)

        if not response.ok:
            raise HandledningError(f"Failed to activate session: {response.status_code}")

        return True

    def deactivate_session(self, session_id: str) -> bool:
        """Deactivate a session (teacher only).

        Args:
            session_id: Session ID

        Returns:
            True if successfully deactivated

        Raises:
            HandledningError: If deactivation fails
        """
        self._ensure_authenticated()

        url = build_url(self.base_url, "session", session_id, "deactivate")

        response = self.session.post(url)

        if not response.ok:
            raise HandledningError(f"Failed to deactivate session: {response.status_code}")

        return True

    def get_all_active_sessions(self) -> list[HandledningSession]:
        """Get all currently active sessions.

        Returns:
            List of HandledningSession objects
        """
        self._ensure_authenticated()

        url = build_url(self.base_url, "sessions", "active")
        response = self.session.get(url)
        response.raise_for_status()

        return self._parse_teacher_sessions(response.text)

    def close(self) -> None:
        """Close the client session."""
        self.session.close()
        self.auth.__exit__(None, None, None)

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


class AsyncHandledningClient(BaseAsyncClient):
    """Asynchronous client for Handledning system."""

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        mobile: bool = False,
        cache_backend: Optional[CacheBackend] = None,
        cache_ttl: int = 86400,
    ):
        """Initialize async Handledning client.

        Args:
            username: SU username (default: read from SU_USERNAME env var)
            password: SU password (default: read from SU_PASSWORD env var)
            mobile: Use mobile version (default: False for desktop)
            cache_backend: Cache backend for authentication cookies (default: NullCache)
            cache_ttl: Cache TTL in seconds (default: 86400 = 24 hours)

        Raises:
            AuthenticationError: If username/password not provided and not in env vars
        """
        # Get credentials from env vars if not provided
        username = username or os.environ.get("SU_USERNAME")
        password = password or os.environ.get("SU_PASSWORD")

        if not username or not password:
            raise AuthenticationError(
                "Username and password must be provided either as arguments or "
                "via SU_USERNAME and SU_PASSWORD environment variables"
            )

        self.mobile = mobile
        super().__init__(
            username=username,
            password=password,
            base_url=DSV_URLS["handledning_mobile" if mobile else "handledning_desktop"],
            service="handledning",
            cache_backend=cache_backend,
            cache_ttl=cache_ttl,
        )

    async def get_teacher_sessions(
        self, teacher_username: Optional[str] = None
    ) -> list[HandledningSession]:
        """Get all active sessions for a teacher.

        Args:
            teacher_username: Teacher username (default: current user)

        Returns:
            List of HandledningSession objects
        """
        await self._ensure_authenticated()

        if teacher_username is None:
            teacher_username = self.username

        url = build_url(self.base_url, "teacher", teacher_username)

        async with self.session.get(url) as response:
            response.raise_for_status()
            html = await response.text()

        return self._parse_teacher_sessions(html)

    def _parse_teacher_sessions(self, html: str) -> list[HandledningSession]:
        """Parse teacher sessions from HTML (same as sync version)."""
        client = HandledningClient.__new__(HandledningClient)
        client.username = self.username
        return client._parse_teacher_sessions(html)

    async def get_queue(self, session_id: str) -> list[QueueEntry]:
        """Get the queue for a specific session.

        Args:
            session_id: Session ID

        Returns:
            List of QueueEntry objects
        """
        await self._ensure_authenticated()

        url = build_url(self.base_url, "queue", session_id)

        async with self.session.get(url) as response:
            response.raise_for_status()
            html = await response.text()

        return self._parse_queue(html)

    def _parse_queue(self, html: str) -> list[QueueEntry]:
        """Parse queue from HTML (same as sync version)."""
        client = HandledningClient.__new__(HandledningClient)
        return client._parse_queue(html)

    async def add_to_queue(self, session_id: str, student_username: Optional[str] = None) -> bool:
        """Add a student to the queue.

        Args:
            session_id: Session ID
            student_username: Student username (default: current user)

        Returns:
            True if successfully added

        Raises:
            QueueError: If adding to queue fails
        """
        await self._ensure_authenticated()

        if student_username is None:
            student_username = self.username

        url = build_url(self.base_url, "queue", session_id, "add")
        data = {"student": student_username}

        async with self.session.post(url, data=data) as response:
            if not response.ok:
                raise QueueError(f"Failed to add to queue: {response.status}")

            html = await response.text()

        # Check for error messages
        soup = parse_html(html)
        error_elem = soup.find("div", class_=re.compile(r"error|alert-danger"))

        if error_elem:
            raise QueueError(f"Failed to add to queue: {extract_text(error_elem)}")

        return True

    async def remove_from_queue(self, session_id: str, student_username: str) -> bool:
        """Remove a student from the queue.

        Args:
            session_id: Session ID
            student_username: Student username

        Returns:
            True if successfully removed

        Raises:
            QueueError: If removal fails
        """
        await self._ensure_authenticated()

        url = build_url(self.base_url, "queue", session_id, "remove")
        data = {"student": student_username}

        async with self.session.post(url, data=data) as response:
            if not response.ok:
                raise QueueError(f"Failed to remove from queue: {response.status}")

        return True

    async def activate_session(self, session_id: str) -> bool:
        """Activate a session (teacher only).

        Args:
            session_id: Session ID

        Returns:
            True if successfully activated

        Raises:
            HandledningError: If activation fails
        """
        await self._ensure_authenticated()

        url = build_url(self.base_url, "session", session_id, "activate")

        async with self.session.post(url) as response:
            if not response.ok:
                raise HandledningError(f"Failed to activate session: {response.status}")

        return True

    async def deactivate_session(self, session_id: str) -> bool:
        """Deactivate a session (teacher only).

        Args:
            session_id: Session ID

        Returns:
            True if successfully deactivated

        Raises:
            HandledningError: If deactivation fails
        """
        await self._ensure_authenticated()

        url = build_url(self.base_url, "session", session_id, "deactivate")

        async with self.session.post(url) as response:
            if not response.ok:
                raise HandledningError(f"Failed to deactivate session: {response.status}")

        return True

    async def get_all_active_sessions(self) -> list[HandledningSession]:
        """Get all currently active sessions.

        Returns:
            List of HandledningSession objects
        """
        await self._ensure_authenticated()

        url = build_url(self.base_url, "sessions", "active")

        async with self.session.get(url) as response:
            response.raise_for_status()
            html = await response.text()

        return self._parse_teacher_sessions(html)
