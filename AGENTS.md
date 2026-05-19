## Project Status

- **99 of 99 pytest tests passing** - 100% pass rate!
- **Major architecture refactor COMPLETE**: Fully migrated from requests/aiohttp to httpx
- **Strict error handling implemented**: Silent failures replaced with explicit ParseError exceptions
- All clients (ACTLab, Daisy, Handledning, Clickmap, Play) now use unified httpx architecture
- Sync and async clients have full API parity with automated tests to prevent de-sync
- **All authentication and cookie issues resolved**
- ~50% code duplication eliminated through shared parsing functions
- BaseAsyncClient removed - no longer needed
- Disclaimer added to README regarding AI-generated code experiment
- **NEW: Clickmap client added** - Extract DSV office/workspace placements
- **NEW: Mail client added** - Send and read emails via SU webmail (mail.su.se)
- **NEW: Play client added** - Access DSVPlay presentations, transcripts, and courses
- **NEW: Daisy course/medverkande API** - Iterate course offerings per semester, fetch details, list participants

## Architecture Changes (2025-11-24)

### httpx Migration
- **Replaced requests + aiohttp with httpx**: Now using a single HTTP library for both sync and async
- **Benefits**:
  - ~50% reduction in code duplication potential
  - Simpler cookie management (no complex cookie transfer between libraries)
  - Unified API for sync and async HTTP calls
  - Better redirect handling and modern HTTP/2 support

### New Structure
- `ShibbolethAuth` now uses `httpx.Client` instead of `requests.Session`
- `AsyncShibbolethAuth` still wraps sync auth using `asyncio.to_thread()` but now works with httpx
- All clients use `httpx.Client` (sync) or `httpx.AsyncClient` (async)
- **BaseAsyncClient completely removed** - all clients follow the new httpx pattern
- All async clients use `__aenter__`/`__aexit__` context managers with httpx.AsyncClient
- **httpx clients are private** - stored as `_client` (not `client`) to prevent external access to internal HTTP client

### Parsing Functions Pattern
- Created `/dsv_wrapper/parsers/` module for shared parsing logic
- Parsing functions are pure functions that take HTML and return models
- Both sync and async clients use the same parsing functions
- **Example**: `dsv_wrapper/parsers/actlab.py` contains all ACTLab HTML parsing

### ACTLabClient Refactor (Complete)
- Both `ACTLabClient` and `AsyncACTLabClient` now use httpx
- Share parsing functions from `dsv_wrapper/parsers/actlab.py`
- Eliminated `__new__()` hack for parsing
- All ACTLab tests passing

### DaisyClient Refactor (Complete)
- Both `DaisyClient` and `AsyncDaisyClient` now use httpx
- Share parsing functions from `dsv_wrapper/parsers/daisy.py`
- Eliminated all `__new__()` hacks and removed BaseAsyncClient dependency
- All Daisy tests passing
- Cookie conflict issues resolved by using cookie jar directly
- **Added `download_profile_picture(url)` method**: Proper wrapper method for downloading images
  - Returns image bytes directly
  - Raises `NetworkError` on HTTP failures
  - Validates content type to ensure response is an image
  - External code no longer needs to access internal httpx client

### HandledningClient Refactor (Complete)
- Both `HandledningClient` and `AsyncHandledningClient` now use httpx
- Share parsing functions from `dsv_wrapper/parsers/handledning.py`
- Eliminated all `__new__()` hacks and removed BaseAsyncClient dependency
- All Handledning tests passing

### ClickmapClient (New - 2025-11-25)
- **New client for clickmap.dsv.su.se** - DSV office/workspace placement map
- Both `ClickmapClient` and `AsyncClickmapClient` implemented with httpx
- **API endpoints**:
  - `GET /api/points` - Returns all workspace placements with person info
  - `GET /api/export` - Export all data as TSV (admin/export permissions required)
- **Placement model** with fields:
  - `id`: UUID
  - `place_name`: Workspace/room identifier (e.g., "66109", "6:7")
  - `person_name`: Name of person at this workspace
  - `person_role`: Title/role of the person
  - `latitude`, `longitude`: Map coordinates
  - `comment`: Additional notes (requires export permission)
  - `is_occupied`: Property to check if workspace has a person
- **Client methods**:
  - `get_placements()`: Get all workspace placements
  - `search_placements(query)`: Search by person or place name
  - `get_placement_by_person(name)`: Find by exact person name
  - `get_placement_by_place(name)`: Find by exact place name
  - `get_occupied_placements()`: Get only placements with people
  - `get_vacant_placements()`: Get only empty placements
