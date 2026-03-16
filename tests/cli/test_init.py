"""Tests for the InitCommand class."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import typer

from hippo.cli.commands.init import InitCommand
from hippo.cli.templates import TEMPLATES, get_template, list_templates


class TestTemplateRegistry:
    """Tests for template registry."""

    def test_get_template_basic(self):
        template = get_template("basic")
        assert template is not None
        assert template.name == "basic"
        assert "config.json" in template.files
        assert ".gitignore" in template.files

    def test_get_template_full(self):
        template = get_template("full")
        assert template is not None
        assert template.name == "full"
        assert "README.md" in template.files

    def test_get_template_invalid(self):
        template = get_template("nonexistent")
        assert template is None

    def test_list_templates(self):
        templates = list_templates()
        assert len(templates) == 3
        assert all("name" in t and "description" in t for t in templates)


class TestInitCommand:
    """Tests for InitCommand class."""

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as td:
            yield Path(td)

    def test_init_basic_template(self, temp_dir):
        cmd = InitCommand(
            path=str(temp_dir / "myproject"), template="basic", force=False
        )
        cmd.run()

        config_path = temp_dir / "myproject" / "config.json"
        assert config_path.exists()

        config_data = json.loads(config_path.read_text())
        assert config_data["version"] == "0.1"

    def test_init_full_template(self, temp_dir):
        cmd = InitCommand(
            path=str(temp_dir / "myproject"), template="full", force=False
        )
        cmd.run()

        config_path = temp_dir / "myproject" / "config.json"
        readme_path = temp_dir / "myproject" / "README.md"
        schemas_dir = temp_dir / "myproject" / "schemas"

        assert config_path.exists()
        assert readme_path.exists()
        assert schemas_dir.exists()

    def test_init_creates_data_directory(self, temp_dir):
        cmd = InitCommand(
            path=str(temp_dir / "myproject"), template="basic", force=False
        )
        cmd.run()

        data_dir = temp_dir / "myproject" / "data"
        assert data_dir.exists()
        assert data_dir.is_dir()

    def test_init_invalid_template_raises_error(self, temp_dir):
        with pytest.raises(typer.Exit):
            cmd = InitCommand(
                path=str(temp_dir / "myproject"), template="invalid", force=False
            )
            cmd.run()

    def test_init_existing_config_raises_error(self, temp_dir):
        project_dir = temp_dir / "myproject"
        project_dir.mkdir()
        (project_dir / "config.json").write_text('{"version": "0.1"}')

        with pytest.raises(typer.Exit):
            cmd = InitCommand(path=str(project_dir), template="basic", force=False)
            cmd.run()

    def test_init_force_overwrites_existing(self, temp_dir):
        project_dir = temp_dir / "myproject"
        project_dir.mkdir()
        (project_dir / "config.json").write_text('{"version": "0.1"}')

        cmd = InitCommand(path=str(project_dir), template="basic", force=True)
        cmd.run()

        config_data = json.loads((project_dir / "config.json").read_text())
        assert config_data["version"] == "0.1"

    def test_init_non_empty_dir_raises_error(self, temp_dir):
        project_dir = temp_dir / "myproject"
        project_dir.mkdir()
        (project_dir / "somefile.txt").write_text("content")

        with pytest.raises(typer.Exit):
            cmd = InitCommand(path=str(project_dir), template="basic", force=False)
            cmd.run()

    def test_init_force_non_empty_dir_succeeds(self, temp_dir):
        project_dir = temp_dir / "myproject"
        project_dir.mkdir()
        (project_dir / "somefile.txt").write_text("content")

        cmd = InitCommand(path=str(project_dir), template="basic", force=True)
        cmd.run()

        assert (project_dir / "config.json").exists()

    def test_init_minimal_template(self, temp_dir):
        cmd = InitCommand(
            path=str(temp_dir / "myproject"), template="minimal", force=False
        )
        cmd.run()

        config_path = temp_dir / "myproject" / "config.json"
        assert config_path.exists()
        config_data = json.loads(config_path.read_text())
        assert config_data["version"] == "0.1"


class TestInitCommandIntegration:
    """Integration tests for hippo init command."""

    def test_cli_init_basic(self):
        with tempfile.TemporaryDirectory() as td:
            result = os.system(f"hippo init --path {td}/testproj")
            assert result == 0

            config_path = Path(td) / "testproj" / "config.json"
            assert config_path.exists()

    def test_cli_init_with_template_option(self):
        with tempfile.TemporaryDirectory() as td:
            result = os.system(f"hippo init --path {td}/testproj --template full")
            assert result == 0

            readme_path = Path(td) / "testproj" / "README.md"
            assert readme_path.exists()

    def test_cli_init_invalid_template_shows_available(self):
        with tempfile.TemporaryDirectory() as td:
            result = os.system(f"hippo init --path {td}/testproj --template bad")
            assert result != 0
