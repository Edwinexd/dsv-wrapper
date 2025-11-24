"""Daisy client for room booking and schedule management."""

import logging
import os
import re
from datetime import date, datetime, time
from typing import Optional
from urllib.parse import urlparse

import httpx

from .auth import AsyncShibbolethAuth, ShibbolethAuth
from .auth.cache_backend import CacheBackend, NullCache
from .exceptions import AuthenticationError, BookingError, NetworkError, ParseError, RoomNotAvailableError
from .models import BookingSlot, InstitutionID, Room, RoomActivity, RoomCategory, RoomTime, Schedule, Staff, Student
from .parsers import daisy as daisy_parsers
from .utils import (
    DEFAULT_HEADERS,
    DSV_URLS,
    build_url,
    extract_attr,
    extract_text,
    parse_html,
    parse_time,
)

logger = logging.getLogger(__name__)


class DaisyClient:
    """Synchronous client for Daisy system."""

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        service: str = "daisy_staff",
        cache_backend: Optional[CacheBackend] = None,
        cache_ttl: int = 86400,
    ):
        """Initialize Daisy client.

        Args:
            username: SU username (default: read from SU_USERNAME env var)
            password: SU password (default: read from SU_PASSWORD env var)
            service: Service type (daisy_staff or daisy_student)
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
        self.service = service
        self.base_url = DSV_URLS[service]
        self.auth = ShibbolethAuth(self.username, self.password, cache_backend=cache_backend, cache_ttl=cache_ttl)
        self._client = httpx.Client(headers=DEFAULT_HEADERS, follow_redirects=True)
        self._authenticated = False

    def _ensure_authenticated(self) -> None:
        """Ensure the client is authenticated."""
        if not self._authenticated:
            cookies = self.auth._login(self.service)
            # Copy cookies from auth client to this client
            for cookie in self.auth._client.cookies.jar:
                self._client.cookies.set(
                    cookie.name,
                    cookie.value,
                    domain=cookie.domain,
                    path=cookie.path
                )
            self._authenticated = True

    def get_schedule(
        self, category: RoomCategory, schedule_date: Optional[date] = None
    ) -> Schedule:
        """Get room schedule for a category and date.

        Args:
            category: Room category
            schedule_date: Date to get schedule for (default: today)

        Returns:
            Schedule object with activities

        Raises:
            ParseError: If schedule parsing fails
        """
        self._ensure_authenticated()

        if schedule_date is None:
            schedule_date = date.today()

        url = f"{self.base_url}/servlet/schema.LokalSchema"

        data = {
            "lokalkategori": str(category.value),
            "year": schedule_date.year,
            "month": f"{schedule_date.month:02d}",
            "day": f"{schedule_date.day:02d}",
            "datumSubmit": "Visa"
        }

        response = self._client.post(url, data=data)
        response.raise_for_status()

        return daisy_parsers.parse_schedule(response.text)

    def book_room(
        self,
        room_id: str,
        schedule_date: date,
        start_time: time,
        end_time: time,
        purpose: Optional[str] = None,
    ) -> bool:
        """Book a room for a specific time slot.

        Args:
            room_id: Room ID
            schedule_date: Date to book
            start_time: Start time
            end_time: End time
            purpose: Booking purpose (optional)

        Returns:
            True if booking successful

        Raises:
            BookingError: If booking fails
            RoomNotAvailableError: If room is not available
        """
        self._ensure_authenticated()

        booking_url = build_url(
            self.base_url,
            "book",
            room=room_id,
            date=schedule_date.isoformat(),
            start=start_time.strftime("%H:%M"),
            end=end_time.strftime("%H:%M"),
        )

        data = {}
        if purpose:
            data["purpose"] = purpose

        response = self._client.post(booking_url, data=data)

        if response.status_code == 409:
            raise RoomNotAvailableError(f"Room {room_id} is not available for the requested time")

        if not response.is_success:
            raise BookingError(f"Booking failed with status {response.status_code}")

        # Check if booking was successful
        soup = parse_html(response.text)
        success_msg = soup.find(text=re.compile(r"bokning|booked|success", re.I))

        if success_msg:
            return True

        error_msg = soup.find("div", class_=re.compile(r"error|alert"))
        if error_msg:
            raise BookingError(f"Booking failed: {extract_text(error_msg)}")

        return True

    def search_students(self, query: str, limit: int = 50) -> list[Student]:
        """Search for students by name or username.

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of Student objects
        """
        self._ensure_authenticated()

        url = build_url(self.base_url, "search", "students", q=query, limit=limit)
        response = self._client.get(url)
        response.raise_for_status()

        return daisy_parsers.parse_students(response.text)

    def get_room_activities(
        self, room_id: str, schedule_date: Optional[date] = None
    ) -> list[RoomActivity]:
        """Get all activities scheduled in a room.

        Args:
            room_id: Room ID
            schedule_date: Date to get activities for (default: today)

        Returns:
            List of RoomActivity objects
        """
        self._ensure_authenticated()

        if schedule_date is None:
            schedule_date = date.today()

        url = build_url(
            self.base_url,
            "rooms",
            room_id,
            "activities",
            date=schedule_date.isoformat(),
        )

        response = self._client.get(url)
        response.raise_for_status()

        return daisy_parsers.parse_activities(response.text, room_id, schedule_date)

    def search_staff(
        self,
        last_name: str = "",
        first_name: str = "",
        email: str = "",
        username: str = "",
        institution_id: str | InstitutionID = InstitutionID.DSV,
        unit_id: str = "",
    ) -> list[Staff]:
        """Search for staff members in Daisy.

        Args:
            last_name: Last name to search for
            first_name: First name to search for
            email: Email to search for
            username: Username to search for
            institution_id: Institution ID (default: InstitutionID.DSV)
            unit_id: Unit ID filter

        Returns:
            List of Staff objects with basic info
        """
        self._ensure_authenticated()

        logger.info(f"Searching for staff at institution {institution_id}")

        # Convert enum to value if needed
        institution_value = institution_id.value if hasattr(institution_id, 'value') else institution_id

        form_data = {
            "efternamn": last_name,
            "fornamn": first_name,
            "epost": email,
            "anvandarnamn": username,
            "svenskTitel": "",
            "engelskTitel": "",
            "personalkategori": "",
            "institutionID": institution_value,
            "anstalldTyp": "ALL",
            "enhetID": unit_id,
            "action:sokanstalld": "Sök",
        }

        response = self._client.post(
            f"{self.base_url}/sok/visaanstalld.jspa", data=form_data, timeout=30
        )
        response.raise_for_status()

        return daisy_parsers.parse_staff_search(response.text, self.base_url)

    def get_staff_details(self, person_id: str) -> Staff:
        """Get detailed information for a specific staff member.

        Args:
            person_id: Person ID

        Returns:
            Staff object with complete details
        """
        self._ensure_authenticated()

        logger.debug(f"Fetching details for staff {person_id}")

        url = f"{self.base_url}/anstalld/anstalldinfo.jspa?personID={person_id}"
        response = self._client.get(url, timeout=10)
        response.raise_for_status()

        return daisy_parsers.parse_staff_details(person_id, response.text, self.base_url)

    def get_all_staff(
        self,
        institution_id: str | InstitutionID = InstitutionID.DSV,
        batch_size: int = 10,
        delay_between_batches: float = 0.5
    ) -> list[Staff]:
        """Get all staff members with complete details.

        Note: For sync version, batch_size and delay_between_batches are ignored.
        They exist for API compatibility with async version.

        Args:
            institution_id: Institution ID (default: InstitutionID.DSV)
            batch_size: Ignored in sync version (exists for API compatibility)
            delay_between_batches: Ignored in sync version (exists for API compatibility)

        Returns:
            List of Staff objects with complete details
        """
        self._ensure_authenticated()

        logger.info(f"Fetching all staff for institution {institution_id}")

        # First, search for all staff
        staff_list = self.search_staff(institution_id=institution_id)

        # Then fetch details for each (sequentially)
        logger.info(f"Fetching details for {len(staff_list)} staff members...")

        detailed_staff = []
        for i, staff in enumerate(staff_list):
            try:
                detailed = self.get_staff_details(staff.person_id)
                detailed_staff.append(detailed)

                if (i + 1) % 10 == 0:
                    logger.info(f"Progress: {i+1}/{len(staff_list)}")
            except Exception as e:
                logger.error(f"Error fetching details for {staff.name}: {e}")
                raise

        logger.info(f"Completed: {len(detailed_staff)} staff members with details")
        return detailed_staff

    def download_profile_picture(self, url: str) -> bytes:
        """Download a profile picture from the given URL.

        Args:
            url: The URL of the profile picture

        Returns:
            Image bytes

        Raises:
            NetworkError: If the download fails
            ValueError: If the response is not an image
        """
        self._ensure_authenticated()

        try:
            response = self._client.get(url, timeout=10)
            response.raise_for_status()

            content_type = response.headers.get('Content-Type', '')
            if 'image' not in content_type:
                raise ValueError(f"URL did not return an image (Content-Type: {content_type})")

            return response.content

        except httpx.HTTPError as e:
            raise NetworkError(f"Failed to download profile picture: {e}") from e

    def close(self) -> None:
        """Close the client session."""
        self._client.close()
        self.auth.__exit__(None, None, None)

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()



class AsyncDaisyClient:
    """Asynchronous client for Daisy system."""

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        service: str = "daisy_staff",
        cache_backend: Optional[CacheBackend] = None,
        cache_ttl: int = 86400,
    ):
        """Initialize async Daisy client.

        Args:
            username: SU username (default: read from SU_USERNAME env var)
            password: SU password (default: read from SU_PASSWORD env var)
            service: Service type (daisy_staff or daisy_student)
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

        self.service = service
        self.base_url = DSV_URLS[service]
        self.auth = AsyncShibbolethAuth(self.username, self.password, cache_backend=cache_backend, cache_ttl=cache_ttl)
        self._client: Optional[httpx.AsyncClient] = None
        self._authenticated = False

        logger.debug(f"Initialized AsyncDaisyClient for user: {self.username}")

    async def __aenter__(self):
        """Async context manager entry."""
        await self.auth.__aenter__()
        self._client = httpx.AsyncClient(headers=DEFAULT_HEADERS)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
        await self.auth.__aexit__(exc_type, exc_val, exc_tb)

    async def _ensure_authenticated(self) -> None:
        """Ensure the client is authenticated."""
        if not self._authenticated:
            logger.info(f"Authenticating to {self.service}")
            cookies = await self.auth.login(service=self.service)
            # Copy cookies from auth client to this client (preserve domain/path)
            for cookie in self.auth._sync_auth._client.cookies.jar:
                self._client.cookies.set(
                    cookie.name,
                    cookie.value,
                    domain=cookie.domain,
                    path=cookie.path
                )
            self._authenticated = True
            logger.info(f"Successfully authenticated to {self.service}")

    async def get_schedule(
        self, category: RoomCategory, schedule_date: Optional[date] = None
    ) -> Schedule:
        """Get room schedule for a category and date.

        Args:
            category: Room category
            schedule_date: Date to get schedule for (default: today)

        Returns:
            Schedule object with activities

        Raises:
            ParseError: If schedule parsing fails
        """
        await self._ensure_authenticated()

        if schedule_date is None:
            schedule_date = date.today()

        url = f"{self.base_url}/servlet/schema.LokalSchema"

        data = {
            "lokalkategori": str(category.value),
            "year": schedule_date.year,
            "month": f"{schedule_date.month:02d}",
            "day": f"{schedule_date.day:02d}",
            "datumSubmit": "Visa"
        }

        response = await self._client.post(url, data=data)
        response.raise_for_status()

        return daisy_parsers.parse_schedule(response.text)

    async def book_room(
        self,
        room_id: str,
        schedule_date: date,
        start_time: time,
        end_time: time,
        purpose: Optional[str] = None,
    ) -> bool:
        """Book a room for a specific time slot.

        Args:
            room_id: Room ID
            schedule_date: Date to book
            start_time: Start time
            end_time: End time
            purpose: Booking purpose (optional)

        Returns:
            True if booking successful

        Raises:
            BookingError: If booking fails
            RoomNotAvailableError: If room is not available
        """
        await self._ensure_authenticated()

        booking_url = build_url(
            self.base_url,
            "book",
            room=room_id,
            date=schedule_date.isoformat(),
            start=start_time.strftime("%H:%M"),
            end=end_time.strftime("%H:%M"),
        )

        data = {}
        if purpose:
            data["purpose"] = purpose

        response = await self._client.post(booking_url, data=data)

        if response.status_code == 409:
            raise RoomNotAvailableError(f"Room {room_id} is not available for the requested time")

        if not response.is_success:
            raise BookingError(f"Booking failed with status {response.status_code}")

        # Check if booking was successful
        soup = parse_html(response.text)
        success_msg = soup.find(text=re.compile(r"bokning|booked|success", re.I))

        if success_msg:
            return True

        error_msg = soup.find("div", class_=re.compile(r"error|alert"))
        if error_msg:
            raise BookingError(f"Booking failed: {extract_text(error_msg)}")

        return True

    async def search_students(self, query: str, limit: int = 50) -> list[Student]:
        """Search for students by name or username.

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of Student objects
        """
        await self._ensure_authenticated()

        url = build_url(self.base_url, "search", "students", q=query, limit=limit)
        response = await self._client.get(url)
        response.raise_for_status()

        return daisy_parsers.parse_students(response.text)

    async def get_room_activities(
        self, room_id: str, schedule_date: Optional[date] = None
    ) -> list[RoomActivity]:
        """Get all activities scheduled in a room.

        Args:
            room_id: Room ID
            schedule_date: Date to get activities for (default: today)

        Returns:
            List of RoomActivity objects
        """
        await self._ensure_authenticated()

        if schedule_date is None:
            schedule_date = date.today()

        url = build_url(
            self.base_url,
            "rooms",
            room_id,
            "activities",
            date=schedule_date.isoformat(),
        )

        response = await self._client.get(url)
        response.raise_for_status()

        return daisy_parsers.parse_activities(response.text, room_id, schedule_date)

    async def search_staff(
        self,
        last_name: str = "",
        first_name: str = "",
        email: str = "",
        username: str = "",
        institution_id: str | InstitutionID = InstitutionID.DSV,
        unit_id: str = "",
    ) -> list[Staff]:
        """Search for staff members in Daisy.

        Args:
            last_name: Last name to search for
            first_name: First name to search for
            email: Email to search for
            username: Username to search for
            institution_id: Institution ID (default: InstitutionID.DSV)
            unit_id: Unit ID filter

        Returns:
            List of Staff objects with basic info
        """
        await self._ensure_authenticated()

        logger.info(f"Searching for staff at institution {institution_id}")

        # Convert enum to value if needed
        institution_value = institution_id.value if hasattr(institution_id, 'value') else institution_id

        form_data = {
            "efternamn": last_name,
            "fornamn": first_name,
            "epost": email,
            "anvandarnamn": username,
            "svenskTitel": "",
            "engelskTitel": "",
            "personalkategori": "",
            "institutionID": institution_value,
            "anstalldTyp": "ALL",
            "enhetID": unit_id,
            "action:sokanstalld": "Sök",
        }

        response = await self._client.post(
            f"{self.base_url}/sok/visaanstalld.jspa", data=form_data, timeout=30
        )
        response.raise_for_status()

        return daisy_parsers.parse_staff_search(response.text, self.base_url)

    async def get_staff_details(self, person_id: str) -> Staff:
        """Get detailed information for a specific staff member.

        Args:
            person_id: Person ID

        Returns:
            Staff object with complete details
        """
        await self._ensure_authenticated()

        logger.debug(f"Fetching details for staff {person_id}")

        url = f"{self.base_url}/anstalld/anstalldinfo.jspa?personID={person_id}"
        response = await self._client.get(url, timeout=10)
        response.raise_for_status()

        return daisy_parsers.parse_staff_details(person_id, response.text, self.base_url)

    async def get_all_staff(
        self,
        institution_id: str | InstitutionID = InstitutionID.DSV,
        batch_size: int = 10,
        delay_between_batches: float = 0.5
    ) -> list[Staff]:
        """Get all staff members with complete details.

        Args:
            institution_id: Institution ID (default: InstitutionID.DSV)
            batch_size: Number of staff details to fetch concurrently (default: 10)
            delay_between_batches: Delay in seconds between batches (default: 0.5)

        Returns:
            List of Staff objects with complete details
        """
        import asyncio

        # First, get list of all staff
        logger.info(f"Fetching all staff for institution {institution_id}")
        staff_list = await self.search_staff(institution_id=institution_id)
        logger.info(f"Found {len(staff_list)} staff members, fetching details...")

        detailed_staff = []

        # Fetch details in batches
        for i in range(0, len(staff_list), batch_size):
            batch = staff_list[i:i + batch_size]
            logger.debug(f"Fetching batch {i//batch_size + 1}/{(len(staff_list) + batch_size - 1)//batch_size}")

            # Create tasks for this batch
            tasks = []
            for staff in batch:
                async def fetch_details(s: Staff) -> Staff:
                    """Fetch staff details."""
                    try:
                        return await self.get_staff_details(s.person_id)
                    except Exception as e:
                        logger.error(f"Error fetching details for {s.name}: {e}")
                        raise

                tasks.append(fetch_details(staff))

            # Execute batch concurrently
            batch_results = await asyncio.gather(*tasks)
            detailed_staff.extend(batch_results)

            # Delay between batches (except for last batch)
            if i + batch_size < len(staff_list):
                await asyncio.sleep(delay_between_batches)

        logger.info(f"Completed: {len(detailed_staff)} staff members with details")
        return detailed_staff

    async def download_profile_picture(self, url: str) -> bytes:
        """Download a profile picture from the given URL.

        Args:
            url: The URL of the profile picture

        Returns:
            Image bytes

        Raises:
            NetworkError: If the download fails
            ValueError: If the response is not an image
        """
        await self._ensure_authenticated()

        try:
            response = await self._client.get(url, timeout=10)
            response.raise_for_status()

            content_type = response.headers.get('Content-Type', '')
            if 'image' not in content_type:
                raise ValueError(f"URL did not return an image (Content-Type: {content_type})")

            return response.content

        except httpx.HTTPError as e:
            raise NetworkError(f"Failed to download profile picture: {e}") from e

