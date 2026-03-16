"""Tests for provenance immutability triggers."""

import os
import sqlite3
import tempfile

import pytest

from hippo.core.storage.adapters import SQLiteAdapter


class TestProvenanceImmutability:
    """Tests for database-level immutability of provenance records."""

    @pytest.fixture
    def db_path(self) -> "str":
        """Create a temporary database path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.join(tmpdir, "test.db")

    @pytest.fixture
    def adapter(self, db_path: str) -> SQLiteAdapter:
        """Create a SQLite adapter."""
        adapter = SQLiteAdapter(db_path, wal_mode=True)
        yield adapter
        adapter.close()

    @pytest.fixture
    def conn(self, adapter: SQLiteAdapter, db_path: str) -> "sqlite3.Connection":
        """Get a direct connection for testing triggers."""
        import sqlite3

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        yield conn
        conn.close()

    def test_primary_key_update_rejection(self, conn) -> None:
        """Test 4.1: Primary key update is rejected by database trigger."""
        cursor = conn.cursor()

        cursor.execute(
            """INSERT INTO provenance 
               (entity_id, entity_type, operation_type, timestamp, user_context, payload) 
               VALUES ('test-1', 'TestEntity', 'CREATE', '2024-01-01', 'test', '{}')"""
        )
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError) as exc_info:
            cursor.execute(
                "UPDATE provenance SET entity_id = 'new-id' WHERE entity_id = 'test-1'"
            )
            conn.commit()

        assert "primary key" in str(exc_info.value).lower()
        assert "Cannot update primary key" in str(exc_info.value)

    def test_timestamp_update_rejection(self, conn) -> None:
        """Test 4.2: Timestamp update is rejected by database trigger."""
        cursor = conn.cursor()

        cursor.execute(
            """INSERT INTO provenance 
               (entity_id, entity_type, operation_type, timestamp, user_context, payload) 
               VALUES ('test-2', 'TestEntity', 'CREATE', '2024-01-01', 'test', '{}')"""
        )
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError) as exc_info:
            cursor.execute(
                "UPDATE provenance SET timestamp = '2025-01-01' WHERE entity_id = 'test-2'"
            )
            conn.commit()

        assert "timestamp" in str(exc_info.value).lower()

    def test_metadata_update_rejection(self, conn) -> None:
        """Test 4.3: Metadata (user_context) update is rejected by database trigger."""
        cursor = conn.cursor()

        cursor.execute(
            """INSERT INTO provenance 
               (entity_id, entity_type, operation_type, timestamp, user_context, payload) 
               VALUES ('test-3', 'TestEntity', 'CREATE', '2024-01-01', 'original', '{}')"""
        )
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError) as exc_info:
            cursor.execute(
                "UPDATE provenance SET user_context = 'modified' WHERE entity_id = 'test-3'"
            )
            conn.commit()

        assert "user_context" in str(exc_info.value).lower()

    def test_content_update_rejection(self, conn) -> None:
        """Test 4.4: Content (payload) update is rejected by database trigger."""
        cursor = conn.cursor()

        cursor.execute(
            """INSERT INTO provenance 
               (entity_id, entity_type, operation_type, timestamp, user_context, payload) 
               VALUES ('test-4', 'TestEntity', 'CREATE', '2024-01-01', 'test', '{}')"""
        )
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError) as exc_info:
            cursor.execute(
                "UPDATE provenance SET payload = '{\"modified\": true}' WHERE entity_id = 'test-4'"
            )
            conn.commit()

        assert "payload" in str(exc_info.value).lower()

    def test_delete_rejection(self, conn) -> None:
        """Test 4.5: Delete is rejected by database trigger."""
        cursor = conn.cursor()

        cursor.execute(
            """INSERT INTO provenance 
               (entity_id, entity_type, operation_type, timestamp, user_context, payload) 
               VALUES ('test-5', 'TestEntity', 'CREATE', '2024-01-01', 'test', '{}')"""
        )
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError) as exc_info:
            cursor.execute("DELETE FROM provenance WHERE entity_id = 'test-5'")
            conn.commit()

        assert "delete" in str(exc_info.value).lower()

    def test_transaction_scoped_immutability(self, conn) -> None:
        """Test 4.6: Immutability is enforced within transaction scope."""
        cursor = conn.cursor()

        cursor.execute(
            """INSERT INTO provenance 
               (entity_id, entity_type, operation_type, timestamp, user_context, payload) 
               VALUES ('test-6', 'TestEntity', 'CREATE', '2024-01-01', 'test', '{}')"""
        )
        conn.commit()

        try:
            cursor.execute(
                "UPDATE provenance SET entity_id = 'new-id' WHERE entity_id = 'test-6'"
            )
            conn.commit()
            pytest.fail("Update should have been blocked")
        except sqlite3.IntegrityError:
            conn.rollback()

        cursor.execute("SELECT * FROM provenance WHERE entity_id = 'test-6'")
        row = cursor.fetchone()
        assert row is not None
        assert row["entity_id"] == "test-6"
