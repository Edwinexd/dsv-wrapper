## Project Status

- All pytest tests are passing (29/29)
- Sync and async clients have full API parity with automated tests to prevent de-sync
- Async authentication now works by wrapping sync auth using asyncio.to_thread()
- Disclaimer added to README regarding AI-generated code experiment
- Authentication tests updated to use correct internal API (`_login` method)
- Model tests updated to match actual Pydantic model structure
- Integration tests that hit non-existent endpoints have been removed or simplified

## Important Notes

- **HTTP 200 doesn't mean success in Daisy**: The service returns 200 status codes even for login pages and error pages. Always check the HTML content to verify successful responses.
- **Async auth implementation**: AsyncShibbolethAuth now wraps the sync ShibbolethAuth using asyncio.to_thread() to avoid reimplementing the complex SAML flow. This ensures both versions work identically.

## Recent Changes

- **Fixed async authentication** by wrapping sync auth with asyncio.to_thread() instead of reimplementing SAML flow
- **Added rate limiting to async get_all_staff()** - processes requests in batches (default 10) with delays (default 0.5s) to avoid overwhelming the server
- Added missing staff methods to AsyncDaisyClient (search_staff, get_staff_details, get_all_staff)
- Added missing methods to AsyncACTLabClient (upload_slide, cleanup_old_slides)
- Created API parity tests for all sync/async client pairs (Daisy, Handledning, ACTLab)
- Added pytest-asyncio to requirements.txt and fixed async fixtures
- Fixed parsing methods to work when called from async clients (base_url handling)
- Fixed HandledningClient auth method call
- Updated test files to match actual API structure
- Removed outdated integration tests
- Added AI experiment disclaimer to README