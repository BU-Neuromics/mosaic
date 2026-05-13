"""Unit tests for client.supersede_entity() — Gap 3."""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from hippo.core.client import HippoClient
from hippo.core.exceptions import EntityAlreadySupersededError, EntityNotFoundError
from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter
from tests.conftest import _build_minimal_schema_registry


class TestSupersededEntity:
    """Tests for client.supersede_entity() happy and error paths."""

    @pytest.fixture
    def db_path(self) -> str:
        """Create a temporary database path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.join(tmpdir, "test_supersede.db")

    @pytest.fixture
    def client(self, db_path: str) -> HippoClient:
        """Create a HippoClient with SQLite storage."""
        storage = SQLiteAdapter(db_path, schema_registry=_build_minimal_schema_registry())
        return HippoClient(storage=storage, bypass_validation=True)

    def test_supersede_entity_marks_source_as_unavailable(
        self, client: HippoClient
    ) -> None:
        """Happy path: source entity is unavailable after supersession."""
        client.put("Sample", {"id": "old-e1", "name": "old"})
        client.put("Sample", {"id": "new-e2", "name": "new"})

        client.supersede_entity("old-e1", "new-e2", reason="upgraded")

        # Source entity is now unavailable (read() returns None for unavailable entities).
        storage = client._storage
        assert storage.read("old-e1") is None

        # read_any() includes unavailable entities.
        entity = storage.read_any("old-e1")
        assert entity is not None
        assert entity.is_available is False
        assert entity.superseded_by == "new-e2"

    def test_supersede_entity_sets_superseded_by_column(
        self, client: HippoClient
    ) -> None:
        """superseded_by column is set to replacement_id after supersession."""
        client.put("Sample", {"id": "col-old", "name": "old"})
        client.put("Sample", {"id": "col-new", "name": "new"})

        client.supersede_entity("col-old", "col-new")

        entity = client._storage.read_any("col-old")
        assert entity.superseded_by == "col-new"

    def test_supersede_entity_writes_supersede_provenance_event(
        self, client: HippoClient
    ) -> None:
        """A 'supersede' provenance event is recorded on the source entity.

        Per sec9 §9.6 / Decision 9.6.B, "EntitySuperseded" maps to the
        ``supersede`` Operation enum; the replacement's id is carried in
        ``derived_from_id`` (not in the patch payload as under the legacy
        shape).
        """
        client.put("Sample", {"id": "prov-old", "name": "old"})
        client.put("Sample", {"id": "prov-new", "name": "new"})

        client.supersede_entity(
            "prov-old", "prov-new", reason="new version", actor="test-actor"
        )

        history = client.history("prov-old")
        superseded_events = [
            e for e in history if e["operation_type"] == "supersede"
        ]
        assert len(superseded_events) == 1

    def test_supersede_entity_writes_update_provenance_on_replacement(
        self, client: HippoClient
    ) -> None:
        """An 'update' provenance event is recorded on the replacement entity.

        Legacy "EntityUpdated" → ``update`` per Decision 9.6.B. The record
        notes the supersession relationship in the patch.
        """
        client.put("Sample", {"id": "rep-old", "name": "old"})
        client.put("Sample", {"id": "rep-new", "name": "new"})

        client.supersede_entity("rep-old", "rep-new")

        history = client.history("rep-new")
        # put() writes one 'create' event; supersede_entity adds one 'update'
        # event annotating rep-new as the active replacement for rep-old.
        update_events = [e for e in history if e["operation_type"] == "update"]
        assert len(update_events) == 1

    def test_supersede_entity_creates_relationship_edge(
        self, client: HippoClient
    ) -> None:
        """A superseded_by relationship edge is created from source to replacement."""
        client.put("Sample", {"id": "rel-old", "name": "old"})
        client.put("Sample", {"id": "rel-new", "name": "new"})

        client.supersede_entity("rel-old", "rel-new")

        storage = client._storage
        with storage._transaction() as conn:
            rel_store = storage._get_relationship_store(conn)
            rels = list(
                rel_store.find(
                    source_id="rel-old",
                    target_id="rel-new",
                    relationship_type="superseded_by",
                )
            )
        assert len(rels) == 1
        assert rels[0].source_id == "rel-old"
        assert rels[0].target_id == "rel-new"
        assert rels[0].relationship_type == "superseded_by"

    def test_already_superseded_raises_error_with_no_state_change(
        self, client: HippoClient
    ) -> None:
        """Calling supersede_entity() on an already-superseded entity raises EntityAlreadySupersededError."""
        client.put("Sample", {"id": "dup-old", "name": "old"})
        client.put("Sample", {"id": "dup-new", "name": "new"})
        client.put("Sample", {"id": "dup-another", "name": "another"})

        client.supersede_entity("dup-old", "dup-new")

        with pytest.raises(EntityAlreadySupersededError) as exc_info:
            client.supersede_entity("dup-old", "dup-another")

        assert exc_info.value.entity_id == "dup-old"
        assert exc_info.value.superseded_by == "dup-new"

        # No state change: the relationship edge to "dup-another" was not created.
        storage = client._storage
        with storage._transaction() as conn:
            rel_store = storage._get_relationship_store(conn)
            rels = list(
                rel_store.find(
                    source_id="dup-old",
                    target_id="dup-another",
                )
            )
        assert len(rels) == 0

    def test_nonexistent_source_entity_raises_error(self, client: HippoClient) -> None:
        """Calling supersede_entity() with a non-existent source raises EntityNotFoundError."""
        client.put("Sample", {"id": "real-new", "name": "new"})

        with pytest.raises(EntityNotFoundError):
            client.supersede_entity("does-not-exist", "real-new")

    def test_nonexistent_replacement_entity_raises_error(
        self, client: HippoClient
    ) -> None:
        """Calling supersede_entity() with a non-existent replacement raises EntityNotFoundError."""
        client.put("Sample", {"id": "real-old", "name": "old"})

        with pytest.raises(EntityNotFoundError):
            client.supersede_entity("real-old", "does-not-exist")

    def test_get_on_superseded_entity_raises_by_default(
        self, client: HippoClient
    ) -> None:
        """client.get() on a superseded entity raises EntityNotFoundError by default.

        Use include_unavailable=True to access superseded entities for audit/provenance.
        """
        client.put("Sample", {"id": "get-old", "name": "old"})
        client.put("Sample", {"id": "get-new", "name": "new"})

        client.supersede_entity("get-old", "get-new")

        with pytest.raises(EntityNotFoundError):
            client.get("Sample", "get-old")

    def test_get_on_superseded_entity_with_include_unavailable_returns_superseded_by_field(
        self, client: HippoClient
    ) -> None:
        """client.get(include_unavailable=True) returns superseded entity with superseded_by."""
        client.put("Sample", {"id": "get-old", "name": "old"})
        client.put("Sample", {"id": "get-new", "name": "new"})

        client.supersede_entity("get-old", "get-new")

        result = client.get("Sample", "get-old", include_unavailable=True)

        assert result["superseded_by"] == "get-new"
        assert result["id"] == "get-old"

    def test_get_on_non_superseded_entity_returns_none_superseded_by(
        self, client: HippoClient
    ) -> None:
        """client.get() on a non-superseded entity returns superseded_by as None."""
        client.put("Sample", {"id": "not-superseded", "name": "test"})

        result = client.get("Sample", "not-superseded")

        assert result.get("superseded_by") is None
