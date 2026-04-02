"""Integration tests for common LinkML constructs important for Hippo.

Tests the schema compiler (Hippo DSL → LinkML) and the migrate pipeline
with schemas that exercise the full range of LinkML-relevant constructs:
enums, references, constraints, multi-entity graphs, and round-trip
compile → validate → migrate workflows.
"""

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from hippo.cli.main import app
from hippo.core.storage.schema_compiler import compile_schema_to_linkml

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
# Direct unit-level tests of compile_schema_to_linkml
# ---------------------------------------------------------------------------
class TestCompileSchemaToLinkMLDirect:
    """Call the compiler function directly to validate LinkML output structure."""

    def test_invalid_input_type(self):
        with pytest.raises(ValueError, match="must be a dictionary"):
            compile_schema_to_linkml("not a dict")

    def test_default_name_and_description(self):
        result = yaml.safe_load(compile_schema_to_linkml({"entities": []}))
        assert result["name"] == "hippo_schema"
        assert result["description"] == "Compiled from Hippo DSL"

    def test_prefixes_and_imports(self):
        result = yaml.safe_load(compile_schema_to_linkml({"entities": []}))
        assert "linkml" in result["prefixes"]
        assert "schema" in result["prefixes"]
        assert "linkml:types" in result["imports"]

    def test_entity_becomes_linkml_class(self):
        schema = {
            "entities": [
                {
                    "name": "sample",
                    "description": "A biological sample",
                    "properties": [
                        {"name": "id", "type": "string", "required": True},
                    ],
                }
            ]
        }
        result = yaml.safe_load(compile_schema_to_linkml(schema))
        assert "sample" in result["classes"]
        cls = result["classes"]["sample"]
        assert cls["description"] == "A biological sample"
        assert "id" in cls["attributes"]
        assert cls["attributes"]["id"]["required"] is True

    def test_all_hippo_types_round_trip(self):
        """Every Hippo type should survive compile → parse without error."""
        types_and_expected = {
            "string": "string",
            "integer": "integer",
            "float": "float",
            "boolean": "boolean",
            "date": "date",
            "datetime": "datetime",
            "uri": "uri",
            "enum": "string",
            "list": "string",
            "dict": "string",
            "reference": "string",
        }
        for hippo_type, expected_range in types_and_expected.items():
            schema = {
                "entities": [
                    {
                        "name": "test",
                        "properties": [{"name": "f", "type": hippo_type}],
                    }
                ]
            }
            result = yaml.safe_load(compile_schema_to_linkml(schema))
            assert result["classes"]["test"]["attributes"]["f"]["range"] == expected_range

    def test_enum_values_become_examples(self):
        schema = {
            "entities": [
                {
                    "name": "sample",
                    "properties": [
                        {
                            "name": "status",
                            "type": "enum",
                            "values": ["active", "archived", "deleted"],
                        }
                    ],
                }
            ]
        }
        result = yaml.safe_load(compile_schema_to_linkml(schema))
        attr = result["classes"]["sample"]["attributes"]["status"]
        example_vals = [e["value"] for e in attr["examples"]]
        assert set(example_vals) == {"active", "archived", "deleted"}

    def test_constraint_mapping(self):
        schema = {
            "entities": [
                {
                    "name": "sample",
                    "properties": [
                        {
                            "name": "barcode",
                            "type": "string",
                            "min_length": 6,
                            "max_length": 20,
                            "pattern": r"^BC-\d+$",
                        }
                    ],
                }
            ]
        }
        result = yaml.safe_load(compile_schema_to_linkml(schema))
        attr = result["classes"]["sample"]["attributes"]["barcode"]
        assert attr["minimum_length"] == 6
        assert attr["maximum_length"] == 20
        assert attr["pattern"] == r"^BC-\d+$"

    def test_relationship_with_cardinality(self):
        schema = {
            "entities": [
                {
                    "name": "sample",
                    "properties": [],
                    "relationships": [
                        {
                            "name": "project",
                            "required": True,
                            "cardinality": "1..1",
                        },
                        {
                            "name": "aliquots",
                            "required": False,
                            "cardinality": "0..*",
                        },
                    ],
                }
            ]
        }
        result = yaml.safe_load(compile_schema_to_linkml(schema))
        attrs = result["classes"]["sample"]["attributes"]
        assert attrs["project"]["required"] is True
        assert attrs["project"]["cardinality"] == "1..1"
        assert attrs["aliquots"]["required"] is False
        assert attrs["aliquots"]["cardinality"] == "0..*"

    def test_json_output_format(self):
        schema = {"name": "test", "entities": []}
        result = compile_schema_to_linkml(schema, format="json")
        parsed = json.loads(result)
        assert parsed["name"] == "test"

    def test_yaml_output_format(self):
        schema = {"name": "test", "entities": []}
        result = compile_schema_to_linkml(schema, format="yaml")
        parsed = yaml.safe_load(result)
        assert parsed["name"] == "test"


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


