# DSV Wrapper

A reusable Python package for accessing DSV systems (Daisy, Handledning) at Stockholm University.

## ⚠️ Disclaimer

**This project is an experimental initiative where all code is intended to be written by agentic AI.** The code is provided as-is for research and educational purposes. Use at your own risk.

For questions or concerns regarding this project, please contact: edwinsu@dsv.su.se

## Features

- **Unified Authentication**: Shibboleth SSO login with cookie caching
- **Daisy Integration**: Room booking, schedule retrieval, student/staff search, course (moment) iteration per semester with role-grouped medverkande and lazy username resolution
- **Handledning Integration**: Lab supervision queue management
- **Clickmap Integration**: DSV office/workspace placement lookup
- **Mail Integration**: Send and read emails via SU webmail (mail.su.se)
- **Play Integration**: List DSVPlay courses/presentations, fetch transcripts, enumerate and download mp4 tracks
- **Sync & Async**: Both synchronous and asynchronous APIs
- **Type Safe**: Pydantic models for all data structures
- **Python 3.12+**: Modern Python with latest features

## Installation

### From source

```bash
git clone https://github.com/Edwinexd/dsv-wrapper.git
cd dsv-wrapper
python3.13 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -e .
```

### From requirements.txt in another project

```bash
# Add to your requirements.txt
-e git+https://github.com/Edwinexd/dsv-wrapper.git#egg=dsv-wrapper

# Or install directly
pip install -e git+https://github.com/Edwinexd/dsv-wrapper.git#egg=dsv-wrapper
```

## Quick Start

### Using the Unified Client

```python
from dsv_wrapper import DSVClient
from dsv_wrapper.models import RoomCategory
from datetime import date

# Initialize the unified client
with DSVClient(username="your_username", password="your_password") as client:
    # Access Daisy
    schedule = client.daisy.get_schedule(RoomCategory.BOOKABLE_GROUP_ROOMS, date.today())
    print(f"Found {len(schedule.activities)} activities")

    # Access Handledning
    sessions = client.handledning.get_all_active_sessions()
    print(f"Found {len(sessions)} active sessions")
```

### Using Individual Clients

#### Daisy Client

```python
from dsv_wrapper import DaisyClient, Semester, AmbiguousMatchError
from dsv_wrapper.models import RoomCategory, Room, RoomTime, BookingSlot
from datetime import date

with DaisyClient(username="user", password="pass", service="daisy_staff") as daisy:
    # Room schedule
    schedule = daisy.get_schedule(RoomCategory.BOOKABLE_GROUP_ROOMS, date.today())
    print(f"Schedule for {schedule.room_category_title}")
    for room_name, activities in schedule.activities.items():
        print(f"\nRoom: {room_name}")
        for a in activities:
            print(f"  {a.time_slot_start.to_string()}-{a.time_slot_end.to_string()}: {a.event}")

    # Room booking
    slot = BookingSlot(room=Room.G10_1, from_time=RoomTime.NINE, to_time=RoomTime.TEN)

    # Search for students by full first+last name (returns 0-N hits)
    hits = daisy.search_students(first_name="Edwin", last_name="Sundberg")
    for s in hits:
        print(f"Student {s.full_name} (personID={s.person_id})")
        # Username isn't on the search row — resolve on demand:
        print(f"  username: {s.get_username(daisy)}")

    # Staff search and full profile (with usernames, office hours, …)
    staff_list = daisy.search_staff(last_name="Åkerblom")
    staff = daisy.get_staff_details(staff_list[0].person_id)
    print(staff.usernames, staff.office_hours, staff.website)


# --- Department-wide course/medverkande iteration ----------------------------
# Iterate every course offering for a semester, list everyone involved with
# their roles, and resolve missing personIDs/usernames lazily.

with DaisyClient() as daisy:
    vt2026 = Semester.from_label("VT2026")     # also: Semester.from_termin_id("20261")
    for course in daisy.get_courses(vt2026):    # auto-paginated
        print(f"\n{course.beteckning} — {course.name}  ({course.ects} hp)")
        print(f"  {course.start_date} → {course.end_date}")
        print(f"  syllabus: {course.syllabus_url or '-'}")

        for cs in daisy.get_course_participants(course.momenttillf_id):
            # cs.roles is a list, e.g. ['Kurs-/delkursansvarig', 'Examination']
            # cs.person_id is None for plain-text names (typically student-handledare)
            try:
                pid = cs.get_person_id(daisy)
            except AmbiguousMatchError as e:
                print(f"    ! {cs.name} unresolved: {e}")
                continue

            if cs.profile_url and "studentinfo" in cs.profile_url:
                details = daisy.get_student_details(pid)
                username = details.username
            else:
                details = daisy.get_staff_details(pid)
                username = details.usernames[0] if details.usernames else None

            print(f"  {cs.name:30s} {cs.roles}  → {username}")
```

