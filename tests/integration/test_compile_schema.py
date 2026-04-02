"""Integration tests for the compile_schema CLI command.

Tests the full pipeline: Hippo DSL YAML → compile_schema → LinkML output,
covering all common LinkML constructs important for Hippo.
"""

import json
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


def _write_schema(tmp_dir: Path, content: dict, filename: str = "schema.yaml") -> Path:
    """Write a Hippo DSL schema to a temp file and return its path."""
    path = tmp_dir / filename
    path.write_text(yaml.dump(content, default_flow_style=False))
    return path


# ---------------------------------------------------------------------------
# Minimal schema
# ---------------------------------------------------------------------------
class TestCompileSchemaBasic:
    def test_compile_minimal_schema(self, tmp_dir):
        schema = {
            "name": "biobank",
            "description": "Biobank metadata schema",
            "entities": [
                {
                    "name": "sample",
                    "description": "A biological sample",
                    "properties": [
                        {"name": "sample_id", "type": "string", "required": True},
                    ],
                }
            ],
        }
        path = _write_schema(tmp_dir, schema)
        result = runner.invoke(app, ["compile-schema", str(path)])

        assert result.exit_code == 0
        assert "Compiling" in result.output
        assert "Compilation complete" in result.output
        # The YAML output should contain LinkML structure
        assert "linkml:types" in result.output
        assert "sample" in result.output

    def test_compile_schema_json_format(self, tmp_dir):
        schema = {
            "name": "biobank",
            "entities": [
                {
                    "name": "sample",
                    "properties": [
                        {"name": "sample_id", "type": "string", "required": True},
                    ],
                }
            ],
        }
        path = _write_schema(tmp_dir, schema)
        result = runner.invoke(app, ["compile-schema", str(path), "--format", "json"])

        assert result.exit_code == 0
        # Extract the JSON portion (after the "Compiling..." line)
        lines = result.output.strip().split("\n")
        json_text = "\n".join(
            l for l in lines if not l.startswith("Compil")
        )
        parsed = json.loads(json_text)

        assert parsed["name"] == "biobank"
        assert "classes" in parsed
        assert "sample" in parsed["classes"]
        assert "sample_id" in parsed["classes"]["sample"]["attributes"]

    def test_compile_schema_output_to_file(self, tmp_dir):
        schema = {
            "name": "biobank",
            "entities": [
                {
                    "name": "sample",
                    "properties": [
                        {"name": "sample_id", "type": "string", "required": True},
                    ],
                }
            ],
        }
        input_path = _write_schema(tmp_dir, schema)
        output_path = tmp_dir / "output.yaml"

        result = runner.invoke(
            app, ["compile-schema", str(input_path), "--output", str(output_path)]
        )

        assert result.exit_code == 0
        assert output_path.exists()
        compiled = yaml.safe_load(output_path.read_text())
        assert compiled["name"] == "biobank"
        assert "sample" in compiled["classes"]

    def test_compile_nonexistent_file(self, tmp_dir):
        result = runner.invoke(app, ["compile-schema", str(tmp_dir / "missing.yaml")])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_compile_empty_entities(self, tmp_dir):
        schema = {"name": "empty_schema", "entities": []}
        path = _write_schema(tmp_dir, schema)
        result = runner.invoke(app, ["compile-schema", str(path)])
        assert result.exit_code == 0
        assert "Compilation complete" in result.output


