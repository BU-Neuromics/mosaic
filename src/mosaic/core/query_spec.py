"""QuerySpec (ADR-0009 / issue #183): the canonical typed cross-class query
artifact this boundary accepts, as normatively defined by Aperture's
ADR-0035 (``design/decisions/ADR-0035-cross-class-queries-typed-queryspec.md``
in the ``aperture`` repo) and its shipped implementation
(``web/src/query/querySpec.ts``).

This module is the Python side of that same artifact: parsing (structural,
schema-independent — mirrors the TS ``validateQuerySpecShape`` shape guard)
and validation (semantic, capability-manifest-driven — mirrors the TS
``validateQuerySpec``, ported to run server-side where the capability
manifest (:mod:`mosaic.core.schema_typing`) is available in-process with no
introspection round-trip).

**Scope note (issue #183, validator-only increment):** this module parses
and validates. It does not compile a validated ``QuerySpec`` into GraphQL
``where:``/aggregation arguments (the executor) and registers no MCP tool —
both are a separate increment (#182 sequencing), gated on #185's auth
decision landing first. Nothing here is reachable from any network surface.

**Shape decisions, and why:** ADR-0035's normative artifact also specifies
``asOf``, ``sort``, and ``columns``, beyond the flat MVP subset
(``v``/``anchor``/``mode``/``criteria``) the current Aperture TS code emits.
The dividing line used here is not "ratified ADR text vs. current code" —
it is *what Mosaic's ``where:`` surface can actually compile today*:

- Nested ``CriteriaGroup``s ARE accepted (depth-capped at 3, per ADR-0035):
  Mosaic's generated ``<Class>Filter`` already carries ``and``/``or``/``not``
  combinators at arbitrary depth (ADR-0006).
- ``asOf`` IS accepted, with the same hard mutual-exclusion against any
  relationship predicate anywhere in the tree that Mosaic's storage layer
  already enforces (``has_relationship_predicate``, ADR-0001).
- ``sort`` IS accepted, checked against the manifest's per-field
  ``orderable`` flag (ADR-0007's ``<Class>OrderField``).
- ``columns`` is REJECTED with a coded, not-a-crash error: its
  aggregate-vs-explode choice on a to-many path has no Mosaic-side
  equivalent to validate against — ADR-0009's own Consequences section
  names this as unresolved even in ADR-0035 itself. Today's real Aperture
  emitter never sends this field, so the rejection never fires against an
  actual consumer; it exists so a future caller gets a clear error instead
  of a silently-ignored field.

**Op spelling:** ADR-0035's prose writes ``isNull``; both real
implementations (Aperture's shipped ``QueryOp`` type and this module's
``FilterOp``) use ``is_null``. Code wins — do not "fix" this back to the
prose spelling.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any, Literal, Optional, Union

from mosaic.core.schema_typing import EntityCapability, FilterOp, SlotKind

#: ADR-0035's normative nesting cap on CriteriaGroup depth.
MAX_CRITERIA_DEPTH = 3

_VALID_QUANTIFIERS = frozenset({"some", "none"})
_VALID_MODES = frozenset({"AND", "OR"})


@dataclass(frozen=True)
class FieldCondition:
    """``{slot, op, value}`` — a leaf condition on one field of the entity
    it is evaluated against (the anchor at the top level; a RelatedCondition's
    target entity when nested under one)."""

    slot: str
    op: str
    value: Any = None
    kind: Literal["field"] = "field"


@dataclass(frozen=True)
class RelatedCondition:
    """``{edge, quantifier, criteria}`` — quantified relationship predicate.
    ``criteria`` holds on the SAME related record, flat/AND (matches both
    ADR-0035's prose and the current TS implementation — no nested groups
    inside a RelatedCondition)."""

    edge: str
    quantifier: str
    criteria: tuple[FieldCondition, ...] = ()
    kind: Literal["related"] = "related"


@dataclass(frozen=True)
class CriteriaGroup:
    """Nested ``{mode, criteria}`` boolean group (ADR-0035, depth-capped)."""

    mode: str
    criteria: tuple["Criterion", ...] = ()
    kind: Literal["group"] = "group"


Criterion = Union[FieldCondition, RelatedCondition, CriteriaGroup]


@dataclass(frozen=True)
class SortField:
    """One ``order_by`` field on the anchor (ADR-0007)."""

    slot: str
    direction: str = "asc"  # "asc" | "desc"


@dataclass(frozen=True)
class QuerySpec:
    """The parsed, not-yet-validated artifact (ADR-0009/ADR-0035)."""

    v: int
    anchor: str
    mode: str
    criteria: tuple[Criterion, ...] = ()
    as_of: Optional[str] = None
    sort: tuple[SortField, ...] = ()


class QuerySpecShapeError(ValueError):
    """Structural problem with the raw input — schema-independent (mirrors
    the TS ``validateQuerySpecShape`` guard). Never raised for a problem
    that depends on what a specific deployment's schema supports; that is
    :func:`validate_query_spec`'s job."""

    def __init__(self, code: str, message: str, path: str = "$"):
        self.code = code
        self.path = path
        super().__init__(f"{path}: {message}")


