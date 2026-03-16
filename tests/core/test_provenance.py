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
        """Helper to retrieve provenance records directly from DB."""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        if entity_id:
            cursor.execute(
                "SELECT * FROM provenance WHERE entity_id = ? ORDER BY timestamp",
                (entity_id,),
            )
        else:
            cursor.execute("SELECT * FROM provenance ORDER BY timestamp")

        columns = [desc[0] for desc in cursor.description]
        results = []
        for row in cursor.fetchall():
            results.append(dict(zip(columns, row)))
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
        payload = json.loads(delete_record["payload"])
        assert payload["id"] == "test-entity-2"

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
        """Test that provenance indexes are created."""
        adapter = SQLiteAdapter(db_path, wal_mode=True)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_provenance_%'"
        )
        indexes = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert "idx_provenance_entity_id" in indexes
        assert "idx_provenance_operation_type" in indexes
        assert "idx_provenance_timestamp" in indexes

        adapter.close()

    def test_provenance_table_schema(self, db_path: str) -> None:
        """Test that provenance table has correct schema."""
        adapter = SQLiteAdapter(db_path, wal_mode=True)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(provenance)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        conn.close()

        assert "entity_id" in columns
        assert "entity_type" in columns
        assert "operation_type" in columns
        assert "timestamp" in columns
        assert "user_context" in columns
        assert "payload" in columns

        adapter.close()

    def test_provenance_new_columns_exist(self, db_path: str) -> None:
        """Test that new provenance columns exist (operation_id, previous_state_hash, state_snapshot)."""
        adapter = SQLiteAdapter(db_path, wal_mode=True)

        entity = TestEntity(id="test-entity-new", name="New Columns Test")
        adapter.create(entity)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(provenance)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()

        assert "operation_id" in columns
        assert "previous_state_hash" in columns
        assert "state_snapshot" in columns

        adapter.close()

    def test_provenance_operation_id_generation(self, db_path: str) -> None:
        """Test that operation_id is generated for each provenance record."""
        adapter = SQLiteAdapter(db_path, wal_mode=True)

        entity = TestEntity(id="test-op-id", name="Operation ID Test")
        adapter.create(entity)

        records = self._get_provenance_records(db_path, "test-op-id")

        assert len(records) == 1
        assert records[0]["operation_id"] is not None

        import uuid

        uuid.UUID(records[0]["operation_id"])

        adapter.close()

    def test_provenance_state_hash_computation(self, db_path: str) -> None:
        """Test that previous_state_hash is computed using SHA-256."""
        import hashlib

        adapter = SQLiteAdapter(db_path, wal_mode=True)

        entity = TestEntity(id="test-hash", name="Hash Test")
        adapter.create(entity)

        records = self._get_provenance_records(db_path, "test-hash")

        assert records[0]["previous_state_hash"] is not None
        assert len(records[0]["previous_state_hash"]) == 64

        expected_hash = hashlib.sha256(
            json.dumps(
                {"id": "test-hash", "name": "Hash Test"}, sort_keys=True
            ).encode()
        ).hexdigest()
        assert records[0]["previous_state_hash"] == expected_hash

        adapter.close()

    def test_provenance_state_snapshot(self, db_path: str) -> None:
        """Test that state_snapshot is recorded."""
        adapter = SQLiteAdapter(db_path, wal_mode=True)

        entity = TestEntity(id="test-snapshot", name="Snapshot Test")
        adapter.create(entity)

        records = self._get_provenance_records(db_path, "test-snapshot")

        assert records[0]["state_snapshot"] is not None
        snapshot = json.loads(records[0]["state_snapshot"])
        assert snapshot["id"] == "test-snapshot"
        assert snapshot["name"] == "Snapshot Test"

        adapter.close()

    def test_composite_index_exists(self, db_path: str) -> None:
        """Test that composite index on (entity_id, timestamp) exists."""
        adapter = SQLiteAdapter(db_path, wal_mode=True)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_provenance_entity_timestamp'"
        )
        result = cursor.fetchone()
        conn.close()

        assert result is not None
        assert result[0] == "idx_provenance_entity_timestamp"

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
            created_at=now,
            updated_at=now,
        )
        adapter.create(entity)

        entity2 = SQLiteEntity(
            id="history-test-1",
            entity_type="TestEntity",
            is_available=True,
            version=2,
            data={"name": "Version 2"},
            created_at=now,
            updated_at=now,
        )
        with adapter._transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE entities SET data = ?, version = ?, updated_at = ?
                   WHERE id = ? AND is_available = 1""",
                ('{"name": "Version 2"}', 2, now, "history-test-1"),
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
        assert history[0]["operation_type"] == "CREATE"
        assert history[1]["operation_type"] == "UPDATE"

        for record in history:
            assert record["operation_id"] is not None
            assert record["previous_state_hash"] is not None

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
            created_at=time1,
            updated_at=time1,
        )
        adapter.create(entity)

        history = adapter.history("state-test-1")
        create_timestamp = history[0]["timestamp"]

        time2 = (now.replace(second=now.second + 1)).isoformat()

        with adapter._transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE entities SET data = ?, version = ?, updated_at = ?
                   WHERE id = ? AND is_available = 1""",
                ('{"name": "Updated"}', 2, time2, "state-test-1"),
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
            created_at=time1,
            updated_at=time1,
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
            created_at=time1,
            updated_at=time1,
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
        assert history[0]["operation_type"] == "CREATE"

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
