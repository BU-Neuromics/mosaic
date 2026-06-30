"""Query/Mutation generation and SDK delegation for the GraphQL transport.

Every resolver is a THIN wrapper over ``HippoClient`` — the same
SDK-first contract the REST routers follow (sec2 §2.7, sec4 §4.1).
Resolvers never touch storage adapters or validation pipelines
directly; they translate GraphQL arguments to SDK calls and SDK
envelopes/errors back to GraphQL shapes.

Error mapping: SDK validation failures surface as structured GraphQL
errors with ``extensions.code = "VALIDATION_FAILED"`` and, when the
sec9 §9.9 envelope is available, the tier-annotated ``failures`` list.
Missing entities map to ``extensions.code = "NOT_FOUND"``.
"""

from __future__ import annotations

import enum
from typing import Any, Optional

import strawberry
from graphql import GraphQLError
from strawberry.extensions import QueryDepthLimiter
from strawberry.scalars import JSON
from strawberry.tools import create_type
from strawberry.types import Info

from hippo.core.exceptions import (
    EntityAlreadySupersededError,
    EntityNotFoundError,
    ValidationError as HippoValidationError,
    ValidationFailed,
    ValidationFailure,
)
from hippo.core.schema_typing import EntityTypeModel
from hippo.core.validation.validators import WriteOperation
from hippo.graphql import DEFAULT_MAX_QUERY_DEPTH
from hippo.graphql.schema_builder import (
    EntityGraphQLInfo,
    GraphQLTypeBuilder,
    ISODateTime,
    camel_case,
)
from hippo.linkml_bridge import SchemaRegistry


@strawberry.enum(description="How multiple filters compose (SDK filter_mode).")
class FilterMode(enum.Enum):
    AND = "and"
    OR = "or"


@strawberry.input(description="Field/value equality filter (SDK query filter).")
class FilterInput:
    field: str
    value: JSON


@strawberry.type(
    description=(
        "One provenance log entry for an entity (append-only audit "
        "trail; see sec6/sec9 §9.6)."
    )
)
class ProvenanceEntry:
    operation_id: Optional[strawberry.ID]
    entity_id: Optional[strawberry.ID]
    entity_type: Optional[str]
    operation: Optional[str]
    timestamp: Optional[ISODateTime]
    actor_id: Optional[str]
    patch: Optional[JSON]


@strawberry.type(
    description=(
        "Result of an availability transition. Hippo never hard-deletes; "
        "lifecycle status drivers (active/archived/superseded/deleted/"
        "distributed/removed) are recorded in provenance (sec3, sec9 §9.5)."
    )
)
class AvailabilityResult:
    entity_id: strawberry.ID
    is_available: bool


@strawberry.type(description="One per-entity failure from a bulk availability change.")
class BulkAvailabilityFailure:
    entity_id: strawberry.ID
    error: str


@strawberry.type(
    description=(
        "Summary of a bulk availability change (mirrors REST "
        "POST /entities/{type}/bulk-availability): per-record error "
        "isolation — failures never roll back sibling successes."
    )
)
class BulkAvailabilityResult:
    total: int
    succeeded: int
    failed: int
    successes: list[AvailabilityResult]
    failures: list[BulkAvailabilityFailure]


@strawberry.type(
    description=(
        "Entity resolved from an external reference (system, value) pair "
        "via the hippo_external_xref reverse-lookup index (issue #48). "
        "Generic envelope shape — the matching entity type is only known "
        "at query time, so `data` carries the typed payload as JSON; use "
        "`entityType` with the per-type queries for typed traversal."
    )
)
class XrefMatch:
    entity_id: strawberry.ID
    entity_type: str
    data: JSON
    version: Optional[int]
    created_at: Optional[ISODateTime]
    updated_at: Optional[ISODateTime]


@strawberry.type(description="Result of a supersede operation.")
class SupersedeResult:
    entity_id: strawberry.ID
    superseded_by: strawberry.ID


@strawberry.type(
    description=(
        "Entity-level supersession state (mirrors REST GET "
        "/entities/{id}/superseded). `supersededBy` is the direct "
        "replacement (null when the entity is current); `chain` follows "
        "replacement links forward to the terminal replacement."
    )
)
class SupersessionInfo:
    entity_id: strawberry.ID
    superseded_by: Optional[strawberry.ID]
    chain: list[strawberry.ID]


