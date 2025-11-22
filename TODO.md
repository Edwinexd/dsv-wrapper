# DSV Wrapper Package - Implementation TODO

## Project Overview
Create a reusable Python package for accessing DSV systems (Daisy, Handledning) with sync/async support, Pydantic models, and cookie caching.

**Tech Stack:** Python 3.12+, Pydantic, requests, aiohttp, BeautifulSoup4

---

## Phase 1: Project Setup
- [ ] Create virtual environment (`venv/`)
- [ ] Create `pyproject.toml` with dependencies
- [ ] Install dependencies in venv
- [ ] Create package structure with `__init__.py` files
- [ ] Create `.gitignore` (venv/, *.pyc, __pycache__/, .env, .cookie_cache.json)
- [ ] Update requirements.txt

---

## Phase 2: Core Infrastructure

### Exceptions Module (`dsv_wrapper/exceptions.py`)
- [ ] Create base `DSVWrapperError` exception
- [ ] Add `AuthenticationError` for login failures
- [ ] Add `SessionExpiredError` for expired sessions
- [ ] Add `BookingError` for Daisy booking failures
- [ ] Add `HandledningError` for tutoring queue errors
- [ ] Add `ValidationError` for data validation issues

### Utilities Module (`dsv_wrapper/utils.py`)
- [ ] Create standard headers dict with User-Agent
- [ ] Add HTML parsing helper functions (BeautifulSoup wrappers)
- [ ] Add date/time utilities (timezone handling, date formatting)
- [ ] Add async run helper (from daisy-booker utils.py)
- [ ] Add logging configuration

---

## Phase 3: Authentication System

### Cookie Cache (`dsv_wrapper/auth/cache.py`)
**Source:** `/Users/edwin/dsv-map/cookie_cache.py`
- [ ] Port `get_cached_cookie()` function
- [ ] Port `save_cookie_to_cache()` function
- [ ] Make cache file path configurable
- [ ] Make cache duration configurable (default 24h)
- [ ] Add cache invalidation method
- [ ] Add async versions of cache functions

### Shibboleth SSO Login (`dsv_wrapper/auth/sso.py`)
**Sources:**
- `/Users/edwin/Documents/dsv-daisy-booker/login.py` (Daisy)
- `/Users/edwin/dsv-map/login.py` (Handledning variants)

#### Sync Implementation
- [ ] Extract Shibboleth login flow (8-step process)
- [ ] Implement `sso_login(username, password, target_url)` function
- [ ] Implement `daisy_login(username, password, staff=False)` wrapper
- [ ] Implement `handledning_login(username, password)` wrapper
- [ ] Implement `mobil_handledning_login(username, password)` wrapper
- [ ] Add session validation `is_session_valid(jsessionid, service)`
- [ ] Integrate cookie caching

#### Async Implementation
- [ ] Create async version of Shibboleth flow (aiohttp)
- [ ] Implement `async_sso_login()` function
- [ ] Implement async wrappers for all login variants
- [ ] Implement `async_is_session_valid()`
- [ ] Integrate with async cookie cache

### Session Manager (`dsv_wrapper/auth/session.py`)
- [ ] Create `SessionManager` class for sync operations
- [ ] Auto-refresh expired sessions
- [ ] Handle multiple service sessions (Daisy, Handledning)
- [ ] Create `AsyncSessionManager` class
- [ ] Add context manager support (`with` statement)

---

## Phase 4: Data Models

### Pydantic Models (`dsv_wrapper/models.py`)
**Source:** `/Users/edwin/Documents/dsv-daisy-booker/schemas.py`

#### Room & Time Models
- [ ] Convert `RoomTime` enum (9-23 hours) to Pydantic
- [ ] Convert `RoomCategory` enum (9 categories) to Pydantic
- [ ] Convert `Room` enum (60+ rooms) to Pydantic
- [ ] Add room lookup helpers (by name, by ID)

#### Booking Models
- [ ] Convert `BookingSlot` to Pydantic model
- [ ] Create `Booking` model (with confirmation details)
- [ ] Add validation (from_time < to_time, etc.)

