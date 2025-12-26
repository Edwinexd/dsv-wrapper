"""Shibboleth SSO authentication handlers."""

import logging
from typing import Literal

import httpx

from ..exceptions import AuthenticationError, NetworkError
from ..utils import DEFAULT_HEADERS, DSV_SSO_TARGETS, extract_attr, parse_html
from .cache_backend import CacheBackend, NullCache

logger = logging.getLogger(__name__)

ServiceType = Literal["daisy_staff", "daisy_student", "handledning", "actlab", "clickmap"]


class ShibbolethAuth:
    """Synchronous Shibboleth SSO authentication handler."""

    def __init__(
        self,
        username: str,
        password: str,
        cache_backend: CacheBackend | None = None,
        cache_ttl: int = 86400,
    ):
        """Initialize Shibboleth authenticator.

        Args:
            username: SU username
            password: SU password
            cache_backend: Cache backend instance (default: NullCache - no caching)
            cache_ttl: Cache time-to-live in seconds (default: 86400 = 24 hours)
        """
        self.username = username
        self.password = password
        self.cache_backend = cache_backend if cache_backend is not None else NullCache()
        self.cache_ttl = cache_ttl
        self._client = httpx.Client(headers=DEFAULT_HEADERS, follow_redirects=False)

        logger.debug(f"Initialized ShibbolethAuth for user: {username}")
        logger.debug(f"Cache backend: {type(self.cache_backend).__name__}")

    def _login(
        self, service: ServiceType = "daisy_staff", validate_cache: bool = True
    ) -> httpx.Cookies:
        """Perform SSO login and get authenticated cookies (internal use only).

        Args:
            service: Service to authenticate with (default: daisy_staff)
            validate_cache: Whether to validate cached cookies before using (default: True)

        Returns:
            Authenticated cookies

        Raises:
            AuthenticationError: If authentication fails
            NetworkError: If network request fails
        """
        logger.info(f"Attempting to login to {service} for user {self.username}")
        cache_key = f"{self.username}_{service}"

        # Try to get cached cookies first
        cached_cookies = self.cache_backend.get(cache_key)
        if cached_cookies is not None:
            logger.debug("Found cached cookies")
            self._client.cookies.update(cached_cookies)

            # Validate cached cookies if requested
            if validate_cache:
                logger.debug("Validating cached cookies...")
                if self._validate_cookies(service):
                    logger.info("Using cached authentication cookies (validated)")
                    return cached_cookies
                else:
                    logger.warning("Cached cookies are invalid, re-authenticating")
                    self.cache_backend.delete(cache_key)
                    self._client.cookies.clear()
            else:
                logger.info("Using cached authentication cookies (unvalidated)")
                return cached_cookies

        # Perform fresh login
        try:
            logger.debug(f"Performing SSO login to {service}")
            cookies = self._perform_login(service)

            # Cache the cookies
            self.cache_backend.set(cache_key, self._client.cookies, ttl=self.cache_ttl)
            logger.debug(f"Cached authentication cookies with key: {cache_key}")

            logger.info(f"Successfully authenticated to {service}")
            return cookies

        except httpx.HTTPError as e:
            logger.error(f"Network error during authentication: {e}")
            raise NetworkError(f"Network error during authentication: {e}") from e

    def _validate_cookies(self, service: ServiceType) -> bool:
        """Validate that cookies are still valid by making a test request.

        Args:
            service: Service type

        Returns:
            True if cookies are valid, False otherwise
        """
        try:
            # Make a lightweight test request based on service
            test_url = self._get_validation_url(service)
            response = self._client.get(test_url, timeout=60)

            # If we get redirected to login, cookies are invalid
            if response.status_code in (301, 302, 303):
                location = response.headers.get("Location", "")
                if "login" in location.lower() or "sso" in location.lower():
                    logger.debug("Validation failed: redirected to login")
                    return False

            # Check if response looks like a login page (regardless of status code!)
            html_lower = response.text.lower()
            if "login" in html_lower[:1000]:
                # Look for login form indicators
                if "<form" in html_lower[:2000] and "password" in html_lower[:2000]:
                    logger.debug("Validation failed: got login page")
                    return False

            # Check for authenticated indicators (logout, username, etc.)
            if not self._is_authenticated(response.text):
                logger.debug("Validation failed: no authentication indicators found")
                return False

            logger.debug("Validation passed")
            return True

        except (httpx.HTTPError, httpx.TimeoutException) as e:
            logger.warning(f"Cookie validation failed with error: {e}")
            return False

    def _get_validation_url(self, service: ServiceType) -> str:
        """Get a lightweight URL for validating cookies.

        Args:
            service: Service type

        Returns:
            Validation URL
        """
        # For daisy services, use the main index page
        if service in ("daisy_staff", "daisy_student"):
            return "https://daisy.dsv.su.se/index.jspa"
        elif service == "handledning":
            return "https://handledning.dsv.su.se"
        elif service == "actlab":
            return "https://www2.dsv.su.se/act-lab/admin/"
        elif service == "clickmap":
            return "https://clickmap.dsv.su.se/api/"
        else:
            raise ValueError(f"Unknown service type: {service}")

    def _perform_login(self, service: ServiceType) -> httpx.Cookies:
        """Perform the actual SSO login flow.

        Args:
            service: Service to authenticate with

        Returns:
            Authenticated cookies

        Raises:
            AuthenticationError: If authentication fails
        """
        # Get the service URL
        service_url = self._get_service_url(service)
        logger.debug(f"Service URL: {service_url}")

        # Step 1: Request the service URL to get redirected to Shibboleth
        logger.debug("Step 1: Requesting service URL to initiate SSO")
        response = self._client.get(service_url, timeout=60)
        # Manually follow redirects
        while response.status_code in (301, 302, 303):
            location = response.headers["Location"]
            # Make relative URLs absolute
            if location.startswith("/"):
                # Use the current response URL's base
                base_url = f"{response.url.scheme}://{response.url.host}"
                location = base_url + location
            response = self._client.get(location, timeout=60)

        # Step 2: Handle intermediate localStorage form (if present)
        logger.debug("Step 2: Checking for intermediate localStorage form")
        soup = parse_html(response.text)
        intermediate_form = soup.find("form")

        if intermediate_form and not intermediate_form.get("id") == "login":
            # This is the localStorage form, submit it
            form_action = extract_attr(intermediate_form, "action")
            logger.debug(f"Found intermediate form, posting to: {form_action}")

            form_data = {}
            for input_field in intermediate_form.find_all("input"):
                name = extract_attr(input_field, "name")
                value = extract_attr(input_field, "value")
                if name:
                    form_data[name] = value or ""

            # Add the _eventId_proceed field
            form_data["_eventId_proceed"] = ""

            # Submit the form (need full URL if action is relative)
            if form_action.startswith("/"):
                form_action = "https://idp.it.su.se" + form_action
            response = self._client.post(form_action, data=form_data, timeout=60)

            # Follow redirect if needed
            while response.status_code in (301, 302, 303):
                location = response.headers["Location"]
                if location.startswith("/"):
                    base_url = f"{response.url.scheme}://{response.url.host}"
                    location = base_url + location
                response = self._client.get(location, timeout=60)

            soup = parse_html(response.text)

        # Step 3: Parse the login form
        logger.debug("Step 3: Parsing login form")
        login_form = soup.find("form", {"id": "login"})

        if login_form is None:
            login_form = soup.find("form")
            if login_form is None or "j_username" not in str(login_form):
                # No login form - check if we're on a login/error page
                logger.debug("No login form found, checking if on login page")
                html_lower = response.text.lower()
                # Check if this looks like a login or error page
                if "log in" in html_lower[:1000] or "login" in html_lower[:500]:
                    if "<form" in html_lower[:2000] and (
                        "password" in html_lower[:2000] or "submit" in html_lower[:2000]
                    ):
                        logger.error("Still on login page after authentication attempt")
                        raise AuthenticationError("Authentication failed: Invalid credentials")

                # Not on login page, already past login - skip to SAML/validation
                logger.debug("Not on login page, skipping to step 6 (SAML)")
                # Skip steps 3-5, go directly to step 6
                # (response already has the page we're on)
        else:
            # We have a login form, proceed with credential submission
            form_action = extract_attr(login_form, "action")
            if form_action is None:
                logger.error("Could not find login form action")
                raise AuthenticationError("Could not find login form action")

            logger.debug(f"Login form action: {form_action}")

            # Step 4: Submit credentials
            logger.debug("Step 4: Submitting credentials")

            # Extract all form fields (including csrf_token, etc.)
            login_data = {}
            for input_field in login_form.find_all("input"):
                name = extract_attr(input_field, "name")
                value = extract_attr(input_field, "value")
                if name:
                    login_data[name] = value or ""

            # Update with username and password
            login_data.update(
                {
                    "j_username": self.username,
                    "j_password": self.password,
                    "_eventId_proceed": "",
                }
            )

            # Remove SPNEGO-related fields (per old login.py)
            login_data.pop("_eventId_authn/SPNEGO", None)
            login_data.pop("_eventId_trySPNEGO", None)

            # Build full URL if action is relative
            if form_action.startswith("/"):
                form_action = "https://idp.it.su.se" + form_action

            response = self._client.post(form_action, data=login_data, timeout=60)
            logger.debug(f"Login response status: {response.status_code}")

            # Check if login failed - either 200 with error or stayed on login page
            if response.status_code == 200:
                soup = parse_html(response.text)
                error = soup.find("p", class_="form-error")
                if error:
                    error_msg = error.get_text(strip=True)
                    logger.error(f"Login failed: {error_msg}")
                    raise AuthenticationError(f"Login failed: {error_msg}")

                # Check if we're still on the login page (indicates auth failure)
                login_form_check = soup.find("form", {"id": "login"})
                if login_form_check:
                    logger.error("Login failed: still on login page after credential submission")
                    raise AuthenticationError("Authentication failed: Invalid credentials")

            # Step 5: Follow redirects if needed
            if response.status_code in (301, 302, 303):
                logger.debug(f"Step 5: Following redirect to {response.headers.get('Location')}")
                location = response.headers["Location"]
                if location.startswith("/"):
                    base_url = f"{response.url.scheme}://{response.url.host}"
                    location = base_url + location
                response = self._client.get(location, timeout=60)
                while response.status_code in (301, 302, 303):
                    location = response.headers["Location"]
                    if location.startswith("/"):
                        base_url = f"{response.url.scheme}://{response.url.host}"
                        location = base_url + location
                    response = self._client.get(location, timeout=60)

                # After following redirects, check if we ended up back on login page
                soup = parse_html(response.text)
                login_form_check = soup.find("form", {"id": "login"})
                if login_form_check:
                    logger.error("Login failed: redirected back to login page after authentication")
                    raise AuthenticationError("Authentication failed: Invalid credentials")

        # Step 6: Handle SAML response auto-submit form
        logger.debug("Step 6: Handling SAML response")
        soup = parse_html(response.text)
        saml_form = soup.find("form", method="post")

        if saml_form:
            saml_action = extract_attr(saml_form, "action")
            logger.debug(f"Submitting SAML form to {saml_action}")
            saml_data = {}

            for input_field in saml_form.find_all("input"):
                name = extract_attr(input_field, "name")
                value = extract_attr(input_field, "value")
                if name:
                    saml_data[name] = value or ""

            response = self._client.post(saml_action, data=saml_data, timeout=60)
            while response.status_code in (301, 302, 303):
                location = response.headers["Location"]
                if location.startswith("/"):
                    base_url = f"{response.url.scheme}://{response.url.host}"
                    location = base_url + location
                response = self._client.get(location, timeout=60)

        # Verify we're authenticated by checking cookies AND validating them
        logger.debug("Verifying authentication by checking cookies")
        # Check for JSESSIONID or _shibsession cookies
        has_cookies = any(
            name == "JSESSIONID" or name.startswith("_shibsession")
            for name in self._client.cookies.keys()
        )

        if not has_cookies:
            logger.error("Authentication verification failed - no session cookies found")
            raise AuthenticationError("Authentication failed: No session cookies found")

        # Note: We don't validate cookies here because validation can be unreliable
        # (HTTP 200 doesn't mean success in Daisy). Let real requests fail
        # naturally if auth didn't work.
        logger.debug("Authentication flow completed successfully")
        return self._client.cookies

    def _get_service_url(self, service: ServiceType) -> str:
        """Get the SSO target URL for a given service type.

        Args:
            service: Service type

        Returns:
            SSO target URL
        """
        if service in DSV_SSO_TARGETS:
            return DSV_SSO_TARGETS[service]
        else:
            raise ValueError(f"Unknown service type: {service}")

    def _is_authenticated(self, html: str) -> bool:
        """Check if we're authenticated by looking for indicators in HTML.

        Args:
            html: HTML response

        Returns:
            True if authenticated
        """
        # Look for common authenticated indicators
        indicators = [
            "logout",
            "logga ut",
            "profile",
            "profil",
        ]
        # Add username if it's not None
        if self.username:
            indicators.append(self.username.lower())

        html_lower = html.lower()
        return any(indicator in html_lower for indicator in indicators)

    def logout(self) -> None:
        """Clear session and cached cookies."""
        self._client.cookies.clear()
        self.cache_backend.clear()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self._client.close()