- Uses JSON API (no HTML parsing required)
- All 7 clickmap tests passing

### MailClient (Refactored - 2025-11-26)
- **Refactored to use standard IMAP/SMTP** - Much more robust than OWA API
- Both `MailClient` and `AsyncMailClient` implemented with Python's `imaplib` and `smtplib`
- **Server configuration**:
  - IMAP: `ebox.su.se:993` (SSL/TLS)
  - SMTP: `ebox.su.se:587` (STARTTLS)
  - **Username formats**:
    - Personal accounts: `winadsu\username`
    - Function accounts: `winadsu\username\mailbox.institution` (auto-detected)
- **Client initialization**:
  - `username`: SU username (env: `SU_USERNAME`)
  - `password`: SU password (env: `SU_PASSWORD`)
  - `email_address`: Sender email address (env: `SU_EMAIL`)
  - `email_name`: Display name for sender (env: `SU_EMAIL_NAME`) - **Added 2025-11-28**
    - Supports both `"Name"` and `"Name <email@address>"` formats
    - If `<email>` is provided, it must match `email_address` (validated)
    - Emails will show as `"Name" <email@address>` instead of just `email@address`
- **Client methods**:
  - `get_folder(folder_name)`: Get folder info (inbox, drafts, sentitems, etc.)
  - `get_emails(folder_name, limit)`: List emails in a folder (headers only, no body)
  - `get_email(message_id, change_key, body_type)`: Get full email content including body
  - `send_email(to, subject, body, body_type, cc, save_to_sent)`: Send email
  - `delete_email(change_key, permanent)`: Delete email (move to trash or permanent)
- **Models** (unchanged):
  - `MailFolder`: Folder with id, name, total_count, unread_count
  - `EmailMessage`: Full email with subject, body, sender, recipients, dates, etc.
  - `EmailAddress`: Email address with name
  - `SendEmailResult`: Send operation result with success/error
  - `BodyType` enum: TEXT or HTML
  - `Importance` enum: LOW, NORMAL, HIGH
