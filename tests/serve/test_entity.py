"""Tests for entity router."""

import pytest
from fastapi.testclient import TestClient

from hippo.api.factory import create_app
from hippo.serve.routers import entity, health


@pytest.fixture
def client():
    """Create test client."""
    app = create_app(routers=[health.router, entity.router])
    return TestClient(app)


def test_list_entities_without_auth_returns_401(client):
    """Test that listing entities without auth returns 401."""
    response = client.get("/entities")
    assert response.status_code == 401


def test_list_entities_with_auth_returns_200(client):
    """Test that listing entities with auth returns 200."""
    response = client.get("/entities", headers={"Authorization": "Bearer test-token"})
    assert response.status_code == 200


def test_get_entity_without_auth_returns_401(client):
    """Test that getting entity without auth returns 401."""
    response = client.get("/entities/test-id")
    assert response.status_code == 401


def test_get_entity_with_auth_returns_404(client):
    """Test that getting non-existent entity returns 404."""
    response = client.get(
        "/entities/test-id", headers={"Authorization": "Bearer test-token"}
    )
    assert response.status_code == 404


def test_delete_entity_without_auth_returns_401(client):
    """Test that deleting entity without auth returns 401."""
    response = client.delete("/entities/test-id")
    assert response.status_code == 401
