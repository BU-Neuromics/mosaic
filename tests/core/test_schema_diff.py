import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from hippo.config.models import FieldDefinition, SchemaConfig
from hippo.core.storage.schema_diff import (
    SchemaDiffEngine,
    SchemaDiff,
    SchemaValidator,
    SchemaValidationError,
    TableMetadata,
)


class TestSchemaDiffEngine:
    def test_load_existing_schema(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            cursor.execute('CREATE TABLE "test_table" (id TEXT PRIMARY KEY, name TEXT)')

            engine = SchemaDiffEngine(cursor)
            engine.load_existing_schema(cursor)

            assert "test_table" in engine._existing_tables
            table = engine._existing_tables["test_table"]
            assert len(table.columns) == 2

            conn.close()

    def test_load_schemas_from_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            schema_dir = Path(tmpdir) / "schemas"
            schema_dir.mkdir()

            schema_content = {
                "name": "test_entity",
                "version": "1.0.0",
                "fields": [{"name": "name", "type": "string", "required": True}],
            }
            schema_file = schema_dir / "test.yaml"
            schema_file.write_text(yaml.dump(schema_content))

            engine = SchemaDiffEngine()
            schemas = engine.load_schemas_from_files(schema_dir)

            assert len(schemas) == 1
            assert schemas[0].name == "test_entity"

    def test_compute_diff_new_table(self):
        engine = SchemaDiffEngine()
        engine._existing_tables = {}

        schema = SchemaConfig(
            name="new_entity",
            version="1.0.0",
            fields=[FieldDefinition(name="name", type="string", required=True)],
        )

        diff = engine.compute_diff([schema])

        assert len(diff.new_tables) == 1
        assert diff.new_tables[0].name == "new_entity"

    def test_compute_diff_existing_table(self):
        existing_table = TableMetadata(
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
            ],
        )

        engine = SchemaDiffEngine()
        engine._existing_tables = {"existing_entity": existing_table}

        schema = SchemaConfig(
            name="existing_entity",
            version="1.0.0",
            fields=[
                FieldDefinition(name="name", type="string"),
                FieldDefinition(name="new_field", type="string"),
            ],
        )

        diff = engine.compute_diff([schema])

        assert len(diff.new_tables) == 0
        assert "existing_entity" in diff.new_columns
        assert len(diff.new_columns["existing_entity"]) == 1
        assert diff.new_columns["existing_entity"][0].name == "new_field"

    def test_compute_diff_new_index(self):
        existing_table = TableMetadata(
            name="test_entity",
            columns=[
                {
                    "name": "id",
                    "type": "TEXT",
                    "not_null": True,
                    "default": None,
                    "primary_key": True,
                },
            ],
            indexes=[],
        )

        engine = SchemaDiffEngine()
        engine._existing_tables = {"test_entity": existing_table}

        schema = SchemaConfig(
            name="test_entity",
            version="1.0.0",
            fields=[
                FieldDefinition(name="id", type="string"),
                FieldDefinition(name="name", type="string", index=True),
            ],
        )

        diff = engine.compute_diff([schema])

        assert "test_entity" in diff.new_indexes
        assert len(diff.new_indexes["test_entity"]) == 1
        assert diff.new_indexes["test_entity"][0]["name"] == "idx_test_entity_name"


class TestSchemaValidator:
    def test_validate_duplicate_schema(self):
        schemas = [
            SchemaConfig(name="entity1", version="1.0.0"),
            SchemaConfig(name="entity1", version="1.0.0"),
        ]

        validator = SchemaValidator()
        with pytest.raises(SchemaValidationError) as exc_info:
            validator.validate(schemas)

        assert "Duplicate entity type definition" in str(exc_info.value)

    def test_validate_invalid_field_type(self):
        validator = SchemaValidator()
        assert "invalid_type" not in validator.VALID_FIELD_TYPES

    def test_validate_broken_reference(self):
        schemas = [
            SchemaConfig(
                name="child_entity",
                version="1.0.0",
                fields=[
                    FieldDefinition(
                        name="parent_id",
                        type="string",
                        references={"table": "nonexistent_parent", "column": "id"},
                    )
                ],
            ),
        ]

        validator = SchemaValidator()
        with pytest.raises(SchemaValidationError) as exc_info:
            validator.validate(schemas)

        assert "Broken reference" in str(exc_info.value)

    def test_validate_valid_schemas(self):
        schemas = [
            SchemaConfig(name="parent_entity", version="1.0.0"),
            SchemaConfig(
                name="child_entity",
                version="1.0.0",
                fields=[
                    FieldDefinition(
                        name="parent_id",
                        type="string",
                        references={"table": "parent_entity", "column": "id"},
                    )
                ],
            ),
        ]

        validator = SchemaValidator()
        validator.validate(schemas)

    def test_validate_valid_field_types(self):
        valid_types = [
            "string",
            "integer",
            "float",
            "boolean",
            "date",
            "datetime",
            "list",
            "dict",
            "uri",
            "enum",
        ]

        for field_type in valid_types:
            schemas = [
                SchemaConfig(
                    name="entity1",
                    version="1.0.0",
                    fields=[FieldDefinition(name="field1", type=field_type)],
                ),
            ]

            validator = SchemaValidator()
            validator.validate(schemas)
