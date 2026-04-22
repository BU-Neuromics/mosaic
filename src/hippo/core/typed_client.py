"""Typed client — namespace-aware Pydantic surface over ``HippoClient``.

Implements sec9 §9.8 (Decisions 9.8.A–G). Pydantic classes are generated
in-memory from the merged ``SchemaView`` at ``SchemaRegistry`` load
time. The client exposes each class via a namespace-aware accessor —
``client.samples.create(Sample(...))`` for root-namespace classes,
``client.tissue.samples.create(...)`` for non-root, dot-splitting on
nested namespaces (``assay.quant`` → ``client.assay.quant``).

See ``design/sec9_linkml_redesign.md`` §9.8 for the access-pattern
contract and ``design/sec9_decisions.md`` for the design rationale.
"""

from __future__ import annotations

import logging
import re
import textwrap
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

from hippo.linkml_bridge import (
    HIPPO_ACCESSOR,
    HIPPO_NAMESPACE,
    SchemaRegistry,
    annotation_value,
)


# Names reserved on ``HippoClient`` or at namespace containers. A class
# whose accessor would shadow one of these, or a namespace name matching
# one of these, raises at schema load.
SDK_RESERVED_NAMES: frozenset[str] = frozenset(
    {
        # Core HippoClient methods / attributes
        "storage",
        "pipeline",
        "registry",
        "history",
        "state_at",
        "query",
        "get",
        "put",
        "create",
        "update",
        "delete",
        "replace",
        "supersede_entity",
        "set_availability_bulk",
        "resolve_type",
        "resolve_types",
        # Schema/metadata accessors
        "schemas",
        "metadata",
        # Typed-client surface itself
        "models",
    }
)

# ``root`` is reserved as the alias for flat root-namespace access. A
# user schema MUST NOT declare ``hippo_namespace: root``.
ROOT_NAMESPACE_RESERVED = "root"


def default_accessor(class_name: str) -> str:
    """Derive the default accessor from a class name.

    `snake_case(ClassName) + "s"`. Handles common cases:
    - `Sample` → `samples`
    - `TissueType` → `tissue_types`
    - `DNASample` → `dna_samples`
    """
    # Convert CamelCase / UPPERCase runs to snake_case. The two regexes
    # split acronyms (`DNASample` → `DNA_Sample`) then handle the
    # ClassName → Class_Name boundary.
    s1 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", class_name)
    snake = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()
    return f"{snake}s"


def _is_valid_identifier(name: str) -> bool:
    """A non-empty Python identifier."""
    return bool(name) and name.isidentifier()


class TypedClientError(Exception):
    """Raised at schema load when the typed-client surface cannot be
    built — collisions, reserved-name conflicts, or invalid identifiers.
    """

    def __init__(self, message: str, *, case: Optional[str] = None) -> None:
        self.case = case
        super().__init__(message)


