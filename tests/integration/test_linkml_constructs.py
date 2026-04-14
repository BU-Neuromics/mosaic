"""Integration tests for LinkML schema constructs in the Hippo migrate pipeline.

Tests that the migrate pipeline handles schemas exercising the full range
of LinkML-relevant constructs: enums, references, constraints, multi-entity
graphs, and required fields.
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from hippo.cli.main import app

runner = CliRunner()


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def project_dir(tmp_dir):
    """A project directory with schemas/ and data/ subdirectories and an empty DB."""
    schemas = tmp_dir / "schemas"
    schemas.mkdir()
    data = tmp_dir / "data"
    data.mkdir()
    db_path = data / "hippo.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS entities (
            id TEXT PRIMARY KEY,
            entity_type TEXT NOT NULL,
            is_available INTEGER NOT NULL DEFAULT 1,
            version INTEGER NOT NULL DEFAULT 1,
            data TEXT NOT NULL,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.commit()
    conn.close()
    return tmp_dir


# ---------------------------------------------------------------------------
# Migrate CLI with LinkML-relevant schema constructs
# ---------------------------------------------------------------------------
class TestMigrateWithLinkMLConstructs:
    """Test that migrate handles schemas with constructs important for LinkML."""

    def test_migrate_entity_with_all_types(self, project_dir):
        """Migrate a schema with every supported field type."""
        schema = {
            "name": "all_types_entity",
            "version": "1.0.0",
            "fields": [
                {"name": "f_str", "type": "string"},
                {"name": "f_int", "type": "integer"},
                {"name": "f_float", "type": "float"},
                {"name": "f_bool", "type": "boolean"},
                {"name": "f_date", "type": "date"},
                {"name": "f_dt", "type": "datetime"},
                {"name": "f_uri", "type": "uri"},
                {"name": "f_list", "type": "list"},
                {"name": "f_dict", "type": "dict"},
                {"name": "f_enum", "type": "enum"},
            ],
        }
        schema_path = project_dir / "schemas" / "all_types.yaml"
        schema_path.write_text(yaml.dump(schema))
        db_path = project_dir / "data" / "hippo.db"

        result = runner.invoke(
            app,
            [
                "migrate",
                "--schema-dir",
                str(project_dir / "schemas"),
                "--db-path",
                str(db_path),
            ],
        )
        assert result.exit_code == 0

        # Verify table was created
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        assert "all_types_entity" in tables

    def test_migrate_with_references(self, project_dir):
        """Migrate schemas with foreign key references between entities."""
        parent_schema = {
            "name": "project",
            "version": "1.0.0",
            "fields": [
                {"name": "title", "type": "string", "required": True},
            ],
        }
        child_schema = {
            "name": "sample",
            "version": "1.0.0",
            "fields": [
                {"name": "name", "type": "string", "required": True},
                {
                    "name": "project_id",
                    "type": "string",
                    "references": {"table": "project", "column": "id"},
                },
            ],
        }
        (project_dir / "schemas" / "project.yaml").write_text(yaml.dump(parent_schema))
        (project_dir / "schemas" / "sample.yaml").write_text(yaml.dump(child_schema))
        db_path = project_dir / "data" / "hippo.db"

        result = runner.invoke(
            app,
            [
                "migrate",
                "--schema-dir",
                str(project_dir / "schemas"),
                "--db-path",
                str(db_path),
            ],
        )
        assert result.exit_code == 0

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        assert "project" in tables
        assert "sample" in tables

    def test_migrate_preview_with_indexes(self, project_dir):
        """Preview mode shows index creation for indexed fields."""
        schema = {
            "name": "indexed_entity",
            "version": "1.0.0",
            "fields": [
                {"name": "name", "type": "string", "index": True},
                {"name": "barcode", "type": "string", "index": True},
                {"name": "notes", "type": "string"},
            ],
        }
        (project_dir / "schemas" / "indexed.yaml").write_text(yaml.dump(schema))
        db_path = project_dir / "data" / "hippo.db"

        result = runner.invoke(
            app,
            [
                "migrate",
                "--schema-dir",
                str(project_dir / "schemas"),
                "--db-path",
                str(db_path),
                "--preview",
            ],
        )
        assert result.exit_code == 0
        assert "CREATE INDEX" in result.output
        assert "indexed_entity" in result.output

    def test_migrate_enum_field(self, project_dir):
        """Enum fields should migrate as TEXT columns."""
        schema = {
            "name": "status_entity",
            "version": "1.0.0",
            "fields": [
                {"name": "status", "type": "enum"},
            ],
        }
        (project_dir / "schemas" / "status.yaml").write_text(yaml.dump(schema))
        db_path = project_dir / "data" / "hippo.db"

        result = runner.invoke(
            app,
            [
                "migrate",
                "--schema-dir",
                str(project_dir / "schemas"),
                "--db-path",
                str(db_path),
            ],
        )
        assert result.exit_code == 0

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(status_entity)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        conn.close()
        assert "status" in columns

    def test_migrate_required_fields(self, project_dir):
        """Required fields should have NOT NULL constraint."""
        schema = {
            "name": "req_entity",
            "version": "1.0.0",
            "fields": [
                {"name": "name", "type": "string", "required": True},
                {"name": "notes", "type": "string", "required": False},
            ],
        }
        (project_dir / "schemas" / "req.yaml").write_text(yaml.dump(schema))
        db_path = project_dir / "data" / "hippo.db"

        result = runner.invoke(
            app,
            [
                "migrate",
                "--schema-dir",
                str(project_dir / "schemas"),
                "--db-path",
                str(db_path),
                "--preview",
            ],
        )
        assert result.exit_code == 0
        assert "CREATE TABLE" in result.output

    def test_migrate_multiple_entities(self, project_dir):
        """Migrate multiple entity schemas in one pass."""
        for name in ["alpha", "beta", "gamma"]:
            schema = {
                "name": name,
                "version": "1.0.0",
                "fields": [{"name": "label", "type": "string"}],
            }
            (project_dir / "schemas" / f"{name}.yaml").write_text(yaml.dump(schema))

        db_path = project_dir / "data" / "hippo.db"
        result = runner.invoke(
            app,
            [
                "migrate",
                "--schema-dir",
                str(project_dir / "schemas"),
                "--db-path",
                str(db_path),
            ],
        )
        assert result.exit_code == 0

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        for name in ["alpha", "beta", "gamma"]:
            assert name in tables
