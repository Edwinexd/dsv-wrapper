"""Handledning client for lab supervision queue management."""

import os
import re
from datetime import date, datetime, time
from typing import Optional

import httpx

from .auth import AsyncShibbolethAuth, ShibbolethAuth
from .auth.cache_backend import CacheBackend
from .exceptions import AuthenticationError, HandledningError, QueueError
from .models import (
    HandledningSession,
    QueueEntry,
    QueueStatus,
    Student,
    Teacher,
)
from .parsers import handledning as handledning_parsers
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
        self.client = httpx.Client(headers=DEFAULT_HEADERS, follow_redirects=True)
        self._authenticated = False

    def _ensure_authenticated(self) -> None:
        """Ensure the client is authenticated."""
        if not self._authenticated:
            cookies = self.auth._login("handledning")
            # Copy cookies from auth client to this client
            for cookie in self.auth.client.cookies.jar:
                self.client.cookies.set(
                    cookie.name,
                    cookie.value,
                    domain=cookie.domain,
                    path=cookie.path
                )
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
        response = self.client.get(url)
        response.raise_for_status()

        return handledning_parsers.parse_teacher_sessions(response.text, self.username)

    def get_queue(self, session_id: str) -> list[QueueEntry]:
        """Get the queue for a specific session.

        Args:
            session_id: Session ID

        Returns:
            List of QueueEntry objects
        """
        self._ensure_authenticated()

        url = build_url(self.base_url, "queue", session_id)
        response = self.client.get(url)
        response.raise_for_status()

        return handledning_parsers.parse_queue(response.text)

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

        response = self.client.post(url, data=data)

        if not response.is_success:
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

        response = self.client.post(url, data=data)

        if not response.is_success:
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

        response = self.client.post(url)

        if not response.is_success:
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

        response = self.client.post(url)

        if not response.is_success:
            raise HandledningError(f"Failed to deactivate session: {response.status_code}")

        return True

    def get_all_active_sessions(self) -> list[HandledningSession]:
        """Get all currently active sessions.

        Returns:
            List of HandledningSession objects
        """
        self._ensure_authenticated()

        url = build_url(self.base_url, "sessions", "active")
        response = self.client.get(url)
        response.raise_for_status()

        return handledning_parsers.parse_teacher_sessions(response.text, self.username)

    def close(self) -> None:
        """Close the client session."""
        self.client.close()
        self.auth.__exit__(None, None, None)

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()



class AsyncHandledningClient:
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
        self.username = username or os.environ.get("SU_USERNAME")
        self.password = password or os.environ.get("SU_PASSWORD")

        if not self.username or not self.password:
            raise AuthenticationError(
                "Username and password must be provided either as arguments or "
                "via SU_USERNAME and SU_PASSWORD environment variables"
            )

        self.mobile = mobile
        self.base_url = DSV_URLS["handledning_mobile" if mobile else "handledning_desktop"]
        self.auth = AsyncShibbolethAuth(self.username, self.password, cache_backend=cache_backend, cache_ttl=cache_ttl)
        self.client: Optional[httpx.AsyncClient] = None
        self._authenticated = False

    async def __aenter__(self):
        """Async context manager entry."""
        await self.auth.__aenter__()
        self.client = httpx.AsyncClient(headers=DEFAULT_HEADERS)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.client:
            await self.client.aclose()
        await self.auth.__aexit__(exc_type, exc_val, exc_tb)

    async def _ensure_authenticated(self) -> None:
        """Ensure the client is authenticated."""
        if not self._authenticated:
            cookies = await self.auth.login(service="handledning")
            # Copy cookies from auth client to this client (preserve domain/path)
            for cookie in self.auth._sync_auth.client.cookies.jar:
                self.client.cookies.set(
                    cookie.name,
                    cookie.value,
                    domain=cookie.domain,
                    path=cookie.path
                )
            self._authenticated = True

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
        response = await self.client.get(url)
        response.raise_for_status()

        return handledning_parsers.parse_teacher_sessions(response.text, self.username)

    async def get_queue(self, session_id: str) -> list[QueueEntry]:
        """Get the queue for a specific session.

        Args:
            session_id: Session ID

        Returns:
            List of QueueEntry objects
        """
        await self._ensure_authenticated()

        url = build_url(self.base_url, "queue", session_id)
        response = await self.client.get(url)
        response.raise_for_status()

        return handledning_parsers.parse_queue(response.text)

    async def add_to_queue(self, session_id: str, student_username: Optional[str] = None) -> bool:
        """Add a student to the queue.

        Args:
            session_id: Session ID
            student_username: Student username (default: current user)

        Returns:
            True if added successfully

        Raises:
            QueueError: If addition fails
        """
        await self._ensure_authenticated()

        if student_username is None:
            student_username = self.username

        url = build_url(self.base_url, "queue", session_id, "add")
        data = {"student": student_username}

        response = await self.client.post(url, data=data)

        if not response.is_success:
            raise QueueError(f"Failed to add to queue: {response.status_code}")

        # Check for error messages
        soup = parse_html(response.text)
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
            True if removed successfully

        Raises:
            QueueError: If removal fails
        """
        await self._ensure_authenticated()

        url = build_url(self.base_url, "queue", session_id, "remove")
        data = {"student": student_username}

        response = await self.client.post(url, data=data)

        if not response.is_success:
            raise QueueError(f"Failed to remove from queue: {response.status_code}")

        return True

    async def activate_session(self, session_id: str) -> bool:
        """Activate a session (teacher only).

        Args:
            session_id: Session ID

        Returns:
            True if activated successfully

        Raises:
            HandledningError: If activation fails
        """
        await self._ensure_authenticated()

        url = build_url(self.base_url, "session", session_id, "activate")

        response = await self.client.post(url)

        if not response.is_success:
            raise HandledningError(f"Failed to activate session: {response.status_code}")

        return True

    async def deactivate_session(self, session_id: str) -> bool:
        """Deactivate a session (teacher only).

        Args:
            session_id: Session ID

        Returns:
            True if deactivated successfully

        Raises:
            HandledningError: If deactivation fails
        """
        await self._ensure_authenticated()

        url = build_url(self.base_url, "session", session_id, "deactivate")

        response = await self.client.post(url)

        if not response.is_success:
            raise HandledningError(f"Failed to deactivate session: {response.status_code}")

        return True

    async def get_all_active_sessions(self) -> list[HandledningSession]:
        """Get all currently active sessions.

        Returns:
            List of HandledningSession objects
        """
        await self._ensure_authenticated()

        url = build_url(self.base_url, "sessions", "active")
        response = await self.client.get(url)
        response.raise_for_status()

        return handledning_parsers.parse_teacher_sessions(response.text, self.username)
