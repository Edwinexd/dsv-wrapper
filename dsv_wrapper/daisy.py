"""Daisy client for room booking and schedule management."""

import asyncio
import logging
import os
import re
import time as time_module
from datetime import date, time

import httpx

from .auth import AsyncShibbolethAuth, ShibbolethAuth
from .auth.cache_backend import CacheBackend
from .exceptions import (
    AuthenticationError,
    BookingError,
    NetworkError,
    ParseError,
    RoomNotAvailableError,
)
from .models import (
    CourseStaff,
    DaisyCourse,
    InstitutionID,
    RoomActivity,
    RoomCategory,
    Schedule,
    Semester,
    Staff,
    Student,
)
from .parsers import daisy as daisy_parsers
from .utils import (
    DEFAULT_HEADERS,
    DSV_URLS,
    build_url,
    extract_text,
    parse_html,
)

logger = logging.getLogger(__name__)

# Default concurrency for bulk operations
DEFAULT_MAX_CONCURRENT = 20

# Daisy returns up to 20 course-search results per page
COURSE_SEARCH_PAGE_SIZE = 20


def _build_course_search_form(
    *,
    semester: Semester | None,
    semester_from: Semester | None,
    semester_to: Semester | None,
    beteckning: str,
    name: str,
    institution_id: str | InstitutionID,
    query_page: int,
) -> dict[str, str]:
    """Build POST form data for ``/sok/sokmoment.jspa``.

    ``semester`` (single term) takes precedence over ``semester_from``/``semester_to``.
    A semester value of ``None`` on either bound omits that filter, returning
    courses across all terms available in Daisy.
    """
    if semester is not None:
        semester_from = semester_to = semester
    inst_val = institution_id.value if hasattr(institution_id, "value") else institution_id
    form: dict[str, str] = {
        "beteckning": beteckning or "",
        "namn": name or "",
        "kursID": "",
        "searchTerm": "",
        "momentansvID": "",
        "institution": inst_val or "",
        "searchInstInUnits": "true",
        "nyckelbegrepp": "",
        "fromTerminID": semester_from.termin_id if semester_from else "",
        "tomTerminID": semester_to.termin_id if semester_to else "",
    }
    if query_page > 0:
        form["querypage"] = str(query_page)
    return form


