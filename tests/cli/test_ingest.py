"""Tests for `hippo ingest` command — entity YAML ingest.

TDD RED phase: these tests define the desired behavior for the redesigned
`hippo ingest` command that accepts structured entity YAML (not CSV/JSON data files).

Design decision:
- `hippo ingest` only accepts structured entity YAML files
- CSV/JSON operational data ingestion is Cappella's responsibility
- Reference data ingestion is reference loader plugins' responsibility
- The command creates entities via HippoClient from a declarative YAML spec
"""

import json
import tempfile
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from hippo.cli.main import app


@pytest.fixture()
def runner():
    return CliRunner()


@pytest.fixture()
def tmp_hippo(tmp_path: Path) -> Path:
    """Create a minimal Hippo project directory with a SQLite database."""
    return tmp_path


# ---------------------------------------------------------------------------
# Entity YAML ingest format
# ---------------------------------------------------------------------------

class TestHippoIngestEntityYAML:
    """hippo ingest accepts entity YAML files with structured entity declarations."""

    def _make_entity_file(self, tmp_path: Path, entities: list[dict], name: str = "entities.yaml") -> Path:
        """Create an entity ingest file."""
        content = {"entities": entities}
        p = tmp_path / name
        p.write_text(yaml.dump(content))
        return p

    def test_ingest_entity_file_creates_entities(self, runner, tmp_hippo):
        """hippo ingest <file> creates entities declared in the entity file."""
        entity_file = self._make_entity_file(tmp_hippo, [
            {"type": "GenomeBuild", "data": {"name": "GRCh38", "source": "ensembl", "release": "110"}},
            {"type": "GenomeBuild", "data": {"name": "CHM13", "source": "t2t", "release": "2.0"}},
        ])

        from hippo.core.client import HippoClient
        from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter
        client = HippoClient(storage=SQLiteAdapter(str(tmp_hippo / "test.db")))

        from hippo.cli.commands.ingest import ingest_entity_file, IngestResult
        result = ingest_entity_file(entity_file, client)

        assert result.created == 2
        assert result.errors == 0
        items = list(client.query("GenomeBuild").items)
        assert len(items) == 2

    def test_ingest_entity_file_idempotent(self, runner, tmp_hippo):
        """hippo ingest is idempotent — re-ingesting same file does not duplicate entities."""
        entity_file = self._make_entity_file(tmp_hippo, [
            {"type": "GenomeBuild", "data": {"name": "GRCh38", "source": "ensembl", "release": "110"},
             "external_id": "ensembl_grch38_110"},
        ])

        from hippo.core.client import HippoClient
        from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter
        from hippo.cli.commands.ingest import ingest_entity_file
        client = HippoClient(storage=SQLiteAdapter(str(tmp_hippo / "test.db")))

        r1 = ingest_entity_file(entity_file, client)
        assert r1.created == 1

        r2 = ingest_entity_file(entity_file, client)
        assert r2.created == 0
        assert r2.unchanged == 1

        items = list(client.query("GenomeBuild").items)
        assert len(items) == 1

    def test_ingest_entity_file_updates_changed_entity(self, runner, tmp_hippo):
        """Re-ingest with changed data updates the entity."""
        from hippo.core.client import HippoClient
        from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter
        from hippo.cli.commands.ingest import ingest_entity_file
        client = HippoClient(storage=SQLiteAdapter(str(tmp_hippo / "test.db")))

        v1 = self._make_entity_file(tmp_hippo, [
            {"type": "GenomeBuild", "data": {"name": "GRCh38", "release": "109"},
             "external_id": "grch38"},
        ], "v1.yaml")
        ingest_entity_file(v1, client)

        v2 = self._make_entity_file(tmp_hippo, [
            {"type": "GenomeBuild", "data": {"name": "GRCh38", "release": "110"},
             "external_id": "grch38"},
        ], "v2.yaml")
        r2 = ingest_entity_file(v2, client)

        assert r2.updated == 1
        assert r2.created == 0
        items = list(client.query("GenomeBuild").items)
        assert len(items) == 1
        assert items[0]["data"]["release"] == "110"

    def test_ingest_entity_file_missing_type_raises(self, runner, tmp_hippo):
        """Entity entries missing 'type' field are rejected with a clear error."""
        from hippo.core.client import HippoClient
        from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter
        from hippo.cli.commands.ingest import ingest_entity_file, IngestError
        client = HippoClient(storage=SQLiteAdapter(str(tmp_hippo / "test.db")))

        bad_file = tmp_hippo / "bad.yaml"
        bad_file.write_text(yaml.dump({"entities": [{"data": {"name": "GRCh38"}}]}))

        with pytest.raises(IngestError, match="missing 'type'"):
            ingest_entity_file(bad_file, client)

    def test_ingest_entity_file_missing_data_raises(self, runner, tmp_hippo):
        """Entity entries missing 'data' field are rejected."""
        from hippo.core.client import HippoClient
        from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter
        from hippo.cli.commands.ingest import ingest_entity_file, IngestError
        client = HippoClient(storage=SQLiteAdapter(str(tmp_hippo / "test.db")))

        bad_file = tmp_hippo / "bad.yaml"
        bad_file.write_text(yaml.dump({"entities": [{"type": "GenomeBuild"}]}))

        with pytest.raises(IngestError, match="missing 'data'"):
            ingest_entity_file(bad_file, client)

    def test_ingest_entity_file_not_found_raises(self, runner, tmp_hippo):
        """Non-existent file raises IngestError."""
        from hippo.core.client import HippoClient
        from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter
        from hippo.cli.commands.ingest import ingest_entity_file, IngestError
        client = HippoClient(storage=SQLiteAdapter(str(tmp_hippo / "test.db")))

        with pytest.raises(IngestError, match="not found"):
            ingest_entity_file(tmp_hippo / "nonexistent.yaml", client)

    def test_ingest_entity_file_top_level_not_entities_raises(self, runner, tmp_hippo):
        """Entity file without top-level 'entities' key raises IngestError."""
        from hippo.core.client import HippoClient
        from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter
        from hippo.cli.commands.ingest import ingest_entity_file, IngestError
        client = HippoClient(storage=SQLiteAdapter(str(tmp_hippo / "test.db")))

        bad_file = tmp_hippo / "bad.yaml"
        bad_file.write_text(yaml.dump({"records": [{"type": "GenomeBuild", "data": {}}]}))

        with pytest.raises(IngestError, match="'entities'"):
            ingest_entity_file(bad_file, client)

    def test_ingest_entity_file_partial_failure_continues(self, runner, tmp_hippo):
        """If one entity fails validation, others are still created."""
        from hippo.core.client import HippoClient
        from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter
        from hippo.cli.commands.ingest import ingest_entity_file
        client = HippoClient(storage=SQLiteAdapter(str(tmp_hippo / "test.db")))

        # Entity 2 has empty data — should fail but entity 1 should succeed
        entity_file = self._make_entity_file(tmp_hippo, [
            {"type": "GenomeBuild", "data": {"name": "GRCh38"}},
            {"type": "GenomeBuild", "data": {}},   # empty data → ValidationFailure
        ])
        result = ingest_entity_file(entity_file, client)

        assert result.created == 1
        assert result.errors == 1