# ---------------------------------------------------------------------------
# Batch unit-of-work (issue #84): whole-set dry-run validation + atomic
# multi-entity write. Cross-type, so these are root mutations with generic
# JSON payloads (each entity's typed shape is only known at runtime).
# ---------------------------------------------------------------------------


@strawberry.input(description="One entity in a batch validate/write request.")
class BatchEntityInput:
    entity_type: str
    data: JSON
    operation: str = "insert"


@strawberry.input(
    description=(
        "One intra-batch relationship edge, created after the entities "
        "within the same atomic transaction. Source/target may reference "
        "entities created earlier in the same batch."
    )
)
class BatchRelationshipInput:
    source_id: strawberry.ID
    target_id: strawberry.ID
    relationship_type: str
    metadata: Optional[JSON] = None


@strawberry.type(description="One tier-annotated validation failure (sec9 §9.9).")
class ValidationFailureType:
    tier: str
    rule: str
    message: str
    field: Optional[str] = None
    details: Optional[JSON] = None


@strawberry.type(description="Per-entity validation outcome within a batch.")
class BatchEntityValidation:
    entity_id: Optional[strawberry.ID]
    passed: bool
    failures: list[ValidationFailureType]


@strawberry.type(
    description=(
        "Whole-set dry-run validation result (HippoClient.validate_batch); "
        "aggregated per-entity, no writes."
    )
)
class BatchValidationGraphQLResult:
    passed: bool
    results: list[BatchEntityValidation]


@strawberry.type(
    description=(
        "Result of an atomic multi-entity write (HippoClient.batch_put). "
        "The set commits all-or-nothing; `entities`/`relationships` carry the "
        "written (or, on a dry run, planned) payloads as JSON."
    )
)
class BatchWriteGraphQLResult:
    committed: bool
    dry_run: bool
    validation: BatchValidationGraphQLResult
    entities: list[JSON]
    relationships: list[JSON]


# ---------------------------------------------------------------------------
# Hippo schema introspection (the LinkML type model — distinct from
# GraphQL's own __schema introspection; mirrors REST GET /schemas and
# GET /schemas/{type}/references).
# ---------------------------------------------------------------------------


@strawberry.type(
    description=(
        "One slot of an entity type, as classified by the shared LinkML "
        "type model (hippo.core.schema_typing)."
    )
)
class HippoSlotInfo:
    name: str
    kind: str  # scalar | enum | reference
    range: str  # raw LinkML range
    role: str  # user | system
    required: bool
    multivalued: bool
    identifier: bool
    description: Optional[str]
    target_entity_type: Optional[str]  # set when kind == reference
    enum_name: Optional[str]
    enum_values: list[str]


@strawberry.type(
    description=(
        "One relationship of an entity type (mirrors REST GET "
        "/schemas/{type}/references)."
    )
)
class HippoReferenceInfo:
    field: str
    target_entity_type: str


@strawberry.type(
    description=(
        "One exposed entity type from the deployment's merged LinkML "
        "schema (mirrors REST GET /schemas). This is Hippo's *domain* "
        "schema introspection — the LinkML type model the GraphQL "
        "surface itself is generated from."
    )
)
class HippoEntityTypeInfo:
    name: str
    accessor_name: str
    description: Optional[str]
    fields: list[HippoSlotInfo]
    relationships: list[HippoReferenceInfo]


def _entity_type_info(model: EntityTypeModel) -> HippoEntityTypeInfo:
    return HippoEntityTypeInfo(
        name=model.class_name,
        accessor_name=model.accessor_name,
        description=model.description,
        fields=[
            HippoSlotInfo(
                name=slot.name,
                kind=slot.kind.value,
                range=slot.range,
                role=slot.role.value,
                required=slot.required,
                multivalued=slot.multivalued,
                identifier=slot.identifier,
                description=slot.description,
                target_entity_type=slot.target_class,
                enum_name=slot.enum_name,
                enum_values=list(slot.enum_values),
            )
            for slot in model.fields
        ],
        relationships=[
            HippoReferenceInfo(
                field=slot.name,
                target_entity_type=slot.target_class or slot.range,
            )
            for slot in model.relationships
        ],
    )


