"""Integration tests for the schema_diff CLI command.

Tests comparing two Hippo DSL schema files and verifying the diff output
covers entity additions, removals, property changes, and type modifications.
"""

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


def _write_schema(tmp_dir: Path, content: dict, filename: str) -> Path:
    path = tmp_dir / filename
    path.write_text(yaml.dump(content, default_flow_style=False))
    return path


class TestSchemaDiffCLI:
    def test_diff_identical_schemas(self, tmp_dir):
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
        file1 = _write_schema(tmp_dir, schema, "v1.yaml")
        file2 = _write_schema(tmp_dir, schema, "v2.yaml")

        result = runner.invoke(app, ["schema-diff", str(file1), str(file2)])
        assert result.exit_code == 0
        assert "Schema comparison complete" in result.output
        # No additions or removals
        assert "Added" not in result.output
        assert "Removed" not in result.output

    def test_diff_added_entity(self, tmp_dir):
        schema_v1 = {
            "entities": [
                {
                    "name": "sample",
                    "properties": [{"name": "id", "type": "string"}],
                }
            ]
        }
        schema_v2 = {
            "entities": [
                {
                    "name": "sample",
                    "properties": [{"name": "id", "type": "string"}],
                },
                {
                    "name": "experiment",
                    "properties": [{"name": "id", "type": "string"}],
                },
            ]
        }
        file1 = _write_schema(tmp_dir, schema_v1, "v1.yaml")
        file2 = _write_schema(tmp_dir, schema_v2, "v2.yaml")

        result = runner.invoke(app, ["schema-diff", str(file1), str(file2)])
        assert result.exit_code == 0
        assert "Added entities" in result.output
        assert "experiment" in result.output

    def test_diff_removed_entity(self, tmp_dir):
        schema_v1 = {
            "entities": [
                {
                    "name": "sample",
                    "properties": [{"name": "id", "type": "string"}],
                },
                {
                    "name": "donor",
                    "properties": [{"name": "id", "type": "string"}],
                },
            ]
        }
        schema_v2 = {
            "entities": [
                {
                    "name": "sample",
                    "properties": [{"name": "id", "type": "string"}],
                }
            ]
        }
        file1 = _write_schema(tmp_dir, schema_v1, "v1.yaml")
        file2 = _write_schema(tmp_dir, schema_v2, "v2.yaml")

        result = runner.invoke(app, ["schema-diff", str(file1), str(file2)])
        assert result.exit_code == 0
        assert "Removed entities" in result.output
        assert "donor" in result.output

    def test_diff_added_property(self, tmp_dir):
        schema_v1 = {
            "entities": [
                {
                    "name": "sample",
                    "properties": [{"name": "id", "type": "string"}],
                }
            ]
        }
        schema_v2 = {
            "entities": [
                {
                    "name": "sample",
                    "properties": [
                        {"name": "id", "type": "string"},
                        {"name": "barcode", "type": "string", "required": True},
                    ],
                }
            ]
        }
        file1 = _write_schema(tmp_dir, schema_v1, "v1.yaml")
        file2 = _write_schema(tmp_dir, schema_v2, "v2.yaml")

        result = runner.invoke(app, ["schema-diff", str(file1), str(file2)])
        assert result.exit_code == 0
        assert "Added property" in result.output
        assert "barcode" in result.output

    def test_diff_removed_property(self, tmp_dir):
        schema_v1 = {
            "entities": [
                {
                    "name": "sample",
                    "properties": [
                        {"name": "id", "type": "string"},
                        {"name": "barcode", "type": "string"},
                    ],
                }
            ]
        }
        schema_v2 = {
            "entities": [
                {
                    "name": "sample",
                    "properties": [{"name": "id", "type": "string"}],
                }
            ]
        }
        file1 = _write_schema(tmp_dir, schema_v1, "v1.yaml")
        file2 = _write_schema(tmp_dir, schema_v2, "v2.yaml")

        result = runner.invoke(app, ["schema-diff", str(file1), str(file2)])
        assert result.exit_code == 0
        assert "Removed property" in result.output
        assert "barcode" in result.output

    def test_diff_modified_property_type_with_added_prop(self, tmp_dir):
        """Modified properties are shown when there are also added/removed props."""
        schema_v1 = {
            "entities": [
                {
                    "name": "sample",
                    "properties": [
                        {"name": "count", "type": "string"},
                    ],
                }
            ]
        }
        schema_v2 = {
            "entities": [
                {
                    "name": "sample",
                    "properties": [
                        {"name": "count", "type": "integer"},
                        {"name": "label", "type": "string"},
                    ],
                }
            ]
        }
        file1 = _write_schema(tmp_dir, schema_v1, "v1.yaml")
        file2 = _write_schema(tmp_dir, schema_v2, "v2.yaml")

        result = runner.invoke(app, ["schema-diff", str(file1), str(file2)])
        assert result.exit_code == 0
        assert "Modified property" in result.output
        assert "count" in result.output
        assert "string" in result.output
        assert "integer" in result.output

    def test_diff_only_modified_property_no_output(self, tmp_dir):
        """When only common properties change (no adds/removes), no changes shown.

        Note: this is a known limitation of the current schema_diff implementation.
        """
        schema_v1 = {
            "entities": [
                {
                    "name": "sample",
                    "properties": [{"name": "count", "type": "string"}],
                }
            ]
        }
        schema_v2 = {
            "entities": [
                {
                    "name": "sample",
                    "properties": [{"name": "count", "type": "integer"}],
                }
            ]
        }
        file1 = _write_schema(tmp_dir, schema_v1, "v1.yaml")
        file2 = _write_schema(tmp_dir, schema_v2, "v2.yaml")

        result = runner.invoke(app, ["schema-diff", str(file1), str(file2)])
        assert result.exit_code == 0
        # Current implementation only shows modified props when there are also
        # added or removed props in the same entity
        assert "Modified property" not in result.output

    def test_diff_modified_required_flag_with_added_prop(self, tmp_dir):
        """Required flag change is shown when combined with added/removed props."""
        schema_v1 = {
            "entities": [
                {
                    "name": "sample",
                    "properties": [
                        {"name": "name", "type": "string", "required": False},
                    ],
                }
            ]
        }
        schema_v2 = {
            "entities": [
                {
                    "name": "sample",
                    "properties": [
                        {"name": "name", "type": "string", "required": True},
                        {"name": "tag", "type": "string"},
                    ],
                }
            ]
        }
        file1 = _write_schema(tmp_dir, schema_v1, "v1.yaml")
        file2 = _write_schema(tmp_dir, schema_v2, "v2.yaml")

        result = runner.invoke(app, ["schema-diff", str(file1), str(file2)])
        assert result.exit_code == 0
        assert "Modified property" in result.output
        assert "name" in result.output

    def test_diff_nonexistent_file(self, tmp_dir):
        schema = {"entities": []}
        file1 = _write_schema(tmp_dir, schema, "v1.yaml")

        result = runner.invoke(
            app, ["schema-diff", str(file1), str(tmp_dir / "missing.yaml")]
        )
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_diff_both_nonexistent(self, tmp_dir):
        result = runner.invoke(
            app,
            [
                "schema-diff",
                str(tmp_dir / "a.yaml"),
                str(tmp_dir / "b.yaml"),
            ],
        )
        assert result.exit_code == 1

    def test_diff_added_top_level_key(self, tmp_dir):
        schema_v1 = {"entities": []}
        schema_v2 = {"entities": [], "version": "2.0"}
        file1 = _write_schema(tmp_dir, schema_v1, "v1.yaml")
        file2 = _write_schema(tmp_dir, schema_v2, "v2.yaml")

        result = runner.invoke(app, ["schema-diff", str(file1), str(file2)])
        assert result.exit_code == 0
        assert "Added top-level keys" in result.output
        assert "version" in result.output

    def test_diff_complex_evolution(self, tmp_dir):
        """Simulate a real schema evolution: add entity, add property, modify type."""
        schema_v1 = {
            "name": "biobank",
            "entities": [
                {
                    "name": "sample",
                    "properties": [
                        {"name": "id", "type": "string"},
                        {"name": "weight", "type": "string"},
                    ],
                }
            ],
        }
        schema_v2 = {
            "name": "biobank",
            "entities": [
                {
                    "name": "sample",
                    "properties": [
                        {"name": "id", "type": "string"},
                        {"name": "weight", "type": "float"},
                        {"name": "barcode", "type": "string", "required": True},
                    ],
                },
                {
                    "name": "experiment",
                    "properties": [
                        {"name": "id", "type": "string"},
                    ],
                },
            ],
        }
        file1 = _write_schema(tmp_dir, schema_v1, "v1.yaml")
        file2 = _write_schema(tmp_dir, schema_v2, "v2.yaml")

        result = runner.invoke(app, ["schema-diff", str(file1), str(file2)])
        assert result.exit_code == 0
        assert "experiment" in result.output  # new entity
        assert "barcode" in result.output  # new property
        assert "weight" in result.output  # modified type
