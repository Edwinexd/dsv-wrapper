"""Daisy client for room booking and schedule management."""

import logging
import os
import re
from datetime import date, datetime, time
from typing import Optional
from urllib.parse import urlparse

import aiohttp
import requests

from .auth import AsyncShibbolethAuth, ShibbolethAuth
from .auth.cache_backend import CacheBackend, NullCache
from .base import BaseAsyncClient
from .exceptions import AuthenticationError, BookingError, ParseError, RoomNotAvailableError

logger = logging.getLogger(__name__)
from .models import BookingSlot, InstitutionID, Room, RoomActivity, RoomCategory, RoomTime, Schedule, Staff, Student
from .utils import (
    DEFAULT_HEADERS,
    DSV_URLS,
    build_url,
    extract_attr,
    extract_text,
    parse_html,
    parse_time,
)


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
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self._authenticated = False

    def _ensure_authenticated(self) -> None:
        """Ensure the client is authenticated."""
        if not self._authenticated:
            cookies = self.auth._login(self.service)
            self.session.cookies.update(cookies)
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

        response = self.session.post(url, data=data)
        response.raise_for_status()

        return self._parse_schedule(response.text)

    def _parse_schedule(self, html: str) -> Schedule:
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
                    except (ValueError, KeyError):
                        continue

        # Extract metadata
        room_category_title = extract_text(rows[0].find_all("td")[1].find("b"))
        category_link = rows[0].find_all("td")[1].find("a")
        room_category_id = int(
            category_link.get("href").split("&")[1].split("=")[1]
        )

        date_column = list(rows[0].find_all("td")[1].children)[2]
        date_match = re.findall(r"(\d{4})-(\d{2})-(\d{2})", str(date_column))[0]
        schedule_datetime = datetime(
            int(date_match[0]), int(date_match[1]), int(date_match[2])
        )

        return Schedule(
            activities=activities,
            room_category_title=room_category_title,
            room_category_id=room_category_id,
            room_category=RoomCategory(room_category_id),
            datetime=schedule_datetime,
        )

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

        response = self.session.post(booking_url, data=data)

        if response.status_code == 409:
            raise RoomNotAvailableError(f"Room {room_id} is not available for the requested time")

        if not response.ok:
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
        response = self.session.get(url)
        response.raise_for_status()

        return self._parse_students(response.text)

    def _parse_students(self, html: str) -> list[Student]:
        """Parse student search results.

        Args:
            html: HTML content

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
                last_name=(
                    " ".join(extract_text(name_cell).split()[1:]) if name_cell else None
                ),
                email=extract_text(email_cell) if email_cell else None,
                program=extract_text(program_cell) if program_cell else None,
            )
            students.append(student)

        return students

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

        response = self.session.get(url)
        response.raise_for_status()

        return self._parse_activities(response.text, room_id, schedule_date)

    def _parse_activities(
        self, html: str, room_id: str, schedule_date: date
    ) -> list[RoomActivity]:
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
                except ValueError:
                    continue

        return activities

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

        form_data = {
            "efternamn": last_name,
            "fornamn": first_name,
            "epost": email,
            "anvandarnamn": username,
            "svenskTitel": "",
            "engelskTitel": "",
            "personalkategori": "",
            "institutionID": institution_id,
            "anstalldTyp": "ALL",
            "enhetID": unit_id,
            "action:sokanstalld": "Sök",
        }

        response = self.session.post(
            f"{self.base_url}/sok/visaanstalld.jspa", data=form_data, timeout=30
        )
        response.raise_for_status()

        return self._parse_staff_search(response.text)

    def _parse_staff_search(self, html: str) -> list[Staff]:
        """Parse staff search results.

        Args:
            html: HTML content from search results

        Returns:
            List of Staff objects
        """
        soup = parse_html(html)
        staff_list = []

        # Get base_url, handling case where this is called from async client
        base_url = getattr(self, 'base_url', DSV_URLS.get('daisy_staff', 'https://daisy.dsv.su.se'))

        tables = soup.find_all("table", class_="randig")
        for table in tables:
            rows = table.find_all("tr")

            for row in rows[1:]:  # Skip header
                cols = row.find_all("td")
                if len(cols) >= 2:
                    profile_link = row.find("a", href=lambda x: x and "personID" in x)
                    if profile_link:
                        person_id_match = re.search(
                            r"personID=(\d+)", profile_link.get("href", "")
                        )
                        if person_id_match:
                            person_id = person_id_match.group(1)
                            name = profile_link.get_text().strip()

                            staff = Staff(
                                person_id=person_id,
                                name=name,
                                profile_url=f"{base_url}{profile_link.get('href')}",
                            )
                            staff_list.append(staff)

        logger.info(f"Found {len(staff_list)} staff members")
        return staff_list

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
        response = self.session.get(url, timeout=10)
        response.raise_for_status()

        return self._parse_staff_details(person_id, response.text)

    def _parse_staff_details(self, person_id: str, html: str) -> Staff:
        """Parse detailed staff information from profile page.

        Args:
            person_id: Person ID
            html: HTML content from profile page

        Returns:
            Staff object with details
        """
        soup = parse_html(html)

        # Get base_url, handling case where this is called from async client
        base_url = getattr(self, 'base_url', DSV_URLS.get('daisy_staff', 'https://daisy.dsv.su.se'))

        # Extract profile picture
        profile_pic_url = None
        img_tag = soup.find("img", src=lambda x: x and "daisy.Jpg" in x)
        if img_tag:
            pic_src = img_tag.get("src", "")
            if pic_src.startswith("/"):
                parsed = urlparse(base_url)
                profile_pic_url = f"{parsed.scheme}://{parsed.netloc}{pic_src}"

        # Extract email
        email = None
        email_link = soup.find("a", href=lambda x: x and "mailto:" in x)
        if email_link:
            email = email_link.get("href", "").replace("mailto:", "")

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
                # Add basic info if details fetch fails
                detailed_staff.append(staff)

        logger.info(f"Completed: {len(detailed_staff)} staff members with details")
        return detailed_staff

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


class AsyncDaisyClient(BaseAsyncClient):
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
        username = username or os.environ.get("SU_USERNAME")
        password = password or os.environ.get("SU_PASSWORD")

        if not username or not password:
            raise AuthenticationError(
                "Username and password must be provided either as arguments or "
                "via SU_USERNAME and SU_PASSWORD environment variables"
            )

        super().__init__(
            username=username,
            password=password,
            base_url=DSV_URLS[service],
            service=service,
            cache_backend=cache_backend,
            cache_ttl=cache_ttl,
        )

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

        async with self.session.post(url, data=data) as response:
            response.raise_for_status()
            html = await response.text()

        return self._parse_schedule(html)

    def _parse_schedule(self, html: str) -> Schedule:
        """Parse schedule HTML into Schedule object (same as sync version)."""
        # Use the same parsing logic as sync version
        client = DaisyClient.__new__(DaisyClient)
        return client._parse_schedule(html)

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

        async with self.session.post(booking_url, data=data) as response:
            if response.status == 409:
                raise RoomNotAvailableError(
                    f"Room {room_id} is not available for the requested time"
                )

            if not response.ok:
                raise BookingError(f"Booking failed with status {response.status}")

            html = await response.text()

        # Check if booking was successful
        soup = parse_html(html)
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

        async with self.session.get(url) as response:
            response.raise_for_status()
            html = await response.text()

        return self._parse_students(html)

    def _parse_students(self, html: str) -> list[Student]:
        """Parse student search results (same as sync version)."""
        client = DaisyClient.__new__(DaisyClient)
        return client._parse_students(html)

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

        async with self.session.get(url) as response:
            response.raise_for_status()
            html = await response.text()

        return self._parse_activities(html, room_id, schedule_date)

    def _parse_activities(
        self, html: str, room_id: str, schedule_date: date
    ) -> list[RoomActivity]:
        """Parse room activities from HTML (same as sync version)."""
        client = DaisyClient.__new__(DaisyClient)
        return client._parse_activities(html, room_id, schedule_date)

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

        form_data = {
            "efternamn": last_name,
            "fornamn": first_name,
            "epost": email,
            "anvandarnamn": username,
            "svenskTitel": "",
            "engelskTitel": "",
            "personalkategori": "",
            "institutionID": institution_id,
            "anstalldTyp": "ALL",
            "enhetID": unit_id,
            "action:sokanstalld": "Sök",
        }

        url = f"{self.base_url}/sok/visaanstalld.jspa"
        logger.debug(f"Posting to {url}")
        logger.debug(f"Session has {len(self.session.cookie_jar)} cookies")

        async with self.session.post(url, data=form_data, timeout=30) as response:
            logger.debug(f"Response status: {response.status}")
            logger.debug(f"Response cookies: {response.cookies}")
            response.raise_for_status()
            html = await response.text()
            logger.debug(f"Response length: {len(html)} chars")
            # Debug: save response to file
            import os
            if os.getenv("DEBUG_SAVE_HTML"):
                with open("/tmp/async_staff_response.html", "w") as f:
                    f.write(html)
                logger.debug("Saved response to /tmp/async_staff_response.html")

        result = self._parse_staff_search(html)
        logger.debug(f"Parsed {len(result)} staff members")
        return result

    def _parse_staff_search(self, html: str) -> list[Staff]:
        """Parse staff search results (same as sync version)."""
        client = DaisyClient.__new__(DaisyClient)
        return client._parse_staff_search(html)

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

        async with self.session.get(url, timeout=10) as response:
            response.raise_for_status()
            html = await response.text()

        return self._parse_staff_details(person_id, html)

    def _parse_staff_details(self, person_id: str, html: str) -> Staff:
        """Parse detailed staff information from profile page (same as sync version)."""
        client = DaisyClient.__new__(DaisyClient)
        return client._parse_staff_details(person_id, html)

    async def get_all_staff(
        self,
        institution_id: str | InstitutionID = InstitutionID.DSV,
        batch_size: int = 10,
        delay_between_batches: float = 0.5
    ) -> list[Staff]:
        """Get all staff members with complete details.

        Args:
            institution_id: Institution ID (default: InstitutionID.DSV)
            batch_size: Number of concurrent requests per batch (default: 10)
            delay_between_batches: Delay in seconds between batches (default: 0.5)

        Returns:
            List of Staff objects with complete details
        """
        await self._ensure_authenticated()

        logger.info(f"Fetching all staff for institution {institution_id}")

        # First, search for all staff
        staff_list = await self.search_staff(institution_id=institution_id)

        # Then fetch details in batches to avoid overwhelming the server
        logger.info(f"Fetching details for {len(staff_list)} staff members in batches of {batch_size}...")

        import asyncio

        async def fetch_with_fallback(staff: Staff) -> Staff:
            """Fetch details with fallback to basic info on error."""
            try:
                return await self.get_staff_details(staff.person_id)
            except Exception as e:
                logger.error(f"Error fetching details for {staff.name}: {e}")
                return staff

        detailed_staff = []

        # Process in batches
        for i in range(0, len(staff_list), batch_size):
            batch = staff_list[i:i + batch_size]
            logger.debug(f"Processing batch {i // batch_size + 1}/{(len(staff_list) + batch_size - 1) // batch_size}")

            batch_results = await asyncio.gather(
                *[fetch_with_fallback(staff) for staff in batch]
            )
            detailed_staff.extend(batch_results)

            # Add delay between batches (except after the last batch)
            if i + batch_size < len(staff_list):
                await asyncio.sleep(delay_between_batches)

        logger.info(f"Completed: {len(detailed_staff)} staff members with details")
        return detailed_staff
