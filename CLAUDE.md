## Project Status

- **36 of 36 pytest tests passing** - 100% pass rate!
- **Major architecture refactor COMPLETE**: Fully migrated from requests/aiohttp to httpx
- **Strict error handling implemented**: Silent failures replaced with explicit ParseError exceptions
- All clients (ACTLab, Daisy, Handledning, Clickmap) now use unified httpx architecture
- Sync and async clients have full API parity with automated tests to prevent de-sync
- **All authentication and cookie issues resolved**
- ~50% code duplication eliminated through shared parsing functions
- BaseAsyncClient removed - no longer needed
- Disclaimer added to README regarding AI-generated code experiment
- **NEW: Clickmap client added** - Extract DSV office/workspace placements

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

- **Test coverage: 36/36 passing - 100%!**
- All authentication tests pass including invalid credentials detection
- API parity tests verify sync/async clients have identical method signatures
- All ACTLab, Daisy, Handledning, and Clickmap tests pass with httpx implementation
- Cookie handling fixed: domain/path properly preserved in async clients
- Enum serialization fixed: InstitutionID properly converted to value in form data
- Clickmap tests include: placements retrieval, search, filtering, model validation, API parity
