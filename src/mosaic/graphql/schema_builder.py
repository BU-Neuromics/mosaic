"""GraphQL type rendering for the shared LinkML type model.

Builds Strawberry object types, input types, page (pagination) types,
and enums for every exposed entity class. *What* to expose — the class
set, each slot's scalar/enum/reference classification, relationship
targets, enum values, system vs. user fields — comes from the shared
type model in :mod:`mosaic.core.schema_typing` (issue #47), the same
model the typed SDK renders. This module only decides *how* that model
renders into GraphQL:

- One object type per exposed entity class (``build_type_model``).
- Slots map to GraphQL fields with scalar/enum/list typing.
- Reference slots (``SlotKind.REFERENCE``) get TWO fields: the raw
  stored UUID (``donor`` → ``donorId: ID``) and a resolved field
  (``donor: Donor``) that traverses the graph via a per-request
  DataLoader.
- System fields (``id``, ``is_available``) come from the entity table;
  temporal fields (``schema_typing.TEMPORAL_FIELDS`` plus ``version``
  and ``superseded_by``) are computed at read time from the provenance
  log by the SDK (sec9 §9.7) and exposed read-only.

No business logic lives here: conversion between SDK envelopes
(``client.get`` / ``client.query`` dicts) and GraphQL instances is pure
shape mapping.
"""

from __future__ import annotations

import enum
import keyword
import re
from dataclasses import dataclass, field as dc_field
from typing import Any, NewType, Optional

import strawberry
from strawberry.dataloader import DataLoader
from strawberry.scalars import JSON
from strawberry.types import Info

# INFRASTRUCTURE_CLASSES is re-exported for callers/tests: the single
# definition lives in the schema-typing core (issue #47), so the
# GraphQL, typed-client, and OpenAPI surfaces cannot drift.
from mosaic.core.schema_typing import (
    INFRASTRUCTURE_CLASSES,  # noqa: F401  (re-export)
    TEMPORAL_FIELDS,
    EntityTypeModel,
    SlotKind,
    SlotModel,
    build_type_model,
)
from mosaic.linkml_bridge import SchemaRegistry

# ISO-8601 passthrough scalars. Mosaic stores temporal values as ISO
# strings (SQLite TEXT columns); these scalars document the format
# without forcing a parse/serialize round-trip in the transport.
ISODateTime = strawberry.scalar(
    NewType("ISODateTime", str),
    name="DateTime",
    description="ISO-8601 datetime string (UTC).",
    serialize=str,
    parse_value=str,
)
ISODate = strawberry.scalar(
    NewType("ISODate", str),
    name="Date",
    description="ISO-8601 date string.",
    serialize=str,
    parse_value=str,
)
ISOTime = strawberry.scalar(
    NewType("ISOTime", str),
    name="Time",
    description="ISO-8601 time string.",
    serialize=str,
    parse_value=str,
)

# LinkML scalar range → GraphQL (Python) type. This is pure rendering:
# the *classification* of a slot as scalar comes from the type model
# (SlotKind.SCALAR); this map only picks the GraphQL type for a scalar
# range string. Unknown ranges (including references to classes the
# typing core does not expose, e.g. infrastructure classes) fall back
# to String.
SCALAR_RANGE_MAP: dict[str, Any] = {
    "string": str,
    "integer": int,
    "float": float,
    "double": float,
    "decimal": float,
    "boolean": bool,
    "date": ISODate,
    "datetime": ISODateTime,
    "time": ISOTime,
    "uri": str,
    "uriorcurie": str,
    "curie": str,
    "ncname": str,
    "objectidentifier": str,
    "nodeidentifier": str,
}

# Read-only computed fields added to every generated entity type. The
# temporal names come from the schema-typing core (sec9 §9.7: computed
# from ProvenanceRecord at read time — never stored on entity tables);
# ``version`` and ``superseded_by`` are SDK envelope fields with the
# same read-only nature.
_TEMPORAL_FIELD_TYPES: dict[str, Any] = {
    "created_at": Optional[ISODateTime],
    "updated_at": Optional[ISODateTime],
    "schema_version": Optional[str],
    "created_by": Optional[str],
    "updated_by": Optional[str],
}
COMPUTED_FIELDS: list[tuple[str, Any]] = [
    ("version", Optional[int]),
    *((name, _TEMPORAL_FIELD_TYPES[name]) for name in TEMPORAL_FIELDS),
    ("superseded_by", Optional[strawberry.ID]),
]