`Semester` encodes Daisy's 5-digit `terminID` (`YYYY1`=VT, `YYYY2`=HT) and accepts `from_label("VT2026")` / `from_termin_id(20261)`. Course offerings ("moment") expose `beteckning`, `name`, `ects`, `start_date`/`end_date`, `info_url`, `schedule_url`, `participants_url`, and (after `get_course`) `syllabus_url` + `unit`.

`CourseStaff.get_person_id(client)` is cached: it returns the parsed `person_id` from the page immediately, falls back to a Daisy student search by full first+last name (with a second attempt using `first_token / remaining_tokens` for multi-word surnames like *Fathi Tachinabadi*), and raises `AmbiguousMatchError` on 0 or >1 hits. `Student.get_username(client)` and `Staff.get_usernames(client)` follow the same lazy-cache-or-throw pattern.

#### Handledning Client

```python
from dsv_wrapper import HandledningClient

with HandledningClient(username="user", password="pass") as handledning:
    # Get teacher sessions
    sessions = handledning.get_teacher_sessions()

    for session in sessions:
        print(f"{session.course_code}: {session.course_name}")
        print(f"  {session.start_time} - {session.end_time}")
        print(f"  Active: {session.is_active}")

    # Get queue for a session
    if sessions:
        queue = handledning.get_queue(session_id="session123")
        print(f"Queue length: {len(queue)}")

        for entry in queue:
            print(f"  {entry.position}. {entry.student.username} - {entry.status}")

    # Add student to queue
    handledning.add_to_queue(session_id="session123")

    # Activate session (teacher only)
    handledning.activate_session(session_id="session123")
```

#### Mail Client

```python
from dsv_wrapper import MailClient, BodyType

with MailClient(username="user", password="pass") as mail:
    # Get inbox stats
    inbox = mail.get_folder("inbox")
    print(f"Inbox: {inbox.total_count} emails, {inbox.unread_count} unread")

    # List recent emails (headers only, no body for efficiency)
    emails = mail.get_emails("inbox", limit=10)
    for email in emails:
        sender = email.sender.email if email.sender else "Unknown"
        print(f"{email.subject} - from {sender}")

    # Get full email content including body
    if emails:
        full_email = mail.get_email(emails[0].id, emails[0].change_key)
        print(f"Body: {full_email.body[:200]}...")

    # Send an email
    result = mail.send_email(
        to="recipient@example.com",
        subject="Hello from dsv-wrapper",
        body="This is a test email.",
        body_type=BodyType.TEXT,
        cc=["cc@example.com"],  # Optional
        save_to_sent=True,  # Save copy to sent items
    )
    if result.success:
        print(f"Email sent! Message ID: {result.message_id}")
    else:
        print(f"Failed to send: {result.error}")
```

#### Play Client

```python
from dsv_wrapper import PlayClient

with PlayClient(username="user", password="pass") as play:
    # Discover content
    courses = play.get_courses()
    presentations = play.get_presentations(courses[0].code)
    transcript = play.get_transcript_text(presentations[0].id)

    # Enumerate mp4 tracks. The returned TrackInfo carries no URLs — every
    # track is addressable only through (presentation_uuid, track_index)
    # within the same authenticated session, so the SSO session never
    # leaves the library.
    tracks = play.get_media_tracks(presentations[0].id)
    for t in tracks:
        size_mb = (t.size_bytes or 0) / 1024 / 1024
        print(f"  idx={t.index} {t.height}p {size_mb:.1f} MB ({t.mime_type})")

    # Cheap moov-atom probe (~2 MiB) before committing to a full download
    # — play-store-prod.dsv.su.se honours HTTP Range headers.
    head = b"".join(play.stream_track(presentations[0].id, 0, end_byte=2 * 1024 * 1024 - 1))

    # Stream the chosen track to disk in 1 MiB chunks.
    play.download_track(presentations[0].id, 0, "/tmp/lecture.mp4")
```

