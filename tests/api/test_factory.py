"""Tests for Mosaic API factory."""

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient
from fastapi.exceptions import RequestValidationError

from mosaic.api import create_app, EntityNotFoundError
from mosaic.core.exceptions import ValidationError as MosaicValidationError


def test_factory_creates_app_without_routers():
    """Test that factory creates app without routers."""
    app = create_app()
    assert isinstance(app, FastAPI)
    assert app.title == "Mosaic API"


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
    """Test that MosaicValidationError handler returns 422."""
    app = create_app()

    @app.get("/hippo-validate")
    def hippo_validate():
        raise MosaicValidationError(
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


def test_factory_omits_cors_headers_by_default():
    """No cors_allow_origins means no CORS middleware at all (issue #207)."""
    app = create_app()

    @app.get("/ping")
    def ping():
        return {"ok": True}

    client = TestClient(app)
    response = client.get("/ping", headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers

    preflight = client.options(
        "/ping",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert preflight.status_code == 405


def test_factory_cors_allow_origins_enables_configured_origin():
    """An explicit cors_allow_origins list opts a browser origin in (issue #207)."""
    app = create_app(cors_allow_origins=["http://localhost:5173"])

    @app.post("/ping")
    def ping():
        return {"ok": True}

    client = TestClient(app)
    preflight = client.options(
        "/ping",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert preflight.status_code == 200
    assert (
        preflight.headers["access-control-allow-origin"]
        == "http://localhost:5173"
    )

    response = client.post("/ping", headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_factory_cors_rejects_unlisted_origin():
    """An origin not in the explicit list gets no CORS headers (issue #207)."""
    app = create_app(cors_allow_origins=["http://localhost:5173"])

    @app.get("/ping")
    def ping():
        return {"ok": True}

    client = TestClient(app)
    response = client.get("/ping", headers={"Origin": "http://evil.example"})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
