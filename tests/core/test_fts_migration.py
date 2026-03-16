"""Tests for FTS migration functionality."""

import pytest
from hippo.config.models import FieldDefinition, SchemaConfig
from hippo.core.storage.ddl_generator import FTSMigrationPlanner
from hippo.core.storage.migration import MigrationPlanner, MigrationExecutor


class TestFTSMigrationPlanner:
    """Tests for FTS migration planner."""

    def test_add_schema_with_fts_fields(self):
        """Test adding schema with FTS fields."""
        planner = FTSMigrationPlanner()
        schema = SchemaConfig(
            name="Sample",
            version="1.0",
            fields=[
                FieldDefinition(name="id", type="string", primary_key=True),
                FieldDefinition(name="title", type="string", search="fts5"),
                FieldDefinition(name="description", type="string", search="fts"),
            ],
        )

        planner.add_schema(schema)
        all_tables = planner.get_all_fts_tables()

        assert "Sample" in all_tables
        assert len(all_tables["Sample"]) == 2

    def test_get_fts_tables_for_entity_type(self):
        """Test getting FTS tables for entity type."""
        planner = FTSMigrationPlanner()
        schema = SchemaConfig(
            name="Sample",
            version="1.0",
            fields=[
                FieldDefinition(name="title", type="string", search="fts5"),
            ],
        )

        planner.add_schema(schema)
        tables = planner.get_fts_tables_for_entity_type("Sample")

        assert len(tables) == 1
        assert tables[0].table_name == "fts_sample_title"

    def test_generate_fts_ddl(self):
        """Test generating FTS DDL statements."""
        planner = FTSMigrationPlanner()
        schema = SchemaConfig(
            name="Sample",
            version="1.0",
            fields=[
                FieldDefinition(name="title", type="string", search="fts5"),
            ],
        )

        planner.add_schema(schema)
        ddl_statements = planner.generate_fts_ddl()

        assert len(ddl_statements) == 1
        assert "CREATE VIRTUAL TABLE" in ddl_statements[0]
        assert "fts_sample_title" in ddl_statements[0]


class TestMigrationPlanner:
    """Tests for migration planner."""

    def test_plan_migration_with_fts(self, sqlite_connection):
        """Test planning migration with FTS tables."""
        planner = MigrationPlanner()

        cursor = sqlite_connection.cursor()
        planner.load_existing_tables(cursor)
        planner.load_existing_fts_tables(cursor)

        schema = SchemaConfig(
            name="Sample",
            version="1.0",
            fields=[
                FieldDefinition(name="id", type="string", primary_key=True),
                FieldDefinition(name="title", type="string", search="fts5"),
            ],
        )

        plan = planner.plan_migration([schema])

        assert len(plan.fts_ddl_statements) > 0
        assert len(plan.backfill_tasks) > 0


class TestMigrationExecutor:
    """Tests for migration executor."""

    def test_execute_migration_creates_fts_tables(self, sqlite_connection):
        """Test executing migration creates FTS tables."""
        executor = MigrationExecutor(sqlite_connection)

        planner = MigrationPlanner()
        cursor = sqlite_connection.cursor()
        planner.load_existing_tables(cursor)
        planner.load_existing_fts_tables(cursor)

        schema = SchemaConfig(
            name="Sample",
            version="1.0",
            fields=[
                FieldDefinition(name="id", type="string", primary_key=True),
                FieldDefinition(name="title", type="string", search="fts5"),
            ],
        )

        plan = planner.plan_migration([schema])
        result = executor.execute_migration(plan)

        assert result.success is True
        assert len(result.fts_tables_created) > 0

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'fts_%'"
        )
        tables = cursor.fetchall()
        assert len(tables) > 0


class TestBatchedFunction:
    """Tests for batched utility function."""

    def test_batched_basic(self):
        """Test basic batching."""
        from hippo.core.storage.migration import batched

        result = list(batched([1, 2, 3, 4, 5], 2))
        assert result == [[1, 2], [3, 4], [5]]

    def test_batched_exact_batch(self):
        """Test batching with exact multiple."""
        from hippo.core.storage.migration import batched

        result = list(batched([1, 2, 3, 4], 2))
        assert result == [[1, 2], [3, 4]]

    def test_batched_single_item(self):
        """Test batching single item."""
        from hippo.core.storage.migration import batched

        result = list(batched([1], 2))
        assert result == [[1]]


@pytest.fixture
def sqlite_connection():
    """Create a test SQLite connection."""
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()
