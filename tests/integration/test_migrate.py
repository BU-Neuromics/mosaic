import sqlite3
import tempfile
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from hippo.cli.main import app

runner = CliRunner()


@pytest.fixture
def temp_project_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir) / "test_project"
        project_dir.mkdir()

        data_dir = project_dir / "data"
        data_dir.mkdir()

        db_path = data_dir / "hippo.db"
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
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_entity (
                id TEXT PRIMARY KEY,
                name TEXT,
                is_available INTEGER NOT NULL DEFAULT 1
            )
        """)
        conn.commit()
        conn.close()

        yield project_dir


@pytest.fixture
def schema_dir(temp_project_dir):
    schemas_dir = temp_project_dir / "schemas"
    schemas_dir.mkdir()
    return schemas_dir


class TestMigrateCommand:
    def test_migrate_no_schemas_dir(self, tmp_path):
        result = runner.invoke(app, ["migrate", "--db-path", str(tmp_path / "test.db")])
        assert result.exit_code == 1
        assert "Schema directory not found" in result.output

    def test_migrate_no_schema_files(self, schema_dir):
        result = runner.invoke(
            app,
            ["migrate", "--schema-dir", str(schema_dir), "--db-path", "nonexistent.db"],
        )
        assert "No schema files found" in result.output
        assert "No migrations needed" in result.output

    def test_migrate_no_changes_detected(self, schema_dir, temp_project_dir):
        db_path = temp_project_dir / "data" / "hippo.db"

        schema_content = {
            "name": "test_entity",
            "version": "1.0.0",
            "fields": [{"name": "name", "type": "string"}],
        }
        schema_file = schema_dir / "test.yaml"
        schema_file.write_text(yaml.dump(schema_content))

        result = runner.invoke(
            app, ["migrate", "--schema-dir", str(schema_dir), "--db-path", str(db_path)]
        )

        assert "No schema changes detected" in result.output

    def test_migrate_preview_new_table(self, schema_dir, temp_project_dir):
        db_path = temp_project_dir / "data" / "hippo.db"

        schema_content = {
            "name": "new_entity",
            "version": "1.0.0",
            "fields": [{"name": "name", "type": "string", "required": True}],
        }
        schema_file = schema_dir / "new_entity.yaml"
        schema_file.write_text(yaml.dump(schema_content))

        result = runner.invoke(
            app,
            [
                "migrate",
                "--schema-dir",
                str(schema_dir),
                "--db-path",
                str(db_path),
                "--preview",
            ],
        )

        assert "New tables to create" in result.output
        assert "new_entity" in result.output
        assert "CREATE TABLE" in result.output

    def test_migrate_with_duplicate_schema(self, schema_dir, temp_project_dir):
        db_path = temp_project_dir / "data" / "hippo.db"

        schema_content = {"name": "entity1", "version": "1.0.0", "fields": []}
        schema_file1 = schema_dir / "entity1.yaml"
        schema_file1.write_text(yaml.dump(schema_content))

        schema_file2 = schema_dir / "entity1_dup.yaml"
        schema_file2.write_text(yaml.dump(schema_content))

        result = runner.invoke(
            app, ["migrate", "--schema-dir", str(schema_dir), "--db-path", str(db_path)]
        )

        assert "Duplicate entity type definition" in result.output

    def test_migrate_with_invalid_field_type(self, schema_dir, temp_project_dir):
        db_path = temp_project_dir / "data" / "hippo.db"

        schema_content = {
            "name": "entity1",
            "version": "1.0.0",
            "fields": [{"name": "field1", "type": "invalid_type"}],
        }
        schema_file = schema_dir / "entity1.yaml"
        schema_file.write_text(yaml.dump(schema_content))

        result = runner.invoke(
            app, ["migrate", "--schema-dir", str(schema_dir), "--db-path", str(db_path)]
        )

        assert result.exit_code == 1


class TestPreviewModeOutput:
    def test_preview_mode_shows_ddl(self, schema_dir, temp_project_dir):
        db_path = temp_project_dir / "data" / "hippo.db"

        schema_content = {
            "name": "preview_test",
            "version": "1.0.0",
            "fields": [
                {"name": "name", "type": "string"},
                {"name": "count", "type": "integer", "index": True},
            ],
        }
        schema_file = schema_dir / "preview_test.yaml"
        schema_file.write_text(yaml.dump(schema_content))

        result = runner.invoke(
            app,
            [
                "migrate",
                "--schema-dir",
                str(schema_dir),
                "--db-path",
                str(db_path),
                "--preview",
            ],
        )

        assert "DDL Statements (Preview)" in result.output
        assert "CREATE TABLE" in result.output
        assert "CREATE INDEX" in result.output

    def test_preview_does_not_modify_db(self, schema_dir, temp_project_dir):
        db_path = temp_project_dir / "data" / "hippo.db"

        schema_content = {
            "name": "preview_no_change",
            "version": "1.0.0",
            "fields": [{"name": "name", "type": "string"}],
        }
        schema_file = schema_dir / "preview_no_change.yaml"
        schema_file.write_text(yaml.dump(schema_content))

        result = runner.invoke(
            app,
            [
                "migrate",
                "--schema-dir",
                str(schema_dir),
                "--db-path",
                str(db_path),
                "--preview",
            ],
        )

        assert "Preview complete. No changes applied" in result.output

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert "preview_no_change" not in tables