#### Schedule Models
- [ ] Convert `Schedule` to Pydantic model
- [ ] Convert `RoomActivity` to Pydantic model
- [ ] Add datetime parsing/formatting

#### User Models
- [ ] Create `Student` model (name, ID, email, etc.)
- [ ] Create `Teacher` model (name, ID, email, rooms, etc.)
- [ ] Create `Course` model (code, name, period, etc.)

#### Handledning Models
- [ ] Create `TutoringList` model (list ID, name, active, etc.)
- [ ] Create `TutoringQueue` model (students, teacher, room, etc.)
- [ ] Create `Schedule` model for handledning sessions

---

## Phase 5: Daisy Client

### Sync Daisy Client (`dsv_wrapper/daisy/client.py`)
**Sources:**
- `/Users/edwin/Documents/dsv-daisy-booker/daisy.py`
- `/Users/edwin/dsv-map/login.py`

#### Core Client
- [ ] Port `Daisy` class structure
- [ ] Initialize with credentials and session manager
- [ ] Implement `_ensure_valid_jsessionid()` for auto-refresh
- [ ] Add `_make_request()` helper with error handling

#### Booking Operations
- [ ] Port `create_booking()` method (lines 142-216 in daisy.py)
- [ ] Port `book_slots()` method for batch booking
- [ ] Add `cancel_booking()` method
- [ ] Add `list_my_bookings()` method

#### Schedule Operations
- [ ] Port `get_schedule_for_category()` method
- [ ] Add date range schedule retrieval
- [ ] Parse schedule HTML to `Schedule` models

#### Search Operations
- [ ] Port `daisy_search_student()` from login.py:622-679
- [ ] Return list of `Student` models
- [ ] Add fuzzy search support

#### Staff Operations
- [ ] Port staff list scraping from `/Users/edwin/dsv-map/get_all_dsv_employees.py`
- [ ] Return list of `Teacher` models
- [ ] Add caching for staff list (rarely changes)

### Async Daisy Client (`dsv_wrapper/daisy/async_client.py`)
- [ ] Create `AsyncDaisy` class mirroring sync client
- [ ] Use aiohttp for all requests
- [ ] Implement all booking operations (async)
- [ ] Implement all schedule operations (async)
- [ ] Implement all search operations (async)
- [ ] Implement staff operations (async)

---

## Phase 6: Handledning Client

### Sync Handledning Client (`dsv_wrapper/handledning/client.py`)
**Source:** `/Users/edwin/dsv-map/login.py` (lines 324-1067)

#### Desktop Handledning
- [ ] Port `get_planned_schedules()` (lines 324-476)
- [ ] Parse schedule HTML and return `TutoringList` models
- [ ] Port `get_list_info_for_student()` (lines 869-981)
- [ ] Port `parse_list_details()` (lines 478-867)

#### Mobile Handledning
- [ ] Port `get_mobile_schedules()` (lines 983-1004)
- [ ] Port `activate_all_lists()` (lines 1006-1067)
- [ ] Add `activate_list()` for single list
- [ ] Add `deactivate_list()` method

#### Queue Management
- [ ] Add `get_queue_status()` method
- [ ] Add `get_waiting_students()` method
- [ ] Add student tracking across lists

### Async Handledning Client (`dsv_wrapper/handledning/async_client.py`)
- [ ] Create `AsyncHandledning` class mirroring sync client
- [ ] Use aiohttp for all requests
- [ ] Implement all desktop operations (async)
- [ ] Implement all mobile operations (async)
- [ ] Implement queue management (async)

---

## Phase 7: Unified Client Interface

### Main Client (`dsv_wrapper/client.py`)
- [ ] Create `DSVClient` class
- [ ] Initialize with SU username/password
- [ ] Property for `daisy` client (lazy init)
- [ ] Property for `handledning` client (lazy init)
- [ ] Property for `mobil_handledning` client (lazy init)
- [ ] Enable/disable caching via constructor
- [ ] Support staff vs student mode

### Async Client (`dsv_wrapper/async_client.py`)
- [ ] Create `AsyncDSVClient` class
- [ ] Same interface as sync client
- [ ] Async context manager support
- [ ] Proper cleanup of aiohttp sessions

