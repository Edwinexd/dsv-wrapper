"""Cache backend interface and implementations for cookie storage."""

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path

from requests.cookies import RequestsCookieJar

logger = logging.getLogger(__name__)


class CacheBackend(ABC):
    """Abstract base class for cache backends.

    Implement this interface to create custom cache backends (e.g., Redis, DB).
    """

    @abstractmethod
    def get(self, key: str) -> RequestsCookieJar | None:
        """Get cached cookies by key.

        Args:
            key: Cache key

        Returns:
            Cached cookies if found and valid, None otherwise
        """
        pass

    @abstractmethod
    def set(self, key: str, cookies: RequestsCookieJar, ttl: int | None = None) -> None:
        """Set cached cookies with optional TTL.

        Args:
            key: Cache key
            cookies: Cookies to cache
            ttl: Time-to-live in seconds (None = use backend default)
        """
        pass

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete cached cookies by key.

        Args:
            key: Cache key
        """
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear all cached cookies."""
        pass


class NullCache(CacheBackend):
    """No-op cache backend that never caches anything.

    Use this when you don't want any caching.
    """

    def get(self, key: str) -> RequestsCookieJar | None:
        return None

    def set(self, key: str, cookies: RequestsCookieJar, ttl: int | None = None) -> None:
        pass

    def delete(self, key: str) -> None:
        pass

    def clear(self) -> None:
        pass


class MemoryCache(CacheBackend):
    """In-memory cache backend (no persistence).

    Cached cookies are lost when the process exits.
    """

    def __init__(self, default_ttl: int = 86400):
        """Initialize memory cache.

        Args:
            default_ttl: Default time-to-live in seconds (default: 24 hours)
        """
        self.default_ttl = default_ttl
        self._cache: dict[str, tuple[RequestsCookieJar, datetime]] = {}

    def get(self, key: str) -> RequestsCookieJar | None:
        if key not in self._cache:
            return None

        cookies, expires_at = self._cache[key]

        if datetime.now() > expires_at:
            logger.debug(f"Cache expired for key: {key}")
            del self._cache[key]
            return None

        logger.debug(f"Cache hit for key: {key}")
        return cookies

    def set(self, key: str, cookies: RequestsCookieJar, ttl: int | None = None) -> None:
        ttl = ttl if ttl is not None else self.default_ttl
        expires_at = datetime.now() + timedelta(seconds=ttl)
        self._cache[key] = (cookies, expires_at)
        logger.debug(f"Cached cookies for key: {key} (TTL: {ttl}s)")

    def delete(self, key: str) -> None:
        if key in self._cache:
            del self._cache[key]
            logger.debug(f"Deleted cache for key: {key}")

    def clear(self) -> None:
        self._cache.clear()
        logger.debug("Cleared all cached cookies")


class FileCache(CacheBackend):
    """File-based cache backend.

    Stores cookies as JSON files in a specified directory.
    """

    def __init__(self, cache_dir: str | Path = ".cache/dsv-wrapper", default_ttl: int = 86400):
        """Initialize file cache.

        Args:
            cache_dir: Directory to store cache files (relative or absolute)
            default_ttl: Default time-to-live in seconds (default: 24 hours)
        """
        self.cache_dir = Path(cache_dir).expanduser().resolve()
        self.default_ttl = default_ttl
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"File cache initialized at: {self.cache_dir}")

    def _get_cache_path(self, key: str) -> Path:
        """Get cache file path for a key."""
        # Sanitize key for filesystem
        safe_key = key.replace("/", "_").replace("\\", "_")
        return self.cache_dir / f"{safe_key}.json"

    def get(self, key: str) -> RequestsCookieJar | None:
        cache_path = self._get_cache_path(key)

        if not cache_path.exists():
            return None

        try:
            with open(cache_path) as f:
                data = json.load(f)

            # Check if expired
            expires_at = datetime.fromisoformat(data["expires_at"])
            if datetime.now() > expires_at:
                logger.debug(f"Cache expired for key: {key}")
                cache_path.unlink()
                return None

            # Reconstruct cookies
            jar = RequestsCookieJar()
            for cookie_data in data["cookies"]:
                jar.set(
                    cookie_data["name"],
                    cookie_data["value"],
                    domain=cookie_data.get("domain"),
                    path=cookie_data.get("path", "/"),
                )

            logger.debug(f"Cache hit for key: {key}")
            return jar

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Failed to load cache for key {key}: {e}")
            cache_path.unlink(missing_ok=True)
            return None

    def set(self, key: str, cookies, ttl: int | None = None) -> None:
        ttl = ttl if ttl is not None else self.default_ttl
        expires_at = datetime.now() + timedelta(seconds=ttl)

        # Serialize cookies - handle both dict and RequestsCookieJar
        if isinstance(cookies, dict):
            cookies_data = [
                {
                    "name": name,
                    "value": value,
                    "domain": "",
                    "path": "/",
                }
                for name, value in cookies.items()
            ]
        else:
            # RequestsCookieJar or similar iterable of cookie objects
            cookies_data = [
                {
                    "name": cookie.name,
                    "value": cookie.value,
                    "domain": cookie.domain,
                    "path": cookie.path,
                }
                for cookie in cookies
            ]

        data = {
            "expires_at": expires_at.isoformat(),
            "cookies": cookies_data,
        }

        cache_path = self._get_cache_path(key)
        with open(cache_path, "w") as f:
            json.dump(data, f, indent=2)

        logger.debug(f"Cached cookies for key: {key} at {cache_path} (TTL: {ttl}s)")

    def delete(self, key: str) -> None:
        cache_path = self._get_cache_path(key)
        cache_path.unlink(missing_ok=True)
        logger.debug(f"Deleted cache for key: {key}")

    def clear(self) -> None:
        for cache_file in self.cache_dir.glob("*.json"):
            cache_file.unlink()
        logger.debug(f"Cleared all cached cookies from {self.cache_dir}")
