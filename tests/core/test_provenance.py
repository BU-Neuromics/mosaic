"""Tests for provenance tracking in SQLite adapter."""

import json
import os
import sqlite3
import tempfile

import pytest

from hippo.core.storage.adapters import SQLiteAdapter


class TestEntity:
    """Test entity for provenance tests."""

    def __init__(self, id: str, name: str = None):
        self.id = id
        self.name = name


class TestProvenanceTracking:
    """Tests for provenance event generation."""

    @pytest.fixture
    def db_path(self) -> str:
        """Create a temporary database path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.join(tmpdir, "test_provenance.db")

    @pytest.fixture
    def adapter(self, db_path: str) -> SQLiteAdapter:
        """Create a SQLite adapter."""
        adapter = SQLiteAdapter(db_path, wal_mode=True)
        yield adapter
        adapter.close()

    def _get_provenance_records(
        self, db_path: str, entity_id: str = None
    ) -> list[dict]:
        """Helper to retrieve ProvenanceRecord rows with legacy-shape dicts.

        Queries the sec9 §9.6 ProvenanceRecord table but aliases columns
        back to the legacy names (``operation`` → ``operation_type``,
        ``actor_id`` → ``user_context``, ``patch`` → ``payload``) so
        existing assertions continue to work during the transition. The
        legacy-only ``CREATE`` / ``SOFT_DELETE`` operation strings are
        also re-mapped to the new enum values at the assertion layer.
        """
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        legacy_map = {
            "create": "CREATE",
            "update": "UPDATE",
            "availability_change": "SOFT_DELETE",
            "supersede": "SUPERSEDE",
            "relationship_add": "RELATE",
            "relationship_remove": "UNRELATE",
        }

        if entity_id:
            cursor.execute(
                'SELECT id, entity_id, entity_type, operation, actor_id, '
                'timestamp, patch FROM "ProvenanceRecord" '
                "WHERE entity_id = ? ORDER BY timestamp",
                (entity_id,),
            )
        else:
            cursor.execute(
                'SELECT id, entity_id, entity_type, operation, actor_id, '
                'timestamp, patch FROM "ProvenanceRecord" '
                "ORDER BY timestamp"
            )

        results = []
        for row in cursor.fetchall():
            actor = row[4]
            if actor == "unknown":
                actor = None
            results.append(
                {
                    "operation_id": row[0],
                    "entity_id": row[1],
                    "entity_type": row[2],
                    "operation_type": legacy_map.get(row[3], row[3]),
                    "user_context": actor,
                    "timestamp": row[5],
                    "payload": row[6],
                    "previous_state_hash": None,
                    "state_snapshot": row[6],
                }
            )
        conn.close()
        return results

    def test_create_provenance_event_generation(self, db_path: str) -> None:
        """Test 5.1: CREATE provenance event generation."""
        adapter = SQLiteAdapter(db_path, wal_mode=True)

        entity = TestEntity(id="test-entity-1", name="Test Entity")
        adapter.create(entity)

        records = self._get_provenance_records(db_path, "test-entity-1")

        assert len(records) == 1
        record = records[0]
        assert record["entity_id"] == "test-entity-1"
        assert record["entity_type"] == "TestEntity"
        assert record["operation_type"] == "CREATE"
        assert record["user_context"] is None
        payload = json.loads(record["payload"])
        assert payload["id"] == "test-entity-1"

        adapter.close()

    def test_soft_delete_provenance_with_original_data(self, db_path: str) -> None:
        """Test 5.2: SOFT_DELETE provenance event with original data preservation."""
        adapter = SQLiteAdapter(db_path, wal_mode=True)

        entity = TestEntity(id="test-entity-2", name="To Be Deleted")
        adapter.create(entity)

        deleted = adapter.delete("test-entity-2")
        assert deleted is True

        records = self._get_provenance_records(db_path, "test-entity-2")

        assert len(records) == 2

        record_types = {r["operation_type"] for r in records}
        assert "CREATE" in record_types
        assert "SOFT_DELETE" in record_types

        delete_record = [r for r in records if r["operation_type"] == "SOFT_DELETE"][0]
        # sec9 §9.6: availability_change patches carry status + data.
        # The original entity snapshot rides under patch.data during the transition.
        patch = json.loads(delete_record["payload"])
        assert patch["status"] == "deleted"
        assert patch["is_available"] is False
        assert patch["data"]["id"] == "test-entity-2"

        adapter.close()

    def test_transaction_bound_provenance_events(self, db_path: str) -> None:
        """Test 5.3: Integration test for transaction-bound provenance events."""
        adapter = SQLiteAdapter(db_path, wal_mode=True)

        entity = TestEntity(id="test-entity-3", name="Transaction Test")
        adapter.create(entity)

        deleted = adapter.delete("test-entity-3")
        assert deleted is True

        records = self._get_provenance_records(db_path, "test-entity-3")

        assert len(records) == 2
        for record in records:
            assert record["entity_id"] == "test-entity-3"

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM entities WHERE id = ?", ("test-entity-3",))
        row = cursor.fetchone()
        conn.close()

        assert row is not None

        adapter.close()

    def test_user_context_inclusion(self, db_path: str) -> None:
        """Test 5.4: User context inclusion in provenance records."""
        adapter = SQLiteAdapter(db_path, wal_mode=True)

        entity = TestEntity(id="test-entity-4", name="User Context Test")
        adapter.create(entity, user_context="test-user@example.com")

        records = self._get_provenance_records(db_path, "test-entity-4")

        assert len(records) == 1
        assert records[0]["user_context"] == "test-user@example.com"

        adapter.delete("test-entity-4", user_context="admin@example.com")

        records = self._get_provenance_records(db_path, "test-entity-4")

        assert len(records) == 2
        delete_record = [r for r in records if r["operation_type"] == "SOFT_DELETE"][0]
        assert delete_record["user_context"] == "admin@example.com"

        adapter.close()

    def test_provenance_indexes_exist(self, db_path: str) -> None:
        """Test that ProvenanceRecord indexes are created (sec9 §9.6 names)."""
        adapter = SQLiteAdapter(db_path, wal_mode=True)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name LIKE 'idx_ProvenanceRecord_%'"
        )
        indexes = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert "idx_ProvenanceRecord_entity_id" in indexes
        assert "idx_ProvenanceRecord_operation" in indexes
        assert "idx_ProvenanceRecord_timestamp" in indexes

        adapter.close()

    def test_provenance_table_schema(self, db_path: str) -> None:
        """Test that ProvenanceRecord table has the sec9 §9.6 column shape."""
        adapter = SQLiteAdapter(db_path, wal_mode=True)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute('PRAGMA table_info("ProvenanceRecord")')
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        conn.close()

        for col in (
            "id",
            "entity_id",
            "entity_type",
            "operation",
            "actor_id",
            "timestamp",
            "schema_version",
            "derived_from_id",
            "process_id",
            "patch",
            "context",
        ):
            assert col in columns, f"column {col!r} missing from ProvenanceRecord"

        adapter.close()

    def test_composite_index_exists(self, db_path: str) -> None:
        """Test that composite index on (entity_id, timestamp) exists."""
        adapter = SQLiteAdapter(db_path, wal_mode=True)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name='idx_ProvenanceRecord_entity_timestamp'"
        )
        result = cursor.fetchone()
        conn.close()

        assert result is not None

        adapter.close()


class TestHistoryMethods:
    """Tests for history() and state_at() methods."""

    @pytest.fixture
    def db_path(self) -> str:
        """Create a temporary database path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.join(tmpdir, "test_history.db")

    @pytest.fixture
    def adapter(self, db_path: str) -> SQLiteAdapter:
        """Create a SQLite adapter."""
        adapter = SQLiteAdapter(db_path, wal_mode=True)
        yield adapter
        adapter.close()

    def test_history_returns_chronological_order(self, db_path: str) -> None:
        """Test 5.2: history() returns records in chronological order."""
        adapter = SQLiteAdapter(db_path, wal_mode=True)

        from hippo.core.storage.adapters.sqlite_adapter import SQLiteEntity
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()

        entity = SQLiteEntity(
            id="history-test-1",
            entity_type="TestEntity",
            is_available=True,
            version=1,
            data={"name": "Version 1"},
        )
        adapter.create(entity)

        entity2 = SQLiteEntity(
            id="history-test-1",
            entity_type="TestEntity",
            is_available=True,
            version=2,
            data={"name": "Version 2"},
        )
        with adapter._transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE entities SET data = ?, version = ?
                   WHERE id = ? AND is_available = 1""",
                ('{"name": "Version 2"}', 2, "history-test-1"),
            )
            provenance = adapter._get_provenance_store(conn)
            provenance.record(
                entity_id="history-test-1",
                entity_type="TestEntity",
                operation_type="UPDATE",
                user_context=None,
                payload={"name": "Version 2"},
            )

        history = adapter.history("history-test-1")

        assert len(history) == 2
        # sec9 §9.6 Operation enum values (lowercase)
        assert history[0]["operation_type"] == "create"
        assert history[1]["operation_type"] == "update"

        for record in history:
            # operation_id is the record's UUID under the sec9 shape
            assert record["operation_id"] is not None
            # previous_state_hash was dropped in sec9 §9.6 — always None
            assert record["previous_state_hash"] is None

        adapter.close()

    def test_state_at_returns_correct_state(self, db_path: str) -> None:
        """Test 5.3: state_at() returns entity state at specified time."""
        adapter = SQLiteAdapter(db_path, wal_mode=True)

        from hippo.core.storage.adapters.sqlite_adapter import SQLiteEntity
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        time1 = now.isoformat()

        entity = SQLiteEntity(
            id="state-test-1",
            entity_type="TestEntity",
            is_available=True,
            version=1,
            data={"name": "Initial"},
        )
        adapter.create(entity)

        history = adapter.history("state-test-1")
        create_timestamp = history[0]["timestamp"]

        time2 = (now.replace(second=now.second + 1)).isoformat()

        with adapter._transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE entities SET data = ?, version = ?
                   WHERE id = ? AND is_available = 1""",
                ('{"name": "Updated"}', 2, "state-test-1"),
            )
            provenance = adapter._get_provenance_store(conn)
            provenance.record(
                entity_id="state-test-1",
                entity_type="TestEntity",
                operation_type="UPDATE",
                user_context=None,
                payload={"name": "Updated"},
            )

        state_at_create = adapter.state_at("state-test-1", create_timestamp)

        assert state_at_create is not None
        assert state_at_create["state"]["name"] == "Initial"

        state_at_update = adapter.state_at("state-test-1", time2)

        assert state_at_update is not None
        assert state_at_update["state"]["name"] == "Updated"

        adapter.close()

    def test_state_at_before_creation_raises_error(self, db_path: str) -> None:
        """Test 5.4: state_at() raises TemporalQueryError for timestamp before creation."""
        from hippo.core.exceptions import TemporalQueryError

        adapter = SQLiteAdapter(db_path, wal_mode=True)

        from hippo.core.storage.adapters.sqlite_adapter import SQLiteEntity
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)
        time1 = now.isoformat()

        entity = SQLiteEntity(
            id="error-test-1",
            entity_type="TestEntity",
            is_available=True,
            version=1,
            data={"name": "Test"},
        )
        adapter.create(entity)

        before_creation = (now - timedelta(days=1)).isoformat()

        with pytest.raises(TemporalQueryError) as exc_info:
            adapter.state_at("error-test-1", before_creation)

        assert "before entity creation" in str(exc_info.value.message).lower()

        adapter.close()

    def test_state_at_none_for_deleted_entity(self, db_path: str) -> None:
        """Test that state_at() returns None for deleted entities at deletion time."""
        adapter = SQLiteAdapter(db_path, wal_mode=True)

        from hippo.core.storage.adapters.sqlite_adapter import SQLiteEntity
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)
        time1 = now.isoformat()

        entity = SQLiteEntity(
            id="delete-test-1",
            entity_type="TestEntity",
            is_available=True,
            version=1,
            data={"name": "To Delete"},
        )
        adapter.create(entity)

        time_after_create = (
            datetime.now(timezone.utc) + timedelta(milliseconds=10)
        ).isoformat()

        adapter.delete("delete-test-1")

        state = adapter.state_at("delete-test-1", time_after_create)
        assert state is None

        adapter.close()