#### Clickmap Client

```python
from dsv_wrapper import ClickmapClient

with ClickmapClient(username="user", password="pass") as clickmap:
    # Get all workspace placements
    placements = clickmap.get_placements()

    # Search by person or place name
    results = clickmap.search_placements("Karlsson")
    for p in results:
        print(f"{p.person_name} - Room {p.place_name}")

    # Get only occupied workspaces
    occupied = clickmap.get_occupied_placements()
```

### Async Usage

```python
import asyncio
from dsv_wrapper import AsyncDSVClient
from dsv_wrapper.models import RoomCategory
from datetime import date

async def main():
    async with AsyncDSVClient(username="user", password="pass") as client:
        # Get Daisy client
        daisy = await client.get_daisy()
        schedule = await daisy.get_schedule(RoomCategory.BOOKABLE_GROUP_ROOMS, date.today())
        print(f"Found {len(schedule.activities)} activities")

        # Get Handledning client
        handledning = await client.get_handledning()
        sessions = await handledning.get_all_active_sessions()
        print(f"Found {len(sessions)} active sessions")

asyncio.run(main())
```

## Authentication

### Cookie Caching

By default, authentication cookies are not cached. You can enable caching by providing a cache backend:

```python
from dsv_wrapper import DSVClient
from dsv_wrapper.auth.cache_backend import MemoryCache, FileCache

# Using memory cache (simple, but lost on restart)
memory_cache = MemoryCache()

client = DSVClient(
    username="user",
    password="pass",
    cache_backend=memory_cache,
    cache_ttl=86400  # 24 hours in seconds
)

# Or use file cache for persistence
file_cache = FileCache(cache_dir="/custom/cache/path")

client = DSVClient(
    username="user",
    password="pass",
    cache_backend=file_cache,
    cache_ttl=172800  # 48 hours in seconds
)
```

### Service Types

Different service endpoints are available:

```python
from dsv_wrapper import DaisyClient

# Staff version (default)
daisy_staff = DaisyClient(username="user", password="pass", service="daisy_staff")

# Student version
daisy_student = DaisyClient(username="user", password="pass", service="daisy_student")
```

### Direct Authentication

You can authenticate directly to specific services using ShibbolethAuth:

```python
from dsv_wrapper import ShibbolethAuth

auth = ShibbolethAuth(username="user", password="pass")

# Available services
cookies = auth.login(service="daisy_staff")
cookies = auth.login(service="daisy_student")
cookies = auth.login(service="handledning")
cookies = auth.login(service="actlab")
```

## Models

All data is represented using Pydantic models for type safety:

```python
from dsv_wrapper.models import (
    # Daisy models
    Room, RoomCategory, RoomTime, RoomRestriction,
    BookingSlot, RoomActivity, BookableRoom, Schedule, Break,
    Student, Teacher, Course, Staff, ActivityType,
    # Daisy course / medverkande
    Semester, TermSeason, DaisyCourse, CourseStaff, CourseResponsibility,
    # Handledning models
    QueueEntry, QueueStatus, HandledningSession,
    # Clickmap models
    Placement,
    # Mail models
    MailFolder, EmailMessage, EmailAddress, SendEmailResult,
    BodyType, Importance,
    # Play models
    PlayCourse, Presentation, TrackInfo, TranscriptCue, VideoSource,
)

# Room enums with specific IDs
room = Room.G10_1
print(f"Room ID: {room.value}")  # 633

# Room categories with numeric IDs
category = RoomCategory.BOOKABLE_GROUP_ROOMS
print(f"Category ID: {category.value}")  # 68
print(f"Category string: {category.to_string()}")  # "68"

# Time slots
start = RoomTime.NINE
end = RoomTime.TEN
print(f"Time: {start.to_string()} - {end.to_string()}")  # "09:00 - 10:00"

# Booking slots (models are immutable/frozen)
booking = BookingSlot(
    room=Room.G10_1,
    from_time=RoomTime.NINE,
    to_time=RoomTime.TEN
)
# booking.room = Room.G10_2  # This would raise an error

# Room restrictions for filtering
restriction = RoomRestriction.GREEN_AREA
filter_func = restriction.to_filter()
rooms = [Room.G10_1, Room.G10_6, Room.G5_1]
green_area_rooms = [r for r in rooms if filter_func(r)]
```

