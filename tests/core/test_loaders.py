"""Tests for hippo.core.loaders — EntityLoader ABC, ConfigurableLoader, concrete loaders, IngestPipeline."""

import json
import tempfile
from pathlib import Path

import pytest
import yaml


# ---------------------------------------------------------------------------
# EntityLoader ABC
# ---------------------------------------------------------------------------

class TestEntityLoaderABC:
    """EntityLoader cannot be instantiated directly."""

    def test_cannot_instantiate_entity_loader(self):
        from hippo.core.loaders.base import EntityLoader

        with pytest.raises(TypeError):
            EntityLoader()  # abstract

    def test_subclass_without_fetch_cannot_instantiate(self):
        from hippo.core.loaders.base import EntityLoader

        class Incomplete(EntityLoader):
            name = "incomplete"
            entity_types = ["Foo"]

            def transform(self, record):
                return record
            # missing fetch()

        with pytest.raises(TypeError):
            Incomplete()

    def test_subclass_without_transform_cannot_instantiate(self):
        from hippo.core.loaders.base import EntityLoader

        class Incomplete(EntityLoader):
            name = "incomplete"
            entity_types = ["Foo"]

            def fetch(self, since=None, **kwargs):
                return iter([])
            # missing transform()

        with pytest.raises(TypeError):
            Incomplete()

    def test_concrete_subclass_has_default_validate(self):
        from hippo.core.loaders.base import EntityLoader

        class Minimal(EntityLoader):
            name = "minimal"
            entity_types = ["Foo"]

            def fetch(self, since=None, **kwargs):
                return iter([])

            def transform(self, record):
                return record

        loader = Minimal()
        assert loader.validate({}, None) == []

    def test_concrete_subclass_has_default_health_check(self):
        from hippo.core.loaders.base import EntityLoader

        class Minimal(EntityLoader):
            name = "minimal"
            entity_types = ["Foo"]

            def fetch(self, since=None, **kwargs):
                return iter([])

            def transform(self, record):
                return record

        loader = Minimal()
        assert loader.health_check()["status"] == "unknown"


# ---------------------------------------------------------------------------
# ConfigurableLoader.transform
# ---------------------------------------------------------------------------

class TestConfigurableLoaderTransform:
    """ConfigurableLoader.transform applies field_map and vocabulary_map."""

    def _loader(self, config: dict):
        from hippo.core.loaders.base import ConfigurableLoader

        class ConcreteLoader(ConfigurableLoader):
            name = "test"

            def fetch(self, since=None, **kwargs):
                return iter([])

        return ConcreteLoader(config)

    def test_no_mapping_passthrough(self):
        loader = self._loader({"entity_type": "Sample"})
        record = {"external_id": "X1", "name": "Alice"}
        assert loader.transform(record) == {"external_id": "X1", "name": "Alice"}

    def test_field_map_renames_keys(self):
        loader = self._loader({
            "entity_type": "Sample",
            "field_map": {"SUBJECT_ID": "external_id", "SEX": "sex"},
        })
        record = {"SUBJECT_ID": "BU0001", "SEX": "M"}
        result = loader.transform(record)
        assert result == {"external_id": "BU0001", "sex": "M"}

    def test_vocabulary_map_normalizes_values(self):
        loader = self._loader({
            "entity_type": "Sample",
            "field_map": {"DIAGNOSIS": "diagnosis"},
            "vocabulary_map": {
                "diagnosis": {"CTE": "chronic traumatic encephalopathy", "AD": "Alzheimer disease"}
            },
        })
        record = {"DIAGNOSIS": "CTE"}
        result = loader.transform(record)
        assert result["diagnosis"] == "chronic traumatic encephalopathy"

    def test_vocabulary_map_unknown_value_passthrough(self):
        loader = self._loader({
            "entity_type": "Sample",
            "vocabulary_map": {"status": {"active": "ACTIVE"}},
        })
        record = {"status": "unknown_value"}
        result = loader.transform(record)
        assert result["status"] == "unknown_value"

    def test_field_map_then_vocabulary_map_applied_in_order(self):
        loader = self._loader({
            "entity_type": "Sample",
            "field_map": {"SEX_CODE": "sex"},
            "vocabulary_map": {"sex": {"M": "male", "F": "female"}},
        })
        record = {"SEX_CODE": "F"}
        result = loader.transform(record)
        assert result["sex"] == "female"

    def test_entity_type_stored(self):
        loader = self._loader({"entity_type": "Donor"})
        assert loader.entity_type == "Donor"

    def test_external_id_field_default(self):
        loader = self._loader({"entity_type": "Donor"})
        assert loader.external_id_field == "external_id"

    def test_external_id_field_custom(self):
        loader = self._loader({"entity_type": "Donor", "external_id_field": "SUBJECT_ID"})
        assert loader.external_id_field == "SUBJECT_ID"