# ---------------------------------------------------------------------------
# LinkML type mapping for all Hippo types
# ---------------------------------------------------------------------------
class TestCompileSchemaTypeMapping:
    """Verify every Hippo DSL type maps to the correct LinkML range."""

    @pytest.mark.parametrize(
        "hippo_type,expected_linkml_range",
        [
            ("string", "string"),
            ("integer", "integer"),
            ("float", "float"),
            ("boolean", "boolean"),
            ("date", "date"),
            ("datetime", "datetime"),
            ("uri", "uri"),
            ("enum", "string"),
            ("list", "string"),
            ("dict", "string"),
            ("reference", "string"),
        ],
    )
    def test_type_mapping(self, tmp_dir, hippo_type, expected_linkml_range):
        schema = {
            "name": "type_test",
            "entities": [
                {
                    "name": "typed_entity",
                    "properties": [
                        {"name": "test_field", "type": hippo_type},
                    ],
                }
            ],
        }
        path = _write_schema(tmp_dir, schema)
        result = runner.invoke(app, ["compile-schema", str(path), "--format", "json"])
        assert result.exit_code == 0

        lines = result.output.strip().split("\n")
        json_text = "\n".join(l for l in lines if not l.startswith("Compil"))
        parsed = json.loads(json_text)

        attr = parsed["classes"]["typed_entity"]["attributes"]["test_field"]
        assert attr["range"] == expected_linkml_range


# ---------------------------------------------------------------------------
# Enum constructs
# ---------------------------------------------------------------------------
class TestCompileSchemaEnums:
    def test_enum_with_values(self, tmp_dir):
        schema = {
            "name": "enum_schema",
            "entities": [
                {
                    "name": "sample",
                    "properties": [
                        {
                            "name": "status",
                            "type": "enum",
                            "values": ["active", "archived", "superseded"],
                        }
                    ],
                }
            ],
        }
        path = _write_schema(tmp_dir, schema)
        result = runner.invoke(app, ["compile-schema", str(path), "--format", "json"])
        assert result.exit_code == 0

        lines = result.output.strip().split("\n")
        json_text = "\n".join(l for l in lines if not l.startswith("Compil"))
        parsed = json.loads(json_text)

        attr = parsed["classes"]["sample"]["attributes"]["status"]
        assert attr["range"] == "string"
        # Enum values are stored as examples in LinkML
        assert "examples" in attr
        example_values = [e["value"] for e in attr["examples"]]
        assert "active" in example_values
        assert "archived" in example_values
        assert "superseded" in example_values

    def test_enum_without_values(self, tmp_dir):
        """Enum type without explicit values should still compile."""
        schema = {
            "name": "enum_schema",
            "entities": [
                {
                    "name": "sample",
                    "properties": [
                        {"name": "category", "type": "enum"},
                    ],
                }
            ],
        }
        path = _write_schema(tmp_dir, schema)
        result = runner.invoke(app, ["compile-schema", str(path), "--format", "json"])
        assert result.exit_code == 0

        lines = result.output.strip().split("\n")
        json_text = "\n".join(l for l in lines if not l.startswith("Compil"))
        parsed = json.loads(json_text)

        attr = parsed["classes"]["sample"]["attributes"]["category"]
        assert attr["range"] == "string"
        assert "examples" not in attr


