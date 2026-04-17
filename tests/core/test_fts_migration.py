"""Tests for FTS migration functionality."""

import pytest

from hippo.core.storage.ddl_generator import FTSMigrationPlanner
from hippo.core.storage.migration import MigrationExecutor, MigrationPlanner
from tests.support.linkml_schemas import build_registry


class TestFTSMigrationPlanner:
    def test_add_class_registers_fts_tables(self):
        reg = build_registry(
            {
                "Sample": {
                    "attributes": {
                        "id": {"identifier": True},
                        "title": {
                            "range": "string",
                            "annotations": {"hippo_search": "fts5"},
                        },
                        "description": {
                            "range": "string",
                            "annotations": {"hippo_search": "fts"},
                        },
                    }
                }
            }
        )
        planner = FTSMigrationPlanner()
        planner.add_class(reg, "Sample")
        all_tables = planner.get_all_fts_tables()
        assert "Sample" in all_tables
        assert len(all_tables["Sample"]) == 2

    def test_get_fts_tables_for_entity_type(self):
        reg = build_registry(
            {
                "Sample": {
                    "attributes": {
                        "id": {"identifier": True},
                        "title": {
                            "range": "string",
                            "annotations": {"hippo_search": "fts5"},
                        },
                    }
                }
            }
        )
        planner = FTSMigrationPlanner()
        planner.add_class(reg, "Sample")
        tables = planner.get_fts_tables_for_entity_type("Sample")
        assert len(tables) == 1
        assert tables[0].table_name == "fts_sample_title"

    def test_generate_fts_ddl(self):
        reg = build_registry(
            {
                "Sample": {
                    "attributes": {
                        "id": {"identifier": True},
                        "title": {
                            "range": "string",
                            "annotations": {"hippo_search": "fts5"},
                        },
                    }
                }
            }
        )
        planner = FTSMigrationPlanner()
        planner.add_class(reg, "Sample")
        ddl = planner.generate_fts_ddl()
        assert len(ddl) == 1
        assert "CREATE VIRTUAL TABLE" in ddl[0]
        assert "fts_sample_title" in ddl[0]


class TestMigrationPlanner:
    def test_plan_includes_fts(self, sqlite_connection):
        reg = build_registry(
            {
                "Sample": {
                    "attributes": {
                        "id": {"identifier": True},
                        "title": {
                            "range": "string",
                            "annotations": {"hippo_search": "fts5"},
                        },
                    }
                }
            }
        )
        planner = MigrationPlanner()
        cursor = sqlite_connection.cursor()
        planner.load_existing_fts_tables(cursor)
        plan = planner.plan_migration(reg)
        assert len(plan.fts_ddl_statements) > 0
        assert len(plan.backfill_tasks) > 0


class TestMigrationExecutor:
    def test_execute_migration_creates_fts_tables(self, sqlite_connection):
        reg = build_registry(
            {
                "Sample": {
                    "attributes": {
                        "id": {"identifier": True},
                        "title": {
                            "range": "string",
                            "annotations": {"hippo_search": "fts5"},
                        },
                    }
                }
            }
        )
        executor = MigrationExecutor(sqlite_connection)
        planner = MigrationPlanner()
        cursor = sqlite_connection.cursor()
        planner.load_existing_fts_tables(cursor)
        plan = planner.plan_migration(reg)
        result = executor.execute_migration(plan)
        assert result.success is True
        assert len(result.fts_tables_created) > 0
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'fts_%'"
        )
        assert len(cursor.fetchall()) > 0


class TestBatchedFunction:
    def test_batched_basic(self):
        from hippo.core.storage.migration import batched

        assert list(batched([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]

    def test_batched_exact_batch(self):
        from hippo.core.storage.migration import batched

        assert list(batched([1, 2, 3, 4], 2)) == [[1, 2], [3, 4]]

    def test_batched_single_item(self):
        from hippo.core.storage.migration import batched

        assert list(batched([1], 2)) == [[1]]


@pytest.fixture
def sqlite_connection():
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()