def _require(cond: bool, code: str, message: str, path: str) -> None:
    if not cond:
        raise QuerySpecShapeError(code, message, path)


def _parse_field_condition(raw: Any, path: str) -> FieldCondition:
    _require(isinstance(raw, dict), "INVALID_QUERYSPEC_SHAPE", "must be an object", path)
    _require(isinstance(raw.get("slot"), str), "INVALID_QUERYSPEC_SHAPE", "'slot' must be a string", f"{path}.slot")
    _require(isinstance(raw.get("op"), str), "INVALID_QUERYSPEC_SHAPE", "'op' must be a string", f"{path}.op")
    return FieldCondition(slot=raw["slot"], op=raw["op"], value=raw.get("value"))


def _parse_related_condition(raw: dict, path: str) -> RelatedCondition:
    _require(isinstance(raw.get("edge"), str), "INVALID_QUERYSPEC_SHAPE", "'edge' must be a string", f"{path}.edge")
    quantifier = raw.get("quantifier")
    _require(
        quantifier in _VALID_QUANTIFIERS,
        "INVALID_QUERYSPEC_SHAPE",
        f"'quantifier' must be one of {sorted(_VALID_QUANTIFIERS)}",
        f"{path}.quantifier",
    )
    raw_criteria = raw.get("criteria", [])
    _require(isinstance(raw_criteria, list), "INVALID_QUERYSPEC_SHAPE", "'criteria' must be a list", f"{path}.criteria")
    sub = tuple(
        _parse_field_condition(c, f"{path}.criteria[{i}]") for i, c in enumerate(raw_criteria)
    )
    return RelatedCondition(edge=raw["edge"], quantifier=quantifier, criteria=sub)


def _parse_criterion(raw: Any, path: str, depth: int) -> Criterion:
    _require(isinstance(raw, dict), "INVALID_QUERYSPEC_SHAPE", "must be an object", path)
    kind = raw.get("kind")
    if kind == "field":
        return _parse_field_condition(raw, path)
    if kind == "related":
        return _parse_related_condition(raw, path)
    if kind == "group":
        return _parse_criteria_group(raw, path, depth)
    raise QuerySpecShapeError(
        "INVALID_QUERYSPEC_SHAPE",
        f"'kind' must be one of 'field', 'related', 'group' (got {kind!r})",
        f"{path}.kind",
    )


def _parse_criteria_group(raw: dict, path: str, depth: int) -> CriteriaGroup:
    _require(
        depth <= MAX_CRITERIA_DEPTH,
        "DEPTH_EXCEEDED",
        f"criteria nesting exceeds ADR-0035's cap of {MAX_CRITERIA_DEPTH}",
        path,
    )
    mode = raw.get("mode")
    _require(mode in _VALID_MODES, "INVALID_QUERYSPEC_SHAPE", "'mode' must be 'AND' or 'OR'", f"{path}.mode")
    raw_criteria = raw.get("criteria", [])
    _require(isinstance(raw_criteria, list), "INVALID_QUERYSPEC_SHAPE", "'criteria' must be a list", f"{path}.criteria")
    sub = tuple(
        _parse_criterion(c, f"{path}.criteria[{i}]", depth + 1)
        for i, c in enumerate(raw_criteria)
    )
    return CriteriaGroup(mode=mode, criteria=sub)


def _parse_sort_field(raw: Any, path: str) -> SortField:
    _require(isinstance(raw, dict), "INVALID_QUERYSPEC_SHAPE", "must be an object", path)
    _require(isinstance(raw.get("slot"), str), "INVALID_QUERYSPEC_SHAPE", "'slot' must be a string", f"{path}.slot")
    direction = raw.get("direction", "asc")
    _require(direction in ("asc", "desc"), "INVALID_QUERYSPEC_SHAPE", "'direction' must be 'asc' or 'desc'", f"{path}.direction")
    return SortField(slot=raw["slot"], direction=direction)