# ---------------------------------------------------------------------------
# Constraints (min_length, max_length, pattern)
# ---------------------------------------------------------------------------
class TestCompileSchemaConstraints:
    def test_min_max_length_constraints(self, tmp_dir):
        schema = {
            "name": "constraint_schema",
            "entities": [
                {
                    "name": "sample",
                    "properties": [
                        {
                            "name": "barcode",
                            "type": "string",
                            "min_length": 8,
                            "max_length": 12,
                        }
                    ],
                }
            ],
        }
        path = _write_schema(tmp_dir, schema)
        result = runner.invoke(app, ["compile-schema", str(path), "--format", "json"])
        assert result.exit_code == 0

        lines = result.output.strip().split("\n")
        json_text = "\n".join(l for l in lines if not l.startswith("Compil"))
        parsed = json.loads(json_text)

        attr = parsed["classes"]["sample"]["attributes"]["barcode"]
        assert attr["minimum_length"] == 8
        assert attr["maximum_length"] == 12

    def test_pattern_constraint(self, tmp_dir):
        schema = {
            "name": "pattern_schema",
            "entities": [
                {
                    "name": "sample",
                    "properties": [
                        {
                            "name": "accession",
                            "type": "string",
                            "pattern": r"^[A-Z]{3}-\d{6}$",
                        }
                    ],
                }
            ],
        }
        path = _write_schema(tmp_dir, schema)
        result = runner.invoke(app, ["compile-schema", str(path), "--format", "json"])
        assert result.exit_code == 0

        lines = result.output.strip().split("\n")
        json_text = "\n".join(l for l in lines if not l.startswith("Compil"))
        parsed = json.loads(json_text)

        attr = parsed["classes"]["sample"]["attributes"]["accession"]
        assert attr["pattern"] == r"^[A-Z]{3}-\d{6}$"

    def test_required_constraint(self, tmp_dir):
        schema = {
            "name": "required_schema",
            "entities": [
                {
                    "name": "sample",
                    "properties": [
                        {"name": "name", "type": "string", "required": True},
                        {"name": "notes", "type": "string", "required": False},
                        {"name": "tag", "type": "string"},  # default not required
                    ],
                }
            ],
        }
        path = _write_schema(tmp_dir, schema)
        result = runner.invoke(app, ["compile-schema", str(path), "--format", "json"])
        assert result.exit_code == 0

        lines = result.output.strip().split("\n")
        json_text = "\n".join(l for l in lines if not l.startswith("Compil"))
        parsed = json.loads(json_text)

        attrs = parsed["classes"]["sample"]["attributes"]
        assert attrs["name"]["required"] is True
        assert attrs["notes"]["required"] is False
        assert attrs["tag"]["required"] is False


# ---------------------------------------------------------------------------
# References (foreign keys)
# ---------------------------------------------------------------------------
class TestCompileSchemaReferences:
    def test_reference_property(self, tmp_dir):
        schema = {
            "name": "ref_schema",
            "entities": [
                {
                    "name": "project",
                    "properties": [
                        {"name": "project_id", "type": "string", "required": True},
                    ],
                },
                {
                    "name": "sample",
                    "properties": [
                        {"name": "sample_id", "type": "string", "required": True},
                        {
                            "name": "project_id",
                            "type": "string",
                            "references": {"table": "project", "column": "project_id"},
                        },
                    ],
                },
            ],
        }
        path = _write_schema(tmp_dir, schema)
        result = runner.invoke(app, ["compile-schema", str(path), "--format", "json"])
        assert result.exit_code == 0

        lines = result.output.strip().split("\n")
        json_text = "\n".join(l for l in lines if not l.startswith("Compil"))
        parsed = json.loads(json_text)

        assert "project" in parsed["classes"]
        assert "sample" in parsed["classes"]
        # Reference is compiled to range: string
        attr = parsed["classes"]["sample"]["attributes"]["project_id"]
        assert attr["range"] == "string"


# ---------------------------------------------------------------------------
# Relationships
# ---------------------------------------------------------------------------
class TestCompileSchemaRelationships:
    def test_relationship_definition(self, tmp_dir):
        schema = {
            "name": "rel_schema",
            "entities": [
                {
                    "name": "sample",
                    "description": "A biological sample",
                    "properties": [
                        {"name": "sample_id", "type": "string", "required": True},
                    ],
                    "relationships": [
                        {
                            "name": "project",
                            "description": "The project this sample belongs to",
                            "required": True,
                            "cardinality": "1..1",
                        },
                        {
                            "name": "derived_samples",
                            "description": "Samples derived from this one",
                            "required": False,
                            "cardinality": "0..*",
                        },
                    ],
                }
            ],
        }
        path = _write_schema(tmp_dir, schema)
        result = runner.invoke(app, ["compile-schema", str(path), "--format", "json"])
        assert result.exit_code == 0

        lines = result.output.strip().split("\n")
        json_text = "\n".join(l for l in lines if not l.startswith("Compil"))
        parsed = json.loads(json_text)

        attrs = parsed["classes"]["sample"]["attributes"]
        # Relationships appear as attributes in LinkML
        assert "project" in attrs
        assert attrs["project"]["required"] is True
        assert "derived_samples" in attrs
        assert attrs["derived_samples"]["required"] is False


