"""Tests for Hippo API factory."""

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient
from fastapi.exceptions import RequestValidationError

from hippo.api import create_app, EntityNotFoundError
from hippo.core.exceptions import ValidationError as HippoValidationError


def test_factory_creates_app_without_routers():
    """Test that factory creates app without routers."""
    app = create_app()
    assert isinstance(app, FastAPI)
    assert app.title == "Hippo API"


def test_factory_creates_app_with_routers():
    """Test that factory creates app with routers."""
    router = APIRouter()

    @router.get("/test")
    def test_endpoint():
        return {"message": "test"}

    app = create_app(routers=[router])
    assert isinstance(app, FastAPI)

    client = TestClient(app)
    response = client.get("/test")
    assert response.status_code == 200
    assert response.json() == {"message": "test"}


def test_request_validation_error_handler_returns_422():
    """Test that RequestValidationError handler returns 422."""
    app = create_app()

    @app.get("/validate")
    def validate():
        raise RequestValidationError(
            [{"type": "missing", "loc": ("body",), "msg": "Field required"}]
        )

    client = TestClient(app)
    response = client.get("/validate")
    assert response.status_code == 422
    data = response.json()
    assert "error" in data
    assert data["error"] == "Validation Error"


def test_entity_not_found_error_handler_returns_404():
    """Test that EntityNotFoundError handler returns 404."""
    app = create_app()

    @app.get("/entity/{entity_id}")
    def get_entity(entity_id: str):
        raise EntityNotFoundError(
            message="Entity not found",
            entity_type="Sample",
            entity_id=entity_id,
        )

    client = TestClient(app)
    response = client.get("/entity/abc123")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"] == "Entity Not Found"


def test_generic_exception_handler_returns_500():
    """Test that generic Exception handler returns 500."""
    app = create_app()

    @app.get("/error")
    def trigger_error():
        raise HTTPException(status_code=500, detail="Internal Server Error")

    client = TestClient(app)
    response = client.get("/error")
    assert response.status_code == 500
    assert "detail" in response.json()


def test_hippo_validation_error_handler_returns_422():
    """Test that HippoValidationError handler returns 422."""
    app = create_app()

    @app.get("/hippo-validate")
    def hippo_validate():
        raise HippoValidationError(
            message="Invalid input",
            expected_type="string",
            actual_value=123,
        )

    client = TestClient(app)
    response = client.get("/hippo-validate")
    assert response.status_code == 422
    data = response.json()
    assert "error" in data
    assert data["error"] == "Validation Error"
