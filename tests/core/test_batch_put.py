"""Tests for atomic multi-entity write (batch_put).

Increment 2 of the batch unit-of-work (BU-Neuromics/hippo#84): commit a set of
related entities all-or-nothing inside a single staged transaction, with
intra-batch relationship forward-references resolved.
"""

import os
import tempfile

import pytest

from mosaic.core.client import MosaicClient
from mosaic.core.storage.adapters.sqlite_adapter import SQLiteAdapter
from mosaic.core.validation import (
    BatchWriteResult,
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


@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield os.path.join(tmpdir, "test_batch_put.db")


@pytest.fixture
def client(db_path: str) -> MosaicClient:
    storage = SQLiteAdapter(db_path, schema_registry=_build_minimal_schema_registry())
    c = MosaicClient(storage=storage)
    c.add_validator(_NameRequiredValidator())
    return c


class TestBatchPut:
    def test_commits_valid_set_atomically(self, client: MosaicClient) -> None:
        ops = [
            WriteOperation(operation="insert", entity_type="Sample", data={"id": "s1", "name": "a"}),
            WriteOperation(operation="insert", entity_type="Sample", data={"id": "s2", "name": "b"}),
        ]
        result = client.batch_put(ops)
        assert isinstance(result, BatchWriteResult)
        assert result.committed is True
        assert result.dry_run is False
        assert len(result.entities) == 2
        assert client._storage.read("s1") is not None
        assert client._storage.read("s2") is not None

    def test_invalid_set_writes_nothing(self, client: MosaicClient) -> None:
        ops = [
            WriteOperation(operation="insert", entity_type="Sample", data={"id": "ok", "name": "a"}),
            WriteOperation(operation="insert", entity_type="Sample", data={"id": "bad"}),  # no name
        ]
        result = client.batch_put(ops)
        assert result.committed is False
        assert result.is_valid is False
        # All-or-nothing: the valid sibling is not written either.
        assert client._storage.read("ok") is None
        assert client._storage.read("bad") is None

    def test_dry_run_validates_but_writes_nothing(self, client: MosaicClient) -> None:
        ops = [
            WriteOperation(operation="insert", entity_type="Sample", data={"id": "d1", "name": "a"}),
            WriteOperation(operation="insert", entity_type="Sample", data={"id": "d2", "name": "b"}),
        ]
        result = client.batch_put(ops, dry_run=True)
        assert result.committed is False
        assert result.dry_run is True
        assert result.is_valid is True
        # Plan is reported ...
        assert {e["id"] for e in result.entities} == {"d1", "d2"}
        # ... but nothing is written.
        assert client._storage.read("d1") is None
        assert client._storage.read("d2") is None

    def test_rollback_on_mid_batch_failure(
        self, client: MosaicClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ops = [
            WriteOperation(operation="insert", entity_type="Sample", data={"id": "r1", "name": "a"}),
            WriteOperation(operation="insert", entity_type="Sample", data={"id": "r2", "name": "b"}),
        ]
        orig = client._put_internal
        calls = {"n": 0}

        def failing(entity_type, data, entity_id=None):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("boom on second write")
            return orig(entity_type, data, entity_id)

        monkeypatch.setattr(client, "_put_internal", failing)

        with pytest.raises(RuntimeError, match="boom on second write"):
            client.batch_put(ops)

        # The first (uncommitted) write must have rolled back with the second.
        assert client._storage.read("r1") is None
        assert client._storage.read("r2") is None

    def test_intra_batch_relationship_forward_reference(
        self, client: MosaicClient
    ) -> None:
        # The sample references a donor created in the SAME batch — the edge
        # must resolve even though the donor did not pre-exist.
        ops = [
            WriteOperation(operation="insert", entity_type="Donor", data={"id": "donor-1", "name": "D"}),
            WriteOperation(operation="insert", entity_type="Sample", data={"id": "sample-1", "name": "S"}),
        ]
        rels = [
            {"source_id": "donor-1", "target_id": "sample-1", "relationship_type": "donated"}
        ]
        result = client.batch_put(ops, relationships=rels)
        assert result.committed is True
        assert client._storage.read("donor-1") is not None
        assert client._storage.read("sample-1") is not None
        assert len(result.relationships) == 1
        assert result.relationships[0]["source_id"] == "donor-1"
        assert result.relationships[0]["target_id"] == "sample-1"

    def test_relationship_failure_rolls_back_entities(
        self, client: MosaicClient
    ) -> None:
        # A relationship to a non-existent (and not-in-batch) target must fail
        # and roll back the entities written earlier in the same batch.
        ops = [
            WriteOperation(operation="insert", entity_type="Donor", data={"id": "donor-x", "name": "D"}),
        ]
        rels = [
            {"source_id": "donor-x", "target_id": "missing", "relationship_type": "donated"}
        ]
        with pytest.raises(Exception):
            client.batch_put(ops, relationships=rels)
        assert client._storage.read("donor-x") is None

    def test_assigns_ids_without_mutating_caller_data(self, client: MosaicClient) -> None:
        data = {"name": "a"}
        ops = [WriteOperation(operation="insert", entity_type="Sample", data=data)]
        result = client.batch_put(ops)
        assert result.committed is True
        # Caller's dict untouched ...
        assert "id" not in data
        # ... but an id was assigned and the entity persisted.
        assigned_id = result.entities[0]["id"]
        assert client._storage.read(assigned_id) is not None
