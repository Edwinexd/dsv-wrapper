"""Shibboleth SSO authentication handlers."""

import logging
import re
from typing import Literal, Optional

import aiohttp
import requests
from requests.cookies import RequestsCookieJar

from ..exceptions import AuthenticationError, NetworkError
from ..utils import DEFAULT_HEADERS, DSV_SSO_TARGETS, DSV_URLS, extract_attr, parse_html
from .cache_backend import CacheBackend, NullCache

logger = logging.getLogger(__name__)

ServiceType = Literal["daisy_staff", "daisy_student", "handledning", "actlab"]


class ShibbolethAuth:
    """Synchronous Shibboleth SSO authentication handler."""

    def __init__(
        self,
        username: str,
        password: str,
        cache_backend: Optional[CacheBackend] = None,
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
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

        logger.debug(f"Initialized ShibbolethAuth for user: {username}")
        logger.debug(f"Cache backend: {type(self.cache_backend).__name__}")

    def _login(self, service: ServiceType = "daisy_staff", validate_cache: bool = True) -> RequestsCookieJar:
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
            self.session.cookies.update(cached_cookies)

            # Validate cached cookies if requested
            if validate_cache:
                logger.debug("Validating cached cookies...")
                if self._validate_cookies(service):
                    logger.info("Using cached authentication cookies (validated)")
                    return cached_cookies
                else:
                    logger.warning("Cached cookies are invalid, re-authenticating")
                    self.cache_backend.delete(cache_key)
                    self.session.cookies.clear()
            else:
                logger.info("Using cached authentication cookies (unvalidated)")
                return cached_cookies

        # Perform fresh login
        try:
            logger.debug(f"Performing SSO login to {service}")
            cookies = self._perform_login(service)

            # Cache the cookies
            self.cache_backend.set(cache_key, cookies, ttl=self.cache_ttl)
            logger.debug(f"Cached authentication cookies with key: {cache_key}")

            logger.info(f"Successfully authenticated to {service}")
            return cookies

        except requests.RequestException as e:
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
            response = self.session.get(test_url, timeout=10, allow_redirects=False)

            # If we get redirected to login, cookies are invalid
            if response.status_code in (301, 302, 303):
                location = response.headers.get("Location", "")
                if "login" in location.lower() or "sso" in location.lower():
                    logger.debug("Validation failed: redirected to login")
                    return False

            # Check if response looks like a login page
            if "login" in response.text.lower()[:1000] and response.status_code == 200:
                # Could be login page
                if "<form" in response.text.lower()[:2000] and "password" in response.text.lower()[:2000]:
                    logger.debug("Validation failed: got login page")
                    return False

            logger.debug("Validation passed")
            return True

        except Exception as e:
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
        else:
            raise ValueError(f"Unknown service type: {service}")

    def _perform_login(self, service: ServiceType) -> RequestsCookieJar:
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
        response = self.session.get(service_url, allow_redirects=True)

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
            response = self.session.post(form_action, data=form_data)
            soup = parse_html(response.text)

        # Step 3: Parse the login form
        logger.debug("Step 3: Parsing login form")
        login_form = soup.find("form", {"id": "login"})

        if login_form is None:
            login_form = soup.find("form")
            if login_form is None or "j_username" not in str(login_form):
                # Already authenticated or no login required
                logger.debug("No login form found, assuming already authenticated")
                return self.session.cookies

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
        login_data.update({
            "j_username": self.username,
            "j_password": self.password,
            "_eventId_proceed": "",
        })

        # Remove SPNEGO-related fields (per old login.py)
        login_data.pop("_eventId_authn/SPNEGO", None)
        login_data.pop("_eventId_trySPNEGO", None)

        # Build full URL if action is relative
        if form_action.startswith("/"):
            form_action = "https://idp.it.su.se" + form_action

        response = self.session.post(form_action, data=login_data, allow_redirects=False)
        logger.debug(f"Login response status: {response.status_code}")

        # Check if login failed
        if response.status_code == 200:
            soup = parse_html(response.text)
            error = soup.find("p", class_="form-error")
            if error:
                error_msg = error.get_text(strip=True)
                logger.error(f"Login failed: {error_msg}")
                raise AuthenticationError(f"Login failed: {error_msg}")

        # Step 5: Follow redirects if needed
        if response.status_code in (301, 302, 303):
            logger.debug(f"Step 5: Following redirect to {response.headers.get('Location')}")
            response = self.session.get(response.headers["Location"], allow_redirects=True)

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

            response = self.session.post(saml_action, data=saml_data, allow_redirects=True)

        # Verify we're authenticated by checking cookies
        logger.debug("Verifying authentication by checking cookies")
        # Check for JSESSIONID or _shibsession cookies
        has_cookies = any(
            cookie.name == "JSESSIONID" or cookie.name.startswith("_shibsession")
            for cookie in self.session.cookies
        )

        if not has_cookies:
            logger.error("Authentication verification failed - no session cookies found")
            raise AuthenticationError("Authentication failed: No session cookies found")

        logger.debug("Authentication flow completed successfully")
        return self.session.cookies

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
            self.username.lower(),
            "profile",
            "profil",
        ]

        html_lower = html.lower()
        return any(indicator in html_lower for indicator in indicators)

    def logout(self) -> None:
        """Clear session and cached cookies."""
        self.session.cookies.clear()
        self.cache_backend.clear()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.session.close()


class AsyncShibbolethAuth:
    """Asynchronous Shibboleth SSO authentication handler.

    This wraps the synchronous ShibbolethAuth to avoid reimplementing the complex SAML flow.
    """

    def __init__(
        self,
        username: str,
        password: str,
        cache_backend: Optional[CacheBackend] = None,
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
        self.session: Optional[aiohttp.ClientSession] = None

        logger.debug(f"Initialized AsyncShibbolethAuth for user: {username}")
        logger.debug(f"Cache backend: {type(self.cache_backend).__name__}")

    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession(headers=DEFAULT_HEADERS)
        self._sync_auth.__enter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
        self._sync_auth.__exit__(exc_type, exc_val, exc_tb)

    async def login(self, service: ServiceType = "daisy_staff") -> dict:
        """Perform async SSO login and get authenticated cookies.

        Args:
            service: Service to authenticate with (default: daisy_staff)

        Returns:
            Authenticated cookies as dict

        Raises:
            AuthenticationError: If authentication fails
            NetworkError: If network request fails
        """
        import asyncio

        if self.session is None:
            raise RuntimeError("Session not initialized. Use 'async with' context manager.")

        # Run sync login in thread pool to avoid blocking
        cookies_jar = await asyncio.to_thread(self._sync_auth._login, service)

        # Convert RequestsCookieJar to dict
        return {cookie.name: cookie.value for cookie in cookies_jar}

    # Note: We don't need async implementations of _perform_login, _get_service_url, or _is_authenticated
    # since we're wrapping the sync version using asyncio.to_thread().
