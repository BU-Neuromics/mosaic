"""REST transport persists through a config-built client (issue #42).

Proves the end state: when the app is built with a configured client (as
``hippo serve`` now does), an entity written through the SDK is visible over
the REST API — and that the no-client app (the old default) does not persist.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from hippo.config import HippoConfig
from hippo.core.factory import create_client_from_config
from hippo.serve import create_default_app

_FIXTURE_SCHEMA = (
    Path(__file__).parents[1] / "fixtures" / "schemas" / "sample_schema.yaml"
)
_AUTH = {"Authorization": "Bearer test-token"}


def test_rest_reads_through_configured_client(tmp_path):
    cfg = HippoConfig(
        schema_path=str(_FIXTURE_SCHEMA),
        database_url=str(tmp_path / "api.db"),
        storage_backend="sqlite",
    )
    client = create_client_from_config(cfg)
    app = create_default_app(client)
    api = TestClient(app)

    created = client.create("Project", {"name": "Gamma"})
    pid = created["id"]

    resp = api.get("/entities", params={"entity_type": "Project"}, headers=_AUTH)
    assert resp.status_code == 200
    body = resp.json()
    ids = [item["id"] for item in body["items"]]
    assert pid in ids
    assert body["total"] >= 1


def test_rest_without_client_does_not_persist(tmp_path):
    # The old default: no injected client -> routers fall back to
    # HippoClient() with storage=None, which never persists. A get-by-id
    # therefore 404s because nothing is ever written.
    app = create_default_app()
    api = TestClient(app)
    resp = api.get("/entities/some-id", headers=_AUTH)
    assert resp.status_code == 404
