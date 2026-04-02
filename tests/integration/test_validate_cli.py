"""Integration tests for the validate CLI command.

Tests schema and config file validation through the CLI, covering
valid files, invalid files, missing files, and default validation.
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


def _write_yaml(tmp_dir: Path, content, filename: str) -> Path:
    path = tmp_dir / filename
    path.write_text(yaml.dump(content, default_flow_style=False))
    return path


class TestValidateCLISchema:
    def test_validate_valid_schema(self, tmp_dir):
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
        path = _write_yaml(tmp_dir, schema, "schema.yaml")
        result = runner.invoke(app, ["validate", "--schema", str(path)])
        assert result.exit_code == 0
        assert "Validation complete" in result.output

    def test_validate_schema_nonexistent(self, tmp_dir):
        result = runner.invoke(
            app, ["validate", "--schema", str(tmp_dir / "missing.yaml")]
        )
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_validate_schema_not_dict(self, tmp_dir):
        """A YAML file whose root is a list should fail validation."""
        path = tmp_dir / "bad_schema.yaml"
        path.write_text("- item1\n- item2\n")
        result = runner.invoke(app, ["validate", "--schema", str(path)])
        assert result.exit_code == 1
        assert "Invalid schema format" in result.output

    def test_validate_schema_with_all_field_types(self, tmp_dir):
        """Schema with every Hippo type should pass validation."""
        schema = {
            "name": "all_types",
            "entities": [
                {
                    "name": "everything",
                    "properties": [
                        {"name": "f_str", "type": "string"},
                        {"name": "f_int", "type": "integer"},
                        {"name": "f_float", "type": "float"},
                        {"name": "f_bool", "type": "boolean"},
                        {"name": "f_date", "type": "date"},
                        {"name": "f_dt", "type": "datetime"},
                        {"name": "f_uri", "type": "uri"},
                        {"name": "f_list", "type": "list"},
                        {"name": "f_dict", "type": "dict"},
                        {
                            "name": "f_enum",
                            "type": "enum",
                            "values": ["a", "b"],
                        },
                    ],
                }
            ],
        }
        path = _write_yaml(tmp_dir, schema, "full_types.yaml")
        result = runner.invoke(app, ["validate", "--schema", str(path)])
        assert result.exit_code == 0
        assert "Validation complete" in result.output

    def test_validate_empty_schema(self, tmp_dir):
        """An empty dict should still pass basic structural validation."""
        path = _write_yaml(tmp_dir, {}, "empty.yaml")
        result = runner.invoke(app, ["validate", "--schema", str(path)])
        # Empty dict is a valid dict
        assert result.exit_code == 0


class TestValidateCLIConfig:
    def test_validate_valid_config(self, tmp_dir):
        config = {"storage": {"backend": "sqlite", "path": "data/hippo.db"}}
        path = _write_yaml(tmp_dir, config, "config.yaml")
        result = runner.invoke(app, ["validate", "--config", str(path)])
        assert result.exit_code == 0
        assert "Validation complete" in result.output

    def test_validate_config_nonexistent(self, tmp_dir):
        result = runner.invoke(
            app, ["validate", "--config", str(tmp_dir / "missing.yaml")]
        )
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_validate_config_not_dict(self, tmp_dir):
        path = tmp_dir / "bad_config.yaml"
        path.write_text("just a string")
        result = runner.invoke(app, ["validate", "--config", str(path)])
        assert result.exit_code == 1
        assert "Invalid config format" in result.output


class TestValidateCLIDefault:
    def test_validate_no_args(self):
        """With no --schema or --config, validates default configuration."""
        result = runner.invoke(app, ["validate"])
        assert result.exit_code == 0
        assert "Default configuration is valid" in result.output


class TestValidateCLICombined:
    def test_validate_both_schema_and_config(self, tmp_dir):
        schema = {"name": "test", "entities": []}
        config = {"storage": {"backend": "sqlite"}}
        schema_path = _write_yaml(tmp_dir, schema, "schema.yaml")
        config_path = _write_yaml(tmp_dir, config, "config.yaml")

        result = runner.invoke(
            app,
            ["validate", "--schema", str(schema_path), "--config", str(config_path)],
        )
        assert result.exit_code == 0
        assert "Validation complete" in result.output