class DaisyClient:
    """Synchronous client for Daisy system."""

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        service: str = "daisy_staff",
        cache_backend: CacheBackend | None = None,
        cache_ttl: int = 86400,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
    ):
        """Initialize Daisy client.

        Args:
            username: SU username (default: read from SU_USERNAME env var)
            password: SU password (default: read from SU_PASSWORD env var)
            service: Service type (daisy_staff or daisy_student)
            cache_backend: Cache backend for authentication cookies (default: NullCache)
            cache_ttl: Cache TTL in seconds (default: 86400 = 24 hours)
            max_concurrent: Maximum concurrent requests for bulk operations (default: 20)

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
        self.max_concurrent = max_concurrent
        self.auth = ShibbolethAuth(
            self.username, self.password, cache_backend=cache_backend, cache_ttl=cache_ttl
        )
        self._client = httpx.Client(headers=DEFAULT_HEADERS, follow_redirects=True)
        self._authenticated = False

    def _ensure_authenticated(self) -> None:
        """Ensure the client is authenticated."""
        if not self._authenticated:
            self.auth._login(self.service)
            # Copy cookies from auth client to this client
            for cookie in self.auth._client.cookies.jar:
                self._client.cookies.set(
                    cookie.name, cookie.value, domain=cookie.domain, path=cookie.path
                )
            self._authenticated = True

    def get_schedule(self, category: RoomCategory, schedule_date: date | None = None) -> Schedule:
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
            "datumSubmit": "Visa",
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
        purpose: str | None = None,
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

    def search_students(
        self,
        last_name: str = "",
        first_name: str = "",
        email: str = "",
        username: str = "",
        institution_id: str | InstitutionID = "",
        page_size: int = 25,
    ) -> list[Student]:
        """Search for students via Daisy's ``/sok/visastudent.jspa`` form.

        At least one of the name/email/username filters should be provided;
        an unfiltered search may return tens of thousands of rows. ``hogskolaID``
        is hardcoded to SU (``5``) for now.

        Args:
            last_name: ``efternamn`` field.
            first_name: ``fornamn`` field.
            email: ``epost`` field.
            username: ``anvandarnamn`` field.
            institution_id: ``institutionID`` field (DSV's id is ``4``).
            page_size: Daisy page size (25/50/75/100).

        Returns:
            List of Student rows. The returned objects have ``person_id``
            and ``profile_url`` populated but ``username=None`` – call
            :meth:`Student.get_username` to resolve.
        """
        self._ensure_authenticated()
        inst_val = institution_id.value if hasattr(institution_id, "value") else institution_id
        form = {
            "efternamn": last_name,
            "fornamn": first_name,
            "epost": email,
            "anvandarnamn": username,
            "hogskolaID": "5",
            "terminID": "",
            "institutionID": inst_val or "",
            "kursID": "",
            "programID": "",
            "pageSize": str(page_size),
            "action:sokstudent": "Sök",
        }
        response = self._client.post(f"{self.base_url}/sok/visastudent.jspa", data=form, timeout=30)
        response.raise_for_status()
        return daisy_parsers.parse_students(response.text, self.base_url)

    def get_student_details(self, person_id: str) -> Student:
        """Fetch a student's profile page and return a populated Student."""
        self._ensure_authenticated()
        url = f"{self.base_url}/anstalld/student/studentinfo.jspa?personID={person_id}"
        response = self._client.get(url, timeout=15)
        response.raise_for_status()
        return daisy_parsers.parse_student_details(person_id, response.text, self.base_url)

    def get_room_activities(
        self, room_id: str, schedule_date: date | None = None
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
        institution_value = (
            institution_id.value if hasattr(institution_id, "value") else institution_id
        )

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
        max_retries: int = 3,
    ) -> list[Staff]:
        """Get all staff members with complete details.

        Fetches staff details in parallel using threads, retrying failures.

        Args:
            institution_id: Institution ID (default: InstitutionID.DSV)
            max_retries: Maximum retry attempts for failed fetches (default: 3)

        Returns:
            List of Staff objects with complete details
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        self._ensure_authenticated()

        logger.info(f"Fetching all staff for institution {institution_id}")

        # First, search for all staff
        staff_list = self.search_staff(institution_id=institution_id)
        logger.info(f"Fetching details for {len(staff_list)} staff members...")

        detailed_staff: list[Staff] = []
        failed: list[Staff] = []

        def fetch_one(staff: Staff) -> tuple[Staff, Staff | None]:
            """Fetch details for one staff member."""
            try:
                return staff, self.get_staff_details(staff.person_id)
            except (NetworkError, ParseError, httpx.HTTPError) as e:
                logger.warning(f"Error fetching details for {staff.name}: {e}")
                return staff, None

        # First pass - fetch all in parallel
        with ThreadPoolExecutor(max_workers=self.max_concurrent) as executor:
            futures = {executor.submit(fetch_one, staff): staff for staff in staff_list}
            completed = 0

            for future in as_completed(futures):
                staff, result = future.result()
                completed += 1

                if result is not None:
                    detailed_staff.append(result)
                else:
                    failed.append(staff)

                if completed % 50 == 0:
                    logger.info(f"Progress: {completed}/{len(staff_list)}")

        # Retry failed ones
        for retry in range(max_retries):
            if not failed:
                break

            logger.info(f"Retry {retry + 1}/{max_retries}: {len(failed)} staff members")
            still_failed: list[Staff] = []

            with ThreadPoolExecutor(max_workers=self.max_concurrent) as executor:
                futures = {executor.submit(fetch_one, staff): staff for staff in failed}

                for future in as_completed(futures):
                    staff, result = future.result()
                    if result is not None:
                        detailed_staff.append(result)
                    else:
                        still_failed.append(staff)

            failed = still_failed

        if failed:
            logger.error(f"Failed to fetch {len(failed)} staff after {max_retries} retries")
            for staff in failed:
                logger.error(f"  - {staff.name} (ID: {staff.person_id})")

        logger.info(f"Completed: {len(detailed_staff)} staff members with details")
        return detailed_staff

    def download_profile_picture(self, url: str, max_retries: int = 3) -> bytes:
        """Download a profile picture from the given URL.

        Args:
            url: The URL of the profile picture
            max_retries: Maximum number of retry attempts for transient errors

        Returns:
            Image bytes

        Raises:
            NetworkError: If the download fails after all retries
            ValueError: If the response is not an image
        """
        self._ensure_authenticated()

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                response = self._client.get(url, timeout=10)
                response.raise_for_status()

                content_type = response.headers.get("Content-Type", "")
                if "image" not in content_type:
                    raise ValueError(f"URL did not return an image (Content-Type: {content_type})")

                return response.content

            except httpx.HTTPStatusError as e:
                # Don't retry client errors (4xx)
                if 400 <= e.response.status_code < 500:
                    raise NetworkError(f"Failed to download profile picture: {e}") from e
                last_error = e
            except httpx.HTTPError as e:
                # Retry on network errors (connection, timeout, protocol errors)
                last_error = e

            if attempt < max_retries:
                wait_time = 2**attempt  # Exponential backoff: 1, 2, 4 seconds
                logger.debug(f"Retry {attempt + 1}/{max_retries} for {url} after {wait_time}s")
                time_module.sleep(wait_time)

        msg = f"Failed to download profile picture after {max_retries + 1} attempts: {last_error}"
        raise NetworkError(msg) from last_error

    def get_courses(
        self,
        semester: Semester | None = None,
        *,
        semester_from: Semester | None = None,
        semester_to: Semester | None = None,
        beteckning: str = "",
        name: str = "",
        institution_id: str | InstitutionID = InstitutionID.DSV,
        max_pages: int | None = None,
    ) -> list[DaisyCourse]:
        """List course offerings ("moment") in Daisy.

        Auto-paginates Daisy's ``/sok/sokmoment.jspa`` search.

        Args:
            semester: Restrict to a single semester (e.g. ``Semester.from_label("VT2026")``).
                Mutually exclusive with ``semester_from``/``semester_to``.
            semester_from: Lower-bound semester (inclusive).
            semester_to: Upper-bound semester (inclusive).
            beteckning: Filter by course code substring (case-insensitive in Daisy).
            name: Filter by course name substring.
            institution_id: Institution scope (default DSV).
            max_pages: Stop after this many pages of 20 results. ``None`` = all pages.

        Returns:
            List of DaisyCourse instances with search-page data populated
            (no syllabus_url / unit – use :meth:`get_course` for that).
        """
        self._ensure_authenticated()
        if semester is not None and (semester_from or semester_to):
            raise ValueError("Pass either `semester` or `semester_from`/`semester_to`, not both")

        url = f"{self.base_url}/sok/sokmoment.jspa"
        all_courses: list[DaisyCourse] = []
        page = 0
        while True:
            form = _build_course_search_form(
                semester=semester,
                semester_from=semester_from,
                semester_to=semester_to,
                beteckning=beteckning,
                name=name,
                institution_id=institution_id,
                query_page=page,
            )
            response = self._client.post(url, data=form, timeout=30)
            response.raise_for_status()
            courses, range_from, range_to, total = daisy_parsers.parse_course_search(
                response.text, self.base_url
            )
            all_courses.extend(courses)
            if not courses or range_to is None or total is None or range_to >= total:
                break
            page += 1
            if max_pages is not None and page >= max_pages:
                break
        return all_courses

    def get_course(self, momenttillf_id: str | int) -> DaisyCourse:
        """Fetch the public detail page for a course offering.

        Returns a :class:`DaisyCourse` with ``ects``, ``unit``, ``syllabus_url``
        and ``semester`` populated from the detail page. Start/end dates are
        not on this page – they come from search results.
        """
        self._ensure_authenticated()
        mid = str(momenttillf_id)
        url = f"{self.base_url}/servlet/momentinfo.Momentinfo?id={mid}"
        response = self._client.get(url, timeout=15)
        response.raise_for_status()
        return daisy_parsers.parse_course_detail(response.text, mid, self.base_url)

    def get_course_participants(self, momenttillf_id: str | int) -> list[CourseStaff]:
        """Fetch the role-grouped staff/participants list for a course offering.

        Parses the *Medverkande* section of the public momentinfo page, which
        groups people by free-text role (e.g. *Kurs-/delkursansvarig*,
        *Examination*, *Handledare*, *Laborationsledare*, *Administration*).
        A person appearing under multiple groups is returned once with all
        their roles in :attr:`CourseStaff.roles`.

        Works for any course in Daisy – this endpoint is not gated to the
        course's own teaching team.
        """
        self._ensure_authenticated()
        mid = str(momenttillf_id)
        url = f"{self.base_url}/servlet/momentinfo.Momentinfo?id={mid}"
        response = self._client.get(url, timeout=15)
        response.raise_for_status()
        return daisy_parsers.parse_course_participants(response.text, self.base_url)

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
        username: str | None = None,
        password: str | None = None,
        service: str = "daisy_staff",
        cache_backend: CacheBackend | None = None,
        cache_ttl: int = 86400,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
    ):
        """Initialize async Daisy client.

        Args:
            username: SU username (default: read from SU_USERNAME env var)
            password: SU password (default: read from SU_PASSWORD env var)
            service: Service type (daisy_staff or daisy_student)
            cache_backend: Cache backend for authentication cookies (default: NullCache)
            cache_ttl: Cache TTL in seconds (default: 86400 = 24 hours)
            max_concurrent: Maximum concurrent requests for bulk operations (default: 20)

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
        self.max_concurrent = max_concurrent
        self.auth = AsyncShibbolethAuth(
            self.username, self.password, cache_backend=cache_backend, cache_ttl=cache_ttl
        )
        self._client: httpx.AsyncClient | None = None
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
            await self.auth.login(service=self.service)
            # Copy cookies from auth client to this client (preserve domain/path)
            for cookie in self.auth._sync_auth._client.cookies.jar:
                self._client.cookies.set(
                    cookie.name, cookie.value, domain=cookie.domain, path=cookie.path
                )
            self._authenticated = True
            logger.info(f"Successfully authenticated to {self.service}")

    async def get_schedule(
        self, category: RoomCategory, schedule_date: date | None = None
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
            "datumSubmit": "Visa",
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
        purpose: str | None = None,
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

    async def search_students(
        self,
        last_name: str = "",
        first_name: str = "",
        email: str = "",
        username: str = "",
        institution_id: str | InstitutionID = "",
        page_size: int = 25,
    ) -> list[Student]:
        """Search for students. See :meth:`DaisyClient.search_students`."""
        await self._ensure_authenticated()
        inst_val = institution_id.value if hasattr(institution_id, "value") else institution_id
        form = {
            "efternamn": last_name,
            "fornamn": first_name,
            "epost": email,
            "anvandarnamn": username,
            "hogskolaID": "5",
            "terminID": "",
            "institutionID": inst_val or "",
            "kursID": "",
            "programID": "",
            "pageSize": str(page_size),
            "action:sokstudent": "Sök",
        }
        response = await self._client.post(
            f"{self.base_url}/sok/visastudent.jspa", data=form, timeout=30
        )
        response.raise_for_status()
        return daisy_parsers.parse_students(response.text, self.base_url)

    async def get_student_details(self, person_id: str) -> Student:
        """Fetch a student's profile page and return a populated Student."""
        await self._ensure_authenticated()
        url = f"{self.base_url}/anstalld/student/studentinfo.jspa?personID={person_id}"
        response = await self._client.get(url, timeout=15)
        response.raise_for_status()
        return daisy_parsers.parse_student_details(person_id, response.text, self.base_url)

    async def get_room_activities(
        self, room_id: str, schedule_date: date | None = None
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
        institution_value = (
            institution_id.value if hasattr(institution_id, "value") else institution_id
        )

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
        max_retries: int = 3,
    ) -> list[Staff]:
        """Get all staff members with complete details.

        Fetches staff details concurrently in batches, retrying failures.

        Args:
            institution_id: Institution ID (default: InstitutionID.DSV)
            max_retries: Maximum retry attempts for failed fetches (default: 3)

        Returns:
            List of Staff objects with complete details
        """
        import asyncio

        # First, get list of all staff
        logger.info(f"Fetching all staff for institution {institution_id}")
        staff_list = await self.search_staff(institution_id=institution_id)
        logger.info(f"Fetching details for {len(staff_list)} staff members...")

        detailed_staff: list[Staff] = []
        failed: list[Staff] = []

        async def fetch_one(staff: Staff) -> tuple[Staff, Staff | None]:
            """Fetch details for one staff member."""
            try:
                result = await self.get_staff_details(staff.person_id)
                return staff, result
            except (NetworkError, ParseError, httpx.HTTPError) as e:
                logger.warning(f"Error fetching details for {staff.name}: {e}")
                return staff, None

        # First pass - fetch all in batches
        for i in range(0, len(staff_list), self.max_concurrent):
            batch = staff_list[i : i + self.max_concurrent]

            tasks = [fetch_one(staff) for staff in batch]
            results = await asyncio.gather(*tasks)

            for staff, result in results:
                if result is not None:
                    detailed_staff.append(result)
                else:
                    failed.append(staff)

            done = min(i + self.max_concurrent, len(staff_list))
            logger.info(f"Progress: {done}/{len(staff_list)}")

        # Retry failed ones
        for retry in range(max_retries):
            if not failed:
                break

            logger.info(f"Retry {retry + 1}/{max_retries}: {len(failed)} staff members")
            still_failed: list[Staff] = []

            tasks = [fetch_one(staff) for staff in failed]
            results = await asyncio.gather(*tasks)

            for staff, result in results:
                if result is not None:
                    detailed_staff.append(result)
                else:
                    still_failed.append(staff)

            failed = still_failed

        if failed:
            logger.error(f"Failed to fetch {len(failed)} staff after {max_retries} retries")
            for staff in failed:
                logger.error(f"  - {staff.name} (ID: {staff.person_id})")

        logger.info(f"Completed: {len(detailed_staff)} staff members with details")
        return detailed_staff

    async def get_courses(
        self,
        semester: Semester | None = None,
        *,
        semester_from: Semester | None = None,
        semester_to: Semester | None = None,
        beteckning: str = "",
        name: str = "",
        institution_id: str | InstitutionID = InstitutionID.DSV,
        max_pages: int | None = None,
    ) -> list[DaisyCourse]:
        """List course offerings ("moment") in Daisy.

        See :meth:`DaisyClient.get_courses` for argument details. Auto-paginates.
        """
        await self._ensure_authenticated()
        if semester is not None and (semester_from or semester_to):
            raise ValueError("Pass either `semester` or `semester_from`/`semester_to`, not both")

        url = f"{self.base_url}/sok/sokmoment.jspa"
        all_courses: list[DaisyCourse] = []
        page = 0
        while True:
            form = _build_course_search_form(
                semester=semester,
                semester_from=semester_from,
                semester_to=semester_to,
                beteckning=beteckning,
                name=name,
                institution_id=institution_id,
                query_page=page,
            )
            response = await self._client.post(url, data=form, timeout=30)
            response.raise_for_status()
            courses, range_from, range_to, total = daisy_parsers.parse_course_search(
                response.text, self.base_url
            )
            all_courses.extend(courses)
            if not courses or range_to is None or total is None or range_to >= total:
                break
            page += 1
            if max_pages is not None and page >= max_pages:
                break
        return all_courses

    async def get_course(self, momenttillf_id: str | int) -> DaisyCourse:
        """Fetch the public detail page for a course offering."""
        await self._ensure_authenticated()
        mid = str(momenttillf_id)
        url = f"{self.base_url}/servlet/momentinfo.Momentinfo?id={mid}"
        response = await self._client.get(url, timeout=15)
        response.raise_for_status()
        return daisy_parsers.parse_course_detail(response.text, mid, self.base_url)

    async def get_course_participants(self, momenttillf_id: str | int) -> list[CourseStaff]:
        """Fetch the role-grouped staff list for a course offering.

        See :meth:`DaisyClient.get_course_participants` for details.
        """
        await self._ensure_authenticated()
        mid = str(momenttillf_id)
        url = f"{self.base_url}/servlet/momentinfo.Momentinfo?id={mid}"
        response = await self._client.get(url, timeout=15)
        response.raise_for_status()
        return daisy_parsers.parse_course_participants(response.text, self.base_url)

    async def download_profile_picture(self, url: str, max_retries: int = 3) -> bytes:
        """Download a profile picture from the given URL.

        Args:
            url: The URL of the profile picture
            max_retries: Maximum number of retry attempts for transient errors

        Returns:
            Image bytes

        Raises:
            NetworkError: If the download fails after all retries
            ValueError: If the response is not an image
        """
        await self._ensure_authenticated()

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                response = await self._client.get(url, timeout=10)
                response.raise_for_status()

                content_type = response.headers.get("Content-Type", "")
                if "image" not in content_type:
                    raise ValueError(f"URL did not return an image (Content-Type: {content_type})")

                return response.content

            except httpx.HTTPStatusError as e:
                # Don't retry client errors (4xx)
                if 400 <= e.response.status_code < 500:
                    raise NetworkError(f"Failed to download profile picture: {e}") from e
                last_error = e
            except httpx.HTTPError as e:
                # Retry on network errors (connection, timeout, protocol errors)
                last_error = e

            if attempt < max_retries:
                wait_time = 2**attempt  # Exponential backoff: 1, 2, 4 seconds
                logger.debug(f"Retry {attempt + 1}/{max_retries} for {url} after {wait_time}s")
                await asyncio.sleep(wait_time)

        msg = f"Failed to download profile picture after {max_retries + 1} attempts: {last_error}"
        raise NetworkError(msg) from last_error