# ---------------------------------------------------------------------------
# CSVLoader
# ---------------------------------------------------------------------------

class TestCSVLoader:
    """CSVLoader.fetch yields dicts from CSV data."""

    def test_fetch_from_file(self, tmp_path):
        from hippo.core.loaders.csv import CSVLoader

        csv_file = tmp_path / "data.csv"
        csv_file.write_text("external_id,name,sex\nBU0001,Alice,F\nBU0002,Bob,M\n")

        loader = CSVLoader({"entity_type": "Sample", "source_file": str(csv_file)})
        records = list(loader.fetch())
        assert len(records) == 2
        assert records[0] == {"external_id": "BU0001", "name": "Alice", "sex": "F"}

    def test_fetch_from_bytes(self):
        from hippo.core.loaders.csv import CSVLoader

        data = b"external_id,name\nX001,Carol\nX002,Dave\n"
        loader = CSVLoader({"entity_type": "Sample"})
        records = list(loader.fetch(data=data))
        assert len(records) == 2
        assert records[1]["name"] == "Dave"

    def test_transform_with_field_map(self):
        from hippo.core.loaders.csv import CSVLoader

        loader = CSVLoader({
            "entity_type": "Sample",
            "field_map": {"SUBJECT_ID": "external_id", "SEX": "sex"},
        })
        record = {"SUBJECT_ID": "BU0001", "SEX": "M"}
        result = loader.transform(record)
        assert result == {"external_id": "BU0001", "sex": "M"}

    def test_fetch_no_source_raises(self):
        from hippo.core.loaders.csv import CSVLoader

        loader = CSVLoader({"entity_type": "Sample"})
        with pytest.raises(ValueError, match="no source configured"):
            list(loader.fetch())

    def test_fetch_nonexistent_file_raises(self, tmp_path):
        from hippo.core.loaders.csv import CSVLoader

        loader = CSVLoader({"entity_type": "Sample", "source_file": str(tmp_path / "missing.csv")})
        with pytest.raises(FileNotFoundError):
            list(loader.fetch())


# ---------------------------------------------------------------------------
# JSONLoader
# ---------------------------------------------------------------------------