def parse_query_spec(raw: Any) -> QuerySpec:
    """Parse a raw (JSON-decoded) object into a :class:`QuerySpec`.

    Structural only — every check here is schema-independent (a malformed
    QuerySpec is malformed on every Mosaic deployment). Raises
    :class:`QuerySpecShapeError`. Schema-dependent legality (does this
    anchor/slot/op/edge/enum-value/sort-field exist and is it usable) is
    :func:`validate_query_spec`'s job, run separately against a specific
    deployment's capability manifest.
    """
    _require(isinstance(raw, dict), "INVALID_QUERYSPEC_SHAPE", "QuerySpec must be an object", "$")
    _require(raw.get("v") == 1, "INVALID_QUERYSPEC_SHAPE", "'v' must be 1", "$.v")
    _require(isinstance(raw.get("anchor"), str), "INVALID_QUERYSPEC_SHAPE", "'anchor' must be a string", "$.anchor")
    mode = raw.get("mode")
    _require(mode in _VALID_MODES, "INVALID_QUERYSPEC_SHAPE", "'mode' must be 'AND' or 'OR'", "$.mode")
    if "columns" in raw and raw["columns"] is not None:
        raise QuerySpecShapeError(
            "COLUMNS_NOT_SUPPORTED",
            "'columns' (aggregate-vs-explode selection, ADR-0035) has no "
            "Mosaic-side compiler yet — omit it, or request full envelopes "
            "and project client-side",
            "$.columns",
        )
    raw_criteria = raw.get("criteria", [])
    _require(isinstance(raw_criteria, list), "INVALID_QUERYSPEC_SHAPE", "'criteria' must be a list", "$.criteria")
    criteria = tuple(
        _parse_criterion(c, f"$.criteria[{i}]", depth=1) for i, c in enumerate(raw_criteria)
    )
    as_of = raw.get("asOf") or raw.get("as_of")
    if as_of is not None:
        _require(isinstance(as_of, str), "INVALID_QUERYSPEC_SHAPE", "'asOf' must be an ISO-8601 string", "$.asOf")
    raw_sort = raw.get("sort") or []
    _require(isinstance(raw_sort, list), "INVALID_QUERYSPEC_SHAPE", "'sort' must be a list", "$.sort")
    sort = tuple(_parse_sort_field(s, f"$.sort[{i}]") for i, s in enumerate(raw_sort))
    return QuerySpec(v=1, anchor=raw["anchor"], mode=mode, criteria=criteria, as_of=as_of, sort=sort)


# ---------------------------------------------------------------------------
# Validation: total, capability-manifest-driven (mirrors the TS
# validateQuerySpec, ported server-side per ADR-0009 decision 5).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QuerySpecError:
    """One actionable validation failure (ADR-0009 item 3: "specific and
    actionable per-criterion... load-bearing, not cosmetic"). ``code`` is a
    fixed vocabulary a generic MCP client can branch on; ``message`` names
    the offending slot/op/edge and, for enum/op mismatches, the valid set."""

    code: str
    message: str
    path: str


