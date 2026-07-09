"""Regression tests for per-class typed-table emission in SQLiteAdapter.

These tests verify that ``SQLiteAdapter._init_database`` calls the
``DDLGenerator`` to emit per-class typed tables for every concrete user
class, and that ``create`` / ``update_data`` / ``set_availability`` /
``mark_superseded`` / ``delete`` write to the per-class typed table.

Per the sec9 handoff (Phase 2 / PR 2.3) the legacy ``entities`` blob
table no longer exists; assertions about per-class layout are kept here,
while semantic ("an entity of type X is queryable by name Y") behavior
is exercised by the broader integration suite.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from typing import Iterator

import pytest

from mosaic.core.client import MosaicClient
from mosaic.core.storage.adapters.sqlite_adapter import SQLiteAdapter
from mosaic.linkml_bridge import SchemaRegistry
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
def client(adapter: SQLiteAdapter) -> MosaicClient:
    return MosaicClient(
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

    def test_legacy_entities_table_is_dropped(self, db_path: str):
        SQLiteAdapter(db_path, schema_registry=_registry())
        assert "entities" not in _table_names(db_path)
        assert "entity_external_ids" not in _table_names(db_path)

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


class TestCreate:
    def test_create_writes_typed_row(self, client: MosaicClient, db_path: str):
        result = client.put("Sample", {"name": "S001", "tissue": "DLPFC"})
        row = _per_class_row(db_path, "Sample", result["id"])
        assert row is not None
        assert row["name"] == "S001"
        assert row["tissue"] == "DLPFC"
        assert row["is_available"] == 1

    def test_create_round_trips_via_sdk(self, client: MosaicClient):
        result = client.put("Sample", {"name": "S002", "tissue": "DLPFC"})
        got = client.get("Sample", result["id"])
        assert got is not None
        assert got["data"]["name"] == "S002"
        assert got["data"]["tissue"] == "DLPFC"


class TestUpdateKeepsTablesInSync:
    def test_put_update_propagates_to_typed_table(
        self, client: MosaicClient, db_path: str
    ):
        created = client.put("Sample", {"id": "u1", "name": "S001", "tissue": "old"})
        client.put("Sample", {"name": "S001", "tissue": "new"}, "u1")
        row = _per_class_row(db_path, "Sample", "u1")
        assert row["tissue"] == "new"

    def test_set_availability_propagates_to_typed_table(
        self, client: MosaicClient, db_path: str
    ):
        client.put("Sample", {"id": "a1", "name": "S001"})
        client.set_availability_bulk("Sample", ["a1"], is_available=False)
        row = _per_class_row(db_path, "Sample", "a1")
        assert row is not None
        assert row["is_available"] == 0

    def test_delete_propagates_to_typed_table(
        self, client: MosaicClient, db_path: str
    ):
        client.put("Sample", {"id": "d1", "name": "S001"})
        client.delete("Sample", "d1")
        row = _per_class_row(db_path, "Sample", "d1")
        assert row is not None
        assert row["is_available"] == 0

    def test_mark_superseded_propagates_to_typed_table(
        self, client: MosaicClient, db_path: str
    ):
        client.put("Sample", {"id": "old", "name": "S001"})
        client.put("Sample", {"id": "new", "name": "S002"})
        client.supersede_entity("old", "new", reason="upgrade")
        row = _per_class_row(db_path, "Sample", "old")
        assert row is not None
        assert row["is_available"] == 0
        assert row["superseded_by"] == "new"


class TestFindUsesPerClassTable:
    def test_find_by_entity_type_returns_typed_rows(self, client: MosaicClient):
        client.put("Sample", {"id": "f1", "name": "Alpha", "tissue": "DLPFC"})
        client.put("Sample", {"id": "f2", "name": "Beta", "tissue": "ACC"})

        results = list(
            client._storage.find(
                __import__(
                    "mosaic.core.storage", fromlist=["Query"]
                ).Query(entity_type="Sample")
            )
        )
        names = {e.data.get("name") for e in results}
        assert names == {"Alpha", "Beta"}

    def test_find_filter_uses_column_predicate(self, client: MosaicClient):
        client.put("Sample", {"id": "g1", "name": "Alpha", "tissue": "DLPFC"})
        client.put("Sample", {"id": "g2", "name": "Beta", "tissue": "ACC"})

        Query = __import__("mosaic.core.storage", fromlist=["Query"]).Query
        results = list(
            client._storage.find(Query(entity_type="Sample", filters=[{"name": "Alpha"}]))
        )
        assert len(results) == 1
        assert results[0].data["name"] == "Alpha"


def _multi_class_registry() -> SchemaRegistry:
    return build_registry(
        {
            "Sample": {
                "attributes": {
                    "id": {"identifier": True, "required": True},
                    "name": {"range": "string", "required": True},
                    "tissue": {"range": "string"},
                }
            },
            "Project": {
                "attributes": {
                    "id": {"identifier": True, "required": True},
                    "title": {"range": "string", "required": True},
                }
            },
        }
    )


class TestCrossClassUuidLookup:
    """Given only a UUID, the adapter must return the correct typed
    entity without the caller knowing the class up front (sec9 §9.5 /
    PR 2.4 ``_entity_registry`` shadow table)."""

    @pytest.fixture
    def db_path(self) -> Iterator[str]:
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.join(tmpdir, "cross_class.db")

    @pytest.fixture
    def adapter(self, db_path: str) -> SQLiteAdapter:
        return SQLiteAdapter(db_path, schema_registry=_multi_class_registry())

    @pytest.fixture
    def client(self, adapter: SQLiteAdapter) -> MosaicClient:
        return MosaicClient(
            storage=adapter,
            registry=adapter.schema_registry,
            bypass_validation=True,
        )

    def test_cross_class_uuid_lookup(
        self, client: MosaicClient, adapter: SQLiteAdapter
    ) -> None:
        sample = client.put("Sample", {"name": "S001", "tissue": "DLPFC"})
        project = client.put("Project", {"title": "Atlas"})

        # Given only the UUID — no entity_type — the adapter resolves the
        # class and returns the typed payload.
        sample_entity = adapter.read(sample["id"])
        assert sample_entity is not None
        assert sample_entity.entity_type == "Sample"
        assert sample_entity.data["name"] == "S001"
        assert sample_entity.data["tissue"] == "DLPFC"

        project_entity = adapter.read(project["id"])
        assert project_entity is not None
        assert project_entity.entity_type == "Project"
        assert project_entity.data["title"] == "Atlas"

        # resolve_type / resolve_types must agree.
        assert adapter.resolve_type(sample["id"]) == "Sample"
        assert adapter.resolve_type(project["id"]) == "Project"
        assert adapter.resolve_types([sample["id"], project["id"]]) == {
            sample["id"]: "Sample",
            project["id"]: "Project",
        }

    def test_registry_populated_for_each_create(
        self, client: MosaicClient, db_path: str
    ) -> None:
        sample = client.put("Sample", {"name": "S001"})
        project = client.put("Project", {"title": "Atlas"})

        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute(
                "SELECT uuid, class_name FROM _entity_registry "
                "WHERE uuid IN (?, ?) ORDER BY class_name",
                (sample["id"], project["id"]),
            ).fetchall()
        finally:
            conn.close()

        assert rows == [(project["id"], "Project"), (sample["id"], "Sample")]

    def test_registry_backfills_from_provenance_on_reinit(
        self, client: MosaicClient, adapter: SQLiteAdapter, db_path: str
    ) -> None:
        # Simulate a pre-PR-2.4 DB that has ProvenanceRecord entries but
        # an empty _entity_registry: clear the registry and re-instantiate
        # the adapter. The idempotent backfill in _init_database must
        # re-populate the registry from ProvenanceRecord 'create' events.
        sample = client.put("Sample", {"name": "S001"})
        project = client.put("Project", {"title": "Atlas"})

        conn = sqlite3.connect(db_path)
        try:
            conn.execute("DELETE FROM _entity_registry")
            conn.commit()
        finally:
            conn.close()

        SQLiteAdapter(db_path, schema_registry=_multi_class_registry())

        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute(
                "SELECT uuid, class_name FROM _entity_registry "
                "WHERE uuid IN (?, ?) ORDER BY class_name",
                (sample["id"], project["id"]),
            ).fetchall()
        finally:
            conn.close()

        assert rows == [(project["id"], "Project"), (sample["id"], "Sample")]

    def test_unknown_uuid_returns_none(self, adapter: SQLiteAdapter) -> None:
        assert adapter.resolve_type("not-a-real-uuid") is None
        assert adapter.read("not-a-real-uuid") is None
        assert adapter.resolve_types(["not-a-real-uuid"]) == {}


def _boolean_registry() -> SchemaRegistry:
    return build_registry(
        {
            "Flagged": {
                "attributes": {
                    "id": {"identifier": True, "required": True},
                    "name": {"range": "string", "required": True},
                    "confirmed": {"range": "boolean"},
                }
            }
        }
    )


class TestBooleanRoundTrip:
    """``range: boolean`` slots round-trip as Python ``bool`` (PTS-349).

    ``_coerce_for_column`` stores ``bool`` as SQLite integer ``0``/``1``;
    ``_decode_column_value`` must reverse that for boolean slots on both
    hydration paths (``read`` → ``_read_per_class`` and ``find`` →
    ``_find_per_class``), or downstream LinkML validation rejects the raw
    integer for a ``range: boolean`` slot.
    """

    @pytest.fixture
    def bool_db_path(self) -> Iterator[str]:
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.join(tmpdir, "boolean.db")

    @pytest.fixture
    def bool_client(self, bool_db_path: str) -> MosaicClient:
        adapter = SQLiteAdapter(bool_db_path, schema_registry=_boolean_registry())
        return MosaicClient(
            storage=adapter,
            registry=adapter.schema_registry,
            bypass_validation=True,
        )

    @pytest.mark.parametrize("value", [True, False])
    def test_stored_as_integer_read_back_as_bool(
        self, bool_client: MosaicClient, bool_db_path: str, value: bool
    ) -> None:
        result = bool_client.put("Flagged", {"name": "f1", "confirmed": value})
        entity_id = result["id"]

        # Storage layer keeps the SQLite-native 0/1 integer.
        row = _per_class_row(bool_db_path, "Flagged", entity_id)
        assert row["confirmed"] == (1 if value else 0)
        assert isinstance(row["confirmed"], int)

        # read()/get() path (_read_per_class) reverses to a Python bool.
        got = bool_client.get("Flagged", entity_id)
        assert got["data"]["confirmed"] is value

        # find()/query() path (_find_per_class) reverses to a Python bool.
        items = bool_client.query("Flagged").items
        assert len(items) == 1
        assert items[0]["data"]["confirmed"] is value

    def test_decode_column_value_boolean_flag(self) -> None:
        decode = SQLiteAdapter._decode_column_value
        # With the boolean flag, 0/1 integers reverse to bool.
        assert decode(1, is_boolean=True) is True
        assert decode(0, is_boolean=True) is False
        # Without the flag, integers pass through unchanged (non-boolean slot).
        assert decode(1, is_boolean=False) == 1
        assert decode(1) == 1
        # The flag does not disturb JSON-container decoding.
        assert decode('[1, 2]', is_boolean=True) == [1, 2]


def _string_payload_registry():
    return build_registry(
        {
            "Document": {
                "attributes": {
                    "id": {"identifier": True},
                    "name": {"range": "string"},
                    "payload": {"range": "string"},
                    "tags": {"range": "string", "multivalued": True},
                }
            }
        }
    )


class TestStringRoundTrip:
    """A scalar string slot's text round-trips verbatim — never JSON-decoded.

    Aperture's control-plane documents store serialized ``{"v": …,
    "data": …}`` envelopes in a ``range: string`` ``payload`` slot; the
    read side used to JSON-decode any text that parsed as a container,
    corrupting the string into a dict that GraphQL's String type then
    refused to serialize (aperture#15 live-seam finding, datahelix#45).
    Multivalued string slots still decode: they are stored as JSON arrays.
    """

    @pytest.fixture
    def string_db_path(self) -> str:
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.join(tmpdir, "strings.db")

    @pytest.fixture
    def string_client(self, string_db_path: str) -> MosaicClient:
        adapter = SQLiteAdapter(
            string_db_path, schema_registry=_string_payload_registry()
        )
        return MosaicClient(
            storage=adapter,
            registry=adapter.schema_registry,
            bypass_validation=True,
        )

    @pytest.mark.parametrize(
        "payload",
        ['{"v": 1, "data": []}', "[1, 2, 3]", "plain text", "{not json"],
    )
    def test_json_looking_string_round_trips_verbatim(
        self, string_client: MosaicClient, payload: str
    ) -> None:
        result = string_client.put(
            "Document", {"name": "d1", "payload": payload}
        )
        entity_id = result["id"]

        # read()/get() path (_read_per_class).
        got = string_client.get("Document", entity_id)
        assert got["data"]["payload"] == payload
        assert isinstance(got["data"]["payload"], str)

        # find()/query() path (_find_per_class).
        items = string_client.query("Document").items
        assert len(items) == 1
        assert items[0]["data"]["payload"] == payload
        assert isinstance(items[0]["data"]["payload"], str)

    def test_multivalued_string_slot_still_decodes(
        self, string_client: MosaicClient
    ) -> None:
        result = string_client.put(
            "Document", {"name": "d2", "tags": ["alpha", "beta"]}
        )
        got = string_client.get("Document", result["id"])
        assert got["data"]["tags"] == ["alpha", "beta"]

    def test_decode_column_value_string_flag(self) -> None:
        decode = SQLiteAdapter._decode_column_value
        # With the string flag, JSON-looking text passes through verbatim.
        assert decode('{"v": 1}', is_string=True) == '{"v": 1}'
        assert decode("[1, 2]", is_string=True) == "[1, 2]"
        # Without it, containers still decode (multivalued / value types).
        assert decode("[1, 2]") == [1, 2]