def _client(info: Info) -> Any:
    return info.context["client"]


def _builder(info: Info) -> GraphQLTypeBuilder:
    return info.context["builder"]


def _as_graphql_error(exc: Exception) -> GraphQLError:
    """Map SDK exceptions onto structured GraphQL errors."""
    message = getattr(exc, "message", str(exc))
    if isinstance(exc, ValidationFailed):
        extensions: dict[str, Any] = {"code": "VALIDATION_FAILED"}
        result = getattr(exc, "result", None)
        if result is not None and hasattr(result, "to_envelope"):
            extensions.update(result.to_envelope())
        return GraphQLError(message, extensions=extensions)
    if isinstance(exc, ValidationFailure):
        return GraphQLError(
            message,
            extensions={
                "code": "VALIDATION_FAILED",
                "rule_id": exc.rule_id,
                "entity_type": exc.entity_type,
                "entity_id": exc.entity_id,
            },
        )
    if isinstance(exc, HippoValidationError):
        return GraphQLError(message, extensions={"code": "VALIDATION_FAILED"})
    if isinstance(exc, EntityAlreadySupersededError):
        return GraphQLError(message, extensions={"code": "ALREADY_SUPERSEDED"})
    if isinstance(exc, EntityNotFoundError):
        return GraphQLError(message, extensions={"code": "NOT_FOUND"})
    return GraphQLError(message, extensions={"code": "INTERNAL_ERROR"})


# ---------------------------------------------------------------------------
# Query resolvers
# ---------------------------------------------------------------------------


def _make_get_resolver(builder: GraphQLTypeBuilder, entity: EntityGraphQLInfo):
    class_name = entity.class_name

    def resolver(info: Info, id: strawberry.ID):  # noqa: A002 - GraphQL arg
        try:
            envelope = _client(info).get(class_name, str(id))
        except EntityNotFoundError:
            return None
        return _builder(info).instance_from_envelope(class_name, envelope)

    resolver.__name__ = entity.singular_name
    resolver.__doc__ = f"Fetch one {class_name} by UUID (null when absent)."
    resolver.__annotations__["return"] = Optional[entity.gql_type]
    return resolver


def _make_list_resolver(builder: GraphQLTypeBuilder, entity: EntityGraphQLInfo):
    class_name = entity.class_name

    def resolver(
        info: Info,
        filters: Optional[list[FilterInput]] = None,
        filter_mode: FilterMode = FilterMode.AND,
        limit: int = 100,
        offset: int = 0,
        as_of: Optional[str] = None,
    ):
        paginated = _client(info).query(
            entity_type=class_name,
            filters=[{"field": f.field, "value": f.value} for f in filters or []],
            limit=limit,
            offset=offset,
            filter_mode=filter_mode.value,
            as_of=as_of,
        )
        b = _builder(info)
        return entity.page_type(
            items=[
                b.instance_from_envelope(class_name, item)
                for item in paginated.items
            ],
            total=paginated.total,
            limit=paginated.limit,
            offset=paginated.offset,
        )

    resolver.__name__ = entity.plural_name
    resolver.__doc__ = (
        f"List {class_name} entities with equality filters and offset "
        f"pagination (mirrors HippoClient.query)."
    )
    resolver.__annotations__["return"] = entity.page_type
    return resolver


def _make_search_resolver(builder: GraphQLTypeBuilder, entity: EntityGraphQLInfo):
    class_name = entity.class_name

    def resolver(info: Info, q: str, limit: int = 100, offset: int = 0):
        results = _client(info).search(
            entity_type=class_name,
            query=q,
            limit=limit,
        )
        b = _builder(info)
        return [
            b.instance_from_envelope(class_name, envelope)
            for envelope in results[offset : offset + limit]
        ]

    resolver.__name__ = f"search_{entity.plural_name}"
    resolver.__doc__ = (
        f"Full-text search over {class_name} entities (mirrors REST "
        f"GET /search and HippoClient.search). Requires the schema to "
        f"declare searchable slots for {class_name}; returns matching "
        f"entities, empty list otherwise."
    )
    resolver.__annotations__["return"] = list[entity.gql_type]  # type: ignore[valid-type]
    return resolver


