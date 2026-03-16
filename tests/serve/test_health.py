"""Tests for Hippo Serve routers."""

from fastapi.testclient import TestClient

from hippo.api.factory import create_app
from hippo.serve.routers import health


def test_health_endpoint():
    """Test health check endpoint."""
    app = create_app(routers=[health.router])
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_root_endpoint():
    """Test root endpoint."""
    app = create_app(routers=[health.router])
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == "Hippo API"


def test_openapi_docs_available():
    """Test that OpenAPI documentation is available."""
    app = create_app(routers=[health.router])
    client = TestClient(app)
    response = client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert data["info"]["title"] == "Hippo API"
    assert data["info"]["version"] == "0.1.0"


def test_swagger_ui_available():
    """Test that Swagger UI is available."""
    app = create_app(routers=[health.router])
    client = TestClient(app)
    response = client.get("/docs")
    assert response.status_code == 200


def test_redoc_available():
    """Test that ReDoc is available."""
    app = create_app(routers=[health.router])
    client = TestClient(app)
    response = client.get("/redoc")
    assert response.status_code == 200
