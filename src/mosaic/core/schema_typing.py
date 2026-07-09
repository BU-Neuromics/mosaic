"""Shared, transport-agnostic type model derived from a LinkML schema.

Single source of truth for "how a LinkML schema maps to a typed surface",
consumed by every transport so they cannot drift:

- the typed SDK (Pydantic accessors) — :mod:`mosaic.core.typed_client`
- the GraphQL transport (Strawberry types) — ``mosaic.graphql`` (issue #45)
- the OpenAPI/JSON-Schema transport — REST (issue #46)

This module answers the questions all three previously answered separately:
which classes are exposed, how each slot's range classifies (scalar / enum /
class-reference), the relationship targets, enum values, and which fields are
system vs. computed-temporal. Each transport renders this model into its own
type system; the classification lives here once.

No transport types and no business logic live here — only a normalized view
over a :class:`~mosaic.linkml_bridge.SchemaRegistry`.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field as dc_field
from typing import Any, Optional

from mosaic.linkml_bridge import (
    HIPPO_EXTERNAL_XREF,
    VALUE_TYPE_CLASSES,
    SchemaRegistry,
    annotation_value,
    class_accessor_name,
)

#: hippo_core framework classes that transports never expose as domain
#: entities. ``Entity`` is abstract; the rest are system concerns. This is
#: the single definition — transports import it rather than re-listing it.
INFRASTRUCTURE_CLASSES: frozenset[str] = frozenset(
    {
        "Entity",
        "ProvenanceRecord",
        "Process",
        "Validator",
        "ReferenceLoader",
    }
)

# VALUE_TYPE_CLASSES (imported above) is the framework-baseline value-type
# set, re-exported here for backward compatibility. As of issue #90 the
# authoritative, per-schema set is computed from the schema via
# ``SchemaRegistry.value_type_classes()`` (identifier-less, non-tree-root
# classes — stored inline on the slot that ranges them, no id/lifecycle).
# Slots ranged against a value type classify as ``SlotKind.STRUCTURED`` and
# are not exposed as entity types. Detection logic lives in
# ``mosaic.linkml_bridge``.

#: System fields stored on the entity table (present as induced slots).
SYSTEM_FIELDS: frozenset[str] = frozenset({"id", "is_available"})

#: Read-time fields computed from the provenance log (sec9 §9.7) — not stored
#: slots. Transports expose them read-only; they are not part of an entity's
#: ``fields`` (which derive from induced slots).
TEMPORAL_FIELDS: tuple[str, ...] = (
    "created_at",
    "updated_at",
    "schema_version",
    "created_by",
    "updated_by",
)


class SlotKind(enum.Enum):
    """How a slot's range classifies for type rendering."""

    SCALAR = "scalar"  # string/integer/float/boolean/date/datetime/...
    ENUM = "enum"  # range is a LinkML enum
    REFERENCE = "reference"  # range is another (non-infrastructure) class
    STRUCTURED = "structured"  # range is an inline value type (issue #48)


class FieldRole(enum.Enum):
    """Where a field comes from / how transports should treat it."""

    USER = "user"  # domain slot, writable
    SYSTEM = "system"  # id / is_available — stored, read-only


@dataclass(frozen=True)
class SlotModel:
    """Normalized view of one induced slot on an entity class."""

    name: str
    kind: SlotKind
    range: str  # raw LinkML range string
    role: FieldRole = FieldRole.USER
    required: bool = False
    multivalued: bool = False
    identifier: bool = False
    has_default: bool = False  # LinkML ``ifabsent`` present
    description: Optional[str] = None
    target_class: Optional[str] = None  # set when kind is REFERENCE/STRUCTURED
    enum_name: Optional[str] = None  # set when kind is ENUM
    enum_values: tuple[str, ...] = ()
    #: ``hippo_external_xref`` annotation present (issue #48): the slot's
    #: ``(system, value)`` pairs are reverse-lookup keys with global
    #: uniqueness among available entities. Only meaningful on
    #: STRUCTURED slots ranged against ``ExternalReference``.
    is_external_xref: bool = False


@dataclass(frozen=True)
class EntityTypeModel:
    """Normalized view of one concrete, exposed entity class."""

    class_name: str
    accessor_name: str  # canonical plural accessor (shared naming)
    description: Optional[str] = None
    fields: tuple[SlotModel, ...] = dc_field(default_factory=tuple)

    @property
    def user_fields(self) -> tuple[SlotModel, ...]:
        return tuple(f for f in self.fields if f.role is FieldRole.USER)

    @property
    def system_fields(self) -> tuple[SlotModel, ...]:
        return tuple(f for f in self.fields if f.role is FieldRole.SYSTEM)

    @property
    def relationships(self) -> tuple[SlotModel, ...]:
        return tuple(f for f in self.fields if f.kind is SlotKind.REFERENCE)


def exposed_class_names(registry: SchemaRegistry) -> list[str]:
    """Return the concrete, non-infrastructure entity classes, sorted.

    Replaces the duplicated "skip infrastructure + skip abstract" selection
    that lived in both the typed client and the GraphQL builder.
    """
    sv = registry.schema_view
    value_types = registry.value_type_classes()
    names: list[str] = []
    for name in registry.class_names():
        if name in INFRASTRUCTURE_CLASSES or name in value_types:
            continue
        cls = sv.get_class(name)
        if cls is None or cls.abstract:
            continue
        names.append(name)
    return sorted(names)


def _classify_slot(slot: Any, registry: SchemaRegistry, enums: dict[str, Any]) -> SlotModel:
    rng = slot.range or "string"
    name = slot.name
    role = FieldRole.SYSTEM if name in SYSTEM_FIELDS else FieldRole.USER

    kind = SlotKind.SCALAR
    target_class: Optional[str] = None
    enum_name: Optional[str] = None
    enum_values: tuple[str, ...] = ()

    if rng in enums:
        kind = SlotKind.ENUM
        enum_name = rng
        enum_values = tuple(enums[rng].permissible_values.keys())
    elif rng in registry.value_type_classes():
        # Inline structured value (issue #48 / #90): the stored value is the
        # object itself (JSON), not a UUID reference to another entity.
        kind = SlotKind.STRUCTURED
        target_class = rng
    elif registry.has_class(rng) and rng not in INFRASTRUCTURE_CLASSES:
        kind = SlotKind.REFERENCE
        target_class = rng

    return SlotModel(
        name=name,
        kind=kind,
        range=rng,
        role=role,
        required=bool(slot.required),
        multivalued=bool(slot.multivalued),
        identifier=bool(slot.identifier),
        has_default=getattr(slot, "ifabsent", None) is not None,
        description=slot.description,
        target_class=target_class,
        enum_name=enum_name,
        enum_values=enum_values,
        is_external_xref=bool(annotation_value(slot, HIPPO_EXTERNAL_XREF)),
    )


def build_type_model(registry: SchemaRegistry) -> dict[str, EntityTypeModel]:
    """Build the normalized type model for every exposed entity class.

    Returns a mapping ``class_name -> EntityTypeModel``. Reference slots
    pointing at non-exposed classes keep their ``target_class`` so callers can
    decide how to render a dangling reference.
    """
    sv = registry.schema_view
    enums = sv.all_enums()
    model: dict[str, EntityTypeModel] = {}

    for name in exposed_class_names(registry):
        cls = sv.get_class(name)
        fields = tuple(
            _classify_slot(slot, registry, enums)
            for slot in registry.induced_slots(name)
        )
        model[name] = EntityTypeModel(
            class_name=name,
            accessor_name=class_accessor_name(name, cls),
            description=getattr(cls, "description", None),
            fields=fields,
        )
    return model