class TestJSONLoader:
    """JSONLoader.fetch yields dicts from JSON array data."""

    def test_fetch_from_file(self, tmp_path):
        from hippo.core.loaders.json import JSONLoader

        json_file = tmp_path / "data.json"
        json_file.write_text(json.dumps([
            {"external_id": "J001", "name": "Carol"},
            {"external_id": "J002", "name": "Dave"},
        ]))

        loader = JSONLoader({"entity_type": "Sample", "source_file": str(json_file)})
        records = list(loader.fetch())
        assert len(records) == 2
        assert records[0]["name"] == "Carol"

    def test_fetch_from_bytes(self):
        from hippo.core.loaders.json import JSONLoader

        data = json.dumps([{"external_id": "X1", "name": "Eve"}]).encode()
        loader = JSONLoader({"entity_type": "Sample"})
        records = list(loader.fetch(data=data))
        assert len(records) == 1
        assert records[0]["name"] == "Eve"

    def test_fetch_non_array_raises(self, tmp_path):
        from hippo.core.loaders.json import JSONLoader

        json_file = tmp_path / "data.json"
        json_file.write_text(json.dumps({"key": "value"}))

        loader = JSONLoader({"entity_type": "Sample", "source_file": str(json_file)})
        with pytest.raises(ValueError, match="array"):
            list(loader.fetch())

    def test_transform_with_field_map(self):
        from hippo.core.loaders.json import JSONLoader

        loader = JSONLoader({
            "entity_type": "Sample",
            "field_map": {"SUBJECT_ID": "external_id"},
        })
        record = {"SUBJECT_ID": "J001", "name": "Carol"}
        assert loader.transform(record)["external_id"] == "J001"

    def test_fetch_no_source_raises(self):
        from hippo.core.loaders.json import JSONLoader

        loader = JSONLoader({"entity_type": "Sample"})
        with pytest.raises(ValueError, match="no source configured"):
            list(loader.fetch())


# ---------------------------------------------------------------------------
# EntityYAMLLoader
# ---------------------------------------------------------------------------

class TestEntityYAMLLoader:
    """EntityYAMLLoader.fetch yields entity dicts from structured YAML."""

    def _make_entity_file(self, tmp_path: Path, entities: list) -> Path:
        p = tmp_path / "entities.yaml"
        p.write_text(yaml.dump({"entities": entities}))
        return p

    def test_fetch_yields_entity_dicts(self, tmp_path):
        from hippo.core.loaders.entity_yaml import EntityYAMLLoader

        p = self._make_entity_file(tmp_path, [
            {"type": "GenomeBuild", "data": {"name": "GRCh38"}},
            {"type": "GenomeBuild", "data": {"name": "CHM13"}},
        ])

        loader = EntityYAMLLoader(p)
        records = list(loader.fetch())
        assert len(records) == 2
        assert records[0]["type"] == "GenomeBuild"
        assert records[0]["data"]["name"] == "GRCh38"

    def test_fetch_missing_entities_key_raises(self, tmp_path):
        from hippo.core.loaders.entity_yaml import EntityYAMLLoader

        p = tmp_path / "bad.yaml"
        p.write_text(yaml.dump({"records": []}))

        loader = EntityYAMLLoader(p)
        with pytest.raises(ValueError, match="'entities'"):
            list(loader.fetch())

    def test_transform_passthrough(self, tmp_path):
        from hippo.core.loaders.entity_yaml import EntityYAMLLoader

        p = self._make_entity_file(tmp_path, [])
        loader = EntityYAMLLoader(p)
        record = {"type": "GenomeBuild", "data": {"name": "GRCh38"}, "external_id": "grch38"}
        assert loader.transform(record) == record


# ---------------------------------------------------------------------------
# IngestPipeline: create / unchanged / update cycle
# ---------------------------------------------------------------------------