# ---------------------------------------------------------------------------
# CSV/JSON rejection
# ---------------------------------------------------------------------------

class TestHippoIngestRejectsCSV:
    """hippo ingest must reject CSV/JSON data files — those belong to Cappella."""

    def test_ingest_csv_file_raises_error(self, runner, tmp_hippo):
        """Passing a CSV file to ingest_entity_file raises IngestError, not silently processes it."""
        from hippo.core.client import HippoClient
        from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter
        from hippo.cli.commands.ingest import ingest_entity_file, IngestError
        client = HippoClient(storage=SQLiteAdapter(str(tmp_hippo / "test.db")))

        csv_file = tmp_hippo / "data.csv"
        csv_file.write_text("external_id,name\nBU0001,Alice\n")

        with pytest.raises(IngestError):
            ingest_entity_file(csv_file, client)


# ---------------------------------------------------------------------------
# IngestResult
# ---------------------------------------------------------------------------

class TestIngestResult:
    """IngestResult carries counts and errors."""

    def test_result_defaults(self):
        from hippo.cli.commands.ingest import IngestResult
        r = IngestResult(source_file="test.yaml")
        assert r.created == 0
        assert r.updated == 0
        assert r.unchanged == 0
        assert r.errors == 0
        assert r.error_messages == []

    def test_result_to_dict(self):
        from hippo.cli.commands.ingest import IngestResult
        r = IngestResult(source_file="test.yaml", created=2, errors=1)
        d = r.to_dict()
        assert d["created"] == 2
        assert d["errors"] == 1
        assert "source_file" in d
