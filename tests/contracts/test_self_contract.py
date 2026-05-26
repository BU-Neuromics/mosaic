"""Contract tests: Hippo's own behavioral invariants.

These are the behavioral guarantees Hippo makes to ALL consumers, not just
Canon. They document the public API contract independently of any consumer.

When these fail it means Hippo changed a behavioral invariant. Bump Hippo's
version and update all consumer contracts accordingly.

See TESTING.md for the full failure protocol.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

_root = Path(__file__).parent.parent.parent
_p = str(_root / "src")
if _p not in sys.path:
    sys.path.insert(0, _p)

from hippo.core.client import HippoClient
from hippo.core.exceptions import EntityNotFoundError, ValidationFailure
from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter
from hippo.core.pipeline import ValidationPipeline
from hippo.core.validators.write_validator import CELWriteValidator


def _make_client(tmp_path: Path, schema: dict | None = None, validators: dict | None = None) -> HippoClient:
    storage = SQLiteAdapter(str(tmp_path / "hippo.db"))
    if schema is None and validators is None:
        return HippoClient(storage=storage)

    schema_path = tmp_path / "schema.yaml"
    if schema:
        schema_path.write_text(yaml.dump(schema))

    pipeline = ValidationPipeline()
    if validators:
        validators_path = tmp_path / "validators.yaml"
        validators_path.write_text(yaml.dump(validators))
        cel_validator = CELWriteValidator(validators_path=str(validators_path))
        pipeline.add_validator(cel_validator)

    return HippoClient(storage=storage, pipeline=pipeline)


# ---------------------------------------------------------------------------
# INVARIANT: Entity identity
# ---------------------------------------------------------------------------

class TestEntityIdentityInvariants:
    """IDs must be stable, unique, and string UUIDs."""

    def test_id_is_string(self, tmp_path):
        client = _make_client(tmp_path)
        result = client.create("Sample", {"name": "S001"})
        assert isinstance(result["id"], str)

    def test_id_is_unique_across_creates(self, tmp_path):
        client = _make_client(tmp_path)
        r1 = client.create("Sample", {"name": "S001"})
        r2 = client.create("Sample", {"name": "S002"})
        assert r1["id"] != r2["id"]

    def test_id_stable_across_update(self, tmp_path):
        client = _make_client(tmp_path)
        created = client.create("Sample", {"name": "S001"})
        updated = client.update("Sample", created["id"], {"name": "S001-v2"})
        assert updated["id"] == created["id"]

    def test_entity_type_preserved_across_update(self, tmp_path):
        client = _make_client(tmp_path)
        created = client.create("Sample", {"name": "S001"})
        updated = client.update("Sample", created["id"], {"name": "S001-v2"})
        assert updated["entity_type"] == "Sample"


# ---------------------------------------------------------------------------
# INVARIANT: Version monotonicity
# ---------------------------------------------------------------------------

class TestVersionInvariants:
    """Version must start at 1 and increment by 1 on each update."""

    def test_initial_version_is_1(self, tmp_path):
        client = _make_client(tmp_path)
        result = client.create("Sample", {"name": "S001"})
        assert result["version"] == 1

    def test_update_increments_version(self, tmp_path):
        client = _make_client(tmp_path)
        created = client.create("Sample", {"name": "S001"})
        v2 = client.update("Sample", created["id"], {"name": "S001-v2"})
        assert v2["version"] == 2

    def test_version_increments_monotonically(self, tmp_path):
        client = _make_client(tmp_path)
        r = client.create("Sample", {"name": "S001"})
        for i in range(2, 6):
            r = client.update("Sample", r["id"], {"name": f"S{i:03d}"})
            assert r["version"] == i


# ---------------------------------------------------------------------------
# INVARIANT: Provenance timestamps
# ---------------------------------------------------------------------------

class TestProvenanceInvariants:
    """created_at and updated_at must be present on create and update."""

    def test_create_sets_created_at(self, tmp_path):
        client = _make_client(tmp_path)
        result = client.create("Sample", {"name": "S001"})
        assert "created_at" in result
        assert result["created_at"] is not None

    def test_create_sets_updated_at(self, tmp_path):
        client = _make_client(tmp_path)
        result = client.create("Sample", {"name": "S001"})
        assert "updated_at" in result

    def test_update_sets_updated_at(self, tmp_path):
        client = _make_client(tmp_path)
        created = client.create("Sample", {"name": "S001"})
        updated = client.update("Sample", created["id"], {"name": "S002"})
        assert "updated_at" in updated


# ---------------------------------------------------------------------------
# INVARIANT: Not-found errors
# ---------------------------------------------------------------------------

class TestNotFoundInvariants:
    """get() must raise EntityNotFoundError for missing entities, not return None."""

    def test_get_nonexistent_raises(self, tmp_path):
        client = _make_client(tmp_path)
        with pytest.raises(EntityNotFoundError):
            client.get("Sample", "00000000-0000-0000-0000-000000000000")

    def test_update_nonexistent_raises(self, tmp_path):
        client = _make_client(tmp_path)
        with pytest.raises(EntityNotFoundError):
            client.update("Sample", "00000000-0000-0000-0000-000000000000", {"name": "X"})

    def test_get_wrong_type_raises(self, tmp_path):
        client = _make_client(tmp_path)
        created = client.create("Sample", {"name": "S001"})
        with pytest.raises(EntityNotFoundError):
            client.get("WrongType", created["id"])


# ---------------------------------------------------------------------------
# INVARIANT: Delete soft-semantics
# ---------------------------------------------------------------------------

class TestDeleteInvariants:
    """delete() excludes from query() but is soft (entity still exists in storage)."""

    def test_delete_returns_true(self, tmp_path):
        client = _make_client(tmp_path)
        r = client.create("Sample", {"name": "S001"})
        assert client.delete("Sample", r["id"]) is True

    def test_deleted_excluded_from_query(self, tmp_path):
        client = _make_client(tmp_path)
        r1 = client.create("Sample", {"name": "S001"})
        client.create("Sample", {"name": "S002"})
        client.delete("Sample", r1["id"])
        ids = [i["id"] for i in client.query("Sample").items]
        assert r1["id"] not in ids

    def test_delete_count_reflected_in_query(self, tmp_path):
        client = _make_client(tmp_path)
        r = client.create("Sample", {"name": "S001"})
        client.create("Sample", {"name": "S002"})
        before = len(list(client.query("Sample").items))
        client.delete("Sample", r["id"])
        after = len(list(client.query("Sample").items))
        assert after == before - 1


# ---------------------------------------------------------------------------
# INVARIANT: CEL validation
# ---------------------------------------------------------------------------

class TestCELValidationInvariants:
    """CEL validators must block creates/updates that violate rules."""

    _SCHEMA = {
        "entities": [{
            "name": "Sample",
            "version": "1.0",
            "fields": [
                {"name": "name", "type": "string", "required": True},
                {"name": "tissue", "type": "string", "required": True},
            ],
        }]
    }

    _VALIDATORS = {
        "validators": [{
            "name": "sample_name_format",
            "entity_type": "Sample",
            "operations": ["create", "update"],
            "condition": 'entity.name.matches("^S[0-9]{3}$")',
            "message": "Name must match S###",
        }]
    }

    def test_valid_entity_passes_validation(self, tmp_path):
        client = _make_client(tmp_path, self._SCHEMA, self._VALIDATORS)
        result = client.create("Sample", {"name": "S001", "tissue": "DLPFC"})
        assert result["data"]["name"] == "S001"

    def test_invalid_entity_raises_validation_failure(self, tmp_path):
        client = _make_client(tmp_path, self._SCHEMA, self._VALIDATORS)
        with pytest.raises(ValidationFailure):
            client.create("Sample", {"name": "INVALID", "tissue": "DLPFC"})

    def test_update_also_validated(self, tmp_path):
        client = _make_client(tmp_path, self._SCHEMA, self._VALIDATORS)
        r = client.create("Sample", {"name": "S001", "tissue": "DLPFC"})
        with pytest.raises(ValidationFailure):
            client.update("Sample", r["id"], {"name": "INVALID", "tissue": "HC"})

    def test_validation_error_does_not_persist_entity(self, tmp_path):
        client = _make_client(tmp_path, self._SCHEMA, self._VALIDATORS)
        try:
            client.create("Sample", {"name": "BAD", "tissue": "DLPFC"})
        except (ValidationFailure, Exception):
            pass
        result = client.query("Sample")
        assert list(result.items) == [], (
            "Failed create must not persist any partial entity"
        )


# ---------------------------------------------------------------------------
# INVARIANT: Supersession
# ---------------------------------------------------------------------------

class TestSupersessionInvariants:
    """supersede_entity() must exclude old from query() and keep new available."""

    def test_superseded_excluded_from_query(self, tmp_path):
        client = _make_client(tmp_path)
        old = client.create("Sample", {"name": "S001"})
        new = client.create("Sample", {"name": "S002"})
        client.supersede_entity(old["id"], new["id"])
        ids = [i["id"] for i in client.query("Sample").items]
        assert old["id"] not in ids

    def test_replacement_still_in_query(self, tmp_path):
        client = _make_client(tmp_path)
        old = client.create("Sample", {"name": "S001"})
        new = client.create("Sample", {"name": "S002"})
        client.supersede_entity(old["id"], new["id"])
        ids = [i["id"] for i in client.query("Sample").items]
        assert new["id"] in ids

    def test_double_supersede_raises(self, tmp_path):
        client = _make_client(tmp_path)
        old = client.create("Sample", {"name": "S001"})
        new = client.create("Sample", {"name": "S002"})
        newer = client.create("Sample", {"name": "S003"})
        client.supersede_entity(old["id"], new["id"])
        with pytest.raises(Exception):
            client.supersede_entity(old["id"], newer["id"])
