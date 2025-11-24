"""Cookie cache management with TTL support."""

import json
import pickle
from datetime import datetime, timedelta
from pathlib import Path

from requests.cookies import RequestsCookieJar


class CookieCache:
    """Cache for storing authentication cookies with TTL."""

    def __init__(
        self,
        cache_dir: Path | None = None,
        ttl_hours: int = 24,
        use_pickle: bool = False,
    ):
        """Initialize cookie cache.

        Args:
            cache_dir: Directory to store cache files (default: ~/.cache/dsv-wrapper)
            ttl_hours: Time to live for cached cookies in hours (default: 24)
            use_pickle: Use pickle instead of JSON for serialization (default: False)
        """
        if cache_dir is None:
            cache_dir = Path.home() / ".cache" / "dsv-wrapper"

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = timedelta(hours=ttl_hours)
        self.use_pickle = use_pickle

    def _get_cache_path(self, key: str) -> Path:
        """Get cache file path for a key.

        Args:
            key: Cache key (e.g., username or service name)

        Returns:
            Path to cache file
        """
        ext = ".pkl" if self.use_pickle else ".json"
        return self.cache_dir / f"{key}{ext}"

    def get(self, key: str) -> RequestsCookieJar | None:
        """Get cookies from cache.

        Args:
            key: Cache key

        Returns:
            RequestsCookieJar if found and valid, None otherwise
        """
        cache_path = self._get_cache_path(key)

        if not cache_path.exists():
            return None

        try:
            if self.use_pickle:
                with cache_path.open("rb") as f:
                    data = pickle.load(f)
            else:
                with cache_path.open("r") as f:
                    data = json.load(f)

            # Check if cache is expired
            cached_time = datetime.fromisoformat(data["timestamp"])
            if datetime.now() - cached_time > self.ttl:
                cache_path.unlink()
                return None

            # Restore cookies
            cookies = RequestsCookieJar()
            for cookie_data in data["cookies"]:
                cookies.set(**cookie_data)

            return cookies

        except (json.JSONDecodeError, pickle.PickleError, KeyError, ValueError):
            # Cache corrupted, remove it
            cache_path.unlink(missing_ok=True)
            return None

    def set(self, key: str, cookies: RequestsCookieJar) -> None:
        """Store cookies in cache.

        Args:
            key: Cache key
            cookies: RequestsCookieJar to cache
        """
        cache_path = self._get_cache_path(key)

        # Serialize cookies
        cookies_data = []
        for cookie in cookies:
            cookies_data.append(
                {
                    "name": cookie.name,
                    "value": cookie.value,
                    "domain": cookie.domain,
                    "path": cookie.path,
                }
            )

        data = {"timestamp": datetime.now().isoformat(), "cookies": cookies_data}

        if self.use_pickle:
            with cache_path.open("wb") as f:
                pickle.dump(data, f)
        else:
            with cache_path.open("w") as f:
                json.dump(data, f, indent=2)

    def delete(self, key: str) -> None:
        """Delete cached cookies.

        Args:
            key: Cache key
        """
        cache_path = self._get_cache_path(key)
        cache_path.unlink(missing_ok=True)

    def clear(self) -> None:
        """Clear all cached cookies."""
        for cache_file in self.cache_dir.glob("*"):
            if cache_file.is_file():
                cache_file.unlink()

    def is_valid(self, key: str) -> bool:
        """Check if cached cookies exist and are valid.

        Args:
            key: Cache key

        Returns:
            True if cache exists and is not expired
        """
        return self.get(key) is not None