def _entity_history_resolver(info: Info, entity_id: strawberry.ID) -> list[ProvenanceEntry]:
    """Provenance history for any entity (oldest first)."""
    try:
        records = _client(info).history(str(entity_id))
    except EntityNotFoundError as exc:
        raise _as_graphql_error(exc) from exc
    return [
        ProvenanceEntry(
            operation_id=record.get("operation_id"),
            entity_id=record.get("entity_id"),
            entity_type=record.get("entity_type"),
            operation=record.get("operation_type"),
            timestamp=record.get("timestamp"),
            actor_id=record.get("user_id"),
            patch=record.get("state_snapshot"),
        )
        for record in records
    ]


def _superseded_by_resolver(info: Info, id: strawberry.ID) -> SupersessionInfo:  # noqa: A002
    """Entity-level supersession chain (mirrors REST GET /{id}/superseded).

    Resolves the entity's type from the id, then follows
    ``superseded_by`` links forward (reading superseded entities with
    ``include_unavailable``) until the terminal replacement.
    """
    client = _client(info)
    entity_id = str(id)
    entity_type = client.resolve_type(entity_id)
    if entity_type is None:
        raise GraphQLError(
            f"Entity not found: {entity_id}", extensions={"code": "NOT_FOUND"}
        )

    chain: list[strawberry.ID] = []
    seen = {entity_id}
    current_id, current_type = entity_id, entity_type
    while True:
        try:
            envelope = client.get(
                current_type, current_id, include_unavailable=True
            )
        except EntityNotFoundError as exc:
            if not chain:
                raise _as_graphql_error(exc) from exc
            break
        next_id = envelope.get("superseded_by")
        if not next_id or str(next_id) in seen:  # terminal (or defensive cycle stop)
            break
        next_id = str(next_id)
        chain.append(strawberry.ID(next_id))
        seen.add(next_id)
        next_type = client.resolve_type(next_id)
        if next_type is None:
            break
        current_id, current_type = next_id, next_type

    return SupersessionInfo(
        entity_id=id,
        superseded_by=chain[0] if chain else None,
        chain=chain,
    )


def _find_by_xref_resolver(
    info: Info, system: str, value: str
) -> Optional[XrefMatch]:
    """Reverse lookup over hippo_external_xref-annotated slots.

    Thin delegation to ``HippoClient.find_by_xref`` (mirrors REST
    ``GET /xref/{system}/{value}``). Null when no available entity holds
    the pair; (system, value) is globally unique among available
    entities, so at most one entity can match.
    """
    try:
        envelope = _client(info).find_by_xref(system, value)
    except NotImplementedError as exc:
        raise GraphQLError(
            str(exc), extensions={"code": "NOT_IMPLEMENTED"}
        ) from exc
    if envelope is None:
        return None
    return XrefMatch(
        entity_id=strawberry.ID(str(envelope.get("id"))),
        entity_type=str(envelope.get("entity_type")),
        data=envelope.get("data") or {},
        version=envelope.get("version"),
        created_at=envelope.get("created_at"),
        updated_at=envelope.get("updated_at"),
    )


def _make_hippo_schema_resolver(builder: GraphQLTypeBuilder):
    def resolver(info: Info) -> list[HippoEntityTypeInfo]:
        return [
            _entity_type_info(model)
            for _, model in sorted(_builder(info).type_model.items())
        ]

    resolver.__name__ = "hippo_schema"
    resolver.__doc__ = (
        "The deployment's LinkML type model — every exposed entity type "
        "with its slots and relationships (mirrors REST GET /schemas). "
        "Distinct from GraphQL's own __schema introspection."
    )
    return resolver


def _make_hippo_entity_type_resolver(builder: GraphQLTypeBuilder):
    def resolver(info: Info, name: str) -> Optional[HippoEntityTypeInfo]:
        model = _builder(info).type_model.get(name)
        if model is None:
            return None
        return _entity_type_info(model)

    resolver.__name__ = "hippo_entity_type"
    resolver.__doc__ = (
        "One exposed entity type from the LinkML type model, with its "
        "slots and relationships (mirrors REST GET /schemas/{name} and "
        "/schemas/{name}/references). Null for unknown names."
    )
    return resolver


