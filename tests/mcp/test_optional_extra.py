"""Optional-extra plumbing for the MCP transport (mirrors
``tests/graphql/test_optional_extra.py``)."""

from __future__ import annotations

import sys

import pytest

from mosaic.core.client import MosaicClient
from mosaic.core.exceptions import ConfigError
from mosaic.mcp import MCP_EXTRA_HINT, create_mcp_app, mcp_available


class TestExtraDetection:
    def test_mcp_available_when_installed(self):
        assert mcp_available() is True

    def test_missing_extra_raises_actionable_import_error(self, monkeypatch):
        # ``sys.modules[name] = None`` makes ``import name`` raise
        # ImportError — simulates an environment without the extra.
        monkeypatch.setitem(sys.modules, "mcp", None)
        assert mcp_available() is False
        with pytest.raises(ImportError, match="pip install 'datahelix-mosaic\\[mcp\\]'"):
            create_mcp_app(MosaicClient())
        assert "mcp" in MCP_EXTRA_HINT

    def test_schemaless_client_raises_config_error(self):
        with pytest.raises(ConfigError, match="schema-backed"):
            create_mcp_app(MosaicClient())
