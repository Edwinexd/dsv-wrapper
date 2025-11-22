# DSV Wrapper

A reusable Python package for accessing DSV systems (Daisy, Handledning) at Stockholm University.

## Features

- **Unified Authentication**: Shibboleth SSO login with cookie caching
- **Daisy Integration**: Room booking, schedule retrieval, student search
- **Handledning Integration**: Lab supervision queue management
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
    schedule = client.daisy.get_schedule(RoomCategory.GROUPA, date.today())
    print(f"Found {len(schedule.rooms)} rooms")

    # Access Handledning
    sessions = client.handledning.get_all_active_sessions()
    print(f"Found {len(sessions)} active sessions")
```

### Using Individual Clients

#### Daisy Client

```python
from dsv_wrapper import DaisyClient, RoomCategory
from datetime import date, time

with DaisyClient(username="user", password="pass", service="daisy_staff") as daisy:
    # Get room schedule
    schedule = daisy.get_schedule(RoomCategory.GROUPA, date.today())

    for room in schedule.rooms:
        print(f"Room: {room.name}")
        for slot in room.available_times:
            if slot.available:
                print(f"  Available: {slot.start} - {slot.end}")

    # Book a room
    daisy.book_room(
        room_id="room123",
        schedule_date=date.today(),
        start_time=time(9, 0),
        end_time=time(10, 0),
        purpose="Meeting"
    )

    # Search for students
    students = daisy.search_students("john", limit=10)
    for student in students:
        print(f"Student: {student.full_name} ({student.username})")
```

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

### Async Usage

```python
import asyncio
from dsv_wrapper import AsyncDSVClient, RoomCategory
from datetime import date

async def main():
    async with AsyncDSVClient(username="user", password="pass") as client:
        # Get Daisy client
        daisy = await client.get_daisy()
        schedule = await daisy.get_schedule(RoomCategory.GROUPA, date.today())
        print(f"Found {len(schedule.rooms)} rooms")

        # Get Handledning client
        handledning = await client.get_handledning()
        sessions = await handledning.get_all_active_sessions()
        print(f"Found {len(sessions)} active sessions")

asyncio.run(main())
```

## Authentication

### Cookie Caching

By default, authentication cookies are cached for 24 hours to avoid repeated logins:

```python
from dsv_wrapper import DSVClient, CookieCache

# Custom cache configuration
cache = CookieCache(
    cache_dir="/custom/cache/path",
    ttl_hours=48,  # Cache for 48 hours
)

client = DSVClient(
    username="user",
    password="pass",
    use_cache=True  # Default
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

### Unified SSO

The authentication system supports the unified SSO endpoint:

```python
from dsv_wrapper import ShibbolethAuth

auth = ShibbolethAuth(username="user", password="pass")

# Login to unified SSO
cookies = auth.login(service="unified")

# Or specific services
cookies = auth.login(service="daisy_staff")
cookies = auth.login(service="daisy_student")
cookies = auth.login(service="handledning")
```

## Models

All data is represented using Pydantic models for type safety:

```python
from dsv_wrapper.models import (
    Room, RoomCategory, RoomTime, BookingSlot, Schedule,
    Student, Teacher, Course,
    QueueEntry, QueueStatus, HandledningSession,
    RoomActivity, ActivityType
)

# Models are immutable (frozen)
room = Room(id="123", name="Room A", category=RoomCategory.GROUPA)
# room.name = "New name"  # This would raise an error

# Access model properties
print(room.name)
print(room.category.value)

# Models have validation
booking = BookingSlot(
    room_id="123",
    room_name="Room A",
    date=date.today(),
    start_time=time(9, 0),
    end_time=time(10, 0)
)
print(f"Duration: {booking.duration_hours} hours")
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
│   │   └── cache.py         # Cookie caching
│   ├── models.py            # Pydantic models
│   ├── daisy.py             # Daisy client
│   ├── handledning.py       # Handledning client
│   ├── client.py            # Unified client
│   ├── utils.py             # Utilities
│   └── exceptions.py        # Custom exceptions
├── examples/                # Example scripts
├── pyproject.toml          # Project configuration
├── requirements.txt        # Dependencies
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
