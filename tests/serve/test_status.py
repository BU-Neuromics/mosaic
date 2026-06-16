"""Tests for the ``GET /status`` system endpoint and ``HippoClient.status()``.

The spec's system-endpoint table (sec4) promises ``/status`` reports the
adapter type, schema version, entity counts, and capability summary.
"""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

import hippo
from hippo.api.factory import create_app
from hippo.core.client import HippoClient
from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter
from hippo.serve.routers import health
from tests.conftest import _build_minimal_schema_registry


@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield os.path.join(tmpdir, "test_status.db")


@pytest.fixture
def storage(db_path):
    return SQLiteAdapter(
        db_path, schema_registry=_build_minimal_schema_registry()
    )


@pytest.fixture
def hippo_client(storage):
    return HippoClient(
        storage=storage,
        registry=_build_minimal_schema_registry(),
        bypass_validation=True,
    )


@pytest.fixture
def client(hippo_client):
    app = create_app(routers=[health.router], hippo_client=hippo_client)
    return TestClient(app, raise_server_exceptions=False)


AUTH = {"Authorization": "Bearer test-token"}


class TestClientStatus:
    """SDK-level status summary."""

    def test_status_reports_adapter_and_capabilities(
        self, hippo_client: HippoClient
    ) -> None:
        status = hippo_client.status()

        assert status["service"] == "hippo"
        assert status["version"] == hippo.__version__
        assert status["adapter"] == "SQLiteAdapter"
        assert "fts" in status["capabilities"]["search"]
        assert status["capabilities"]["staged_transaction"] is True

    def test_status_reports_schema_metadata(
        self, hippo_client: HippoClient
    ) -> None:
        status = hippo_client.status()

        assert status["schema_version"] is not None
        assert "Sample" in status["entity_types"]

    def test_status_counts_entities_per_type(
        self, hippo_client: HippoClient
    ) -> None:
        assert hippo_client.status()["entity_counts"] == {}

        hippo_client.put("Sample", {"name": "a"})
        hippo_client.put("Sample", {"name": "b"})

        assert hippo_client.status()["entity_counts"] == {"Sample": 2}

    def test_status_counts_include_unavailable_entities(
        self, hippo_client: HippoClient
    ) -> None:
        """No hard deletes — a soft-deleted entity still counts."""
        result = hippo_client.put("Sample", {"name": "gone"})
        hippo_client.delete("Sample", result["id"])

        assert hippo_client.status()["entity_counts"] == {"Sample": 1}

    def test_status_without_storage_or_registry(self) -> None:
        bare = HippoClient(bypass_validation=True)
        status = bare.status()

        assert status["adapter"] is None
        assert status["schema_version"] is None
        assert status["entity_types"] == []
        assert status["entity_counts"] == {}
        assert status["capabilities"] == {}


class TestStatusEndpoint:
    """REST /status endpoint."""

    def test_status_requires_auth(self, client) -> None:
        assert client.get("/status").status_code == 401

    def test_status_returns_summary(self, client, hippo_client) -> None:
        hippo_client.put("Sample", {"name": "s1"})

        response = client.get("/status", headers=AUTH)

        assert response.status_code == 200
        body = response.json()
        assert body["service"] == "hippo"
        assert body["version"] == hippo.__version__
        assert body["adapter"] == "SQLiteAdapter"
        assert body["entity_counts"] == {"Sample": 1}
        assert "fts" in body["capabilities"]["search"]

    def test_health_remains_unauthenticated(self, client) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_root_reports_package_version(self, client) -> None:
        response = client.get("/")
        assert response.status_code == 200
        assert response.json()["version"] == hippo.__version__
