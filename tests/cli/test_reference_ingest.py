"""Integration tests for CLI reference and ingest commands."""

import json
import os
import tempfile
from pathlib import Path

import pytest
import yaml


class TestReferenceInstall:
    """Tests for hippo reference install command."""

    @pytest.fixture(autouse=True)
    def setup_test_env(self, monkeypatch, tmp_path):
        """Set up test environment with temporary directories."""
        test_data_dir = tmp_path / ".hippo" / "data"
        test_data_dir.mkdir(parents=True)
        monkeypatch.setenv("HOME", str(tmp_path))

    def test_install_valid_package(self):
        """Test installing a valid package."""
        result = os.system("python -m hippo.cli.main reference install pyyaml")
        assert result == 0

    def test_install_invalid_package(self):
        """Test installing a non-existent package shows error."""
        result = os.system(
            "python -m hippo.cli.main reference install non-existent-package-xyz 2>&1"
        )
        assert result != 0

    def test_install_already_installed_package(self):
        """Test installing an already installed package shows error."""
        os.system("python -m hippo.cli.main reference install pyyaml")
        result = os.system("python -m hippo.cli.main reference install pyyaml 2>&1")
        assert result != 0


class TestReferenceList:
    """Tests for hippo reference list command."""

    @pytest.fixture(autouse=True)
    def setup_test_env(self, monkeypatch, tmp_path):
        """Set up test environment with temporary directories."""
        test_data_dir = tmp_path / ".hippo" / "data"
        test_data_dir.mkdir(parents=True)
        monkeypatch.setenv("HOME", str(tmp_path))

    def test_list_with_installed_loaders(self):
        """Test listing with installed loaders."""
        os.system("python -m hippo.cli.main reference install pyyaml")
        result = os.system("python -m hippo.cli.main reference list")
        assert result == 0

    def test_list_with_no_loaders(self):
        """Test listing with no loaders installed."""
        installed_file = (
            Path.home() / ".hippo" / "data" / "references" / "installed.json"
        )
        if installed_file.exists():
            installed_file.unlink()
        result = os.system("python -m hippo.cli.main reference list")
        assert result == 0


class TestIngest:
    """Tests for hippo ingest command."""

    @pytest.fixture(autouse=True)
    def setup_test_env(self, monkeypatch, tmp_path):
        """Set up test environment with temporary directories."""
        test_data_dir = tmp_path / ".hippo" / "data"
        test_data_dir.mkdir(parents=True)
        monkeypatch.setenv("HOME", str(tmp_path))

    def test_ingest_with_configured_sources(self, tmp_path):
        """Test ingest with configured data sources."""
        config_path = tmp_path / ".hippo" / "data" / "sources.yaml"
        config_path.write_text(
            yaml.dump(
                {
                    "sources": [
                        {
                            "name": "test_source",
                            "type": "starlims",
                            "connection": {"host": "localhost"},
                        }
                    ]
                }
            )
        )
        result = os.system(f"python -m hippo.cli.main ingest --config {config_path}")
        assert result == 0

    def test_ingest_with_no_configured_sources(self):
        """Test ingest with no configured sources shows error."""
        config_path = Path.home() / ".hippo" / "data" / "sources.yaml"
        if config_path.exists():
            config_path.unlink()
        result = os.system("python -m hippo.cli.main ingest 2>&1")
        assert result != 0

    def test_ingest_with_empty_sources(self, tmp_path):
        """Test ingest with empty sources list shows error."""
        config_path = tmp_path / ".hippo" / "data" / "sources.yaml"
        config_path.write_text(yaml.dump({"sources": []}))
        result = os.system(
            f"python -m hippo.cli.main ingest --config {config_path} 2>&1"
        )
        assert result != 0

    def test_ingest_with_nonexistent_config_file(self):
        """Test ingest with nonexistent config file shows error."""
        result = os.system(
            "python -m hippo.cli.main ingest --config /nonexistent/config.yaml 2>&1"
        )
        assert result != 0
