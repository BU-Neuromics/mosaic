"""Tests for the backend factory — create_backend() coverage."""

from __future__ import annotations

import pytest

from mosaic.tui.backend import create_backend
from mosaic.tui.backend.sdk import SDKBackend
from mosaic.tui.backend.rest import RESTBackend


def test_factory_returns_sdk_backend():
    """create_backend('sdk', ...) returns an SDKBackend instance."""
    backend = create_backend("sdk", db_path=":memory:")
    assert isinstance(backend, SDKBackend)


def test_factory_returns_rest_backend():
    """create_backend('rest', ...) returns a RESTBackend instance."""
    backend = create_backend("rest", url="http://localhost:8000", token="t")
    assert isinstance(backend, RESTBackend)


def test_factory_raises_for_unknown_mode():
    """create_backend raises ValueError for unrecognised modes."""
    with pytest.raises(ValueError, match="Unknown backend mode"):
        create_backend("graphql")


def test_factory_unknown_mode_message_is_descriptive():
    """ValueError message names the invalid mode."""
    with pytest.raises(ValueError) as exc_info:
        create_backend("bogus")
    assert "bogus" in str(exc_info.value)