def snake_case(name: str) -> str:
    """``DNASample`` → ``dna_sample`` (same regex as ``default_accessor``)."""
    s1 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def camel_case(name: str) -> str:
    """``create_sample`` → ``createSample`` (GraphQL field convention)."""
    head, *rest = name.split("_")
    return head + "".join(part.capitalize() for part in rest)


def _safe_attr(name: str) -> str:
    """Coerce a LinkML slot name into a valid Python attribute name."""
    attr = re.sub(r"\W", "_", name)
    if not attr or attr[0].isdigit():
        attr = f"f_{attr}"
    if keyword.iskeyword(attr):
        attr = f"{attr}_"
    return attr


def _enum_member_name(value: str) -> str:
    member = re.sub(r"\W", "_", value)
    if not member or member[0].isdigit():
        member = f"V_{member}"
    if keyword.iskeyword(member):
        member = f"{member}_"
    return member


@dataclass
class SlotSpec:
    """How one type-model slot renders onto the generated GraphQL surface."""

    slot_name: str  # LinkML slot name == storage data key
    attr_name: str  # Python attribute on the generated type
    kind: str  # "scalar" | "enum" | "reference"
    multivalued: bool
    required: bool
    has_default: bool  # LinkML ifabsent present
    target_class: Optional[str] = None  # for kind == "reference"
    resolvable: bool = False  # reference target has a generated type
    resolved_attr: Optional[str] = None  # resolver field name for references
    enum_cls: Optional[type] = None  # for kind == "enum"
    scalar_type: Any = None  # for kind == "scalar"
    description: Optional[str] = None


@dataclass
class EntityGraphQLInfo:
    """Everything the resolvers need to serve one entity class."""

    class_name: str
    singular_name: str  # GraphQL query name, snake form (e.g. "sample")
    plural_name: str  # list-query name, from the accessor convention
    model: Optional[EntityTypeModel] = None  # shared type model entry
    slots: list[SlotSpec] = dc_field(default_factory=list)
    computed_fields: list[str] = dc_field(default_factory=list)
    gql_type: Any = None
    page_type: Any = None
    create_input: Any = None
    update_input: Any = None
    create_specs: list[SlotSpec] = dc_field(default_factory=list)
    update_specs: list[SlotSpec] = dc_field(default_factory=list)


def get_entity_loader(context: Any, class_name: str) -> DataLoader:
    """Per-request, per-entity-type DataLoader (batched relationship reads).

    A single GraphQL request resolving N relationship fields of the same
    target type issues ONE ``client.query`` (OR-composed id filters; one
    storage round-trip + one batched temporal aggregation) instead of N
    ``client.get`` calls.
    """
    loaders = context.setdefault("entity_loaders", {})
    if class_name not in loaders:
        client = context["client"]

        async def load_fn(keys: list[str]) -> list[Optional[dict[str, Any]]]:
            paginated = client.query(
                entity_type=class_name,
                filters=[{"field": "id", "value": key} for key in keys],
                filter_mode="or",
            )
            by_id = {item["id"]: item for item in paginated.items}
            return [by_id.get(key) for key in keys]

        loaders[class_name] = DataLoader(load_fn=load_fn)
    return loaders[class_name]