class TestIngestPipeline:
    """IngestPipeline upserts entities via a real HippoClient."""

    @pytest.fixture()
    def real_client(self, tmp_path):
        from hippo.core.client import HippoClient
        from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter

        return HippoClient(storage=SQLiteAdapter(str(tmp_path / "test.db")))

    def _csv_loader(self, data: bytes, config: dict = None):
        from hippo.core.loaders.csv import CSVLoader

        cfg = {"entity_type": "Sample", "external_id_field": "external_id"}
        if config:
            cfg.update(config)
        loader = CSVLoader(cfg)
        loader._pending_data = data
        return loader, data

    def test_create_cycle(self, real_client):
        from hippo.core.loaders.csv import CSVLoader
        from hippo.core.loaders.pipeline import IngestPipeline

        data = b"external_id,name\nS001,Alice\nS002,Bob\n"
        loader = CSVLoader({"entity_type": "Sample"})
        pipeline = IngestPipeline(client=real_client, loader=loader)
        result = pipeline.run(data=data)

        assert result.created == 2
        assert result.errors == 0

    def test_unchanged_cycle(self, real_client):
        from hippo.core.loaders.csv import CSVLoader
        from hippo.core.loaders.pipeline import IngestPipeline

        data = b"external_id,name\nS001,Alice\n"
        loader = CSVLoader({"entity_type": "Sample"})
        pipeline = IngestPipeline(client=real_client, loader=loader)
        pipeline.run(data=data)

        result2 = pipeline.run(data=data)
        assert result2.unchanged == 1
        assert result2.created == 0

    def test_update_cycle(self, real_client):
        from hippo.core.loaders.csv import CSVLoader
        from hippo.core.loaders.pipeline import IngestPipeline

        data_v1 = b"external_id,name\nS001,Alice\n"
        data_v2 = b"external_id,name\nS001,Alice-Updated\n"
        loader = CSVLoader({"entity_type": "Sample"})
        pipeline = IngestPipeline(client=real_client, loader=loader)
        pipeline.run(data=data_v1)
        result2 = pipeline.run(data=data_v2)

        assert result2.updated == 1
        assert result2.created == 0
        items = list(real_client.query("Sample").items)
        assert len(items) == 1
        assert items[0]["data"]["name"] == "Alice-Updated"

    def test_dry_run_does_not_write(self, real_client):
        from hippo.core.loaders.csv import CSVLoader
        from hippo.core.loaders.pipeline import IngestPipeline

        data = b"external_id,name\nS001,Alice\n"
        loader = CSVLoader({"entity_type": "Sample"})
        pipeline = IngestPipeline(client=real_client, loader=loader)
        result = pipeline.run(data=data, dry_run=True)

        assert result.created == 1
        items = list(real_client.query("Sample").items)
        assert len(items) == 0

    def test_json_loader_create_cycle(self, real_client):
        from hippo.core.loaders.json import JSONLoader
        from hippo.core.loaders.pipeline import IngestPipeline

        data = json.dumps([
            {"external_id": "J001", "name": "Carol"},
        ]).encode()
        loader = JSONLoader({"entity_type": "Sample"})
        pipeline = IngestPipeline(client=real_client, loader=loader)
        result = pipeline.run(data=data)

        assert result.created == 1
        assert result.errors == 0


# ---------------------------------------------------------------------------
# SQLLoader: query safety validation
# ---------------------------------------------------------------------------

class TestSQLLoaderQuerySafety:
    """SQLLoader rejects queries containing write/DDL keywords."""

    def test_select_query_accepted(self):
        from hippo.core.loaders.sql import SQLLoader

        loader = SQLLoader({
            "entity_type": "Sample",
            "connection_url": "sqlite:///:memory:",
            "query": "SELECT id, name FROM samples",
        })
        assert loader._query == "SELECT id, name FROM samples"

    @pytest.mark.parametrize("keyword", [
        "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE"
    ])
    def test_forbidden_keyword_raises(self, keyword):
        from hippo.core.loaders.sql import SQLLoader

        with pytest.raises(ValueError, match="forbidden keyword"):
            SQLLoader({
                "entity_type": "Sample",
                "connection_url": "sqlite:///:memory:",
                "query": f"{keyword} INTO samples VALUES (1)",
            })

    def test_forbidden_keyword_case_insensitive(self):
        from hippo.core.loaders.sql import SQLLoader

        with pytest.raises(ValueError, match="forbidden keyword"):
            SQLLoader({
                "entity_type": "Sample",
                "connection_url": "sqlite:///:memory:",
                "query": "delete from samples where id = 1",
            })

    def test_validate_read_only_query_direct(self):
        from hippo.core.loaders.sql import validate_read_only_query

        validate_read_only_query("SELECT * FROM foo")  # should not raise

    def test_validate_read_only_query_raises_for_insert(self):
        from hippo.core.loaders.sql import validate_read_only_query

        with pytest.raises(ValueError):
            validate_read_only_query("INSERT INTO foo VALUES (1)")