@dataclass(frozen=True)
class ValidationResult:
    errors: tuple[QuerySpecError, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.errors


def _contains_related_condition(criteria: tuple[Criterion, ...]) -> bool:
    for c in criteria:
        if isinstance(c, RelatedCondition):
            return True
        if isinstance(c, CriteriaGroup) and _contains_related_condition(c.criteria):
            return True
    return False


def _validate_field_condition(
    cond: FieldCondition, entity: EntityCapability, path: str, errors: list[QuerySpecError]
) -> None:
    field = entity.fields_by_name.get(cond.slot)
    if field is None:
        errors.append(
            QuerySpecError(
                "UNKNOWN_SLOT",
                f"{entity.class_name!r} has no field {cond.slot!r}. "
                f"Known fields: {sorted(entity.fields_by_name)}",
                f"{path}.slot",
            )
        )
        return
    try:
        op = FilterOp(cond.op)
    except ValueError:
        errors.append(
            QuerySpecError(
                "INVALID_QUERYSPEC_SHAPE",
                f"unknown operator {cond.op!r}. Valid operators: "
                f"{sorted(o.value for o in FilterOp)}",
                f"{path}.op",
            )
        )
        return
    if op not in field.filter_ops:
        if field.predicate:
            errors.append(
                QuerySpecError(
                    "UNSUPPORTED_OP",
                    f"{entity.class_name}.{cond.slot} is a relationship — filter "
                    f"it with a RelatedCondition (edge={cond.slot!r}), not a "
                    f"FilterOp",
                    f"{path}.op",
                )
            )
        else:
            errors.append(
                QuerySpecError(
                    "UNSUPPORTED_OP",
                    f"{entity.class_name}.{cond.slot} does not support "
                    f"{cond.op!r}. Supported: {sorted(o.value for o in field.filter_ops)}",
                    f"{path}.op",
                )
            )
        return
    value_ok = True
    if op is FilterOp.IN and not isinstance(cond.value, list):
        errors.append(QuerySpecError("INVALID_VALUE_TYPE", "'in' requires a list value", f"{path}.value"))
        value_ok = False
    elif op is FilterOp.IS_NULL and not isinstance(cond.value, bool):
        errors.append(QuerySpecError("INVALID_VALUE_TYPE", "'is_null' requires a boolean value", f"{path}.value"))
        value_ok = False
    elif op not in (FilterOp.IS_NULL,) and cond.value is None:
        errors.append(QuerySpecError("MISSING_VALUE", f"{cond.slot!r} needs a 'value' for {cond.op!r}", f"{path}.value"))
        value_ok = False
    if value_ok and field.slot.kind is SlotKind.ENUM and cond.value is not None:
        values = cond.value if op is FilterOp.IN else [cond.value]
        bad = [v for v in values if isinstance(v, str) and v not in field.slot.enum_values]
        if bad:
            errors.append(
                QuerySpecError(
                    "INVALID_ENUM_VALUE",
                    f"{entity.class_name}.{cond.slot} does not accept {bad!r}. "
                    f"Valid values: {list(field.slot.enum_values)}",
                    f"{path}.value",
                )
            )


def _validate_related_condition(
    cond: RelatedCondition,
    entity: EntityCapability,
    manifest: dict[str, EntityCapability],
    path: str,
    errors: list[QuerySpecError],
) -> None:
    field = entity.fields_by_name.get(cond.edge)
    if field is None or field.slot.kind is not SlotKind.REFERENCE:
        errors.append(
            QuerySpecError(
                "UNKNOWN_EDGE",
                f"{entity.class_name!r} has no relationship {cond.edge!r}. "
                f"Known relationships: "
                f"{sorted(f.slot.name for f in entity.fields if f.slot.kind is SlotKind.REFERENCE)}",
                f"{path}.edge",
            )
        )
        return
    if not field.predicate:
        errors.append(
            QuerySpecError(
                "NOT_PREDICATE_FILTERABLE",
                f"{entity.class_name}.{cond.edge} targets a type not exposed "
                f"on this deployment — cannot filter through it",
                f"{path}.edge",
            )
        )
        return
    target = manifest.get(field.slot.target_class)
    if target is None:
        errors.append(
            QuerySpecError("NOT_PREDICATE_FILTERABLE", f"target type {field.slot.target_class!r} is not exposed", f"{path}.edge")
        )
        return
    for i, sub in enumerate(cond.criteria):
        _validate_field_condition(sub, target, f"{path}.criteria[{i}]", errors)


def _validate_criteria(
    criteria: tuple[Criterion, ...],
    entity: EntityCapability,
    manifest: dict[str, EntityCapability],
    path: str,
    errors: list[QuerySpecError],
) -> None:
    for i, c in enumerate(criteria):
        cpath = f"{path}[{i}]"
        if isinstance(c, FieldCondition):
            _validate_field_condition(c, entity, cpath, errors)
        elif isinstance(c, RelatedCondition):
            _validate_related_condition(c, entity, manifest, cpath, errors)
        elif isinstance(c, CriteriaGroup):
            _validate_criteria(c.criteria, entity, manifest, f"{cpath}.criteria", errors)


def validate_query_spec(
    spec: QuerySpec, manifest: dict[str, EntityCapability]
) -> ValidationResult:
    """Total, capability-manifest-driven validation (ADR-0009 item 3).

    Every anchor/slot/op/edge/enum-value/sort-field is checked against what
    this specific deployment's schema actually advertises. A ``QuerySpec``
    that validates cleanly compiles to a query the ``where:``/aggregation
    surface accepts.
    """
    errors: list[QuerySpecError] = []
    anchor = manifest.get(spec.anchor)
    if anchor is None:
        return ValidationResult(
            errors=(
                QuerySpecError(
                    "UNKNOWN_ANCHOR",
                    f"unknown anchor {spec.anchor!r}. Known types: {sorted(manifest)}",
                    "$.anchor",
                ),
            )
        )
    _validate_criteria(spec.criteria, anchor, manifest, "$.criteria", errors)
    if spec.as_of is not None and _contains_related_condition(spec.criteria):
        errors.append(
            QuerySpecError(
                "ASOF_RELATIONSHIP_FILTER_UNSUPPORTED",
                "'asOf' cannot combine with a RelatedCondition anywhere in "
                "'criteria' (ADR-0001)",
                "$.asOf",
            )
        )
    for i, s in enumerate(spec.sort):
        field = anchor.fields_by_name.get(s.slot)
        if field is None:
            errors.append(
                QuerySpecError(
                    "UNKNOWN_SLOT",
                    f"{anchor.class_name!r} has no field {s.slot!r}",
                    f"$.sort[{i}].slot",
                )
            )
        elif not field.orderable:
            errors.append(
                QuerySpecError(
                    "UNORDERABLE_SORT_FIELD",
                    f"{anchor.class_name}.{s.slot} is not orderable "
                    f"(multivalued, reference, or structured fields have no "
                    f"meaningful order)",
                    f"$.sort[{i}].slot",
                )
            )
    return ValidationResult(errors=tuple(errors))
