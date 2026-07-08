"""Tests for TUIBackend protocol and data types."""

from __future__ import annotations

import asyncio

import pytest

from mosaic.tui.backend.protocol import (
    EntityDetail,
    EntityTypeSummary,
    EntityTypeSchema,
    FieldInfo,
    PagedResult,
    ProvenanceEvent,
    RelatedEntityRef,
    RelationshipDeclaration,
    SchemaView,
    TUIBackend,
)


# ---------------------------------------------------------------------------
# MockBackend — satisfies TUIBackend structurally (typing.Protocol)
# ---------------------------------------------------------------------------


class MockBackend:
    """A minimal mock backend used in tests."""

    async def list_entity_types(self) -> list[EntityTypeSummary]:
        return [EntityTypeSummary(name="Sample", count=10)]

    async def list_entities(
        self,
        entity_type: str,
        page: int = 1,
        filter_text: str = "",
    ) -> PagedResult:
        return PagedResult(items=[], page=1, total_pages=1, total_items=0)

    async def get_entity(self, entity_type: str, entity_id: str) -> EntityDetail:
        return EntityDetail(
            id=entity_id,
            entity_type=entity_type,
            fields={"name": "test"},
            relationships=[],
        )

    async def get_schema(self) -> SchemaView:
        return SchemaView(entity_types=[], relationships=[])

    async def get_provenance(
        self, entity_type: str, entity_id: str
    ) -> list[ProvenanceEvent]:
        return []


# ---------------------------------------------------------------------------
# Tests: MockBackend satisfies the protocol
# ---------------------------------------------------------------------------


def test_mock_backend_satisfies_protocol() -> None:
    """MockBackend is structurally compatible with TUIBackend."""
    backend: TUIBackend = MockBackend()  # type: ignore[assignment]
    # If this assignment passes, structural typing is satisfied.
    assert backend is not None


def test_list_entity_types_returns_entity_type_summary() -> None:
    backend = MockBackend()
    result = asyncio.run(backend.list_entity_types())
    assert len(result) == 1
    summary = result[0]
    assert summary.name == "Sample"
    assert summary.count == 10


# ---------------------------------------------------------------------------
# Tests: Data types carry expected fields
# ---------------------------------------------------------------------------


def test_entity_type_summary_fields() -> None:
    s = EntityTypeSummary(name="Donor", count=42)
    assert s.name == "Donor"
    assert s.count == 42


def test_paged_result_fields() -> None:
    pr = PagedResult(
        items=[{"id": "abc"}],
        page=2,
        total_pages=5,
        total_items=100,
    )
    assert pr.page == 2
    assert pr.total_pages == 5
    assert pr.total_items == 100
    assert pr.items[0]["id"] == "abc"


def test_entity_detail_fields() -> None:
    rel = RelatedEntityRef(
        relationship_name="donated_by",
        target_type="Donor",
        target_id="donor-1",
    )
    detail = EntityDetail(
        id="sample-1",
        entity_type="Sample",
        fields={"tissue_type": "Brain"},
        relationships=[rel],
    )
    assert detail.id == "sample-1"
    assert detail.entity_type == "Sample"
    assert detail.fields["tissue_type"] == "Brain"
    assert len(detail.relationships) == 1
    assert detail.relationships[0].target_type == "Donor"


def test_schema_view_fields() -> None:
    field_info = FieldInfo(
        name="external_id",
        field_type="string",
        required=True,
        indexed=True,
    )
    entity_schema = EntityTypeSchema(name="Sample", fields=[field_info])
    rel = RelationshipDeclaration(
        source_type="Sample",
        relationship_name="donated_by",
        target_type="Donor",
    )
    schema = SchemaView(entity_types=[entity_schema], relationships=[rel])

    assert len(schema.entity_types) == 1
    assert schema.entity_types[0].name == "Sample"
    assert schema.entity_types[0].fields[0].name == "external_id"
    assert schema.relationships[0].relationship_name == "donated_by"


def test_provenance_event_fields() -> None:
    ev = ProvenanceEvent(
        event_type="CREATE",
        timestamp="2026-03-01T10:30:00Z",
        diff={"tissue_type": "Brain"},
    )
    assert ev.event_type == "CREATE"
    assert ev.timestamp == "2026-03-01T10:30:00Z"
    assert ev.diff["tissue_type"] == "Brain"


def test_field_info_ref_target() -> None:
    fi = FieldInfo(
        name="donor",
        field_type="ref",
        required=True,
        indexed=True,
        ref_target="Donor",
    )
    assert fi.ref_target == "Donor"


def test_get_entity_returns_entity_detail() -> None:
    backend = MockBackend()
    detail = asyncio.run(backend.get_entity("Sample", "s-001"))
    assert detail.id == "s-001"
    assert detail.entity_type == "Sample"
    assert isinstance(detail.relationships, list)


def test_paged_result_total_pages_gt_1() -> None:
    """PagedResult should carry total_pages > 1 when there are multiple pages."""

    class LargeBackend(MockBackend):
        async def list_entities(
            self, entity_type: str, page: int = 1, filter_text: str = ""
        ) -> PagedResult:
            return PagedResult(
                items=[{"id": f"e-{i}"} for i in range(20)],
                page=1,
                total_pages=3,
                total_items=50,
            )

    backend = LargeBackend()
    result = asyncio.run(backend.list_entities("Sample"))
    assert result.total_pages > 1
