"""Unit tests for HippoClient availability filtering.

TDD cycle — RED phase.

These tests specify the desired behavior for the three API gaps identified
via contract/platform test xfails:

  1. get() raises EntityNotFoundError for deleted entities by default
  2. get() raises EntityNotFoundError for superseded entities by default
  3. get(include_unavailable=True) returns deleted/superseded entities
  4. update() raises EntityNotFoundError when entity_id does not exist

See TESTING.md § TDD Policy for the full workflow.
Xfails in tests/contracts/ and tests/platform/ will be converted to hard
assertions once this test file passes (GREEN phase).

Implementation target: hippo/src/hippo/core/client.py
  - get(): add include_unavailable=False param; raise on is_available=False by default
  - update(): add existence check before write
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hippo.core.client import HippoClient
from hippo.core.exceptions import EntityNotFoundError
from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter


@pytest.fixture()
def client(tmp_path: Path) -> HippoClient:
    storage = SQLiteAdapter(str(tmp_path / "hippo.db"))
    return HippoClient(storage=storage)


# ---------------------------------------------------------------------------
# get() — deleted entities
# ---------------------------------------------------------------------------

class TestGetDeletedEntity:

    def test_get_deleted_entity_raises_by_default(self, client):
        """get() must raise EntityNotFoundError for a deleted entity.

        Deleted entities have is_available=False in the storage layer.
        The default behavior (include_unavailable=False) must treat them
        as not found, consistent with query() which already excludes them.
        """
        entity = client.create("Sample", {"name": "S001"})
        client.delete("Sample", entity["id"])

        with pytest.raises(EntityNotFoundError):
            client.get("Sample", entity["id"])

    def test_get_deleted_entity_with_include_unavailable_returns_entity(self, client):
        """get(include_unavailable=True) must return deleted entities.

        Used for audit queries, provenance lookups, and debugging.
        """
        entity = client.create("Sample", {"name": "S001"})
        client.delete("Sample", entity["id"])

        result = client.get("Sample", entity["id"], include_unavailable=True)

        assert result["id"] == entity["id"]
        assert result["data"]["name"] == "S001"

    def test_get_available_entity_unaffected_by_include_unavailable_false(self, client):
        """get() must continue to return available entities when include_unavailable=False."""
        entity = client.create("Sample", {"name": "S001"})

        result = client.get("Sample", entity["id"])
        assert result["id"] == entity["id"]

    def test_get_available_entity_unaffected_by_include_unavailable_true(self, client):
        """get(include_unavailable=True) must also return normal available entities."""
        entity = client.create("Sample", {"name": "S001"})

        result = client.get("Sample", entity["id"], include_unavailable=True)
        assert result["id"] == entity["id"]

    def test_get_deleted_entity_different_type_still_raises(self, client):
        """get() with wrong entity_type raises even with include_unavailable=True."""
        entity = client.create("Sample", {"name": "S001"})
        client.delete("Sample", entity["id"])

        with pytest.raises(EntityNotFoundError):
            client.get("WrongType", entity["id"], include_unavailable=True)


# ---------------------------------------------------------------------------
# get() — superseded entities
# ---------------------------------------------------------------------------

class TestGetSupersededEntity:

    def test_get_superseded_entity_raises_by_default(self, client):
        """get() must raise EntityNotFoundError for a superseded entity.

        Superseded entities have is_available=False and superseded_by set.
        Default behavior must treat them as not found.
        """
        old = client.create("Sample", {"name": "S001"})
        new = client.create("Sample", {"name": "S002"})
        client.supersede_entity(old["id"], new["id"])

        with pytest.raises(EntityNotFoundError):
            client.get("Sample", old["id"])

    def test_get_superseded_entity_with_include_unavailable_returns_entity(self, client):
        """get(include_unavailable=True) must return superseded entities.

        Used to trace supersession chains and audit artifact provenance.
        """
        old = client.create("Sample", {"name": "S001"})
        new = client.create("Sample", {"name": "S002"})
        client.supersede_entity(old["id"], new["id"])

        result = client.get("Sample", old["id"], include_unavailable=True)

        assert result["id"] == old["id"]
        assert result["data"]["name"] == "S001"

    def test_get_superseded_entity_result_has_superseded_by_field(self, client):
        """get(include_unavailable=True) on superseded entity includes superseded_by."""
        old = client.create("Sample", {"name": "S001"})
        new = client.create("Sample", {"name": "S002"})
        client.supersede_entity(old["id"], new["id"])

        result = client.get("Sample", old["id"], include_unavailable=True)

        assert result.get("superseded_by") == new["id"], (
            "Result must expose superseded_by so callers can trace the chain"
        )

    def test_get_replacement_entity_still_available_after_supersede(self, client):
        """The replacement entity must remain accessible via normal get()."""
        old = client.create("Sample", {"name": "S001"})
        new = client.create("Sample", {"name": "S002"})
        client.supersede_entity(old["id"], new["id"])

        result = client.get("Sample", new["id"])
        assert result["id"] == new["id"]


# ---------------------------------------------------------------------------
# get() — nonexistent entity (regression)
# ---------------------------------------------------------------------------

class TestGetNonexistentRegression:
    """Existing behavior must not regress with the new include_unavailable param."""

    def test_get_nonexistent_raises_entity_not_found(self, client):
        with pytest.raises(EntityNotFoundError):
            client.get("Sample", "00000000-0000-0000-0000-000000000000")

    def test_get_nonexistent_with_include_unavailable_still_raises(self, client):
        """include_unavailable=True does not conjure entities out of thin air."""
        with pytest.raises(EntityNotFoundError):
            client.get(
                "Sample",
                "00000000-0000-0000-0000-000000000000",
                include_unavailable=True,
            )

    def test_get_wrong_type_raises_entity_not_found(self, client):
        entity = client.create("Sample", {"name": "S001"})
        with pytest.raises(EntityNotFoundError):
            client.get("WrongType", entity["id"])


# ---------------------------------------------------------------------------
# update() — existence check
# ---------------------------------------------------------------------------

class TestUpdateExistenceCheck:

    def test_update_nonexistent_id_raises_entity_not_found(self, client):
        """update() must raise EntityNotFoundError when entity_id does not exist.

        Currently update() silently upserts (creates a new entity with the
        provided id). This is a data integrity bug — callers expect update()
        to only mutate existing entities.
        """
        with pytest.raises(EntityNotFoundError):
            client.update(
                "Sample",
                "00000000-0000-0000-0000-000000000000",
                {"name": "S001"},
            )

    def test_update_existing_entity_succeeds(self, client):
        """Regression: update() on an existing entity must still work."""
        entity = client.create("Sample", {"name": "S001"})
        result = client.update("Sample", entity["id"], {"name": "S001-v2"})

        assert result["id"] == entity["id"]
        assert result["data"]["name"] == "S001-v2"
        assert result["version"] == 2

    def test_update_deleted_entity_raises(self, client):
        """update() on a deleted entity must raise EntityNotFoundError.

        A deleted entity is no longer available and should not be mutable.
        This prevents silent resurrection of soft-deleted records.
        """
        entity = client.create("Sample", {"name": "S001"})
        client.delete("Sample", entity["id"])

        with pytest.raises(EntityNotFoundError):
            client.update("Sample", entity["id"], {"name": "S001-v2"})

    def test_update_superseded_entity_raises(self, client):
        """update() on a superseded entity must raise EntityNotFoundError.

        A superseded entity has been replaced and should not be mutable.
        """
        old = client.create("Sample", {"name": "S001"})
        new = client.create("Sample", {"name": "S002"})
        client.supersede_entity(old["id"], new["id"])

        with pytest.raises(EntityNotFoundError):
            client.update("Sample", old["id"], {"name": "S001-updated"})