# ---------------------------------------------------------------------------
# Mutation resolvers
# ---------------------------------------------------------------------------


def _refetch(info: Info, class_name: str, entity_id: str) -> Any:
    """Read back the full envelope (incl. computed temporal fields)."""
    envelope = _client(info).get(class_name, entity_id)
    return _builder(info).instance_from_envelope(class_name, envelope)


def _make_create_resolver(builder: GraphQLTypeBuilder, entity: EntityGraphQLInfo):
    class_name = entity.class_name

    def resolver(info: Info, data):
        payload = _builder(info).input_to_dict(class_name, data, mode="create")
        try:
            created = _client(info).create(class_name, payload)
        except Exception as exc:
            # Validation failures get the structured VALIDATION_FAILED
            # envelope; anything else (e.g. adapter integrity errors on
            # dangling references) maps to INTERNAL_ERROR so callers
            # always see a coded GraphQL error.
            raise _as_graphql_error(exc) from exc
        return _refetch(info, class_name, created["id"])

    resolver.__name__ = f"create_{entity.singular_name}"
    resolver.__doc__ = (
        f"Create a {class_name}. The SDK assigns a UUID when `id` is "
        f"omitted and records a `create` provenance entry."
    )
    resolver.__annotations__["data"] = entity.create_input
    resolver.__annotations__["return"] = entity.gql_type
    return resolver


def _make_update_resolver(builder: GraphQLTypeBuilder, entity: EntityGraphQLInfo):
    class_name = entity.class_name

    def resolver(info: Info, id: strawberry.ID, data):  # noqa: A002
        payload = _builder(info).input_to_dict(class_name, data, mode="update")
        # ``HippoClient.update`` has full-replace semantics (PUT — sec4
        # §4.3): omitted slots are nulled in storage. GraphQL update
        # inputs are partial by convention, so compose the SDK's read
        # and write: merge the patch over the current stored data. Pure
        # envelope composition — the SDK remains the only reader/writer.
        try:
            existing = _client(info).get(class_name, str(id))
        except EntityNotFoundError as exc:
            raise _as_graphql_error(exc) from exc
        merged = {**(existing.get("data") or {}), **payload}
        try:
            _client(info).update(class_name, str(id), merged)
        except Exception as exc:
            raise _as_graphql_error(exc) from exc
        return _refetch(info, class_name, str(id))

    resolver.__name__ = f"update_{entity.singular_name}"
    resolver.__doc__ = (
        f"Partially update an existing {class_name} (provided fields are "
        f"merged over the stored data); records an `update` provenance "
        f"entry. Errors with NOT_FOUND when the id is unknown."
    )
    resolver.__annotations__["data"] = entity.update_input
    resolver.__annotations__["return"] = entity.gql_type
    return resolver


def _make_availability_resolver(entity: EntityGraphQLInfo):
    class_name = entity.class_name

    def resolver(
        info: Info,
        id: strawberry.ID,  # noqa: A002
        is_available: bool,
        reason: Optional[str] = None,
    ) -> AvailabilityResult:
        result = _client(info).set_availability_bulk(
            entity_type=class_name,
            entity_ids=[str(id)],
            is_available=is_available,
            reason=reason,
        )
        if result["failed"]:
            error = result["failures"][0].get("error", "availability change failed")
            code = "NOT_FOUND" if "not found" in error.lower() else "AVAILABILITY_CHANGE_FAILED"
            raise GraphQLError(error, extensions={"code": code})
        return AvailabilityResult(entity_id=id, is_available=is_available)

    resolver.__name__ = f"set_{entity.singular_name}_availability"
    resolver.__doc__ = (
        f"Availability transition for a {class_name} — Hippo's "
        f"no-hard-delete lifecycle. The transition and its reason are "
        f"recorded as an `availability_change` provenance entry."
    )
    return resolver


