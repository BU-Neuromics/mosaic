from tests.conftest import _build_minimal_schema_registry
"""Tests for SQLite WAL mode concurrent access."""

import os
import sqlite3
import tempfile
import threading
import time
from pathlib import Path

import pytest

from hippo.core.storage.adapters import SQLiteAdapter


class TestWALModeConcurrentAccess:
    """Tests for WAL mode concurrent read/write operations."""

    @pytest.fixture
    def db_path(self) -> "str":
        """Create a temporary database path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.join(tmpdir, "test.db")

    @pytest.fixture
    def adapter(self, db_path: str) -> SQLiteAdapter:
        """Create a SQLite adapter with WAL mode."""
        adapter = SQLiteAdapter(db_path, wal_mode=True, schema_registry=_build_minimal_schema_registry())
        yield adapter
        adapter.close()

    def test_wal_mode_enabled(self, db_path: str) -> None:
        """Test that WAL mode is enabled."""
        adapter = SQLiteAdapter(db_path, wal_mode=True, schema_registry=_build_minimal_schema_registry())
        mode = adapter.get_journal_mode()
        assert mode == "wal"
        adapter.close()

    def test_concurrent_reads_during_write_operations(self, db_path: str) -> None:
        """Test 2.1: Concurrent reads during write operations."""
        adapter = SQLiteAdapter(db_path, wal_mode=True, schema_registry=_build_minimal_schema_registry())

        class TestEntity:
            def __init__(self, id: str):
                self.id = id

        for i in range(20):
            entity = TestEntity(id=f"test-{i}")
            adapter.create(entity)

        read_results = []
        errors = []
        results_lock = threading.Lock()

        def reader():
            try:
                for _ in range(10):
                    result = adapter.read("test-1")
                    with results_lock:
                        read_results.append(result)
            except Exception as e:
                errors.append(str(e))

        def writer():
            try:
                for i in range(20, 30):
                    entity = TestEntity(id=f"test-{i}")
                    adapter.create(entity)
            except Exception as e:
                errors.append(str(e))

        threads = []
        for _ in range(2):
            t = threading.Thread(target=reader)
            threads.append(t)
        writer_thread = threading.Thread(target=writer)
        threads.append(writer_thread)

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0, f"Errors: {errors}"
        adapter.close()

    def test_multiple_readers_with_active_writer(self, db_path: str) -> None:
        """Test 2.2: Multiple readers with active writer."""
        adapter = SQLiteAdapter(db_path, wal_mode=True, schema_registry=_build_minimal_schema_registry())

        class TestEntity:
            def __init__(self, id: str):
                self.id = id

        write_started = threading.Event()
        write_done = threading.Event()
        read_count = [0]
        count_lock = threading.Lock()
        errors = []

        def writer():
            write_started.set()
            for i in range(30):
                entity = TestEntity(id=f"entity-{i}")
                adapter.create(entity)
            write_done.set()

        def reader():
            write_started.wait(timeout=5)
            while not write_done.is_set():
                try:
                    list(adapter.findAll())
                    with count_lock:
                        read_count[0] += 1
                except Exception as e:
                    errors.append(str(e))

        threads = []
        writer_thread = threading.Thread(target=writer)
        threads.append(writer_thread)

        for _ in range(3):
            t = threading.Thread(target=reader)
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0, f"Errors: {errors}"
        assert read_count[0] > 0, "No reads completed"
        adapter.close()

    def test_no_blocking_between_read_write(self, db_path: str) -> None:
        """Test 2.3: Verify no blocking occurs between read/write operations."""
        adapter = SQLiteAdapter(db_path, wal_mode=True, schema_registry=_build_minimal_schema_registry())

        class TestEntity:
            def __init__(self, id: str):
                self.id = id

        timings = {"read": [], "write": []}
        errors = []

        def writer():
            for i in range(15):
                start = time.time()
                entity = TestEntity(id=f"write-{i}")
                adapter.create(entity)
                timings["write"].append(time.time() - start)

        def reader():
            for i in range(15):
                start = time.time()
                adapter.read(f"write-{i}")
                timings["read"].append(time.time() - start)

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert len(errors) == 0, f"Errors: {errors}"
        avg_read_time = (
            sum(timings["read"]) / len(timings["read"]) if timings["read"] else 0
        )
        avg_write_time = (
            sum(timings["write"]) / len(timings["write"]) if timings["write"] else 0
        )

        assert avg_read_time < 2.0, f"Read took too long: {avg_read_time}"
        assert avg_write_time < 2.0, f"Write took too long: {avg_write_time}"
        adapter.close()

    def test_checkpoint_operations_execute(self, db_path: str) -> None:
        """Test 3.1: Verify checkpoint operations execute correctly."""
        adapter = SQLiteAdapter(db_path, wal_mode=True, schema_registry=_build_minimal_schema_registry())

        class TestEntity:
            def __init__(self, id: str):
                self.id = id

        for i in range(50):
            entity = TestEntity(id=f"entity-{i}")
            adapter.create(entity)

        result = adapter.checkpoint()
        assert result is not None
        adapter.close()

    def test_wal_file_created(self, db_path: str) -> None:
        """Test 3.2: Verify WAL file is created after writes."""
        adapter = SQLiteAdapter(db_path, wal_mode=True, schema_registry=_build_minimal_schema_registry())

        class TestEntity:
            def __init__(self, id: str):
                self.id = id

        wal_path = Path(db_path).with_suffix(".db-wal")

        for i in range(10):
            entity = TestEntity(id=f"entity-{i}")
            adapter.create(entity)

        time.sleep(0.1)

        assert wal_path.exists(), "WAL file should exist after writes"
        adapter.close()

    def test_data_persists_across_connections(self, db_path: str) -> None:
        """Test 3.3: Verify data persists correctly across connections."""

        class TestEntity:
            def __init__(self, id: str):
                self.id = id

        adapter1 = SQLiteAdapter(db_path, wal_mode=True, schema_registry=_build_minimal_schema_registry())
        entity = TestEntity(id="persist-test")
        adapter1.create(entity)
        adapter1.close()

        adapter2 = SQLiteAdapter(db_path, wal_mode=True, schema_registry=_build_minimal_schema_registry())
        read_entity = adapter2.read("persist-test")
        assert read_entity is not None
        adapter2.close()

    def test_wal_checkpoint_truncation(self, db_path: str) -> None:
        """Test WAL checkpoint truncates WAL file."""

        class TestEntity:
            def __init__(self, id: str):
                self.id = id

        adapter = SQLiteAdapter(db_path, wal_mode=True, schema_registry=_build_minimal_schema_registry())

        for i in range(100):
            entity = TestEntity(id=f"entity-{i}")
            adapter.create(entity)

        time.sleep(0.1)

        size_before = adapter.get_wal_file_size()
        assert size_before > 0, "WAL file should have content"

        adapter.checkpoint()

        time.sleep(0.2)

        size_after = adapter.get_wal_file_size()
        adapter.close()

        assert size_before >= size_after, (
            "WAL file should be truncated after checkpoint"
        )


class TestWALModeDirectSQL:
    """Tests for WAL mode using direct SQL connections."""

    @pytest.fixture
    def db_path(self) -> str:
        """Create a temporary database path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.join(tmpdir, "test_direct.db")

    def test_wal_pragma_execution(self, db_path: str) -> None:
        """Test that WAL PRAGMA is correctly executed."""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("PRAGMA journal_mode=WAL")
        mode = cursor.fetchone()[0]
        conn.close()

        assert mode == "wal"

    def test_concurrent_wal_connections(self, db_path: str) -> None:
        """Test concurrent connections with WAL mode."""
        conn = sqlite3.connect(db_path, timeout=30.0, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS test (id TEXT PRIMARY KEY, value TEXT)"
        )
        conn.close()

        errors = []
        results = []

        def write_task(task_id):
            try:
                conn = sqlite3.connect(db_path, timeout=30.0, isolation_level=None)
                conn.execute("PRAGMA journal_mode=WAL")
                for i in range(5):
                    conn.execute(
                        "INSERT OR REPLACE INTO test VALUES (?, ?)",
                        (f"id-{task_id}-{i}", f"value-{i}"),
                    )
                conn.close()
            except Exception as e:
                errors.append(str(e))

        def read_task(task_id):
            try:
                conn = sqlite3.connect(db_path, timeout=30.0, isolation_level=None)
                conn.execute("PRAGMA journal_mode=WAL")
                for _ in range(5):
                    cursor = conn.execute("SELECT COUNT(*) FROM test")
                    count = cursor.fetchone()[0]
                    results.append(count)
                conn.close()
            except Exception as e:
                errors.append(str(e))

        threads = []
        for i in range(3):
            t = threading.Thread(target=write_task, args=(i,))
            threads.append(t)
        for i in range(2):
            t = threading.Thread(target=read_task, args=(i,))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert len(errors) == 0, f"Errors: {errors}"
        assert len(results) > 0, "No reads completed"
