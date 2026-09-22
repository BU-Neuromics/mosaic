"""The MCP transport's Host allow-list (#214).

The SDK enables DNS-rebinding protection by default and, given no settings,
derives its allow-list from a `host` parameter defaulting to `127.0.0.1`.
Passing neither meant the transport answered only loopback callers and returned
`421 Invalid Host header` to everything else -- invisible while every caller is
a host process on the same machine, and a hard wall the moment the boundary is
containerized.
"""
import pytest

from mosaic.mcp.router import ALLOWED_HOSTS_ENV, _transport_security


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv(ALLOWED_HOSTS_ENV, raising=False)


def test_loopback_is_allowed_by_default():
    # The single-machine case must behave exactly as it did before this became
    # configurable, or every existing deployment breaks to fix a new one.
    s = _transport_security()
    assert s.enable_dns_rebinding_protection
    assert "127.0.0.1" in s.allowed_hosts
    assert "localhost" in s.allowed_hosts


def test_loopback_is_allowed_with_any_port():
    s = _transport_security()
    assert "127.0.0.1:*" in s.allowed_hosts
    assert "localhost:*" in s.allowed_hosts


def test_configured_hosts_are_added_not_substituted(monkeypatch):
    # A deployment that adds a container name must not thereby lose loopback,
    # which is how an operator locally debugs the thing they just configured.
    monkeypatch.setenv(ALLOWED_HOSTS_ENV, "mosaic:*,host.docker.internal:*")
    s = _transport_security()
    assert "mosaic:*" in s.allowed_hosts
    assert "host.docker.internal:*" in s.allowed_hosts
    assert "127.0.0.1" in s.allowed_hosts


def test_whitespace_and_empties_are_tolerated(monkeypatch):
    monkeypatch.setenv(ALLOWED_HOSTS_ENV, " mosaic:* , , gateway ")
    s = _transport_security()
    assert "mosaic:*" in s.allowed_hosts
    assert "gateway" in s.allowed_hosts
    assert "" not in s.allowed_hosts


def test_star_disables_the_check_entirely(monkeypatch):
    # The same judgement `--cors-origin '*'` already offers on the HTTP surface:
    # a deployment may decide its own network boundary is the control.
    monkeypatch.setenv(ALLOWED_HOSTS_ENV, "*")
    s = _transport_security()
    assert s.enable_dns_rebinding_protection is False


def test_protection_is_not_silently_disabled_by_an_empty_value(monkeypatch):
    # An empty string must not read as "*". Failing open on a typo would turn a
    # security control off without anyone noticing.
    monkeypatch.setenv(ALLOWED_HOSTS_ENV, "")
    s = _transport_security()
    assert s.enable_dns_rebinding_protection is True
