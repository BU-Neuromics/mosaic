"""Shared fixtures for TUI tests — a full in-memory fake backend."""

from __future__ import annotations

import math
from typing import Any

import pytest

from mosaic.tui.backend.protocol import (
    PAGE_SIZE,
    BackendCapabilities,
    BackendError,
    ConnectionInfo,
    EntityDetail,
    EntityTypeSchema,
    EntityTypeSummary,
    FieldInfo,
    PagedResult,
    ProvenanceEvent,
    RelationshipDeclaration,
    SchemaView,
    derive_relationships,
)


def make_schema() -> SchemaView:
    """A small two-type schema: Sample → Project."""
    project = EntityTypeSchema(
        name="Project",
        description="A research project",
        fields=[
            FieldInfo("name", "string", required=True, indexed=True),
            FieldInfo("description", "string"),
        ],
    )
    sample = EntityTypeSchema(
        name="Sample",
        description="A physical sample",
        fields=[
            FieldInfo("name", "string", required=True),
            FieldInfo("project_id", "Project", ref_target="Project", indexed=True),
            FieldInfo(
                "status",
                "SampleStatus",
                enum_values=["active", "archived", "distributed"],
            ),
            FieldInfo("volume_ml", "float"),
            FieldInfo("tags", "string", multivalued=True),
            FieldInfo("frozen", "boolean"),
        ],
    )
    return SchemaView(
        entity_types=[project, sample],
        relationships=[
            RelationshipDeclaration("Sample", "project_id", "Project"),
        ],
    )