def _make_bulk_availability_resolver(entity: EntityGraphQLInfo):
    class_name = entity.class_name

    def resolver(
        info: Info,
        ids: list[strawberry.ID],
        is_available: bool,
        reason: Optional[str] = None,
    ) -> BulkAvailabilityResult:
        result = _client(info).set_availability_bulk(
            entity_type=class_name,
            entity_ids=[str(i) for i in ids],
            is_available=is_available,
            reason=reason,
        )
        return BulkAvailabilityResult(
            total=result["total"],
            succeeded=result["succeeded"],
            failed=result["failed"],
            successes=[
                AvailabilityResult(
                    entity_id=item["id"], is_available=item["is_available"]
                )
                for item in result["successes"]
            ],
            failures=[
                BulkAvailabilityFailure(
                    entity_id=item["id"],
                    error=item.get("error", "availability change failed"),
                )
                for item in result["failures"]
            ],
        )

    resolver.__name__ = f"set_{entity.singular_name}_availability_bulk"
    resolver.__doc__ = (
        f"Bulk availability transition for {class_name} entities (mirrors "
        f"REST POST /entities/{{type}}/bulk-availability; wraps "
        f"HippoClient.set_availability_bulk). Per-record error isolation: "
        f"failures are reported per id and never roll back sibling "
        f"successes."
    )
    return resolver


def _make_supersede_resolver(entity: EntityGraphQLInfo):
    class_name = entity.class_name

    def resolver(
        info: Info,
        id: strawberry.ID,  # noqa: A002
        replacement_id: strawberry.ID,
        reason: Optional[str] = None,
    ) -> SupersedeResult:
        try:
            _client(info).supersede_entity(
                str(id), str(replacement_id), reason=reason
            )
        except (EntityNotFoundError, EntityAlreadySupersededError) as exc:
            raise _as_graphql_error(exc) from exc
        return SupersedeResult(entity_id=id, superseded_by=replacement_id)

    resolver.__name__ = f"supersede_{entity.singular_name}"
    resolver.__doc__ = (
        f"Atomically supersede a {class_name} with a replacement entity "
        f"(marks the source unavailable; provenance carries the link)."
    )
    return resolver


# ---------------------------------------------------------------------------
# Batch unit-of-work resolvers (root mutations; issue #84)
# ---------------------------------------------------------------------------


def _ops_from_inputs(entities: list[BatchEntityInput]) -> list[WriteOperation]:
    return [
        WriteOperation(
            operation=e.operation or "insert",
            entity_type=e.entity_type,
            data=dict(e.data or {}),
        )
        for e in entities
    ]


def _gql_batch_validation(vr: Any) -> BatchValidationGraphQLResult:
    return BatchValidationGraphQLResult(
        passed=vr.is_valid,
        results=[
            BatchEntityValidation(
                entity_id=r.entity_id,
                passed=r.is_valid,
                failures=[
                    ValidationFailureType(
                        tier=f.tier,
                        rule=f.rule,
                        message=f.message,
                        field=f.field,
                        details=f.details or None,
                    )
                    for f in r.failures
                ],
            )
            for r in vr.results
        ],
    )


def _validate_batch_resolver(
    info: Info, entities: list[BatchEntityInput]
) -> BatchValidationGraphQLResult:
    """Whole-set dry-run validation (no writes; mirrors REST POST /ingest/validate)."""
    vr = _client(info).validate_batch(_ops_from_inputs(entities))
    return _gql_batch_validation(vr)


def _ingest_batch_resolver(
    info: Info,
    entities: list[BatchEntityInput],
    relationships: Optional[list[BatchRelationshipInput]] = None,
    dry_run: bool = False,
) -> BatchWriteGraphQLResult:
    """Atomic multi-entity write (mirrors REST POST /ingest/batch).

    The set commits all-or-nothing; relationships are created after the
    entities within the same transaction so intra-batch forward references
    resolve. SDK errors map to coded GraphQL errors via ``_as_graphql_error``.
    """
    ops = _ops_from_inputs(entities)
    rels = [
        {
            "source_id": str(r.source_id),
            "target_id": str(r.target_id),
            "relationship_type": r.relationship_type,
            "metadata": r.metadata,
        }
        for r in (relationships or [])
    ] or None
    try:
        result = _client(info).batch_put(ops, relationships=rels, dry_run=dry_run)
    except Exception as exc:
        raise _as_graphql_error(exc) from exc
    return BatchWriteGraphQLResult(
        committed=result.committed,
        dry_run=result.dry_run,
        validation=_gql_batch_validation(result.validation),
        entities=result.entities,
        relationships=result.relationships,
    )


