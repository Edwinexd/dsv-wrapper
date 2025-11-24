"""Tests for ACTLab client."""

import inspect
import logging

from dsv_wrapper.actlab import ACTLabClient, AsyncACTLabClient

logger = logging.getLogger(__name__)


def test_sync_async_actlab_api_parity():
    """Test that sync and async ACTLab clients have the same public API."""
    # Get all public methods from sync client (excluding magic methods and private methods)
    sync_methods = {
        name: method
        for name, method in inspect.getmembers(ACTLabClient, predicate=inspect.isfunction)
        if not name.startswith("_")
    }

    # Get all public methods from async client (excluding magic methods and private methods)
    async_methods = {
        name: method
        for name, method in inspect.getmembers(AsyncACTLabClient, predicate=inspect.isfunction)
        if not name.startswith("_")
    }

    # Check that async client has all the public methods from sync client
    missing_in_async = set(sync_methods.keys()) - set(async_methods.keys())

    # Filter out context manager methods which are intentionally different
    missing_in_async = {m for m in missing_in_async if m not in {"__enter__", "__exit__", "close"}}

    assert not missing_in_async, (
        f"Async ACTLab client is missing these public methods from sync client: {missing_in_async}"
    )

    # Verify method signatures match (excluding self and accounting for async)
    for method_name in sync_methods:
        if method_name in {"__enter__", "__exit__", "close"}:
            continue

        if method_name in async_methods:
            sync_sig = inspect.signature(sync_methods[method_name])
            async_sig = inspect.signature(async_methods[method_name])

            # Get parameters excluding 'self'
            sync_params = [p for p in sync_sig.parameters.values() if p.name != "self"]
            async_params = [p for p in async_sig.parameters.values() if p.name != "self"]

            # Compare parameter names and defaults
            sync_param_names = [p.name for p in sync_params]
            async_param_names = [p.name for p in async_params]

            assert sync_param_names == async_param_names, (
                f"Method '{method_name}' has different parameters:\n"
                f"  Sync: {sync_param_names}\n"
                f"  Async: {async_param_names}"
            )

    logger.info(
        "API parity check passed: sync and async ACTLab clients have matching public methods"
    )
