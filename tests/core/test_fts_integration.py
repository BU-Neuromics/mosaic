"""Tests for FTS integration with SQLite storage adapter."""

import pytest
from mosaic.core.storage.adapters.sqlite_adapter import FTSStore


class TestFTSStore:
    """Tests for FTSStore operations."""

    def test_fts_store_init(self, sqlite_connection):
        """Test FTSStore initialization."""
        store = FTSStore(sqlite_connection)
        assert store._conn is not None

    def test_create_fts_table(self, sqlite_connection):
        """Test FTS table creation."""
        store = FTSStore(sqlite_connection)
        store.create_fts_table(
            table_name="fts_test",
            columns=["title", "description"],
        )

        cursor = sqlite_connection.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fts_test'"
        )
        result = cursor.fetchone()
        assert result is not None
        assert result[0] == "fts_test"

    def test_insert_fts_entry(self, sqlite_connection):
        """Test inserting into FTS table."""
        store = FTSStore(sqlite_connection)
        store.create_fts_table(table_name="fts_test", columns=["title"])
        store.insert_fts_entry("fts_test", "entity-123", "test content")

        cursor = sqlite_connection.cursor()
        cursor.execute("SELECT * FROM fts_test WHERE entity_id = ?", ("entity-123",))
        row = cursor.fetchone()
        assert row is not None

    def test_update_fts_entry(self, sqlite_connection):
        """Test updating FTS entry."""
        store = FTSStore(sqlite_connection)
        store.create_fts_table(table_name="fts_test", columns=["title"])
        store.insert_fts_entry("fts_test", "entity-123", "original content")
        store.update_fts_entry("fts_test", "entity-123", "updated content")

        cursor = sqlite_connection.cursor()
        cursor.execute(
            "SELECT content FROM fts_test WHERE entity_id = ?", ("entity-123",)
        )
        row = cursor.fetchone()
        assert row[0] == "updated content"

    def test_delete_fts_entry(self, sqlite_connection):
        """Test deleting FTS entry."""
        store = FTSStore(sqlite_connection)
        store.create_fts_table(table_name="fts_test", columns=["title"])
        store.insert_fts_entry("fts_test", "entity-123", "test content")
        store.delete_fts_entry("fts_test", "entity-123")

        cursor = sqlite_connection.cursor()
        cursor.execute("SELECT * FROM fts_test WHERE entity_id = ?", ("entity-123",))
        row = cursor.fetchone()
        assert row is None

    def test_search_fts(self, sqlite_connection):
        """Test FTS search."""
        store = FTSStore(sqlite_connection)
        store.create_fts_table(table_name="fts_test", columns=["title"])
        store.insert_fts_entry("fts_test", "entity-1", "hello world")
        store.insert_fts_entry("fts_test", "entity-2", "goodbye world")
        store.insert_fts_entry("fts_test", "entity-3", "hello universe")

        results = store.search_fts("fts_test", "hello")
        assert len(results) == 2
        entity_ids = [r["entity_id"] for r in results]
        assert "entity-1" in entity_ids
        assert "entity-3" in entity_ids

    def test_sync_entity_to_fts_insert(self, sqlite_connection):
        """Test syncing entity to FTS (insert)."""
        store = FTSStore(sqlite_connection)
        store.create_fts_table(table_name="fts_test", columns=["title"])
        store.sync_entity_to_fts("fts_test", "entity-123", "new content")

        cursor = sqlite_connection.cursor()
        cursor.execute(
            "SELECT content FROM fts_test WHERE entity_id = ?", ("entity-123",)
        )
        row = cursor.fetchone()
        assert row[0] == "new content"

    def test_sync_entity_to_fts_update(self, sqlite_connection):
        """Test syncing entity to FTS (update)."""
        store = FTSStore(sqlite_connection)
        store.create_fts_table(table_name="fts_test", columns=["title"])
        store.insert_fts_entry("fts_test", "entity-123", "original content")
        store.sync_entity_to_fts("fts_test", "entity-123", "updated content")

        cursor = sqlite_connection.cursor()
        cursor.execute(
            "SELECT content FROM fts_test WHERE entity_id = ?", ("entity-123",)
        )
        row = cursor.fetchone()
        assert row[0] == "updated content"

    def test_fts_table_exists(self, sqlite_connection):
        """Test checking if FTS table exists."""
        store = FTSStore(sqlite_connection)
        store.create_fts_table(table_name="fts_test", columns=["title"])

        assert store.fts_table_exists("fts_test") is True
        assert store.fts_table_exists("nonexistent") is False

    def test_get_fts_tables_for_entity_type(self, sqlite_connection):
        """Test getting FTS tables for entity type."""
        store = FTSStore(sqlite_connection)
        store.create_fts_table(table_name="fts_sample_title", columns=["title"])
        store.create_fts_table(table_name="fts_sample_desc", columns=["description"])

        tables = store.get_fts_tables_for_entity_type("sample")
        assert len(tables) == 2
        assert "fts_sample_title" in tables
        assert "fts_sample_desc" in tables


@pytest.fixture
def sqlite_connection():
    """Create a test SQLite connection."""
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


class TestFTSStoreThreadRebinding:
    """Regression: _get_fts_store must re-bind to the caller's connection.

    Connections are thread-local. Before the fix, the adapter cached an
    FTSStore bound to the first thread's connection forever; FTS writes
    from any other thread then went through that foreign connection and
    were never committed, leaving the database permanently write-locked.
    """

    def test_get_fts_store_rebinds_to_new_connection(self, tmp_path):
        import sqlite3

        from tests.conftest import _build_minimal_schema_registry
        from mosaic.core.storage.adapters import SQLiteAdapter

        adapter = SQLiteAdapter(
            str(tmp_path / "rebind.db"),
            schema_registry=_build_minimal_schema_registry(),
        )
        conn_a = sqlite3.connect(":memory:")
        conn_b = sqlite3.connect(":memory:")
        store_a = adapter._get_fts_store(conn_a)
        store_b = adapter._get_fts_store(conn_b)
        assert store_a._conn is conn_a
        assert store_b._conn is conn_b
        adapter.close()

    def test_cross_thread_writes_do_not_wedge_database(self, tmp_path):
        import sqlite3
        import threading
        from pathlib import Path

        from mosaic.core.client import MosaicClient
        from mosaic.core.storage.adapters import SQLiteAdapter
        from mosaic.linkml_bridge import SchemaRegistry

        schema = (
            Path(__file__).parents[1] / "fixtures" / "schemas" / "sample_schema.yaml"
        )
        db_path = tmp_path / "threads.db"
        registry = SchemaRegistry.from_path(schema)
        storage = SQLiteAdapter(str(db_path), schema_registry=registry)
        client = MosaicClient(storage=storage, registry=registry)

        # First write on the main thread binds the (formerly sticky) store.
        client.create(entity_type="Project", data={"name": "Alpha"})

        # Second write from a worker thread uses a fresh thread-local
        # connection; its FTS rows must be committed on *that* connection.
        def worker() -> None:
            client.create(entity_type="Project", data={"name": "Beta"})

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        # The database must not be left write-locked by either thread.
        probe = sqlite3.connect(str(db_path), timeout=2)
        try:
            probe.execute("BEGIN IMMEDIATE")
            probe.rollback()
        finally:
            probe.close()
        storage.close()