class FakeBackend:
    """In-memory TUIBackend with call recording, for UI tests."""

    def __init__(
        self,
        schema: SchemaView | None = None,
        supports_filters: bool = True,
        supports_fts: bool = True,
    ) -> None:
        self.schema = schema or make_schema()
        self.supports_filters = supports_filters
        self.supports_fts = supports_fts
        #: entity_type -> entity_id -> record dict
        self.entities: dict[str, dict[str, dict[str, Any]]] = {}
        #: entity_id -> list[ProvenanceEvent] (newest first)
        self.provenance: dict[str, list[ProvenanceEvent]] = {}
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self._next_id = 0

    # -- seeding helpers ------------------------------------------------

    def seed(self, entity_type: str, data: dict[str, Any]) -> str:
        entity_id = f"{entity_type.lower()}-{self._next_id}"
        self._next_id += 1
        self.entities.setdefault(entity_type, {})[entity_id] = {
            "id": entity_id,
            "entity_type": entity_type,
            "data": dict(data),
            "version": 1,
            "is_available": True,
            "created_at": "2026-06-01T10:00:00+00:00",
            "updated_at": "2026-06-01T10:00:00+00:00",
            "schema_version": "1.0.0",
            "created_by": "tester",
            "updated_by": "tester",
            "superseded_by": None,
        }
        self.provenance[entity_id] = [
            ProvenanceEvent("create", "2026-06-01T10:00:00+00:00", "tester", dict(data))
        ]
        return entity_id

    # -- protocol -------------------------------------------------------

    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            supports_filters=self.supports_filters, supports_fts=self.supports_fts
        )

    async def connection_info(self) -> ConnectionInfo:
        return ConnectionInfo(mode="sdk", target="fake.db", ok=True, detail="fake")

    async def list_entity_types(self) -> list[EntityTypeSummary]:
        self.calls.append(("list_entity_types", ()))
        return [
            EntityTypeSummary(
                name=et.name,
                count=len(self.entities.get(et.name, {})),
                description=et.description,
            )
            for et in self.schema.entity_types
        ]

    async def list_entities(
        self, entity_type: str, page: int = 1, filter_text: str = ""
    ) -> PagedResult:
        self.calls.append(("list_entities", (entity_type, page, filter_text)))
        items = [
            record
            for record in self.entities.get(entity_type, {}).values()
            if record["is_available"]
        ]
        if filter_text:
            lowered = filter_text.lower()
            items = [i for i in items if lowered in str(i).lower()]
        total = len(items)
        total_pages = max(1, math.ceil(total / PAGE_SIZE))
        page = max(1, min(page, total_pages))
        offset = (page - 1) * PAGE_SIZE
        return PagedResult(
            items=items[offset : offset + PAGE_SIZE],
            page=page,
            total_pages=total_pages,
            total_items=total,
        )

    async def query_entities(
        self,
        entity_type: str,
        filters: list[dict[str, Any]] | None = None,
        filter_mode: str = "and",
        page: int = 1,
    ) -> PagedResult:
        self.calls.append(("query_entities", (entity_type, filters, filter_mode, page)))
        items = [
            record
            for record in self.entities.get(entity_type, {}).values()
            if record["is_available"]
        ]
        if filters:
            def matches(record: dict[str, Any]) -> bool:
                hits = [
                    str(record["data"].get(f["field"])) == str(f["value"])
                    for f in filters
                ]
                return all(hits) if filter_mode == "and" else any(hits)

            items = [i for i in items if matches(i)]
        return PagedResult(
            items=items, page=1, total_pages=1, total_items=len(items)
        )

    async def search_entities(
        self, entity_type: str, query: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        self.calls.append(("search_entities", (entity_type, query, limit)))
        lowered = query.lower()
        return [
            record
            for record in self.entities.get(entity_type, {}).values()
            if lowered in str(record["data"]).lower()
        ][:limit]

    async def get_entity(self, entity_type: str, entity_id: str) -> EntityDetail:
        self.calls.append(("get_entity", (entity_type, entity_id)))
        record = self.entities.get(entity_type, {}).get(entity_id)
        if record is None:
            raise BackendError(f"Could not load {entity_type} {entity_id}")
        data = dict(record["data"])
        fields = {
            k: record[k]
            for k in (
                "id",
                "is_available",
                "version",
                "created_at",
                "updated_at",
                "schema_version",
            )
        }
        fields.update(data)
        return EntityDetail(
            id=entity_id,
            entity_type=entity_type,
            fields=fields,
            relationships=derive_relationships(self.schema, entity_type, data),
            data=data,
        )

    async def get_schema(self) -> SchemaView:
        self.calls.append(("get_schema", ()))
        return self.schema

    async def get_provenance(
        self, entity_type: str, entity_id: str
    ) -> list[ProvenanceEvent]:
        self.calls.append(("get_provenance", (entity_type, entity_id)))
        return list(self.provenance.get(entity_id, []))

    async def create_entity(self, entity_type: str, data: dict[str, Any]) -> str:
        self.calls.append(("create_entity", (entity_type, data)))
        et = self.schema.get_entity_type(entity_type)
        if et is not None:
            missing = [
                f.name for f in et.fields if f.required and not data.get(f.name)
            ]
            if missing:
                raise BackendError(f"Validation failed: missing {missing}")
        return self.seed(entity_type, data)

    async def update_entity(
        self, entity_type: str, entity_id: str, data: dict[str, Any]
    ) -> None:
        self.calls.append(("update_entity", (entity_type, entity_id, data)))
        record = self.entities.get(entity_type, {}).get(entity_id)
        if record is None:
            raise BackendError(f"Entity not found: {entity_id}")
        record["data"] = dict(data)
        record["version"] += 1
        self.provenance[entity_id].insert(
            0,
            ProvenanceEvent("update", "2026-06-02T10:00:00+00:00", "tester", dict(data)),
        )

    async def set_availability(
        self,
        entity_type: str,
        entity_id: str,
        is_available: bool,
        reason: str | None = None,
    ) -> None:
        self.calls.append(
            ("set_availability", (entity_type, entity_id, is_available, reason))
        )
        record = self.entities.get(entity_type, {}).get(entity_id)
        if record is None:
            raise BackendError(f"Entity not found: {entity_id}")
        record["is_available"] = is_available
        self.provenance[entity_id].insert(
            0,
            ProvenanceEvent(
                "availability_change",
                "2026-06-03T10:00:00+00:00",
                "tester",
                {"is_available": is_available, "reason": reason},
            ),
        )


@pytest.fixture
def fake_backend() -> FakeBackend:
    return FakeBackend()


@pytest.fixture
def seeded_fake_backend() -> FakeBackend:
    backend = FakeBackend()
    project_id = backend.seed("Project", {"name": "Alpha", "description": "first"})
    backend.seed(
        "Sample",
        {
            "name": "S1",
            "project_id": project_id,
            "status": "active",
            "volume_ml": 1.5,
        },
    )
    backend.seed("Sample", {"name": "S2", "project_id": project_id})
    return backend
