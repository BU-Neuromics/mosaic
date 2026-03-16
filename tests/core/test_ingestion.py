"""Tests for ingestion utilities and IngestionPipeline."""

import json
import tempfile
from pathlib import Path

import pytest

from hippo.core.exceptions import (
    IngestionError,
    IngestionValidationError,
)
from hippo.core.ingestion import (
    IngestionPipeline,
    IngestResult,
    flatten_dict,
    parse_csv_with_errors,
)


class TestFlattenDict:
    """Tests for flatten_dict utility."""

    def test_flatten_simple_dict(self):
        data = {"name": "John", "age": 30}
        result = flatten_dict(data)
        assert result == {"name": "John", "age": 30}

    def test_flatten_nested_dict(self):
        data = {"address": {"city": "Boston", "zip": "02101"}}
        result = flatten_dict(data)
        assert result == {"address.city": "Boston", "address.zip": "02101"}

    def test_flatten_deeply_nested_dict(self):
        data = {"a": {"b": {"c": "value"}}}
        result = flatten_dict(data)
        assert result == {"a.b.c": "value"}

    def test_flatten_mixed_dict(self):
        data = {
            "name": "John",
            "address": {"city": "Boston"},
            "age": 30,
        }
        result = flatten_dict(data)
        assert result == {
            "name": "John",
            "address.city": "Boston",
            "age": 30,
        }

    def test_flatten_empty_dict(self):
        data = {}
        result = flatten_dict(data)
        assert result == {}

    def test_flatten_custom_delimiter(self):
        data = {"address": {"city": "Boston"}}
        result = flatten_dict(data, delimiter="_")
        assert result == {"address_city": "Boston"}