# ---------------------------------------------------------------------------
# Multiple entities (real-world-ish schema)
# ---------------------------------------------------------------------------
class TestCompileSchemaMultiEntity:
    def test_multiple_entities_compile(self, tmp_dir):
        """A realistic biobank schema with multiple interrelated entities."""
        schema = {
            "name": "biobank_metadata",
            "description": "LIMS metadata tracking for biobank samples",
            "entities": [
                {
                    "name": "donor",
                    "description": "Tissue donor",
                    "properties": [
                        {"name": "donor_id", "type": "string", "required": True},
                        {"name": "species", "type": "string", "required": True},
                        {"name": "age_at_death", "type": "integer"},
                        {"name": "sex", "type": "enum", "values": ["M", "F", "U"]},
                    ],
                },
                {
                    "name": "sample",
                    "description": "A biological sample",
                    "properties": [
                        {"name": "sample_id", "type": "string", "required": True},
                        {"name": "tissue_type", "type": "string", "required": True},
                        {"name": "collection_date", "type": "date"},
                        {"name": "weight_mg", "type": "float"},
                        {"name": "is_qc_passed", "type": "boolean"},
                        {
                            "name": "donor_id",
                            "type": "string",
                            "references": {"table": "donor", "column": "donor_id"},
                        },
                    ],
                },
                {
                    "name": "experiment",
                    "description": "An experiment on a sample",
                    "properties": [
                        {"name": "experiment_id", "type": "string", "required": True},
                        {"name": "protocol_uri", "type": "uri"},
                        {"name": "started_at", "type": "datetime"},
                        {"name": "parameters", "type": "dict"},
                        {"name": "tags", "type": "list"},
                        {
                            "name": "sample_id",
                            "type": "string",
                            "references": {"table": "sample", "column": "sample_id"},
                        },
                    ],
                },
            ],
        }
        path = _write_schema(tmp_dir, schema)
        result = runner.invoke(app, ["compile-schema", str(path), "--format", "json"])
        assert result.exit_code == 0

        lines = result.output.strip().split("\n")
        json_text = "\n".join(l for l in lines if not l.startswith("Compil"))
        parsed = json.loads(json_text)

        assert parsed["name"] == "biobank_metadata"
        assert len(parsed["classes"]) == 3
        assert set(parsed["classes"].keys()) == {"donor", "sample", "experiment"}

        # Verify donor entity
        donor_attrs = parsed["classes"]["donor"]["attributes"]
        assert donor_attrs["donor_id"]["required"] is True
        assert donor_attrs["age_at_death"]["range"] == "integer"
        assert donor_attrs["sex"]["range"] == "string"  # enum -> string in LinkML

        # Verify sample entity
        sample_attrs = parsed["classes"]["sample"]["attributes"]
        assert sample_attrs["collection_date"]["range"] == "date"
        assert sample_attrs["weight_mg"]["range"] == "float"
        assert sample_attrs["is_qc_passed"]["range"] == "boolean"

        # Verify experiment entity
        exp_attrs = parsed["classes"]["experiment"]["attributes"]
        assert exp_attrs["protocol_uri"]["range"] == "uri"
        assert exp_attrs["started_at"]["range"] == "datetime"

    def test_schema_metadata_in_linkml(self, tmp_dir):
        """Verify top-level schema metadata propagates to LinkML."""
        schema = {
            "name": "my_custom_schema",
            "description": "Custom description for testing",
            "entities": [],
        }
        path = _write_schema(tmp_dir, schema)
        result = runner.invoke(app, ["compile-schema", str(path), "--format", "json"])
        assert result.exit_code == 0

        lines = result.output.strip().split("\n")
        json_text = "\n".join(l for l in lines if not l.startswith("Compil"))
        parsed = json.loads(json_text)

        assert parsed["name"] == "my_custom_schema"
        assert parsed["description"] == "Custom description for testing"
        assert "linkml:types" in parsed["imports"]
        assert "linkml" in parsed["prefixes"]