class TestHistoryClientAPI:
    """Tests for HippoClient history() and state_at() methods."""

    @pytest.fixture
    def db_path(self) -> str:
        """Create a temporary database path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.join(tmpdir, "test_client_history.db")

    @pytest.fixture
    def client(self, db_path: str):
        """Create a HippoClient with SQLite storage."""
        from hippo.core.client import HippoClient
        from hippo.core.storage.adapters import SQLiteAdapter

        adapter = SQLiteAdapter(db_path, wal_mode=True)
        client = HippoClient(storage=adapter)
        yield client
        adapter.close()

    def test_client_history(self, client) -> None:
        """Test 5.2: HippoClient.history() returns entity history."""
        result = client.put("SampleEntity", {"name": "Test Entity"})
        entity_id = result["id"]

        history = client.history(entity_id)

        assert len(history) >= 1
        # sec9 §9.6 Operation enum values (lowercase)
        assert history[0]["operation_type"] == "create"

    def test_client_state_at(self, client) -> None:
        """Test 5.3: HippoClient.state_at() returns entity state at time."""
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)

        result = client.put("SampleEntity", {"name": "Initial"})
        entity_id = result["id"]

        after_create = datetime.now(timezone.utc).isoformat()

        state_result = client.state_at(entity_id, after_create)

        assert state_result is not None
        assert state_result["state"]["name"] == "Initial"

    def test_client_state_at_before_creation_error(self, client) -> None:
        """Test 5.4: HippoClient.state_at() raises error for timestamp before creation."""
        from hippo.core.exceptions import TemporalQueryError
        from datetime import datetime, timezone, timedelta

        result = client.put("ErrorEntity", {"name": "Test"})
        entity_id = result["id"]

        before_creation = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

        with pytest.raises(TemporalQueryError):
            client.state_at(entity_id, before_creation)

    def test_client_history_not_found(self, client) -> None:
        """Test that HippoClient.history() raises error for non-existent entity."""
        from hippo.core.exceptions import EntityNotFoundError

        with pytest.raises(EntityNotFoundError):
            client.history("non-existent-id")