# ---------------------------------------------------------------------------
# Compile → Validate → Migrate round-trip
# ---------------------------------------------------------------------------
class TestCompileValidateMigrateRoundTrip:
    """End-to-end: compile a Hippo DSL schema to LinkML, validate it, migrate."""

    def test_compile_then_validate(self, tmp_dir):
        """Compiled LinkML output should pass validation as a YAML dict."""
        schema = {
            "name": "roundtrip_test",
            "entities": [
                {
                    "name": "sample",
                    "properties": [
                        {"name": "id", "type": "string", "required": True},
                        {"name": "weight", "type": "float"},
                        {
                            "name": "status",
                            "type": "enum",
                            "values": ["active", "archived"],
                        },
                    ],
                }
            ],
        }
        # Step 1: Compile
        input_path = tmp_dir / "input.yaml"
        input_path.write_text(yaml.dump(schema))
        compiled_path = tmp_dir / "compiled.yaml"

        result = runner.invoke(
            app,
            [
                "compile-schema",
                str(input_path),
                "--output",
                str(compiled_path),
            ],
        )
        assert result.exit_code == 0
        assert compiled_path.exists()

        # Step 2: Validate the compiled output as a schema
        result = runner.invoke(app, ["validate", "--schema", str(compiled_path)])
        assert result.exit_code == 0
        assert "Validation complete" in result.output

    def test_full_pipeline_compile_to_json(self, tmp_dir):
        """Compile to JSON, parse, verify LinkML structure is complete."""
        schema = {
            "name": "pipeline_test",
            "description": "Full pipeline test schema",
            "entities": [
                {
                    "name": "donor",
                    "description": "Tissue donor information",
                    "properties": [
                        {"name": "donor_id", "type": "string", "required": True},
                        {
                            "name": "sex",
                            "type": "enum",
                            "values": ["M", "F", "Unknown"],
                        },
                        {"name": "birth_date", "type": "date"},
                    ],
                },
                {
                    "name": "tissue_sample",
                    "description": "Physical tissue sample",
                    "properties": [
                        {"name": "sample_id", "type": "string", "required": True},
                        {"name": "tissue_type", "type": "string", "required": True},
                        {
                            "name": "barcode",
                            "type": "string",
                            "min_length": 8,
                            "max_length": 16,
                            "pattern": r"^TS-\d+$",
                        },
                        {
                            "name": "donor_id",
                            "type": "string",
                            "references": {"table": "donor", "column": "donor_id"},
                        },
                    ],
                    "relationships": [
                        {
                            "name": "experiments",
                            "description": "Experiments run on this sample",
                            "cardinality": "0..*",
                        }
                    ],
                },
            ],
        }
        input_path = tmp_dir / "pipeline.yaml"
        input_path.write_text(yaml.dump(schema))

        result = runner.invoke(
            app,
            ["compile-schema", str(input_path), "--format", "json"],
        )
        assert result.exit_code == 0

        lines = result.output.strip().split("\n")
        json_text = "\n".join(l for l in lines if not l.startswith("Compil"))
        parsed = json.loads(json_text)

        # Verify LinkML structure completeness
        assert parsed["id"] == "https://example.org/pipeline_test"
        assert len(parsed["classes"]) == 2

        # Donor class
        donor = parsed["classes"]["donor"]
        assert donor["attributes"]["donor_id"]["required"] is True
        sex_attr = donor["attributes"]["sex"]
        assert sex_attr["range"] == "string"
        example_vals = [e["value"] for e in sex_attr["examples"]]
        assert "M" in example_vals

        # Tissue sample class
        ts = parsed["classes"]["tissue_sample"]
        barcode = ts["attributes"]["barcode"]
        assert barcode["minimum_length"] == 8
        assert barcode["maximum_length"] == 16
        assert barcode["pattern"] == r"^TS-\d+$"
        # Relationship appears as attribute
        assert "experiments" in ts["attributes"]