class EntityAccessor:
    """Bound accessor for a single class, backed by ``HippoClient``.

    Provides typed entry points to the generic client's operations:
    ``.create(model_instance)``, ``.get(id)``, ``.query(...)``,
    ``.put(data)``, ``.replace(id, data)``, ``.delete(id)``,
    ``.history(id)``, ``.state_at(id, ts)``, ``.supersede(old, new)``.

    A ``model_class`` (Pydantic) is attached when Pydantic generation
    succeeds for this class; callers can pass a Pydantic instance to
    ``.create`` / ``.put`` / ``.replace`` and the accessor converts it
    to a dict via ``.model_dump()``. Callers MAY still pass plain
    dicts — both paths are supported.
    """

    def __init__(
        self,
        client: Any,
        class_name: str,
        model_class: Optional[type] = None,
    ) -> None:
        self._client = client
        self._class_name = class_name
        self._model_class = model_class

    @property
    def class_name(self) -> str:
        return self._class_name

    @property
    def model_class(self) -> Optional[type]:
        return self._model_class

    @staticmethod
    def _to_dict(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        dump = getattr(value, "model_dump", None)
        if callable(dump):
            return dump()
        raise TypeError(
            f"Expected dict or Pydantic model, got {type(value).__name__}"
        )

    def create(self, data: Any) -> dict[str, Any]:
        return self._client.put(self._class_name, self._to_dict(data))

    def put(self, data: Any, entity_id: Optional[str] = None) -> dict[str, Any]:
        return self._client.put(self._class_name, self._to_dict(data), entity_id)

    def get(self, entity_id: str, expand: Optional[str] = None) -> dict[str, Any]:
        return self._client.get(self._class_name, entity_id, expand=expand)

    def query(self, **kwargs: Any) -> Any:
        return self._client.query(self._class_name, **kwargs)

    def replace(self, entity_id: str, data: Any) -> dict[str, Any]:
        return self._client.replace(
            self._class_name, entity_id, self._to_dict(data)
        )

    def delete(self, entity_id: str) -> bool:
        """SDK-level delete routed through ``HippoClient.delete`` so that
        validation hooks and the standard audit path run. For the raw
        adapter-only delete (no SDK hooks), callers can reach
        ``client.storage.delete(...)`` directly.
        """
        return self._client.delete(self._class_name, entity_id)

    def history(self, entity_id: str) -> list[dict[str, Any]]:
        return self._client.history(entity_id)

    def state_at(self, entity_id: str, timestamp: str) -> Optional[dict[str, Any]]:
        return self._client.state_at(entity_id, timestamp)


class Namespace:
    """Container for typed accessors and nested namespaces.

    Attributes are set at build time by :func:`build_typed_surface`.
    """

    def __init__(self, name: str) -> None:
        self._name = name
        # Maintained for introspection / tests:
        self._accessors: dict[str, EntityAccessor] = {}
        self._subnamespaces: dict[str, "Namespace"] = {}

    @property
    def namespace_name(self) -> str:
        return self._name

    def accessors(self) -> dict[str, EntityAccessor]:
        return dict(self._accessors)

    def subnamespaces(self) -> dict[str, "Namespace"]:
        return dict(self._subnamespaces)

    def __repr__(self) -> str:
        parts: list[str] = []
        if self._accessors:
            parts.append(f"accessors={sorted(self._accessors)}")
        if self._subnamespaces:
            parts.append(f"sub={sorted(self._subnamespaces)}")
        return f"Namespace({self._name!r}, {', '.join(parts) or 'empty'})"


def _resolve_namespace(cls_name: str, cls_obj: Any) -> list[str]:
    """Return the namespace path for a class as a list of segments.

    Empty list means root namespace. Dots in ``hippo_namespace: a.b.c``
    produce three segments ``["a", "b", "c"]``.
    """
    ns = annotation_value(cls_obj, HIPPO_NAMESPACE)
    if ns is None or ns == "":
        return []
    if not isinstance(ns, str):
        raise TypedClientError(
            f"hippo_namespace on class {cls_name!r} must be a string, got "
            f"{type(ns).__name__}",
            case="namespace_type",
        )
    if ns == ROOT_NAMESPACE_RESERVED:
        raise TypedClientError(
            f"Class {cls_name!r} declares hippo_namespace: root — `root` is "
            f"reserved as the typed-client flat-access alias. Omit "
            f"`hippo_namespace` for root-namespace classes.",
            case="reserved_root",
        )
    segments = ns.split(".")
    for seg in segments:
        if not _is_valid_identifier(seg):
            raise TypedClientError(
                f"Class {cls_name!r} declares hippo_namespace: {ns!r}; "
                f"segment {seg!r} is not a valid Python identifier.",
                case="invalid_namespace_segment",
            )
        if seg in SDK_RESERVED_NAMES:
            raise TypedClientError(
                f"Class {cls_name!r} declares hippo_namespace: {ns!r}; "
                f"segment {seg!r} conflicts with an SDK-reserved attribute.",
                case="namespace_reserved",
            )
    return segments


def _resolve_accessor(cls_name: str, cls_obj: Any) -> str:
    override = annotation_value(cls_obj, HIPPO_ACCESSOR)
    if override is not None:
        if not isinstance(override, str) or not _is_valid_identifier(override):
            raise TypedClientError(
                f"Class {cls_name!r} declares hippo_accessor: {override!r}; "
                f"must be a valid Python identifier.",
                case="invalid_accessor",
            )
        return override
    return default_accessor(cls_name)


def _walk_to_namespace(root: Namespace, segments: list[str]) -> Namespace:
    """Walk/create intermediate Namespace containers; return the leaf."""
    cur = root
    for seg in segments:
        # Case 2 check: the segment must not clash with an existing
        # class accessor at this level.
        if seg in cur._accessors:
            raise TypedClientError(
                f"accessor/sub-namespace collision: sub-namespace "
                f"segment {seg!r} conflicts with a class accessor of the "
                f"same name at level {cur.namespace_name!r}.",
                case="accessor_vs_namespace",
            )
        if seg not in cur._subnamespaces:
            new_name = f"{cur._name}.{seg}" if cur._name else seg
            cur._subnamespaces[seg] = Namespace(new_name)
        cur = cur._subnamespaces[seg]
    return cur


def _install_accessor(
    target: Namespace,
    accessor_name: str,
    cls_name: str,
    accessor: EntityAccessor,
) -> None:
    # Case 1: same-namespace duplication.
    if accessor_name in target._accessors:
        other = target._accessors[accessor_name].class_name
        raise TypedClientError(
            f"typed-client accessor collision: classes {other!r} and "
            f"{cls_name!r} both resolve to accessor {accessor_name!r} in "
            f"namespace {target.namespace_name!r}. Add `hippo_accessor` to "
            f"at least one class to disambiguate.",
            case="duplicate_accessor",
        )
    # Case 2: clash with an existing sub-namespace segment.
    if accessor_name in target._subnamespaces:
        raise TypedClientError(
            f"accessor/sub-namespace collision: class {cls_name!r} "
            f"(accessor {accessor_name!r}) conflicts with sub-namespace "
            f"{target._subnamespaces[accessor_name].namespace_name!r}.",
            case="accessor_vs_namespace",
        )
    target._accessors[accessor_name] = accessor


def _materialize_attributes(ns: Namespace) -> None:
    """Recursively set accessors and sub-namespaces as Python attributes
    on each ``Namespace`` so that ``client.tissue.samples.create(...)``
    and ``client.assay.quant.measurements.create(...)`` resolve via
    standard attribute lookup.
    """
    for name, accessor in ns._accessors.items():
        setattr(ns, name, accessor)
    for name, sub in ns._subnamespaces.items():
        setattr(ns, name, sub)
        _materialize_attributes(sub)


def build_typed_surface(
    client: Any,
    registry: SchemaRegistry,
    models: Optional[dict[str, type]] = None,
) -> Namespace:
    """Build the namespace-aware accessor tree for ``client``.

    Returns the root ``Namespace``. Non-abstract domain classes (i.e.
    those not inherited from hippo_core primitives that the generic
    client already exposes) get accessors rooted under their declared
    namespace. Raises :class:`TypedClientError` on any of the four
    collision cases (sec9 §9.8 Decision 9.8.B).
    """
    models = models or {}
    root = Namespace("")
    sv = registry.schema_view

    # hippo_core classes are infrastructure; the typed client doesn't
    # expose them as write targets (Entity is abstract; ProvenanceRecord,
    # Process, Validator, ReferenceLoader are system concerns). Domain
    # schemas subclass Entity via is_a, so we identify domain classes
    # as non-abstract concrete classes that are not the hippo_core
    # fixed set.
    hippo_core_infrastructure = {
        "Entity",
        "ProvenanceRecord",
        "Process",
        "Validator",
        "ReferenceLoader",
    }

    for cls_name in registry.class_names():
        if cls_name in hippo_core_infrastructure:
            continue
        cls_obj = sv.get_class(cls_name)
        if cls_obj is None or cls_obj.abstract:
            continue

        segments = _resolve_namespace(cls_name, cls_obj)
        accessor_name = _resolve_accessor(cls_name, cls_obj)

        if accessor_name in SDK_RESERVED_NAMES:
            raise TypedClientError(
                f"accessor/reserved-name collision: class {cls_name!r}'s "
                f"accessor {accessor_name!r} conflicts with an SDK-reserved "
                f"attribute. Add `hippo_accessor` to override.",
                case="accessor_reserved",
            )

        model_class = models.get(cls_name)
        target = _walk_to_namespace(root, segments)
        _install_accessor(
            target,
            accessor_name,
            cls_name,
            EntityAccessor(client, cls_name, model_class=model_class),
        )

    _materialize_attributes(root)
    return root


def generate_pydantic_models(registry: SchemaRegistry) -> dict[str, type]:
    """Generate Pydantic classes from the merged SchemaView.

    Runs LinkML's ``PydanticGenerator`` in memory and returns a mapping
    of ``class_name → Pydantic class``. The schema is a compulsory
    contract (Decision 9.8.H, revised 2026-04-22): any failure —
    generator import, serialization, Pydantic import, or exec of the
    generated module — raises :class:`TypedClientError` at
    ``HippoClient.__init__``. A deployment whose schema can't be
    generated has a schema defect, not a transition gap.
    """
    try:
        from linkml.generators.pydanticgen import PydanticGenerator
    except Exception as exc:
        raise TypedClientError(
            f"typed-client: PydanticGenerator unavailable ({exc}). "
            "LinkML's Pydantic generator is a hard dependency of the "
            "typed-client surface per Decision 9.8.H.",
            case="pydantic_generator_unavailable",
        ) from exc

    try:
        # PydanticGenerator reads from a schema file path or a yaml string;
        # _flatten_for_validator already produces a self-contained schema
        # dict. Re-dump to YAML for the generator.
        import yaml

        from hippo.linkml_bridge import _flatten_for_validator

        flat = _flatten_for_validator(registry.schema_view)
        yaml_text = yaml.safe_dump(flat, sort_keys=False)
        gen = PydanticGenerator(yaml_text)
        code = gen.serialize()
    except Exception as exc:
        raise TypedClientError(
            f"typed-client: Pydantic generation failed ({exc}). The "
            "merged schema is not accepted by LinkML's PydanticGenerator. "
            "Fix the schema; the Pydantic surface is a compulsory "
            "contract (Decision 9.8.H).",
            case="pydantic_generation_failed",
        ) from exc

    try:
        from pydantic import BaseModel
    except Exception as exc:
        raise TypedClientError(
            f"typed-client: Pydantic unavailable ({exc}). Pydantic is a "
            "hard dependency of the typed-client surface.",
            case="pydantic_unavailable",
        ) from exc

    # Execute the generated module in an isolated namespace and harvest
    # every Pydantic class from it by matching against BaseModel.
    module_globals: dict[str, Any] = {}
    try:
        exec(textwrap.dedent(code), module_globals)  # noqa: S102
    except Exception as exc:
        raise TypedClientError(
            f"typed-client: generated Pydantic module failed to import "
            f"({exc}). The generated code is inconsistent; this is either "
            "a LinkML PydanticGenerator defect or a schema pattern the "
            "generator can't express.",
            case="generated_module_invalid",
        ) from exc

    out: dict[str, type] = {}
    for name, value in module_globals.items():
        if (
            isinstance(value, type)
            and issubclass(value, BaseModel)
            and value is not BaseModel
        ):
            out[name] = value
    return out
