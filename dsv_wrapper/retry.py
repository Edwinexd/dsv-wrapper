"""Retrying httpx transports for flaky DSV services.

DSV services occasionally drop connections ("Server disconnected without
sending a response") or answer with transient gateway errors. These
transports retry such failures with exponential backoff and jitter.

Retry rules:
- Errors raised before the request reached the server (connect errors and
  timeouts, pool timeouts) are retried for every method.
- Errors after the request may have been sent (dropped connections, read
  errors/timeouts) and transient statuses (429, 502, 503, 504) are only
  retried for idempotent methods, so e.g. a slide upload is never sent twice.
"""

import asyncio
import logging
import random
import time

import httpx

from .utils import DEFAULT_HEADERS

logger = logging.getLogger(__name__)

DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_FACTOR = 0.5
MAX_BACKOFF = 30.0

IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE", "TRACE"})
RETRY_STATUS_CODES = frozenset({429, 502, 503, 504})

# Raised before the request reached the server - safe to retry for any method
_UNSENT_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)
# The server may have received the request - only safe for idempotent methods
_SENT_ERRORS = (
    httpx.RemoteProtocolError,
    httpx.ReadError,
    httpx.ReadTimeout,
    httpx.WriteError,
    httpx.WriteTimeout,
)


class _RetryPolicy:
    """Shared retry decisions for the sync and async transports."""

    def __init__(self, max_retries: int, backoff_factor: float):
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    def should_retry_error(self, request: httpx.Request, error: httpx.TransportError) -> bool:
        if isinstance(error, _UNSENT_ERRORS):
            return True
        return isinstance(error, _SENT_ERRORS) and request.method in IDEMPOTENT_METHODS

    def should_retry_response(self, request: httpx.Request, response: httpx.Response) -> bool:
        return response.status_code in RETRY_STATUS_CODES and request.method in IDEMPOTENT_METHODS

    def delay(self, attempt: int, response: httpx.Response | None = None) -> float:
        """Seconds to wait before retry number ``attempt`` (0-indexed)."""
        if response is not None:
            retry_after = response.headers.get("Retry-After", "")
            if retry_after.isdigit():
                return min(float(retry_after), MAX_BACKOFF)
        backoff = self.backoff_factor * (2**attempt)
        return min(backoff + random.uniform(0, backoff), MAX_BACKOFF)

    def log_retry(self, request: httpx.Request, attempt: int, reason: str, delay: float) -> None:
        # Path only - query strings may carry session ids or tokens
        logger.warning(
            f"{request.method} {request.url.host}{request.url.path} failed ({reason}), "
            f"retry {attempt + 1}/{self.max_retries} in {delay:.1f}s"
        )


class RetryTransport(httpx.BaseTransport):
    """Sync httpx transport that retries transient failures."""

    def __init__(
        self,
        transport: httpx.BaseTransport | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
    ):
        self._transport = transport if transport is not None else httpx.HTTPTransport()
        self._policy = _RetryPolicy(max_retries, backoff_factor)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        for attempt in range(self._policy.max_retries + 1):
            is_last = attempt == self._policy.max_retries
            try:
                response = self._transport.handle_request(request)
            except httpx.TransportError as e:
                if is_last or not self._policy.should_retry_error(request, e):
                    raise
                delay = self._policy.delay(attempt)
                self._policy.log_retry(request, attempt, repr(e), delay)
                time.sleep(delay)
                continue

            if is_last or not self._policy.should_retry_response(request, response):
                return response
            delay = self._policy.delay(attempt, response)
            self._policy.log_retry(request, attempt, f"HTTP {response.status_code}", delay)
            response.close()
            time.sleep(delay)
        raise AssertionError("unreachable")

    def close(self) -> None:
        self._transport.close()


class AsyncRetryTransport(httpx.AsyncBaseTransport):
    """Async httpx transport that retries transient failures."""

    def __init__(
        self,
        transport: httpx.AsyncBaseTransport | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
    ):
        self._transport = transport if transport is not None else httpx.AsyncHTTPTransport()
        self._policy = _RetryPolicy(max_retries, backoff_factor)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        for attempt in range(self._policy.max_retries + 1):
            is_last = attempt == self._policy.max_retries
            try:
                response = await self._transport.handle_async_request(request)
            except httpx.TransportError as e:
                if is_last or not self._policy.should_retry_error(request, e):
                    raise
                delay = self._policy.delay(attempt)
                self._policy.log_retry(request, attempt, repr(e), delay)
                await asyncio.sleep(delay)
                continue

            if is_last or not self._policy.should_retry_response(request, response):
                return response
            delay = self._policy.delay(attempt, response)
            self._policy.log_retry(request, attempt, f"HTTP {response.status_code}", delay)
            await response.aclose()
            await asyncio.sleep(delay)
        raise AssertionError("unreachable")

    async def aclose(self) -> None:
        await self._transport.aclose()


def create_client(**kwargs) -> httpx.Client:
    """Create an ``httpx.Client`` with default headers and retrying transport."""
    kwargs.setdefault("headers", DEFAULT_HEADERS)
    return httpx.Client(transport=RetryTransport(), **kwargs)


def create_async_client(**kwargs) -> httpx.AsyncClient:
    """Create an ``httpx.AsyncClient`` with default headers and retrying transport."""
    kwargs.setdefault("headers", DEFAULT_HEADERS)
    return httpx.AsyncClient(transport=AsyncRetryTransport(), **kwargs)
