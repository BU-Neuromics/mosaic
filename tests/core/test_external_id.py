"""Unit tests for the ExternalID write path through ProvenanceService.

Following PR 2.2 of the LinkML-native β-refactor (sec9 §9), external IDs
are stored as first-class ``ExternalID`` entities in the per-class typed
table. ``ProvenanceService`` is the seam that orchestrates the writes;
these tests pin its behavior against the underlying ``SQLiteAdapter``.
PR 2.3 removed the legacy ``ExternalIdStorageAdapter`` and the
``entity_external_ids`` table entirely; all reads/writes go through the
``ExternalID`` per-class typed table.
"""

import os
import tempfile
from typing import Iterator

import pytest

from mosaic.core.exceptions import EntityNotFoundError
from mosaic.core.provenance_service import ProvenanceService
from mosaic.core.storage.adapters.sqlite_adapter import SQLiteAdapter, SQLiteEntity
from tests.conftest import _build_minimal_schema_registry


class TestProvenanceServiceExternalId:
    """Tests for the ``ExternalID``-class write path."""

    @pytest.fixture
    def db_path(self) -> Iterator[str]:
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.join(tmpdir, "test_external_id.db")

    @pytest.fixture
    def storage(self, db_path: str) -> SQLiteAdapter:
        return SQLiteAdapter(
            db_path, schema_registry=_build_minimal_schema_registry()
        )

    @pytest.fixture
    def service(self, storage: SQLiteAdapter) -> ProvenanceService:
        return ProvenanceService(storage=storage)

    @pytest.fixture
    def entity_id(self, storage: SQLiteAdapter) -> str:
        """Create a parent entity and return its ID.

        ``Sample`` is declared in the test SchemaRegistry overlay
        (``tests/conftest.py``) as a generic stand-in user class, so the
        adapter persists it in the per-class ``Sample`` table.
        """
        entity = SQLiteEntity(
            id="parent-1",
            entity_type="Sample",
            is_available=True,
            version=1,
            data={"name": "parent"},
        )
        storage.create(entity)
        return "parent-1"

    def test_register_writes_to_external_id_table(
        self,
        storage: SQLiteAdapter,
        service: ProvenanceService,
        entity_id: str,
    ) -> None:
        result = service.register_external_id(entity_id, "EXT-001")

        assert result["entity_id"] == entity_id
        assert result["external_id"] == "EXT-001"
        assert result["source_system"] == "default"
        assert result["superseded_at"] is None

        with storage._transaction() as conn:
            cur = conn.cursor()
            cur.execute(
                'SELECT id, value, source_system, entity, is_active, is_available'
                ' FROM "ExternalID"'
            )
            rows = [dict(r) for r in cur.fetchall()]

        assert len(rows) == 1
        row = rows[0]
        assert row["id"] == result["id"]
        assert row["value"] == "EXT-001"
        assert row["source_system"] == "default"
        assert row["entity"] == entity_id
        assert bool(row["is_active"])
        assert bool(row["is_available"])

    def test_register_records_external_id_add_provenance(
        self,
        storage: SQLiteAdapter,
        service: ProvenanceService,
        entity_id: str,
    ) -> None:
        result = service.register_external_id(entity_id, "EXT-001")

        with storage._transaction() as conn:
            cur = conn.cursor()
            cur.execute(
                'SELECT operation, derived_from_id, patch FROM "ProvenanceRecord"'
                " WHERE entity_id = ? AND operation = 'external_id_add'",
                (entity_id,),
            )
            rows = cur.fetchall()
        assert len(rows) == 1
        assert rows[0]["derived_from_id"] == result["id"]

    def test_register_invalid_entity(
        self, service: ProvenanceService
    ) -> None:
        with pytest.raises(EntityNotFoundError):
            service.register_external_id("non-existent", "EXT-001")

    def test_get_by_external_id_returns_parent(
        self,
        service: ProvenanceService,
        entity_id: str,
    ) -> None:
        service.register_external_id(entity_id, "EXT-001")
        result = service.get_by_external_id("EXT-001")
        assert result["id"] == entity_id
        assert result["external_id"] == "EXT-001"
        assert result["source_system"] == "default"

    def test_get_by_external_id_not_found(
        self, service: ProvenanceService
    ) -> None:
        with pytest.raises(EntityNotFoundError):
            service.get_by_external_id("NON-EXISTENT")

    def test_supersede_marks_old_inactive_and_inserts_new(
        self,
        storage: SQLiteAdapter,
        service: ProvenanceService,
        entity_id: str,
    ) -> None:
        original = service.register_external_id(entity_id, "EXT-001")
        new_record = service.supersede(entity_id, "EXT-001", "EXT-002")

        assert new_record["external_id"] == "EXT-002"
        assert new_record["superseded_at"] is None

        with storage._transaction() as conn:
            cur = conn.cursor()
            cur.execute(
                'SELECT id, value, is_active FROM "ExternalID" ORDER BY value'
            )
            rows = [dict(r) for r in cur.fetchall()]

        assert len(rows) == 2
        by_value = {r["value"]: r for r in rows}
        assert bool(by_value["EXT-001"]["is_active"]) is False
        assert bool(by_value["EXT-002"]["is_active"]) is True
        assert by_value["EXT-001"]["id"] == original["id"]
        assert by_value["EXT-002"]["id"] == new_record["id"]

    def test_supersede_records_supersede_provenance(
        self,
        storage: SQLiteAdapter,
        service: ProvenanceService,
        entity_id: str,
    ) -> None:
        original = service.register_external_id(entity_id, "EXT-001")
        new_record = service.supersede(entity_id, "EXT-001", "EXT-002")

        with storage._transaction() as conn:
            cur = conn.cursor()
            cur.execute(
                'SELECT operation, entity_id, derived_from_id FROM "ProvenanceRecord"'
                " WHERE operation = 'supersede'"
            )
            rows = [dict(r) for r in cur.fetchall()]
        assert len(rows) == 1
        assert rows[0]["entity_id"] == new_record["id"]
        assert rows[0]["derived_from_id"] == original["id"]

    def test_list_external_ids_excludes_superseded_by_default(
        self, service: ProvenanceService, entity_id: str
    ) -> None:
        service.register_external_id(entity_id, "EXT-001")
        service.supersede(entity_id, "EXT-001", "EXT-002")

        results = service.list_external_ids(entity_id)

        assert len(results) == 1
        assert results[0]["external_id"] == "EXT-002"

    def test_list_external_ids_include_superseded(
        self, service: ProvenanceService, entity_id: str
    ) -> None:
        service.register_external_id(entity_id, "EXT-001")
        service.supersede(entity_id, "EXT-001", "EXT-002")

        results = service.list_external_ids(entity_id, include_superseded=True)

        external_ids = {r["external_id"] for r in results}
        assert external_ids == {"EXT-001", "EXT-002"}
        superseded = next(r for r in results if r["external_id"] == "EXT-001")
        assert superseded["superseded_at"] is not None

    def test_register_distinct_source_systems_same_value(
        self,
        storage: SQLiteAdapter,
        service: ProvenanceService,
    ) -> None:
        """Same value across distinct source systems is allowed."""
        e1 = SQLiteEntity(
            id="parent-1", entity_type="Sample", is_available=True, version=1,
            data={"name": "a"},
        )
        e2 = SQLiteEntity(
            id="parent-2", entity_type="Sample", is_available=True, version=1,
            data={"name": "b"},
        )
        storage.create(e1)
        storage.create(e2)

        service.register_external_id("parent-1", "X", source_system="A")
        service.register_external_id("parent-2", "X", source_system="B")

        results_a = service.list_external_ids("parent-1")
        results_b = service.list_external_ids("parent-2")
        assert {r["source_system"] for r in results_a} == {"A"}
        assert {r["source_system"] for r in results_b} == {"B"}
