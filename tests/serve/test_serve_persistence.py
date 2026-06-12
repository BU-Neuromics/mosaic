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


def _make_api(tmp_path):
    cfg = HippoConfig(
        schema_path=str(_FIXTURE_SCHEMA),
        database_url=str(tmp_path / "api.db"),
        storage_backend="sqlite",
    )
    client = create_client_from_config(cfg)
    app = create_default_app(client)
    return client, TestClient(app)


def test_rest_reads_through_configured_client(tmp_path):
    client, api = _make_api(tmp_path)

    created = client.create("Project", {"name": "Gamma"})
    pid = created["id"]

    resp = api.get("/entities", params={"entity_type": "Project"}, headers=_AUTH)
    assert resp.status_code == 200
    body = resp.json()
    ids = [item["id"] for item in body["items"]]
    assert pid in ids
    assert body["total"] >= 1

    # Get-by-id resolves the entity's real type from the id (issue #44):
    # no entity_type in the URL, yet the typed row must come back.
    resp = api.get(f"/entities/{pid}", headers=_AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == pid
    assert body["entity_type"] == "Project"
    assert body["data"]["name"] == "Gamma"


def test_rest_get_by_id_unknown_id_returns_404(tmp_path):
    _, api = _make_api(tmp_path)

    resp = api.get("/entities/no-such-id", headers=_AUTH)
    assert resp.status_code == 404


def test_rest_delete_by_id_resolves_type(tmp_path):
    client, api = _make_api(tmp_path)

    pid = client.create("Project", {"name": "Doomed"})["id"]

    resp = api.delete(f"/entities/{pid}", headers=_AUTH)
    assert resp.status_code == 200
    assert resp.json() == {"status": "deleted", "entity_id": pid}

    # Soft-deleted: no longer readable through the API.
    resp = api.get(f"/entities/{pid}", headers=_AUTH)
    assert resp.status_code == 404


def test_rest_delete_by_id_unknown_id_returns_404(tmp_path):
    _, api = _make_api(tmp_path)

    resp = api.delete("/entities/no-such-id", headers=_AUTH)
    assert resp.status_code == 404


def test_rest_list_without_type_scans_all_types(tmp_path):
    client, api = _make_api(tmp_path)

    pid = client.create("Project", {"name": "Alpha"})["id"]
    sid = client.create("Sample", {"name": "S1", "project_id": pid})["id"]

    resp = api.get("/entities", headers=_AUTH)
    assert resp.status_code == 200
    body = resp.json()
    by_id = {item["id"]: item["entity_type"] for item in body["items"]}
    assert by_id.get(pid) == "Project"
    assert by_id.get(sid) == "Sample"
    assert body["total"] >= 2


def test_rest_without_client_does_not_persist(tmp_path):
    # The old default: no injected client -> routers fall back to
    # HippoClient() with storage=None, which never persists. A get-by-id
    # therefore 404s because nothing is ever written.
    app = create_default_app()
    api = TestClient(app)
    resp = api.get("/entities/some-id", headers=_AUTH)
    assert resp.status_code == 404