# ---------------------------------------------------------------------------
# Schema assembly
# ---------------------------------------------------------------------------


def build_query_type(builder: GraphQLTypeBuilder) -> type:
    fields = []
    for entity in builder.entities.values():
        fields.append(
            strawberry.field(
                resolver=_make_get_resolver(builder, entity),
                name=camel_case(entity.singular_name),
            )
        )
        fields.append(
            strawberry.field(
                resolver=_make_list_resolver(builder, entity),
                name=camel_case(entity.plural_name),
            )
        )
        fields.append(
            strawberry.field(
                resolver=_make_search_resolver(builder, entity),
                name=camel_case(f"search_{entity.plural_name}"),
            )
        )
    fields.append(
        strawberry.field(resolver=_entity_history_resolver, name="entityHistory")
    )
    fields.append(
        strawberry.field(resolver=_superseded_by_resolver, name="supersededBy")
    )
    fields.append(
        strawberry.field(resolver=_find_by_xref_resolver, name="findByXref")
    )
    fields.append(
        strawberry.field(
            resolver=_make_hippo_schema_resolver(builder), name="hippoSchema"
        )
    )
    fields.append(
        strawberry.field(
            resolver=_make_hippo_entity_type_resolver(builder),
            name="hippoEntityType",
        )
    )
    return create_type("Query", fields)


def build_mutation_type(builder: GraphQLTypeBuilder) -> type:
    fields = []
    for entity in builder.entities.values():
        singular = entity.singular_name
        fields.append(
            strawberry.mutation(
                resolver=_make_create_resolver(builder, entity),
                name=camel_case(f"create_{singular}"),
            )
        )
        fields.append(
            strawberry.mutation(
                resolver=_make_update_resolver(builder, entity),
                name=camel_case(f"update_{singular}"),
            )
        )
        fields.append(
            strawberry.mutation(
                resolver=_make_availability_resolver(entity),
                name=camel_case(f"set_{singular}_availability"),
            )
        )
        fields.append(
            strawberry.mutation(
                resolver=_make_bulk_availability_resolver(entity),
                name=camel_case(f"set_{singular}_availability_bulk"),
            )
        )
        fields.append(
            strawberry.mutation(
                resolver=_make_supersede_resolver(entity),
                name=camel_case(f"supersede_{singular}"),
            )
        )
    # Cross-type batch unit-of-work (issue #84) — root mutations, added once.
    fields.append(
        strawberry.mutation(resolver=_ingest_batch_resolver, name="ingestBatch")
    )
    fields.append(
        strawberry.mutation(resolver=_validate_batch_resolver, name="validateBatch")
    )
    return create_type("Mutation", fields)


def build_graphql_schema(
    registry: SchemaRegistry,
    builder: Optional[GraphQLTypeBuilder] = None,
    max_query_depth: int = DEFAULT_MAX_QUERY_DEPTH,
) -> strawberry.Schema:
    """Autogenerate the full ``strawberry.Schema`` for a deployment.

    One call at startup: renders the shared LinkML type model and emits
    per-entity object/input/page types plus Query and Mutation roots.
    Pass an existing :class:`GraphQLTypeBuilder` to share the type
    universe with the router's context.

    ``max_query_depth`` bounds query nesting (strawberry's
    ``QueryDepthLimiter``; introspection fields are exempt so GraphiQL
    keeps working). Relationship fields make arbitrarily deep traversal
    expressible, so a depth cap is the transport's recursion guard.
    """
    builder = (builder or GraphQLTypeBuilder(registry)).build()
    if not builder.entities:
        raise ValueError(
            "GraphQL schema generation found no concrete entity classes "
            "in the merged LinkML schema; nothing to expose."
        )
    return strawberry.Schema(
        query=build_query_type(builder),
        mutation=build_mutation_type(builder),
        # Factory form so a fresh extension is constructed per request.
        extensions=[lambda: QueryDepthLimiter(max_depth=max_query_depth)],
    )