## Error Handling

The package provides a comprehensive exception hierarchy:

```python
from dsv_wrapper import (
    DSVWrapperError,
    AuthenticationError,
    BookingError,
    RoomNotAvailableError,
    HandledningError,
    QueueError,
    AmbiguousMatchError,  # raised by CourseStaff.get_person_id / Student.get_username
)

try:
    daisy.book_room(...)
except RoomNotAvailableError:
    print("Room is already booked")
except BookingError as e:
    print(f"Booking failed: {e}")
except AuthenticationError as e:
    print(f"Authentication failed: {e}")
except DSVWrapperError as e:
    print(f"General error: {e}")
```

## Utilities

Helper functions are available for common operations:

```python
from dsv_wrapper.utils import (
    parse_time,
    parse_date,
    parse_swedish_date,
    format_date_swedish,
    get_weekday_swedish,
)

# Parse time
start = parse_time("09:00")  # Returns time(9, 0)

# Parse Swedish date
date = parse_swedish_date("15 januari 2024")

# Format Swedish date
formatted = format_date_swedish(date.today())  # "21 november 2024"

# Get Swedish weekday
weekday = get_weekday_swedish(date.today())  # "Torsdag"
```

## Environment Variables

You can use environment variables for credentials:

```python
import os
from dotenv import load_dotenv
from dsv_wrapper import DSVClient

load_dotenv()

client = DSVClient(
    username=os.getenv("SU_USERNAME"),
    password=os.getenv("SU_PASSWORD")
)
```

Create a `.env` file:
```bash
SU_USERNAME=your_username
SU_PASSWORD=your_password
```

## Development

### Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=dsv_wrapper
```

### Code Formatting

```bash
# Format code
black dsv_wrapper/

# Lint code
ruff check dsv_wrapper/
```

## Project Structure

```
dsv-wrapper/
├── dsv_wrapper/
│   ├── __init__.py          # Package exports
│   ├── auth/                # Authentication module
│   │   ├── __init__.py
│   │   ├── shibboleth.py   # SSO login handlers
│   │   └── cache_backend.py # Cookie caching
│   ├── models/              # Pydantic models
│   │   ├── __init__.py
│   │   ├── daisy.py        # Daisy models
│   │   ├── handledning.py  # Handledning models
│   │   ├── clickmap.py     # Clickmap models
│   │   ├── mail.py         # Mail models
│   │   └── common.py       # Shared models
│   ├── parsers/             # HTML/data parsing
│   │   ├── actlab.py
│   │   ├── daisy.py
│   │   └── handledning.py
│   ├── daisy.py             # Daisy client
│   ├── handledning.py       # Handledning client
│   ├── actlab.py            # ACT Lab client
│   ├── clickmap.py          # Clickmap client
│   ├── mail.py              # Mail client (OWA API)
│   ├── client.py            # Unified client
│   ├── utils.py             # Utilities
│   └── exceptions.py        # Custom exceptions
├── tests/                   # Test suite
├── pyproject.toml          # Project configuration
├── requirements.txt        # Dependencies
├── CLAUDE.md               # AI development notes
└── README.md               # This file
```

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please read our [Contributing Guidelines](CONTRIBUTING.md) before submitting pull requests.

### Quick Start for Contributors

```bash
# Fork and clone the repository
git clone <your-fork-url>
cd dsv-wrapper

# Set up development environment
python3.13 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black dsv_wrapper/
ruff check dsv_wrapper/
```

## Support

For issues and questions, please open an issue on the repository.
