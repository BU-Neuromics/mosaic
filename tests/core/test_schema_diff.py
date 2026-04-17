"""Tests for SchemaDiffEngine against a LinkML-backed SchemaRegistry."""

import sqlite3
import tempfile
from pathlib import Path

from hippo.core.storage.schema_diff import (
    SchemaDiff,
    SchemaDiffEngine,
    TableMetadata,
)
from tests.support.linkml_schemas import build_registry


class TestSchemaDiffEngine:
    def test_load_existing_schema_reads_columns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute(
                'CREATE TABLE "test_table" (id TEXT PRIMARY KEY, name TEXT)'
            )
            engine = SchemaDiffEngine(cursor)
            engine.load_existing_schema(cursor)
            assert "test_table" in engine._existing_tables
            table = engine._existing_tables["test_table"]
            assert len(table.columns) == 2
            conn.close()

    def test_new_class_is_reported_as_new_table(self):
        reg = build_registry(
            {
                "new_entity": {
                    "attributes": {
                        "id": {"identifier": True},
                        "name": {"range": "string", "required": True},
                    }
                }
            }
        )
        engine = SchemaDiffEngine()
        engine._existing_tables = {}
        diff = engine.compute_diff(reg)
        assert diff.new_tables == ["new_entity"]

    def test_missing_slot_reported_as_new_column(self):
        existing = TableMetadata(
            name="existing_entity",
            columns=[
                {
                    "name": "id",
                    "type": "TEXT",
                    "not_null": True,
                    "default": None,
                    "primary_key": True,
                },
                {
                    "name": "name",
                    "type": "TEXT",
                    "not_null": False,
                    "default": None,
                    "primary_key": False,
                },
                {
                    "name": "is_available",
                    "type": "INTEGER",
                    "not_null": True,
                    "default": "1",
                    "primary_key": False,
                },
                {
                    "name": "superseded_by",
                    "type": "TEXT",
                    "not_null": False,
                    "default": None,
                    "primary_key": False,
                },
            ],
        )
        reg = build_registry(
            {
                "existing_entity": {
                    "attributes": {
                        "id": {"identifier": True},
                        "name": {"range": "string"},
                        "new_field": {"range": "string"},
                    }
                }
            }
        )
        engine = SchemaDiffEngine()
        engine._existing_tables = {"existing_entity": existing}
        diff = engine.compute_diff(reg)
        assert diff.new_tables == []
        assert "existing_entity" in diff.new_columns
        assert [s.name for s in diff.new_columns["existing_entity"]] == ["new_field"]

    def test_missing_index_reported(self):
        existing = TableMetadata(
            name="test_entity",
            columns=[
                {
                    "name": "id",
                    "type": "TEXT",
                    "not_null": True,
                    "default": None,
                    "primary_key": True,
                },
                {
                    "name": "name",
                    "type": "TEXT",
                    "not_null": False,
                    "default": None,
                    "primary_key": False,
                },
            ],
            indexes=[],
        )
        reg = build_registry(
            {
                "test_entity": {
                    "attributes": {
                        "id": {"identifier": True},
                        "name": {
                            "range": "string",
                            "annotations": {"hippo_index": True},
                        },
                    }
                }
            }
        )
        engine = SchemaDiffEngine()
        engine._existing_tables = {"test_entity": existing}
        diff = engine.compute_diff(reg)
        assert "test_entity" in diff.new_indexes
        assert diff.new_indexes["test_entity"][0]["name"] == "idx_test_entity_name"


class TestSchemaDiffDataclass:
    def test_default_fields(self):
        diff = SchemaDiff()
        assert diff.new_tables == []
        assert diff.new_columns == {}
        assert diff.new_indexes == {}
        assert diff.warnings == []
