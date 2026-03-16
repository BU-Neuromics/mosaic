"""Tests for ingest router."""

import pytest
from fastapi.testclient import TestClient

from hippo.api.factory import create_app
from hippo.serve.routers import health, ingest


@pytest.fixture
def client():
    """Create test client."""
    app = create_app(routers=[health.router, ingest.router])
    return TestClient(app)


def test_ingest_without_auth_returns_401(client):
    """Test that ingest without auth returns 401."""
    response = client.post("/ingest", json={"entity_type": "test", "data": {}})
    assert response.status_code == 401


def test_ingest_missing_entity_type_returns_422(client):
    """Test that missing entity_type returns 422."""
    response = client.post(
        "/ingest",
        json={"data": {"name": "test"}},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 422
    assert "entity_type" in response.json()["detail"]


def test_ingest_missing_data_returns_422(client):
    """Test that missing data returns 422."""
    response = client.post(
        "/ingest",
        json={"entity_type": "test"},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 422
    assert "data" in response.json()["detail"]


def test_ingest_with_valid_data_returns_200(client):
    """Test that valid ingest request returns 200."""
    response = client.post(
        "/ingest",
        json={"entity_type": "sample", "data": {"name": "Test Entity"}},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert data["entity_type"] == "sample"