---

## Phase 8: Package Configuration

### pyproject.toml
- [ ] Set package name, version (0.1.0)
- [ ] Set Python requirement (>=3.12)
- [ ] Add dependencies:
  - requests >= 2.31.0
  - aiohttp >= 3.9.0
  - pydantic >= 2.5.0
  - beautifulsoup4 >= 4.12.0
  - python-dotenv >= 1.0.0
  - lxml >= 4.9.0 (faster HTML parsing)
- [ ] Add dev dependencies (pytest, pytest-asyncio, black, mypy)
- [ ] Configure build system (setuptools/hatchling)

### Package Init Files
- [ ] `/dsv_wrapper/__init__.py` - Export main classes
- [ ] `/dsv_wrapper/auth/__init__.py` - Export auth functions
- [ ] `/dsv_wrapper/daisy/__init__.py` - Export Daisy clients
- [ ] `/dsv_wrapper/handledning/__init__.py` - Export Handledning clients

---

## Phase 9: Documentation & Examples

### README.md
- [ ] Package overview and features
- [ ] Installation instructions
- [ ] Quick start example
- [ ] Authentication setup (.env file)
- [ ] Daisy usage examples (booking, search)
- [ ] Handledning usage examples (queue, lists)
- [ ] API reference link
- [ ] Contributing guidelines

### Example Scripts (`examples/`)
- [ ] `example_booking.py` - Book a room in Daisy
- [ ] `example_search.py` - Search for students
- [ ] `example_schedule.py` - Get room schedules
- [ ] `example_handledning.py` - Activate tutoring lists
- [ ] `example_async.py` - Async usage demonstration
- [ ] `.env.example` - Template for credentials

### CLAUDE.md
- [ ] Create project-specific instructions
- [ ] Note to always update TODO.md when tasks are done
- [ ] Note about maintaining requirements.txt
- [ ] Code style preferences (Pydantic models, etc.)

---

## Phase 10: Testing & Quality

### Basic Tests (`tests/`)
- [ ] Test cookie caching (save/load/expire)
- [ ] Test Pydantic model validation
- [ ] Mock authentication flow
- [ ] Test sync clients (mocked responses)
- [ ] Test async clients (mocked responses)
- [ ] Test error handling

### Code Quality
- [ ] Run mypy for type checking
- [ ] Format with black (if available)
- [ ] Ensure all files have final newline
- [ ] Check no security issues (hardcoded credentials, etc.)

---

## Phase 11: Final Steps

- [ ] Test package installation in fresh venv
- [ ] Verify all imports work correctly
- [ ] Run example scripts to ensure they work
- [ ] Update TODO.md to mark all items complete
- [ ] Update requirements.txt with final dependencies
- [ ] Create initial git commit (if desired)

---

## Notes

### Key Files to Reference During Implementation
1. `/Users/edwin/dsv-map/cookie_cache.py` - Cookie caching
2. `/Users/edwin/Documents/dsv-daisy-booker/login.py` - Daisy login (cleanest)
3. `/Users/edwin/dsv-map/login.py` - All Handledning functions
4. `/Users/edwin/Documents/dsv-daisy-booker/daisy.py` - Complete Daisy client
5. `/Users/edwin/Documents/dsv-daisy-booker/schemas.py` - All data models
6. `/Users/edwin/dsv-map/get_all_dsv_employees.py` - Staff scraping

### Design Decisions
- **Pydantic over attrs/dataclasses:** Chosen for validation, serialization
- **Both sync and async:** Maximum flexibility for different use cases
- **Python 3.12+:** Use latest features (type unions with |, etc.)
- **Modular design:** Separate auth, daisy, handledning for clarity
- **Cookie caching:** Reduce login overhead, 24h default TTL

### API Endpoints to Support
- Daisy: `daisy.dsv.su.se` (student & staff logins)
- Handledning: `handledning.dsv.su.se` (desktop version)
- Mobile Handledning: `mobil.handledning.dsv.su.se`
- SU IdP: `idp.it.su.se` (Shibboleth authentication)