class TestParseCSVWithErrors:
    """Tests for parse_csv_with_errors utility."""

    def test_parse_valid_csv(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("name,age,city\n")
            f.write("John,30,Boston\n")
            f.write("Jane,25,NYC\n")
            f.write("Bob,35,LA\n")
            temp_path = f.name

        try:
            valid_rows, error_rows = parse_csv_with_errors(Path(temp_path))
            assert len(valid_rows) == 3
            assert len(error_rows) == 0
            assert valid_rows[0] == {"name": "John", "age": "30", "city": "Boston"}
        finally:
            Path(temp_path).unlink()

    def test_parse_csv_no_headers_raises(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("John,30\n")
            f.write("Jane,25\n")
            temp_path = f.name

        try:
            rows, errors = parse_csv_with_errors(Path(temp_path))
            assert len(rows) == 1
            assert "John" in rows[0]
        finally:
            Path(temp_path).unlink()

    def test_parse_empty_csv(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("")
            temp_path = f.name

        try:
            valid_rows, error_rows = parse_csv_with_errors(Path(temp_path))
            assert len(valid_rows) == 0
            assert len(error_rows) == 0
        finally:
            Path(temp_path).unlink()


class TestIngestResult:
    """Tests for IngestResult dataclass."""

    def test_ingest_result_to_dict(self):
        result = IngestResult(
            entity_type="Sample",
            total_rows=10,
            created=5,
            updated=3,
            unchanged=1,
            errors=1,
            error_messages=["Error 1"],
        )
        d = result.to_dict()
        assert d["entity_type"] == "Sample"
        assert d["total_rows"] == 10
        assert d["created"] == 5
        assert d["updated"] == 3
        assert d["unchanged"] == 1
        assert d["errors"] == 1
        assert d["error_messages"] == ["Error 1"]


class TestIngestionPipeline:
    """Tests for IngestionPipeline class."""

    def test_init_with_defaults(self):
        client = None
        pipeline = IngestionPipeline(client)
        assert pipeline._max_batch_size == 10000
        assert pipeline._flatten_nested is True

    def test_init_with_custom_params(self):
        client = None
        pipeline = IngestionPipeline(client, max_batch_size=5000, flatten_nested=False)
        assert pipeline._max_batch_size == 5000
        assert pipeline._flatten_nested is False


class TestIngestionPipelineCSV:
    """Tests for CSV ingestion in IngestionPipeline."""

    def test_ingest_csv_empty_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("")
            temp_path = f.name

        try:
            client = None
            pipeline = IngestionPipeline(client)
            result = pipeline.ingest_csv(temp_path, "Sample")
            assert result.total_rows == 0
            assert result.created == 0
            assert result.updated == 0
        finally:
            Path(temp_path).unlink()

    def test_ingest_csv_file_not_found(self):
        client = None
        pipeline = IngestionPipeline(client)
        with pytest.raises(IngestionError) as exc_info:
            pipeline.ingest_csv("/nonexistent/file.csv", "Sample")
        assert "File not found" in str(exc_info.value)

    def test_ingest_csv_batch_size_exceeded(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("external_id,name\n")
            for i in range(10001):
                f.write(f"ext-{i},name-{i}\n")
            temp_path = f.name

        try:
            client = None
            pipeline = IngestionPipeline(client, max_batch_size=10000)
            with pytest.raises(IngestionError) as exc_info:
                pipeline.ingest_csv(temp_path, "Sample")
            assert "exceeds maximum" in str(exc_info.value)
        finally:
            Path(temp_path).unlink()


class TestIngestionPipelineJSON:
    """Tests for JSON ingestion in IngestionPipeline."""

    def test_ingest_json_empty_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("")
            temp_path = f.name

        try:
            client = None
            pipeline = IngestionPipeline(client)
            result = pipeline.ingest_json(temp_path, "Sample")
            assert result.total_rows == 0
        finally:
            Path(temp_path).unlink()

    def test_ingest_json_file_not_found(self):
        client = None
        pipeline = IngestionPipeline(client)
        with pytest.raises(IngestionError) as exc_info:
            pipeline.ingest_json("/nonexistent/file.json", "Sample")
        assert "File not found" in str(exc_info.value)

    def test_ingest_json_invalid_json(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{invalid json}")
            temp_path = f.name

        try:
            client = None
            pipeline = IngestionPipeline(client)
            with pytest.raises(IngestionError) as exc_info:
                pipeline.ingest_json(temp_path, "Sample")
            assert "Invalid JSON" in str(exc_info.value)
        finally:
            Path(temp_path).unlink()

    def test_ingest_json_not_array(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"key": "value"}, f)
            temp_path = f.name

        try:
            client = None
            pipeline = IngestionPipeline(client)
            with pytest.raises(IngestionError) as exc_info:
                pipeline.ingest_json(temp_path, "Sample")
            assert "must contain an array" in str(exc_info.value)
        finally:
            Path(temp_path).unlink()

    def test_ingest_json_batch_size_exceeded(self):
        data = [{"external_id": f"ext-{i}", "name": f"name-{i}"} for i in range(10001)]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            client = None
            pipeline = IngestionPipeline(client, max_batch_size=10000)
            with pytest.raises(IngestionError) as exc_info:
                pipeline.ingest_json(temp_path, "Sample")
            assert "exceeds maximum" in str(exc_info.value)
        finally:
            Path(temp_path).unlink()

    def test_ingest_json_nested_flattening(self):
        data = [{"external_id": "ext-1", "address": {"city": "Boston", "zip": "02101"}}]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            client = None
            pipeline = IngestionPipeline(client)
            result = pipeline.ingest_json(temp_path, "Sample")
            assert result.total_rows == 1
        finally:
            Path(temp_path).unlink()


class TestIngestionPipelineJSONL:
    """Tests for JSONL ingestion in IngestionPipeline."""

    def test_ingest_jsonl_empty_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write("")
            temp_path = f.name

        try:
            client = None
            pipeline = IngestionPipeline(client)
            result = pipeline.ingest_jsonl(temp_path, "Sample")
            assert result.total_rows == 0
        finally:
            Path(temp_path).unlink()

    def test_ingest_jsonl_file_not_found(self):
        client = None
        pipeline = IngestionPipeline(client)
        with pytest.raises(IngestionError) as exc_info:
            pipeline.ingest_jsonl("/nonexistent/file.jsonl", "Sample")
        assert "File not found" in str(exc_info.value)

    def test_ingest_jsonl_invalid_json(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"external_id": "ext-1"}\n')
            f.write("invalid json\n")
            f.write('{"external_id": "ext-2"}\n')
            temp_path = f.name

        try:
            client = None
            pipeline = IngestionPipeline(client)
            result = pipeline.ingest_jsonl(temp_path, "Sample")
            assert result.total_rows == 2
            assert result.errors >= 1
        finally:
            Path(temp_path).unlink()

    def test_ingest_jsonl_missing_ext_id(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"external_id": "ext-1", "name": "John"}\n')
            f.write('{"name": "Jane"}\n')
            temp_path = f.name

        try:
            client = None
            pipeline = IngestionPipeline(client)
            result = pipeline.ingest_jsonl(temp_path, "Sample")
            assert result.errors >= 1
        finally:
            Path(temp_path).unlink()

    def test_ingest_jsonl_batch_size_exceeded(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for i in range(10001):
                f.write(
                    json.dumps({"external_id": f"ext-{i}", "name": f"name-{i}"}) + "\n"
                )
            temp_path = f.name

        try:
            client = None
            pipeline = IngestionPipeline(client, max_batch_size=10000)
            with pytest.raises(IngestionError) as exc_info:
                pipeline.ingest_jsonl(temp_path, "Sample")
            assert "exceeds maximum" in str(exc_info.value)
        finally:
            Path(temp_path).unlink()

    def test_ingest_jsonl_nested_flattening(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(
                json.dumps(
                    {
                        "external_id": "ext-1",
                        "address": {"city": "Boston", "zip": "02101"},
                    }
                )
                + "\n"
            )
            temp_path = f.name

        try:
            client = None
            pipeline = IngestionPipeline(client)
            result = pipeline.ingest_jsonl(temp_path, "Sample")
            assert result.total_rows == 1
        finally:
            Path(temp_path).unlink()
