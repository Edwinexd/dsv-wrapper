"""Tests for the retrying httpx transports and the shared client base classes."""

import httpx
import pytest

from dsv_wrapper import ClickmapClient
from dsv_wrapper.base import BaseAsyncClient, BaseClient
from dsv_wrapper.exceptions import AuthenticationError
from dsv_wrapper.retry import AsyncRetryTransport, RetryTransport

URL = "https://daisy.dsv.su.se/index.jspa"


def _flaky_handler(failures: list):
    """Handler that consumes ``failures`` (exceptions or status codes) then returns 200."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if failures:
            failure = failures.pop(0)
            if isinstance(failure, int):
                return httpx.Response(failure, request=request)
            raise failure
        return httpx.Response(200, text="ok", request=request)

    return handler, calls


def _sync_client(failures: list, max_retries: int = 3) -> tuple[httpx.Client, list]:
    handler, calls = _flaky_handler(failures)
    transport = RetryTransport(
        httpx.MockTransport(handler), max_retries=max_retries, backoff_factor=0
    )
    return httpx.Client(transport=transport), calls


def test_retries_dropped_connection_on_get():
    """The 'Server disconnected without sending a response' case from CI."""
    client, calls = _sync_client([httpx.RemoteProtocolError("Server disconnected")] * 2)
    response = client.get(URL)
    assert response.status_code == 200
    assert len(calls) == 3


def test_retries_gateway_errors_on_get():
    client, calls = _sync_client([502, 503, 504])
    assert client.get(URL).status_code == 200
    assert len(calls) == 4


def test_retries_connect_error_on_post():
    """Connect errors happen before the request is sent, so POST is safe to retry."""
    client, calls = _sync_client([httpx.ConnectError("refused")])
    assert client.post(URL, data={"a": "1"}).status_code == 200
    assert len(calls) == 2


def test_does_not_retry_post_after_send():
    """A POST the server may have received must not be sent twice."""
    client, calls = _sync_client([httpx.RemoteProtocolError("Server disconnected")])
    with pytest.raises(httpx.RemoteProtocolError):
        client.post(URL, data={"a": "1"})
    assert len(calls) == 1

    client, calls = _sync_client([503])
    assert client.post(URL).status_code == 503
    assert len(calls) == 1


def test_does_not_retry_client_errors():
    client, calls = _sync_client([404])
    assert client.get(URL).status_code == 404
    assert len(calls) == 1


def test_gives_up_after_max_retries():
    client, calls = _sync_client([httpx.ReadTimeout("slow")] * 10, max_retries=2)
    with pytest.raises(httpx.ReadTimeout):
        client.get(URL)
    assert len(calls) == 3

    client, calls = _sync_client([503] * 10, max_retries=2)
    assert client.get(URL).status_code == 503
    assert len(calls) == 3


def test_retry_after_header_is_respected():
    transport = RetryTransport(backoff_factor=0)
    response = httpx.Response(503, headers={"Retry-After": "7"})
    assert transport._policy.delay(0, response) == 7.0


@pytest.mark.asyncio
async def test_async_retries_dropped_connection():
    handler, calls = _flaky_handler([httpx.RemoteProtocolError("Server disconnected"), 503])
    transport = AsyncRetryTransport(httpx.MockTransport(handler), backoff_factor=0)
    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get(URL)
    assert response.status_code == 200
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_async_does_not_retry_post_after_send():
    handler, calls = _flaky_handler([httpx.ReadError("reset")])
    transport = AsyncRetryTransport(httpx.MockTransport(handler), backoff_factor=0)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(httpx.ReadError):
            await client.post(URL)
    assert len(calls) == 1


def test_clients_use_retry_transport():
    """Service clients and their Shibboleth auth get the retrying transport via the base."""
    with ClickmapClient(username="user", password="pass") as client:
        assert isinstance(client, BaseClient)
        assert isinstance(client._client._transport, RetryTransport)
        assert isinstance(client.auth._client._transport, RetryTransport)


def test_base_client_requires_credentials(monkeypatch):
    monkeypatch.delenv("SU_USERNAME", raising=False)
    monkeypatch.delenv("SU_PASSWORD", raising=False)
    with pytest.raises(AuthenticationError):
        ClickmapClient()


def test_all_service_clients_share_base():
    from dsv_wrapper import (
        ACTLabClient,
        AsyncACTLabClient,
        AsyncClickmapClient,
        AsyncDaisyClient,
        AsyncHandledningClient,
        AsyncPlayClient,
        DaisyClient,
        HandledningClient,
        PlayClient,
    )

    for cls in (ACTLabClient, ClickmapClient, DaisyClient, HandledningClient, PlayClient):
        assert issubclass(cls, BaseClient)
    for cls in (
        AsyncACTLabClient,
        AsyncClickmapClient,
        AsyncDaisyClient,
        AsyncHandledningClient,
        AsyncPlayClient,
    ):
        assert issubclass(cls, BaseAsyncClient)
