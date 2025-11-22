"""Utility functions for dsv-wrapper package."""

from datetime import date, datetime, time
from typing import Optional

from bs4 import BeautifulSoup

from .exceptions import ParseError

# Common headers for requests
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,sv;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

# DSV system URLs - SSO target URLs for authentication
DSV_SSO_TARGETS = {
    "daisy_staff": "https://daisy.dsv.su.se/login_sso_employee.jspa",
    "daisy_student": "https://daisy.dsv.su.se/login_sso_student.jspa",
    "handledning": "https://handledning.dsv.su.se",
    "unified": "https://unified.dsv.su.se",
}

# DSV system base URLs - for making API requests
DSV_URLS = {
    "daisy_staff": "https://daisy.dsv.su.se",
    "daisy_student": "https://daisy.dsv.su.se",
    "handledning_desktop": "https://handledning.dsv.su.se",
    "handledning_mobile": "https://handledning.dsv.su.se/mobile",
    "unified_sso": "https://unified.dsv.su.se",
    "shibboleth_login": "https://login.su.se/idp/profile/SAML2/Redirect/SSO",
}


def parse_html(html: str, parser: str = "lxml") -> BeautifulSoup:
    """Parse HTML content with BeautifulSoup.

    Args:
        html: HTML content as string
        parser: Parser to use (default: lxml)

    Returns:
        BeautifulSoup object

    Raises:
        ParseError: If parsing fails
    """
    try:
        return BeautifulSoup(html, parser)
    except Exception as e:
        raise ParseError(f"Failed to parse HTML: {e}") from e


def parse_time(time_str: str) -> time:
    """Parse time string in HH:MM format.

    Args:
        time_str: Time string (e.g., "09:00", "14:30")

    Returns:
        time object

    Raises:
        ValueError: If time format is invalid
    """
    try:
        return datetime.strptime(time_str.strip(), "%H:%M").time()
    except ValueError as e:
        raise ValueError(f"Invalid time format: {time_str}. Expected HH:MM") from e


def parse_date(date_str: str, fmt: str = "%Y-%m-%d") -> date:
    """Parse date string.

    Args:
        date_str: Date string
        fmt: Date format (default: YYYY-MM-DD)

    Returns:
        date object

    Raises:
        ValueError: If date format is invalid
    """
    try:
        return datetime.strptime(date_str.strip(), fmt).date()
    except ValueError as e:
        raise ValueError(f"Invalid date format: {date_str}. Expected {fmt}") from e


def parse_swedish_date(date_str: str) -> date:
    """Parse Swedish date format (e.g., '2024-01-15' or '15 januari 2024').

    Args:
        date_str: Date string in Swedish format

    Returns:
        date object

    Raises:
        ValueError: If date format is invalid
    """
    swedish_months = {
        "januari": "01",
        "februari": "02",
        "mars": "03",
        "april": "04",
        "maj": "05",
        "juni": "06",
        "juli": "07",
        "augusti": "08",
        "september": "09",
        "oktober": "10",
        "november": "11",
        "december": "12",
    }

    date_str = date_str.strip().lower()

    # Try standard format first
    try:
        return parse_date(date_str)
    except ValueError:
        pass

    # Try Swedish format "15 januari 2024"
    for month_name, month_num in swedish_months.items():
        if month_name in date_str:
            parts = date_str.split()
            if len(parts) == 3:
                day = parts[0].zfill(2)
                year = parts[2]
                return parse_date(f"{year}-{month_num}-{day}")

    raise ValueError(f"Could not parse Swedish date: {date_str}")


def format_date_swedish(d: date) -> str:
    """Format date in Swedish format.

    Args:
        d: date object

    Returns:
        Formatted date string (e.g., "15 januari 2024")
    """
    swedish_months = [
        "januari",
        "februari",
        "mars",
        "april",
        "maj",
        "juni",
        "juli",
        "augusti",
        "september",
        "oktober",
        "november",
        "december",
    ]
    return f"{d.day} {swedish_months[d.month - 1]} {d.year}"


def extract_text(element, default: str = "") -> str:
    """Extract text from BeautifulSoup element.

    Args:
        element: BeautifulSoup element or None
        default: Default value if element is None

    Returns:
        Extracted text or default
    """
    if element is None:
        return default
    return element.get_text(strip=True)


def extract_attr(element, attr: str, default: Optional[str] = None) -> Optional[str]:
    """Extract attribute from BeautifulSoup element.

    Args:
        element: BeautifulSoup element or None
        attr: Attribute name
        default: Default value if element is None or attribute not found

    Returns:
        Attribute value or default
    """
    if element is None:
        return default
    return element.get(attr, default)


def build_url(base: str, *parts: str, **params) -> str:
    """Build URL with path parts and query parameters.

    Args:
        base: Base URL
        *parts: URL path parts
        **params: Query parameters

    Returns:
        Complete URL
    """
    url = base.rstrip("/")
    if parts:
        url += "/" + "/".join(str(p).strip("/") for p in parts)

    if params:
        query_parts = [f"{k}={v}" for k, v in params.items() if v is not None]
        if query_parts:
            url += "?" + "&".join(query_parts)

    return url


def validate_time_slot(start: time, end: time) -> bool:
    """Validate that time slot is valid (start < end).

    Args:
        start: Start time
        end: End time

    Returns:
        True if valid, False otherwise
    """
    return start < end


def get_weekday_swedish(d: date) -> str:
    """Get Swedish weekday name.

    Args:
        d: date object

    Returns:
        Swedish weekday name
    """
    swedish_weekdays = [
        "Måndag",
        "Tisdag",
        "Onsdag",
        "Torsdag",
        "Fredag",
        "Lördag",
        "Söndag",
    ]
    return swedish_weekdays[d.weekday()]