class AsyncShibbolethAuth:
    """Asynchronous Shibboleth SSO authentication handler.

    This wraps the synchronous ShibbolethAuth to avoid reimplementing the complex SAML flow.
    """

    def __init__(
        self,
        username: str,
        password: str,
        cache_backend: CacheBackend | None = None,
        cache_ttl: int = 86400,
    ):
        """Initialize async Shibboleth authenticator.

        Args:
            username: SU username
            password: SU password
            cache_backend: Cache backend instance (default: NullCache - no caching)
            cache_ttl: Cache time-to-live in seconds (default: 86400 = 24 hours)
        """
        self.username = username
        self.password = password
        self.cache_backend = cache_backend if cache_backend is not None else NullCache()
        self.cache_ttl = cache_ttl

        # Use sync auth internally
        self._sync_auth = ShibbolethAuth(username, password, cache_backend, cache_ttl)

        logger.debug(f"Initialized AsyncShibbolethAuth for user: {username}")
        logger.debug(f"Cache backend: {type(self.cache_backend).__name__}")

    async def __aenter__(self):
        """Async context manager entry."""
        self._sync_auth.__enter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        self._sync_auth.__exit__(exc_type, exc_val, exc_tb)

    async def login(self, service: ServiceType = "daisy_staff") -> httpx.Cookies:
        """Perform async SSO login and get authenticated cookies.

        Args:
            service: Service to authenticate with (default: daisy_staff)

        Returns:
            Authenticated cookies (httpx.Cookies)

        Raises:
            AuthenticationError: If authentication fails
            NetworkError: If network request fails
        """
        import asyncio

        # Run sync login in thread pool to avoid blocking
        cookies = await asyncio.to_thread(self._sync_auth._login, service)

        return cookies
