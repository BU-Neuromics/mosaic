"""Regression tests for per-class typed-table emission in SQLiteAdapter (PTS-172).

These tests verify that ``SQLiteAdapter._init_database`` calls the
``DDLGenerator`` to emit per-class typed tables for every concrete user
class, and that ``create`` / ``update_data`` / ``set_availability`` /
``mark_superseded`` / ``delete`` keep the per-class table and the
legacy ``entities`` table in sync.

Per the sec9 handoff (Phase 2 / PR 2.1) tests favour *semantic*
assertions ("an entity of type X is queryable by name Y") over
table-layout assertions, but this module also peeks at the typed
table directly to lock in the contract that PR 2.1 introduces. PR 2.3
drops the legacy ``entities`` table; that PR will update the half of
this file that asserts dual-write.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Iterator

import pytest

from hippo.core.client import HippoClient
from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter
from hippo.linkml_bridge import SchemaRegistry
from tests.support.linkml_schemas import build_registry


def _registry() -> SchemaRegistry:
    return build_registry(
        {
            "Sample": {
                "attributes": {
                    "id": {"identifier": True, "required": True},
                    "name": {"range": "string", "required": True},
                    "tissue": {"range": "string"},
                }
            }
        }
    )


@pytest.fixture
def db_path() -> Iterator[str]:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield os.path.join(tmpdir, "per_class.db")


@pytest.fixture
def adapter(db_path: str) -> SQLiteAdapter:
    return SQLiteAdapter(db_path, schema_registry=_registry())


@pytest.fixture
def client(adapter: SQLiteAdapter) -> HippoClient:
    return HippoClient(
        storage=adapter,
        registry=adapter.schema_registry,
        bypass_validation=True,
    )


def _table_names(db_path: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    finally:
        conn.close()
    return {row[0] for row in rows}


def _per_class_row(db_path: str, entity_type: str, entity_id: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            f'SELECT * FROM "{entity_type}" WHERE id = ?', (entity_id,)
        ).fetchone()
    finally:
        conn.close()


class TestPerClassTableEmission:
    def test_user_schema_class_gets_typed_table(self, db_path: str):
        SQLiteAdapter(db_path, schema_registry=_registry())
        assert "Sample" in _table_names(db_path)

    def test_legacy_entities_table_still_exists(self, db_path: str):
        SQLiteAdapter(db_path, schema_registry=_registry())
        assert "entities" in _table_names(db_path)

    def test_re_init_is_idempotent(self, db_path: str):
        SQLiteAdapter(db_path, schema_registry=_registry())
        # Second instantiation must not raise on already-existing tables.
        SQLiteAdapter(db_path, schema_registry=_registry())
        assert "Sample" in _table_names(db_path)

    def test_provenance_record_is_not_emitted_twice(self, db_path: str):
        SQLiteAdapter(db_path, schema_registry=_registry())
        # ProvenanceRecord is hand-coded above _init_per_class_tables;
        # emitting it twice would raise during init.
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name='ProvenanceRecord'"
            ).fetchall()
        finally:
            conn.close()
        assert len(rows) == 1


class TestCreateDualWrite:
    def test_create_writes_typed_row(self, client: HippoClient, db_path: str):
        result = client.put("Sample", {"name": "S001", "tissue": "DLPFC"})
        row = _per_class_row(db_path, "Sample", result["id"])
        assert row is not None
        assert row["name"] == "S001"
        assert row["tissue"] == "DLPFC"
        assert row["is_available"] == 1

    def test_create_writes_legacy_entities_row(
        self, client: HippoClient, db_path: str
    ):
        result = client.put("Sample", {"name": "S002", "tissue": "DLPFC"})
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT id, entity_type, data FROM entities WHERE id = ?",
                (result["id"],),
            ).fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row["entity_type"] == "Sample"
        data = json.loads(row["data"])
        assert data["name"] == "S002"


class TestUpdateKeepsTablesInSync:
    def test_put_update_propagates_to_typed_table(
        self, client: HippoClient, db_path: str
    ):
        created = client.put("Sample", {"id": "u1", "name": "S001", "tissue": "old"})
        client.put("Sample", {"name": "S001", "tissue": "new"}, "u1")
        row = _per_class_row(db_path, "Sample", "u1")
        assert row["tissue"] == "new"

    def test_set_availability_propagates_to_typed_table(
        self, client: HippoClient, db_path: str
    ):
        client.put("Sample", {"id": "a1", "name": "S001"})
        client.set_availability_bulk("Sample", ["a1"], is_available=False)
        row = _per_class_row(db_path, "Sample", "a1")
        assert row is not None
        assert row["is_available"] == 0

    def test_delete_propagates_to_typed_table(
        self, client: HippoClient, db_path: str
    ):
        client.put("Sample", {"id": "d1", "name": "S001"})
        client.delete("Sample", "d1")
        row = _per_class_row(db_path, "Sample", "d1")
        assert row is not None
        assert row["is_available"] == 0

    def test_mark_superseded_propagates_to_typed_table(
        self, client: HippoClient, db_path: str
    ):
        client.put("Sample", {"id": "old", "name": "S001"})
        client.put("Sample", {"id": "new", "name": "S002"})
        client.supersede_entity("old", "new", reason="upgrade")
        row = _per_class_row(db_path, "Sample", "old")
        assert row is not None
        assert row["is_available"] == 0
        assert row["superseded_by"] == "new"


class TestFindUsesPerClassTable:
    def test_find_by_entity_type_returns_typed_rows(self, client: HippoClient):
        client.put("Sample", {"id": "f1", "name": "Alpha", "tissue": "DLPFC"})
        client.put("Sample", {"id": "f2", "name": "Beta", "tissue": "ACC"})

        results = list(
            client._storage.find(
                __import__(
                    "hippo.core.storage", fromlist=["Query"]
                ).Query(entity_type="Sample")
            )
        )
        names = {e.data.get("name") for e in results}
        assert names == {"Alpha", "Beta"}

    def test_find_filter_uses_column_predicate(self, client: HippoClient):
        client.put("Sample", {"id": "g1", "name": "Alpha", "tissue": "DLPFC"})
        client.put("Sample", {"id": "g2", "name": "Beta", "tissue": "ACC"})

        Query = __import__("hippo.core.storage", fromlist=["Query"]).Query
        results = list(
            client._storage.find(Query(entity_type="Sample", filters=[{"name": "Alpha"}]))
        )
        assert len(results) == 1
        assert results[0].data["name"] == "Alpha"
