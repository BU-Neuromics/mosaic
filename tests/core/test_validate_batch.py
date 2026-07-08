"""Tests for whole-set dry-run validation.

Increment 1 of the batch unit-of-work (BU-Neuromics/hippo#84): validate a
proposed *set* of related entities and report per-entity outcomes without
writing anything.
"""

import os
import tempfile

import pytest

from mosaic.core.client import MosaicClient
from mosaic.core.storage.adapters.sqlite_adapter import SQLiteAdapter
from mosaic.core.validation import (
    BatchValidationResult,
    ValidationResult,
    WriteOperation,
    WriteValidator,
)
from tests.conftest import _build_minimal_schema_registry


class _NameRequiredValidator(WriteValidator):
    """Fails when an operation's data has no non-empty ``name``."""

    def validate(self, operation: WriteOperation) -> ValidationResult:
        if not operation.data.get("name"):
            return ValidationResult(
                is_valid=False,
                errors=["name is required"],
                entity_id=operation.data.get("id"),
            )
        return ValidationResult(is_valid=True, errors=[])


class TestBatchValidationResult:
    """Unit tests for the aggregated result type."""

    def test_aggregates_failures_and_errors(self):
        r1 = ValidationResult(is_valid=True)
        r2 = ValidationResult(is_valid=False, errors=["bad"])
        batch = BatchValidationResult(is_valid=False, results=[r1, r2])
        assert batch.is_valid is False
        assert batch.passed is False
        assert batch.errors == ["bad"]
        assert len(batch.failures) == 1
        assert batch.invalid_results() == [r2]

    def test_all_valid(self):
        batch = BatchValidationResult(
            is_valid=True, results=[ValidationResult(is_valid=True)]
        )
        assert batch.is_valid is True
        assert batch.errors == []
        assert batch.failures == []
        assert batch.invalid_results() == []

    def test_to_envelope(self):
        r = ValidationResult(is_valid=False, errors=["x"], entity_id="e1")
        env = BatchValidationResult(is_valid=False, results=[r]).to_envelope()
        assert env["passed"] is False
        assert env["results"][0]["entity_id"] == "e1"
        assert env["results"][0]["passed"] is False

    def test_is_valid_must_be_bool(self):
        with pytest.raises(TypeError, match="is_valid must be a boolean"):
            BatchValidationResult(is_valid="yes", results=[])

    def test_results_must_be_list(self):
        with pytest.raises(TypeError, match="results must be a list"):
            BatchValidationResult(is_valid=True, results="nope")


class TestValidateBatch:
    """Integration tests for ``MosaicClient.validate_batch`` against storage."""

    @pytest.fixture
    def db_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.join(tmpdir, "test_validate_batch.db")

    @pytest.fixture
    def client(self, db_path: str) -> MosaicClient:
        storage = SQLiteAdapter(
            db_path, schema_registry=_build_minimal_schema_registry()
        )
        c = MosaicClient(storage=storage)
        c.add_validator(_NameRequiredValidator())
        return c

    def test_all_valid_set(self, client: MosaicClient) -> None:
        ops = [
            WriteOperation(operation="insert", entity_type="Sample", data={"name": "a"}),
            WriteOperation(operation="insert", entity_type="Sample", data={"name": "b"}),
        ]
        result = client.validate_batch(ops)
        assert isinstance(result, BatchValidationResult)
        assert result.is_valid is True
        assert len(result.results) == 2
        assert all(r.is_valid for r in result.results)

    def test_mixed_set_aggregates_not_fail_fast(self, client: MosaicClient) -> None:
        ops = [
            WriteOperation(operation="insert", entity_type="Sample", data={"name": "ok"}),
            WriteOperation(operation="insert", entity_type="Sample", data={"value": "x"}),
            WriteOperation(operation="insert", entity_type="Sample", data={"value": "y"}),
        ]
        result = client.validate_batch(ops)
        assert result.is_valid is False
        # Aggregating, not fail-fast: every operation was evaluated.
        assert len(result.results) == 3
        assert len(result.invalid_results()) == 2

    def test_provisional_id_assigned_and_caller_data_untouched(
        self, client: MosaicClient
    ) -> None:
        data = {"name": "x"}
        ops = [WriteOperation(operation="insert", entity_type="Sample", data=data)]
        result = client.validate_batch(ops)
        # Result is addressable by a provisional id ...
        assert result.results[0].entity_id is not None
        # ... but the caller's data is never mutated.
        assert "id" not in data
        assert ops[0].data == {"name": "x"}

    def test_no_writes_occur(self, client: MosaicClient) -> None:
        ids = ["batch-e1", "batch-e2"]
        ops = [
            WriteOperation(
                operation="insert", entity_type="Sample", data={"id": ids[0], "name": "a"}
            ),
            WriteOperation(
                operation="insert", entity_type="Sample", data={"id": ids[1], "name": "b"}
            ),
        ]
        result = client.validate_batch(ops)
        assert result.is_valid is True
        # The whole-set dry-run must not touch storage.
        for eid in ids:
            assert client._storage.read(eid) is None

    def test_assign_ids_false_leaves_id_absent(self, client: MosaicClient) -> None:
        ops = [WriteOperation(operation="insert", entity_type="Sample", data={"name": "x"})]
        result = client.validate_batch(ops, assign_ids=False)
        assert result.results[0].entity_id is None

    def test_empty_set_is_valid(self, client: MosaicClient) -> None:
        result = client.validate_batch([])
        assert result.is_valid is True
        assert result.results == []