class GraphQLTypeBuilder:
    """Renders the shared type model into the Strawberry type universe.

    Two-pass generation: bare classes are created first so cyclic and
    self-referential relationships annotate with real class objects (no
    string forward references), then slots/resolvers are attached and
    the classes are decorated with ``strawberry.type``.
    """

    def __init__(self, registry: SchemaRegistry) -> None:
        self._registry = registry
        self.type_model: dict[str, EntityTypeModel] = {}
        self.entities: dict[str, EntityGraphQLInfo] = {}
        self.enums: dict[str, type] = {}
        self._built = False

    # -- public surface ----------------------------------------------------

    def build(self) -> "GraphQLTypeBuilder":
        """Generate all types. Idempotent."""
        if self._built:
            return self
        self.type_model = build_type_model(self._registry)
        self._select_entities()
        self._build_enums()
        self._build_object_types()
        self._build_page_types()
        self._build_input_types()
        self._built = True
        return self

    def instance_from_envelope(
        self, class_name: str, envelope: dict[str, Any]
    ) -> Any:
        """SDK entity envelope (``client.get``/``client.query`` item) →
        generated GraphQL type instance. Pure shape mapping.
        """
        entity = self.entities[class_name]
        data = envelope.get("data") or {}
        kwargs: dict[str, Any] = {}

        for spec in entity.slots:
            if spec.slot_name == "id":
                kwargs[spec.attr_name] = envelope.get("id", data.get("id"))
                continue
            if spec.slot_name == "is_available":
                kwargs[spec.attr_name] = bool(data.get("is_available", True))
                continue
            raw = data.get(spec.slot_name)
            kwargs[spec.attr_name] = self._convert_out(spec, raw)

        for name in entity.computed_fields:
            kwargs[name] = envelope.get(name)

        return entity.gql_type(**kwargs)

    def input_to_dict(self, class_name: str, data: Any, mode: str) -> dict[str, Any]:
        """Generated input instance → plain dict for ``MosaicClient`` writes.

        UNSET fields are dropped (absent from the write payload); enum
        members are flattened to their LinkML string values.
        """
        entity = self.entities[class_name]
        specs = entity.create_specs if mode == "create" else entity.update_specs
        out: dict[str, Any] = {}
        for spec in specs:
            value = getattr(data, spec.attr_name, strawberry.UNSET)
            if value is strawberry.UNSET or value is None:
                continue
            if spec.kind == "enum":
                if spec.multivalued:
                    value = [getattr(v, "value", v) for v in value]
                else:
                    value = getattr(value, "value", value)
            elif spec.kind == "reference" or spec.scalar_type in (
                ISODate,
                ISODateTime,
                ISOTime,
            ):
                value = [str(v) for v in value] if spec.multivalued else str(value)
            out[spec.slot_name] = value
        return out

    # -- generation passes -------------------------------------------------

    def _select_entities(self) -> None:
        # The exposed class set is the type model's key set — the same
        # selection the typed client renders (exposed_class_names).
        for class_name, model in self.type_model.items():
            self.entities[class_name] = EntityGraphQLInfo(
                class_name=class_name,
                singular_name=snake_case(class_name),
                plural_name=model.accessor_name,
                model=model,
            )

    def _build_enums(self) -> None:
        # Enum membership comes from the type model's slot classification
        # (SlotKind.ENUM + enum_values). The enum *description* is
        # rendering metadata the model does not carry, so it is looked
        # up from the schema view.
        enum_defs = self._registry.schema_view.all_enums() or {}
        for model in self.type_model.values():
            for slot in model.fields:
                if slot.kind is not SlotKind.ENUM or slot.enum_name in self.enums:
                    continue
                members = {
                    _enum_member_name(str(value)): str(value)
                    for value in slot.enum_values
                }
                if not members:
                    continue
                py_enum = enum.Enum(slot.enum_name, members)  # type: ignore[misc]
                enum_def = enum_defs.get(slot.enum_name)
                self.enums[slot.enum_name] = strawberry.enum(  # type: ignore[assignment]
                    py_enum,
                    name=slot.enum_name,
                    description=(
                        enum_def.description if enum_def is not None else None
                    )
                    or None,
                )

    def _slot_spec(self, slot: SlotModel) -> SlotSpec:
        """Render one type-model slot into a :class:`SlotSpec`.

        Reference resolvability is provisional here; final collision
        checks against sibling attribute names happen in
        :meth:`_build_object_types`.
        """
        attr = _safe_attr(slot.name)

        if slot.kind is SlotKind.ENUM and slot.enum_name in self.enums:
            return SlotSpec(
                slot_name=slot.name,
                attr_name=attr,
                kind="enum",
                multivalued=slot.multivalued,
                required=slot.required,
                has_default=slot.has_default,
                enum_cls=self.enums[slot.enum_name],
                description=slot.description or None,
            )

        if slot.kind is SlotKind.STRUCTURED:
            # Inline value type (issue #48, e.g. ExternalReference): the
            # stored value is the structured object itself, not a UUID —
            # rendered as a JSON passthrough scalar in both directions.
            description = f"Inline {slot.target_class or slot.range} value."
            if slot.is_external_xref:
                description += (
                    " Reverse-lookup key (hippo_external_xref): "
                    "(system, value) is globally unique among available "
                    "entities; see the findByXref query."
                )
            return SlotSpec(
                slot_name=slot.name,
                attr_name=attr,
                kind="scalar",
                multivalued=slot.multivalued,
                required=slot.required,
                has_default=slot.has_default,
                scalar_type=JSON,
                description=description,
            )

        if slot.kind is SlotKind.REFERENCE:
            # Relationship slot. Stored value is a UUID (sec9 §9.5). The
            # raw field keeps/derives an ``*_id`` name; the resolved field
            # uses the natural slot name when the target has a generated
            # type, enabling graph traversal in one query.
            resolvable = slot.target_class in self.entities
            if slot.multivalued:
                raw = slot.name if slot.name.endswith("_ids") else f"{slot.name}_ids"
                resolved = (
                    f"{slot.name[: -len('_ids')]}s"  # sample_ids -> samples
                    if slot.name.endswith("_ids")
                    else slot.name
                )
            else:
                raw = slot.name if slot.name.endswith("_id") else f"{slot.name}_id"
                resolved = (
                    slot.name[: -len("_id")]
                    if slot.name.endswith("_id")
                    else slot.name
                )
            raw_attr = _safe_attr(raw)
            resolved_attr = _safe_attr(resolved)
            if resolved_attr == raw_attr:
                resolvable = False  # name collision — raw ID field only
            return SlotSpec(
                slot_name=slot.name,
                attr_name=raw_attr,
                kind="reference",
                multivalued=slot.multivalued,
                required=slot.required,
                has_default=slot.has_default,
                target_class=slot.target_class,
                resolvable=resolvable,
                resolved_attr=resolved_attr if resolvable else None,
                description=slot.description or None,
            )

        # SlotKind.SCALAR — including an ENUM whose definition has no
        # permissible values (no GraphQL enum can be built for it).
        scalar = SCALAR_RANGE_MAP.get(slot.range, str)
        return SlotSpec(
            slot_name=slot.name,
            attr_name=attr,
            kind="scalar",
            multivalued=slot.multivalued,
            required=slot.required,
            has_default=slot.has_default,
            scalar_type=scalar,
            description=slot.description or None,
        )

    def _output_annotation(self, spec: SlotSpec) -> Any:
        if spec.slot_name == "id":
            return strawberry.ID
        if spec.slot_name == "is_available":
            return bool
        if spec.kind == "reference":
            base: Any = strawberry.ID
        elif spec.kind == "enum":
            base = spec.enum_cls
        else:
            base = spec.scalar_type
        if spec.multivalued:
            return Optional[list[base]]
        if spec.required and not spec.has_default:
            return base
        return Optional[base]

    def _build_object_types(self) -> None:
        # Pass 1 — bare classes so relationship annotations can use real
        # class objects (handles cycles and self-references).
        bare: dict[str, type] = {
            name: type(name, (), {}) for name in self.entities
        }

        # Pass 2 — attach fields and decorate.
        for class_name, entity in self.entities.items():
            cls = bare[class_name]
            annotations: dict[str, Any] = {}
            model = entity.model
            assert model is not None

            specs = [self._slot_spec(slot) for slot in model.fields]
            # Final resolvability check: a resolved relationship field
            # must not collide with any sibling attribute name.
            used = {s.attr_name for s in specs}
            for spec in specs:
                if spec.kind == "reference" and spec.resolvable:
                    if spec.resolved_attr in used:
                        spec.resolvable = False
                        spec.resolved_attr = None
                    else:
                        used.add(spec.resolved_attr)  # type: ignore[arg-type]

            for spec in specs:
                entity.slots.append(spec)
                annotations[spec.attr_name] = self._output_annotation(spec)
                setattr(cls, spec.attr_name, None)
                if spec.kind == "reference" and spec.resolvable:
                    target = bare[spec.target_class]  # type: ignore[index]
                    resolver = self._make_reference_resolver(spec, target)
                    setattr(
                        cls,
                        spec.resolved_attr,  # type: ignore[arg-type]
                        strawberry.field(
                            resolver=resolver,
                            description=(
                                f"Resolved {spec.target_class} for "
                                f"`{spec.slot_name}` (graph traversal; "
                                f"batched per request)."
                            ),
                        ),
                    )

            slot_names = {s.slot_name for s in entity.slots}
            for name, annotation in COMPUTED_FIELDS:
                if name in slot_names:
                    continue
                annotations[name] = annotation
                setattr(cls, name, None)
                entity.computed_fields.append(name)

            cls.__annotations__ = annotations
            entity.gql_type = strawberry.type(
                cls, description=model.description or None
            )

    def _make_reference_resolver(self, spec: SlotSpec, target: type) -> Any:
        builder = self
        target_class: str = spec.target_class  # type: ignore[assignment]
        raw_attr = spec.attr_name

        if spec.multivalued:

            async def resolver(self, info: Info):  # type: ignore[no-untyped-def]
                ids = getattr(self, raw_attr) or []
                loader = get_entity_loader(info.context, target_class)
                envelopes = await loader.load_many([str(i) for i in ids])
                return [
                    builder.instance_from_envelope(target_class, env)
                    for env in envelopes
                    if env is not None
                ]

            resolver.__annotations__["return"] = list[target]  # type: ignore[valid-type]
        else:

            async def resolver(self, info: Info):  # type: ignore[no-untyped-def]
                ref_id = getattr(self, raw_attr)
                if not ref_id:
                    return None
                loader = get_entity_loader(info.context, target_class)
                envelope = await loader.load(str(ref_id))
                if envelope is None:
                    return None
                return builder.instance_from_envelope(target_class, envelope)

            resolver.__annotations__["return"] = Optional[target]
        return resolver

    def _build_page_types(self) -> None:
        for entity in self.entities.values():
            page_name = f"{entity.class_name}Page"
            page = type(page_name, (), {})
            page.__annotations__ = {
                "items": list[entity.gql_type],  # type: ignore[name-defined]
                "total": int,
                "limit": int,
                "offset": int,
            }
            entity.page_type = strawberry.type(
                page,
                description=(
                    f"Offset-paginated {entity.class_name} result set "
                    f"(mirrors the SDK's PaginatedResult)."
                ),
            )

    def _input_annotation(self, spec: SlotSpec, force_optional: bool) -> Any:
        if spec.kind == "reference":
            base: Any = strawberry.ID
        elif spec.kind == "enum":
            base = spec.enum_cls
        else:
            base = spec.scalar_type
        if spec.multivalued:
            base = list[base]
        required = spec.required and not spec.has_default and not force_optional
        # ``id`` is SDK-assigned on create; never required on inputs.
        if spec.slot_name == "id":
            required = False
        return base if required else Optional[base]

    def _is_input_required(self, spec: SlotSpec, force_optional: bool) -> bool:
        if force_optional or spec.slot_name == "id":
            return False
        return spec.required and not spec.has_default

    def _build_one_input(
        self, entity: EntityGraphQLInfo, suffix: str, force_optional: bool
    ) -> tuple[Any, list[SlotSpec]]:
        cls = type(f"{entity.class_name}{suffix}", (), {})
        annotations: dict[str, Any] = {}
        specs: list[SlotSpec] = []
        # Inputs use the ORIGINAL slot name for every field (including
        # references — callers pass the target UUID under the slot name)
        # because the dict handed to MosaicClient keys on slot names.
        ordered = sorted(
            entity.slots,
            key=lambda s: not self._is_input_required(s, force_optional),
        )
        for slot_spec in ordered:
            input_spec = SlotSpec(
                slot_name=slot_spec.slot_name,
                attr_name=_safe_attr(slot_spec.slot_name),
                kind=slot_spec.kind,
                multivalued=slot_spec.multivalued,
                required=self._is_input_required(slot_spec, force_optional),
                has_default=slot_spec.has_default,
                target_class=slot_spec.target_class,
                enum_cls=slot_spec.enum_cls,
                scalar_type=slot_spec.scalar_type,
            )
            specs.append(input_spec)
            annotations[input_spec.attr_name] = self._input_annotation(
                slot_spec, force_optional
            )
            if not input_spec.required:
                setattr(cls, input_spec.attr_name, strawberry.UNSET)
        cls.__annotations__ = annotations
        return (
            strawberry.input(
                cls,
                description=(
                    f"{'Create' if suffix == 'CreateInput' else 'Update'} "
                    f"payload for {entity.class_name}. Relationship fields "
                    f"take the target entity UUID."
                ),
            ),
            specs,
        )

    def _build_input_types(self) -> None:
        for entity in self.entities.values():
            entity.create_input, entity.create_specs = self._build_one_input(
                entity, "CreateInput", force_optional=False
            )
            entity.update_input, entity.update_specs = self._build_one_input(
                entity, "UpdateInput", force_optional=True
            )

    # -- conversion helpers --------------------------------------------------

    def _convert_out(self, spec: SlotSpec, raw: Any) -> Any:
        if raw is None:
            return [] if spec.multivalued and spec.required else None
        if spec.kind == "enum":
            enum_cls = spec.enum_cls
            if spec.multivalued:
                return [enum_cls(v) for v in raw]  # type: ignore[misc]
            return enum_cls(raw)  # type: ignore[misc]
        if spec.kind == "reference":
            if spec.multivalued:
                values = raw if isinstance(raw, list) else [raw]
                return [str(v) for v in values]
            return str(raw)
        if spec.multivalued and not isinstance(raw, list):
            return [raw]
        return raw