- **Implementation details**:
  - Uses IMAP for reading emails with proper MIME parsing
  - Uses SMTP for sending with STARTTLS encryption
  - `change_key` field stores folder and IMAP sequence number (format: "folder:seqnum")
  - `delete_email()` selects folder in read-write mode before deletion (fixed 2025-11-27)
  - Folder IDs are hashes of folder names (IMAP doesn't have native IDs)
  - Email IDs are hashes of Message-ID headers
  - **Function account support** (added 2025-11-28):
    - Automatically detects function accounts vs personal accounts
    - Uses correct IMAP login format: `winadsu\username\mailbox.institution`
    - Example: For `lambda@dsv.su.se`, uses `winadsu\edsu8469\lambda.dsv`
- **Benefits over OWA API**:
  - Standard protocols - no fragile JSON API dependencies
  - Simpler authentication - direct username/password
  - Better error handling - clear IMAP/SMTP error codes
  - No session management or token handling needed

### PlayClient (New - 2026-03-31)
- **New client for play.dsv.su.se** - DSVPlay presentation/video platform
- Both `PlayClient` and `AsyncPlayClient` implemented with httpx
- **Authentication**: Shibboleth SSO (added "play" service type)
- **Data sources**:
  - `/user/all` (HTML) - Livewire snapshot contains user's courses
  - `/designation/{code}` (HTML) - Livewire snapshot contains playlist ID and video UUIDs
  - `/presentation/{uuid}` (JSON) - Presentation metadata with video sources, subtitles, JWT token
  - `/playlist/{id}` (JSON) - Playlist items with titles and thumbnails
  - VTT files on `play-store-prod.dsv.su.se` require `?token={jwt}` query param
- **Models**:
  - `PlayCourse`: Course with `code` and `name`
  - `Presenter`: Presenter with `username` and `name`
  - `VideoSource`: Video quality variants (`url_720p`, `url_1080p`, `poster_url`, `play_audio`)
  - `Presentation`: Full presentation with `id`, `title`, `thumb_url`, `sources`, `subtitles`, `token`
    - `has_subtitles` property, `video_url` property (best available URL)
  - `TranscriptCue`: Parsed VTT entry with `start_seconds`, `end_seconds`, `text`
    - `start_timestamp`/`end_timestamp` properties for HH:MM:SS.mmm format
- **Client methods**:
  - `get_courses()`: Get user's courses from DSVPlay
  - `get_presentations(designation)`: Get all presentations for a course (uses playlist endpoint)
  - `get_presentation(presentation_id)`: Get full presentation details (sources, subtitles, token)
  - `get_transcript(presentation_id)`: Get parsed VTT transcript as list of cues
  - `get_transcript_text(presentation_id)`: Get plain text transcript
- **Parsing** (`dsv_wrapper/parsers/play.py`):
  - Courses parsed from Livewire `wire:snapshot` JSON in HTML
  - Playlist ID extracted from Livewire data on designation pages
  - VTT parser handles WebVTT format with multi-line cues
- **Not-ready exception hierarchy** (`dsv_wrapper/exceptions.py`):
  - `PresentationNotReadyError(ParseError)`: recording itself still being
    processed; `/presentation/{uuid}` returned a non-dict envelope (observed
    in production: a list) or no `id` field. Raised by
    `parse_presentation_json` before `get_presentation` can build a model.
  - `TranscriptNotReadyError(PresentationNotReadyError)`: video sources are
    ready but no subtitles yet. Raised by `get_transcript`.
  - Callers wanting to handle either case the same way (e.g. "retry next
    run") catch the parent class; callers needing the captions-pending case
    specifically still catch `TranscriptNotReadyError`.
- All play tests passing (12 unit + 8 integration)

### Daisy Course / Medverkande API (New - 2026-05-19)
- **Iterate course offerings ("moment") in Daisy** with rich models for course
  metadata, participants, and staff responsibilities.
- **New models** (in `dsv_wrapper/models/daisy.py`):
  - `Semester`: combines `year` + `TermSeason` (VT/HT). Helpers:
    `Semester.from_label("VT2026")`, `Semester.from_termin_id("20261")`,
    `.termin_id` (`"20261"`), `.label` (`"VT2026"`). Daisy encodes terms as
    `YYYY1` for VT and `YYYY2` for HT.
  - `DaisyCourse`: a course offering (`momenttillf_id`, `beteckning`, `name`,
    `ects`, `semester`, `start_date`, `end_date`, `info_url`, `schedule_url`,
    `participants_url`, `syllabus_url`, `unit`). Search results omit
    `syllabus_url`/`unit`; the detail page omits start/end dates.
  - `CourseStaff`: a person involved on a course (`name`, `first_name`,
    `last_name`, `person_id`, `profile_url`, `roles: list[str]`). Sourced
    from the public momentinfo page's *Medverkande* section, which groups
    people under free-text role headings (*Kurs-/delkursansvarig*,
    *Examination*, *Handledare*, *Laborationsledare*, *Administration*,
    *Föreläsare*, *Gästföreläsare*, *Utveckling*, *Lektionsledare*, …).
    A person appearing under multiple groups is merged into a single
    `CourseStaff` with all their roles. Profile URLs may point at
    `/anstalld/anstalldinfo.jspa` OR `/anstalld/student/studentinfo.jspa`
    (e.g. former PhDs linked to their student record); the distinction is
    NOT a reliable indicator of current employment status, so we don't
    model it. **`person_id` is `None` for participants listed as plain
    text** without a profile link (typically student-handledare) – call
    `CourseStaff.get_person_id(client)` to resolve them. That method does
    a Daisy student search by full first+last name (with a fallback to
    `first_token / remaining_tokens` for multi-word surnames like
    "Fathi Tachinabadi") and raises :class:`AmbiguousMatchError` on 0 or
    >1 hits. The resolved id is cached on the instance.
  - `CourseResponsibility`: `(semester, beteckningar)` pair listed on a staff
    member's profile. Only the currently-displayed semester is captured per
    profile fetch (Daisy paginates these with arrow links).
  - Extended `Staff` fields: `usernames` (list — KTH/SU/DSV realms),
    `address` (newline-preserved), `home_phone`, `alt_phone`, `office_hours`
    (mottagningstid), `exam_systems`, `research_areas`, `website`,
    `course_responsibilities`.
- **Lazy ID/username resolution** on the models:
  - `CourseStaff.get_person_id(client)` / `.aget_person_id(client)` —
    returns cached `person_id` if set, else searches Daisy students by
    full name, throws :class:`AmbiguousMatchError` on 0/>1 hits.
  - `Student.get_username(client)` / `.aget_username(client)` — returns
    cached `username` if set, else fetches the student profile (using
    `person_id`), throws if none surfaced.
  - `Staff.get_usernames(client)` / `.aget_usernames(client)` — same
    pattern for staff profiles. Backfills every other empty field on
    the instance from the profile fetch.
  - All three caches mutate the instance in place (models are no longer
    frozen for this reason).
- **New client methods** on both `DaisyClient` and `AsyncDaisyClient`:
  - `get_courses(semester=None, *, semester_from=None, semester_to=None,
    beteckning="", name="", institution_id=DSV, max_pages=None)`: lists
    `DaisyCourse`s by auto-paginating
    `POST /sok/sokmoment.jspa` (20 per page, `querypage=N` 0-indexed). Pass
    `semester` for a single term, or `semester_from`/`semester_to` for a range.
  - `get_course(momenttillf_id)`: fetches `/servlet/momentinfo.Momentinfo?id=…`
    and parses out `ects`, `unit`, `semester`, and the external SU syllabus URL.
  - `get_course_participants(momenttillf_id)`: parses the public momentinfo
    page's *Medverkande* section and returns `CourseStaff`s. Works for any
    course in Daisy, not just ones you teach (unlike the auth-gated
    `akt=mdv` tab). Same URL as `get_course` – call both if you need
    metadata + participants, or use the parsers directly to avoid the
    second request. Captures both linked (`<a personID=N>…</a>`) and
    unlinked plain-text names; the latter come back with
    `person_id=None` and are resolved on demand via
    `CourseStaff.get_person_id`.
  - `search_students(last_name="", first_name="", email="", username="",
    institution_id="", page_size=25)`: POSTs to `/sok/visastudent.jspa`
    and parses the result table. Returns `Student` rows with `person_id`
    + `profile_url` populated but `username=None` – call
    `Student.get_username(client)` to resolve.
  - `get_student_details(person_id)`: fetches
    `/anstalld/student/studentinfo.jspa?personID=…` and returns a
    fully-populated `Student` (username, email, phone, program, address).
- **Parsing** (`dsv_wrapper/parsers/daisy.py`):
  - `parse_course_search` returns `(courses, range_from, range_to, total)` so
    callers can drive pagination if they want manual control.
  - `parse_course_detail` extracts beteckning/term from the page `<title>` and
    ECTS / unit from the "Namn / Enhet / Poäng" line.
  - `parse_course_participants` walks the role-grouped
    `<div class="brodtext">` blocks in the *Medverkande* row of the
    momentinfo page; each block starts with `<b>RoleName</b>` and contains
    `<a personID=N>…</a>Name` entries plus plain-text names without `<a>`
    wrappers. Same person across multiple role groups gets merged into
    one `CourseStaff`. The auth-gated `akt=mdv` tab is NOT used – it
    returns "Du är inte behörig" for courses the authenticated user
    doesn't teach. The `deltagarlista.jspa` endpoint is the enrolled-
    student roster (NOT the teaching team); student-handledare are not
    enrolled in their own course, so we can't use it for resolution.
  - `parse_staff_details` was extended to capture all the rich profile fields
    listed above without changing its signature.
- **Daisy URL conventions captured**:
  - `/sok/sokmoment.jspa` (POST) — course search; fields: `institution=4` for
    DSV, `fromTerminID`/`tomTerminID` (5-digit `YYYY[12]`), `beteckning`,
    `namn`, optional `querypage` for pagination.
  - `/servlet/momentinfo.Momentinfo?id=N` — public detail page.
  - `/servlet/schema.moment.Momentschema?id=N` — schedule.
  - `/anstalld/moment/deltagarlista.jspa?momenttillfID=N` — student list.
  - `/anstalld/moment/momentNav.jspa?momenttillfID=N&akt={inf|mdv|sch|exa|grp|utv|upp|med}`
    — internal staff nav (`mdv` = medverkande, `med` = meddelanden). The
    `mdv` tab carries email/phone/room columns but is restricted to the
    course's own teaching team; the public momentinfo page is preferred.
- **Tests**: 12 unit tests against captured HTML fixtures
  (`tests/fixtures/daisy/`) covering Semester roundtrips, course search
  pagination header, course detail title parsing, role-grouped participant
  merging (DB has 8 people across 9 role groups), and staff profile rich
  fields. Plus 3 live-integration tests for the new client methods.

### Strict Error Handling (Complete)
- **Replaced silent failures with explicit ParseError exceptions**
- Parsing functions now raise ParseError instead of silently continuing on errors:
  - Activity time slot parsing in Daisy schedules
  - Activity time parsing in Daisy room activities
  - Time parsing in Handledning sessions and queue entries
- Added validation for HTML attributes (href, src) before use to prevent silent None bugs
- Removed fallback behavior in `get_all_staff_details()` - now raises exceptions instead of returning partial data
- **Benefits**:
  - Parsing errors are immediately visible instead of silently skipped
  - Makes debugging easier by failing fast on malformed HTML
  - Ensures data integrity - no partial/incomplete results
  - More predictable error handling for API consumers

## Important Notes

- **HTTP 200 doesn't mean success in Daisy**: The service returns 200 status codes even for login pages and error pages. Always check the HTML content to verify successful responses.
- **Async auth implementation**: AsyncShibbolethAuth wraps the sync ShibbolethAuth using asyncio.to_thread() to avoid reimplementing the complex SAML flow. This ensures both versions work identically.
- **httpx redirects**: httpx requires absolute URLs for redirects. The auth code now converts relative redirect URLs to absolute before following them.
- **Cookie caching**: Cookies are now stored as dicts in the cache. FileCache backend updated to handle both dict and RequestsCookieJar formats.
- **Private httpx clients**: All httpx clients are stored as `_client` (private) to enforce proper encapsulation and prevent external code from bypassing the API.
- **Logging**: The library uses standard Python logging. **WARNING**: httpx logs at INFO level include session IDs in URLs - always set `logging.getLogger("httpx").setLevel(logging.WARNING)` in production to avoid exposing sensitive data.

## Completed Work

- ✅ ACTLab client migration to httpx
- ✅ Daisy client migration to httpx
- ✅ Handledning client migration to httpx
- ✅ **Clickmap client added** (new service - 2025-11-25)
- ✅ **Mail client refactored to IMAP/SMTP** (2025-11-26) - Replaced fragile OWA API with standard protocols
- ✅ **Play client added** (new service - 2026-03-31) - DSVPlay presentations, transcripts, courses
- ✅ **Daisy course/medverkande API** (2026-05-19) - `get_courses(semester)`, `get_course`, `get_course_participants`, extended `Staff` fields
- ✅ BaseAsyncClient removed
- ✅ Old unified client files removed (base_unified.py, shibboleth_unified.py, actlab_unified.py)
- ✅ requirements.txt updated (removed requests and aiohttp dependencies)
- ✅ All parsing functions extracted to dsv_wrapper/parsers/
- ✅ Strict error handling implemented (merged from strict-error-handling branch)
- ✅ **Critical bug fixes:**
  - Fixed async cookie transfer to preserve domain/path attributes
  - Fixed enum serialization in form data (InstitutionID conversion)
  - All authentication issues resolved
  - Empty staff search now works correctly (returns 300+ results)

## Code Quality and Linting

- **Linter: ruff** - Fast Python linter configured with strict rules
- **Pre-commit hooks**: Automatically run linting before every commit
- **Rules enforced**:
  - BLE (flake8-blind-except): No bare `except Exception:` - must catch specific exceptions
  - B (flake8-bugbear): Common Python bugs and design problems
  - A (flake8-builtins): Shadowing of Python builtins
  - C4 (flake8-comprehensions): Unnecessary comprehensions
  - I (isort): Import sorting
  - N (pep8-naming): PEP 8 naming conventions
  - UP (pyupgrade): Modern Python syntax
  - E/W/F (pycodestyle/pyflakes): Standard Python errors and warnings
- **Exception chaining**: Always use `raise ... from e` when converting exceptions
- **Running the linter**: `ruff check .` (run from project root)
- **Auto-fix issues**: `ruff check . --fix`

## Testing Notes

- **Test coverage: 99/99 passing - 100%!**
- All authentication tests pass including invalid credentials detection
- API parity tests verify sync/async clients have identical method signatures
- All ACTLab, Daisy, Handledning, Clickmap, Mail, and Play tests pass
- Cookie handling fixed: domain/path properly preserved in async clients
- Enum serialization fixed: InstitutionID properly converted to value in form data
- Clickmap tests include: placements retrieval, search, filtering, model validation, API parity
- Mail tests include: folder info, email listing, full email retrieval, send to self, API parity
- Mail tests now use IMAP/SMTP instead of OWA API
- Mail send tests use `AUTOMATEDTESTSEND - {timestamp}` pattern for easy cleanup
- Play tests include: courses, presentations listing, full presentation details, transcript, API parity
- Daisy course tests use captured HTML fixtures in `tests/fixtures/daisy/` and exercise `Semester`, course-search pagination header, course detail title parsing, medverkande K-marker, and rich-staff parsing
