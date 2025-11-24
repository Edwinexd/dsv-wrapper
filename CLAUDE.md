## Project Status

- **29 of 29 pytest tests passing** - 100% pass rate!
- **Major architecture refactor COMPLETE**: Fully migrated from requests/aiohttp to httpx
- All clients (ACTLab, Daisy, Handledning) now use unified httpx architecture
- Sync and async clients have full API parity with automated tests to prevent de-sync
- **All authentication and cookie issues resolved**
- ~50% code duplication eliminated through shared parsing functions
- BaseAsyncClient removed - no longer needed
- Disclaimer added to README regarding AI-generated code experiment

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

### HandledningClient Refactor (Complete)
- Both `HandledningClient` and `AsyncHandledningClient` now use httpx
- Share parsing functions from `dsv_wrapper/parsers/handledning.py`
- Eliminated all `__new__()` hacks and removed BaseAsyncClient dependency
- All Handledning tests passing

## Important Notes

- **HTTP 200 doesn't mean success in Daisy**: The service returns 200 status codes even for login pages and error pages. Always check the HTML content to verify successful responses.
- **Async auth implementation**: AsyncShibbolethAuth wraps the sync ShibbolethAuth using asyncio.to_thread() to avoid reimplementing the complex SAML flow. This ensures both versions work identically.
- **httpx redirects**: httpx requires absolute URLs for redirects. The auth code now converts relative redirect URLs to absolute before following them.
- **Cookie caching**: Cookies are now stored as dicts in the cache. FileCache backend updated to handle both dict and RequestsCookieJar formats.

## Completed Work

- ✅ ACTLab client migration to httpx
- ✅ Daisy client migration to httpx
- ✅ Handledning client migration to httpx
- ✅ BaseAsyncClient removed
- ✅ Old unified client files removed (base_unified.py, shibboleth_unified.py, actlab_unified.py)
- ✅ requirements.txt updated (removed requests and aiohttp dependencies)
- ✅ All parsing functions extracted to dsv_wrapper/parsers/
- ✅ **Critical bug fixes:**
  - Fixed async cookie transfer to preserve domain/path attributes
  - Fixed enum serialization in form data (InstitutionID conversion)
  - All authentication issues resolved
  - Empty staff search now works correctly (returns 300+ results)

## Testing Notes

- **Test coverage: 29/29 passing - 100%!**
- All authentication tests pass including invalid credentials detection
- API parity tests verify sync/async clients have identical method signatures
- All ACTLab, Daisy, and Handledning tests pass with new httpx implementation
- Cookie handling fixed: domain/path properly preserved in async clients
- Enum serialization fixed: InstitutionID properly converted to value in form data
