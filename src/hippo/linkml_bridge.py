"""LinkML-backed schema loading, introspection, and validation.

Thin wrapper around ``linkml_runtime.SchemaView`` and ``linkml.validator`` that
exposes the handful of projections Hippo needs. Hippo-specific slot metadata is
carried via LinkML annotations under flat ``hippo_<name>`` keys (e.g.
``hippo_search: fts5``). User-authored schema YAML stays 100% valid LinkML.

Every ``hippo_*`` annotation used in a user schema must be declared in
``hippo_ext`` (ships with the package at ``src/hippo/schemas/hippo_ext.yaml``).
``SchemaRegistry`` validates this at construction time — undeclared annotations,
value-type mismatches, and wrong-target attachments surface as
``SchemaError`` at load. See sec9 §9.4 for the design rationale and
``design/reference_hippo_ext.md`` for the per-annotation reference.
"""

from __future__ import annotations

import importlib.resources
import re
from pathlib import Path
from typing import Any, Optional, Union

import yaml
from linkml.validator import Validator
from linkml.validator.plugins import JsonschemaValidationPlugin
from linkml_runtime.linkml_model.meta import ClassDefinition, SlotDefinition
from linkml_runtime.utils.schemaview import SchemaView


HIPPO_SEARCH = "hippo_search"
HIPPO_INDEX = "hippo_index"
HIPPO_INDEX_PARTIAL = "hippo_index_partial"
HIPPO_UNIQUE = "hippo_unique"
HIPPO_APPEND_ONLY = "hippo_append_only"
HIPPO_ACCESSOR = "hippo_accessor"
HIPPO_NAMESPACE = "hippo_namespace"

HIPPO_ANNOTATION_PREFIX = "hippo_"
_CLASS_ANNOTATION_SUBSET = "class_annotation"
_SLOT_ANNOTATION_SUBSET = "slot_annotation"

# Name of the synthetic tree-root class used for LinkML-native instance YAML
# (PR 3.1). Carries one multivalued slot per concrete class in the merged
# schema. The leading underscore keeps it from colliding with user classes,
# which by LinkML convention use UpperCamelCase.
TREE_ROOT_CLASS_NAME = "_HippoInstanceBundle"


def default_accessor(class_name: str) -> str:
    """Derive the default accessor / tree-root slot name from a class name.

    ``snake_case(ClassName) + "s"``. Handles common cases:
    - ``Sample`` → ``samples``
    - ``TissueType`` → ``tissue_types``
    - ``DNASample`` → ``dna_samples``
    - ``ExternalID`` → ``external_ids``

    The naive ``+ "s"`` produces awkward plurals for words ending in ``s``
    (e.g. ``Process`` → ``processs``). Schemas override via the
    ``hippo_accessor`` class annotation; see ``class_accessor_name``.
    """
    s1 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", class_name)
    snake = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()
    return f"{snake}s"


def class_accessor_name(class_name: str, cls_obj: Any) -> str:
    """Accessor / tree-root slot name for a class, honoring ``hippo_accessor``.

    Returns the ``hippo_accessor`` annotation value if present (validated
    as a string), else ``default_accessor(class_name)``. Used by both the
    typed-client surface (``typed_client._resolve_accessor``) and the
    synthesized tree-root class so users see one mental model.

    This helper applies only the basic resolution. The typed-client wraps
    it with stricter identifier / collision validation; the tree-root
    synthesis accepts the result as-is since downstream LinkML validation
    will surface any malformed slot name.
    """
    override = annotation_value(cls_obj, HIPPO_ACCESSOR)
    if isinstance(override, str) and override:
        return override
    return default_accessor(class_name)


def annotation_value(element: Any, key: str) -> Optional[Any]:
    """Return the ``.value`` of a named annotation, or ``None`` if absent."""
    ann = getattr(element, "annotations", None)
    if ann is None or key not in ann:
        return None
    return ann[key].value


def slot_default(slot: Any) -> Optional[Any]:
    """Return a slot's default value in a DDL-friendly Python form, or None.

    LinkML stores `ifabsent` as a string (e.g. "true", "false", "active",
    "int(0)", "uuid()"). For boolean-ranged slots we coerce the literal
    "true"/"false" to Python booleans so the downstream ``_format_default``
    helpers emit native SQL (``1``/``0`` for SQLite, ``TRUE``/``FALSE`` for
    Postgres) rather than quoting the string. Other ifabsent forms pass
    through unchanged for now; richer parsing (e.g. ``uuid()``, ``int(0)``)
    is a later concern.
    """
    value = getattr(slot, "ifabsent", None)
    if value is None:
        return None
    if getattr(slot, "range", None) == "boolean" and isinstance(value, str):
        lowered = value.strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    return value


# ---------------------------------------------------------------------------
# Shipped-with-Hippo schemas — hippo_ext (annotation vocabulary) and hippo_core
# (Entity, Status, Operation, Validator, ReferenceLoader). Both are loaded as
# bundled resources; hippo_core is made available to user schemas through
# SchemaView's importmap so callers can declare `imports: [hippo_core]` and
# `is_a: Entity`.
# ---------------------------------------------------------------------------

_HIPPO_EXT_SV: Optional[SchemaView] = None


def _hippo_ext_resource_path() -> str:
    resource = importlib.resources.files("hippo.schemas").joinpath("hippo_ext.yaml")
    return str(resource)


def _hippo_core_resource_path() -> str:
    resource = importlib.resources.files("hippo.schemas").joinpath("hippo_core.yaml")
    return str(resource)


def _hippo_ext_schema_view() -> SchemaView:
    global _HIPPO_EXT_SV
    if _HIPPO_EXT_SV is None:
        _HIPPO_EXT_SV = SchemaView(_hippo_ext_resource_path())
    return _HIPPO_EXT_SV


def _bundled_importmap() -> dict[str, str]:
    """Importmap that lets user schemas say `imports: [hippo_core]`.

    SchemaView resolves import names against this map and appends `.yaml`
    when opening the file, so values must omit the extension.
    """
    return {
        "hippo_core": _hippo_core_resource_path().removesuffix(".yaml"),
    }


def _check_value_type(slot_decl: SlotDefinition, value: Any, enums: dict) -> Optional[str]:
    """Return an error message if ``value`` doesn't match ``slot_decl.range``; else None."""
    rng = slot_decl.range
    if rng is None:
        return None
    if rng == "boolean":
        if not isinstance(value, bool):
            return f"expected boolean, got {type(value).__name__} ({value!r})"
        return None
    if rng == "integer":
        # bool is a subclass of int in Python — reject bool under integer
        if isinstance(value, bool) or not isinstance(value, int):
            return f"expected integer, got {type(value).__name__} ({value!r})"
        return None
    if rng == "string":
        if not isinstance(value, str):
            return f"expected string, got {type(value).__name__} ({value!r})"
        return None
    if rng in enums:
        permissible = set(enums[rng].permissible_values.keys())
        if str(value) not in permissible:
            return (
                f"value {value!r} not in enum {rng} "
                f"(permissible: {sorted(permissible)})"
            )
        return None
    # Unknown range — tolerant.
    return None


def _validate_one_annotation(
    ext_slots: dict,
    ext_enums: dict,
    key: str,
    ann: Any,
    target_kind: str,
    target_path: str,
) -> Optional[str]:
    decl = ext_slots.get(key)
    if decl is None:
        known = sorted(k for k in ext_slots if k.startswith(HIPPO_ANNOTATION_PREFIX))
        return (
            f"annotation `{key}` on {target_kind} `{target_path}` is not "
            f"declared in hippo_ext. Known annotations: {known}"
        )
    expected_subset = (
        _CLASS_ANNOTATION_SUBSET if target_kind == "class" else _SLOT_ANNOTATION_SUBSET
    )
    in_subset = list(decl.in_subset) if decl.in_subset else []
    if expected_subset not in in_subset:
        return (
            f"annotation `{key}` on {target_kind} `{target_path}` is invalid — "
            f"`{key}` may only attach to {', '.join(in_subset) or '(nothing)'}"
        )
    value = getattr(ann, "value", ann)
    type_err = _check_value_type(decl, value, ext_enums)
    if type_err:
        return f"annotation `{key}` on {target_kind} `{target_path}`: {type_err}"
    return None


def _iter_hippo_annotations(element: Any):
    """Yield (key, annotation) pairs for every hippo_* annotation on ``element``.

    LinkML exposes ``.annotations`` as a ``JsonObj`` which supports ``in`` and
    ``[]`` indexing but doesn't implement ``.items()``. We iterate by filtering
    to keys that start with the hippo_ prefix.
    """
    annotations = getattr(element, "annotations", None)
    if annotations is None:
        return
    for key in list(annotations):
        key = str(key)
        if not key.startswith(HIPPO_ANNOTATION_PREFIX):
            continue
        try:
            ann = annotations[key]
        except KeyError:
            continue
        yield key, ann


def _validate_hippo_annotations(sv: SchemaView) -> None:
    """Validate every hippo_* annotation in ``sv`` against hippo_ext.

    Raises ``SchemaError`` aggregating all failures if any annotation is
    undeclared, mistyped, or attached to the wrong kind of element.
    """
    # Skip validation if we're loading hippo_ext itself (circular).
    if sv.schema.name == "hippo_ext":
        return

    ext = _hippo_ext_schema_view()
    ext_slots = ext.all_slots()
    ext_enums = ext.all_enums()

    failures: list[str] = []

    for class_name, cls in sv.all_classes().items():
        for key, ann in _iter_hippo_annotations(cls):
            err = _validate_one_annotation(
                ext_slots, ext_enums, key, ann, "class", class_name
            )
            if err:
                failures.append(err)

        try:
            induced = sv.class_induced_slots(class_name)
        except Exception:
            # A malformed class may throw during induction; skip and let
            # LinkML's own validation surface the deeper problem.
            continue
        for slot in induced:
            for key, ann in _iter_hippo_annotations(slot):
                err = _validate_one_annotation(
                    ext_slots,
                    ext_enums,
                    key,
                    ann,
                    "slot",
                    f"{class_name}.{slot.name}",
                )
                if err:
                    failures.append(err)

    if failures:
        # Deferred import to avoid a module-load cycle with core.exceptions.
        from hippo.core.exceptions import SchemaError

        raise SchemaError(
            f"{len(failures)} hippo_* annotation error(s) in schema:\n  - "
            + "\n  - ".join(failures),
            error_code="HIPPO_EXT_VALIDATION",
        )


def _flatten_for_validator(sv: SchemaView) -> dict[str, Any]:
    """Build a self-contained schema dict with all imports resolved inline.

    LinkML's ``Validator`` re-resolves ``imports:`` when it processes a
    SchemaDefinition, which fails for bundled schemas like ``hippo_core``
    that live outside the user-schema directory and are only visible via
    the ``SchemaRegistry``'s importmap. We work around this by flattening
    the merged ``SchemaView`` back into a dict that has every class, slot,
    enum, and type inlined and no ``imports:`` remaining.
    """
    from linkml_runtime.dumpers import yaml_dumper

    flat: dict[str, Any] = {
        "id": sv.schema.id or "https://example.org/hippo/flat",
        "name": sv.schema.name or "flat",
        "prefixes": dict(sv.schema.prefixes or {}),
        "default_range": sv.schema.default_range or "string",
        "imports": ["linkml:types"],
        "classes": {},
        "slots": {},
        "enums": {},
        "types": {},
    }

    def _to_plain(obj: Any) -> Any:
        return yaml.safe_load(yaml_dumper.dumps(obj))

    for name, cls in sv.all_classes(imports=True).items():
        flat["classes"][name] = _to_plain(cls)
    for name, slot in sv.all_slots(imports=True).items():
        flat["slots"][name] = _to_plain(slot)
    for name, enum in sv.all_enums(imports=True).items():
        flat["enums"][name] = _to_plain(enum)
    for name, typ in (sv.all_types(imports=True) or {}).items():
        flat["types"][name] = _to_plain(typ)

    for section in ("slots", "enums", "types"):
        if not flat[section]:
            del flat[section]
    return flat


def _build_tree_root_class(sv: SchemaView) -> ClassDefinition:
    """Construct the synthesized ``_HippoInstanceBundle`` tree-root class.

    Per the β-handoff (PR 3.1): one multivalued, inlined slot per concrete
    (non-abstract) class in the merged schema, including bundled
    ``hippo_core`` classes. Slot name comes from ``class_accessor_name`` —
    snake_case-pluralized class name, overridable via the ``hippo_accessor``
    class annotation. This keeps the wire format aligned with the
    typed-client accessor surface (sec9 §9.8).

    The returned class is NOT added to ``sv``. ``SchemaRegistry`` injects
    it only into the validator's flat schema so the DDL generator,
    schema-diff engine, and typed-client never see it as a domain class.

    Raises ``SchemaError`` if the user schema already declares a class
    named ``_HippoInstanceBundle`` or if two distinct classes resolve to
    the same tree-root slot name (the wire format is a flat namespace —
    add ``hippo_accessor`` overrides to disambiguate).
    """
    existing = sv.all_classes(imports=True)
    if TREE_ROOT_CLASS_NAME in existing:
        from hippo.core.exceptions import SchemaError

        raise SchemaError(
            f"Class name {TREE_ROOT_CLASS_NAME!r} is reserved for the "
            f"synthesized tree-root and may not be declared in a user schema.",
            error_code="HIPPO_TREE_ROOT_COLLISION",
        )

    attributes: dict[str, SlotDefinition] = {}
    seen_slots: dict[str, str] = {}
    for cls_name, cls in existing.items():
        if cls.abstract:
            continue
        slot_name = class_accessor_name(cls_name, cls)
        if slot_name in seen_slots:
            from hippo.core.exceptions import SchemaError

            raise SchemaError(
                f"Tree-root slot name {slot_name!r} would be assigned to "
                f"both {seen_slots[slot_name]!r} and {cls_name!r}. Add a "
                f"`hippo_accessor` annotation to at least one class to "
                f"disambiguate.",
                error_code="HIPPO_TREE_ROOT_SLOT_COLLISION",
            )
        seen_slots[slot_name] = cls_name
        attributes[slot_name] = SlotDefinition(
            name=slot_name,
            range=cls_name,
            multivalued=True,
            inlined=True,
            inlined_as_list=True,
        )

    return ClassDefinition(
        name=TREE_ROOT_CLASS_NAME,
        tree_root=True,
        description=(
            "Synthesized tree-root for LinkML-native instance YAML. Carries "
            "one multivalued slot per concrete class in the merged schema; "
            "slot names follow the typed-client accessor convention "
            "(`snake_case(ClassName) + 's'`, overridable via "
            "`hippo_accessor`). Not user-authored — Hippo injects it into "
            "the validator schema so `hippo validate` / `hippo ingest` can "
            "target a single tree-shaped root."
        ),
        attributes=attributes,
    )


class SchemaRegistry:
    """Hippo-facing schema registry backed by a LinkML ``SchemaView``."""

    def __init__(self, schema_view: SchemaView) -> None:
        _validate_hippo_annotations(schema_view)
        self._sv = schema_view
        # Synthesize the wire-format tree-root class once at construction.
        # Kept off the SchemaView so DDL generation, schema-diff, and the
        # typed-client surface stay unaware of it; the validator's flat
        # schema gets a copy so `validate(bundle, _HippoInstanceBundle)`
        # works (sec9 PR 3.1).
        self._tree_root_class = _build_tree_root_class(schema_view)
        # Validator needs a self-contained schema (no unresolved imports) so
        # it can generate JSON Schema without re-reading files from disk.
        # See _flatten_for_validator for the rationale.
        flat = _flatten_for_validator(schema_view)
        from linkml_runtime.dumpers import yaml_dumper

        flat["classes"][TREE_ROOT_CLASS_NAME] = yaml.safe_load(
            yaml_dumper.dumps(self._tree_root_class)
        )
        self._validator = Validator(
            schema=flat,
            validation_plugins=[JsonschemaValidationPlugin(closed=True)],
        )

    @classmethod
    def from_path(cls, path: Union[str, Path]) -> "SchemaRegistry":
        p = Path(path)
        if p.is_dir():
            return cls._from_directory(p)
        return cls(SchemaView(str(p), importmap=_bundled_importmap()))

    @classmethod
    def _from_directory(cls, path: Path) -> "SchemaRegistry":
        """Merge all ``*.yaml`` / ``*.yml`` files in ``path`` into one schema."""
        files = sorted(list(path.glob("*.yaml")) + list(path.glob("*.yml")))
        if not files:
            raise FileNotFoundError(f"No schema files found in {path}")
        merged: dict[str, Any] = {
            "id": f"https://example.org/hippo/{path.name}",
            "name": path.name,
            "prefixes": {"linkml": "https://w3id.org/linkml/"},
            "imports": ["linkml:types"],
            "default_range": "string",
            "classes": {},
            "enums": {},
            "slots": {},
            "types": {},
        }
        for file_path in files:
            doc = yaml.safe_load(file_path.read_text()) or {}
            if "id" in doc and not doc.get("imports") is None:
                merged["id"] = doc.get("id", merged["id"])
            for section in ("classes", "enums", "slots", "types"):
                merged[section].update(doc.get(section) or {})
            for pfx, uri in (doc.get("prefixes") or {}).items():
                merged["prefixes"].setdefault(pfx, uri)
            for imp in doc.get("imports") or []:
                if imp not in merged["imports"]:
                    merged["imports"].append(imp)
        if not merged["enums"]:
            del merged["enums"]
        if not merged["slots"]:
            del merged["slots"]
        if not merged["types"]:
            del merged["types"]
        return cls.from_dict(merged)

    @classmethod
    def from_dict(cls, data: dict) -> "SchemaRegistry":
        return cls(SchemaView(yaml.safe_dump(data), importmap=_bundled_importmap()))

    @classmethod
    def from_yaml(cls, yaml_text: str) -> "SchemaRegistry":
        return cls(SchemaView(yaml_text, importmap=_bundled_importmap()))

    @property
    def schema_view(self) -> SchemaView:
        return self._sv

    def tree_root_class_name(self) -> str:
        """Name of the synthesized tree-root class (``_HippoInstanceBundle``).

        Callers pass this to :meth:`validate` to validate a LinkML-native
        instance YAML bundle (one multivalued slot per concrete class).
        See sec9 PR 3.1.

        The tree-root is not a domain class — :meth:`class_names`,
        :meth:`has_class`, :meth:`get_class`, and :meth:`induced_slots`
        do not include or accept it. Use :meth:`tree_root_class` and
        :meth:`tree_root_slots` for direct introspection.
        """
        return TREE_ROOT_CLASS_NAME

    def tree_root_class(self) -> ClassDefinition:
        """The synthesized tree-root ``ClassDefinition``.

        Held on the registry, not the SchemaView, so DDL generation,
        schema-diff, and the typed-client surface stay unaware of it.
        """
        return self._tree_root_class

    def tree_root_slots(self) -> list[SlotDefinition]:
        """Multivalued tree-root slots — one per concrete class."""
        return list(self._tree_root_class.attributes.values())

    def class_names(self) -> list[str]:
        return list(self._sv.all_classes().keys())

    def get_class(self, name: str) -> Optional[ClassDefinition]:
        return self._sv.get_class(name)

    def has_class(self, name: str) -> bool:
        return name in self._sv.all_classes()

    def induced_slots(self, class_name: str) -> list[SlotDefinition]:
        return self._sv.class_induced_slots(class_name)

    def identifier_slot(self, class_name: str) -> Optional[SlotDefinition]:
        return self._sv.get_identifier_slot(class_name)

    def required_slots(self, class_name: str) -> list[SlotDefinition]:
        return [s for s in self.induced_slots(class_name) if s.required]

    def searchable_slots(self, class_name: str) -> list[tuple[SlotDefinition, str]]:
        """Slots annotated with ``hippo_search``; returns (slot, mode) pairs."""
        pairs: list[tuple[SlotDefinition, str]] = []
        for slot in self.induced_slots(class_name):
            mode = annotation_value(slot, HIPPO_SEARCH)
            if mode is not None:
                pairs.append((slot, str(mode)))
        return pairs

    def reference_slots(self, class_name: str) -> list[tuple[str, str]]:
        """(slot_name, target_class) pairs for slots whose range is another class."""
        known = set(self._sv.all_classes().keys())
        refs: list[tuple[str, str]] = []
        for slot in self.induced_slots(class_name):
            rng = slot.range
            if rng and rng in known:
                refs.append((slot.name, rng))
        return refs

    def indexed_slots(self, class_name: str) -> list[tuple[SlotDefinition, bool]]:
        """(slot, partial) pairs for slots annotated with ``hippo_index``."""
        out: list[tuple[SlotDefinition, bool]] = []
        for slot in self.induced_slots(class_name):
            if annotation_value(slot, HIPPO_INDEX):
                partial = bool(annotation_value(slot, HIPPO_INDEX_PARTIAL))
                out.append((slot, partial))
        return out

    def unique_slot_names(self, class_name: str) -> list[str]:
        return [
            s.name
            for s in self.induced_slots(class_name)
            if annotation_value(s, HIPPO_UNIQUE)
        ]

    def reference_loaders(self) -> list[str]:
        """Names of concrete classes that are subclasses of ``ReferenceLoader``.

        Returns every non-abstract class in the merged schema whose ancestry
        includes ``ReferenceLoader``.  Plugin schema fragments that declare a
        loader-specific subclass (``is_a: ReferenceLoader``) appear here after
        their fragment is merged into the live ``SchemaView``.

        Used for discoverability — callers can enumerate which loader types are
        registered in the current deployment.  For provenance queries use the
        ``entity_type`` slot on individual instances.
        """
        out: list[str] = []
        for name, cls in self._sv.all_classes(imports=True).items():
            if cls.abstract:
                continue
            if name == "ReferenceLoader":
                continue
            ancestors = self._sv.class_ancestors(name)
            if "ReferenceLoader" in ancestors:
                out.append(name)
        return out

    def append_only_classes(self) -> set[str]:
        """Names of classes annotated ``hippo_append_only: true``.

        Adapters consult this set to reject UPDATE and DELETE against the
        corresponding tables per sec9 §9.4 / reference_hippo_ext.md. Only
        concrete (non-abstract) classes are returned — an abstract class
        with the annotation is purely declarative. Per sec9 §9.6 this set
        currently contains ``{"ProvenanceRecord"}``; domain schemas may
        mark additional append-only classes.
        """
        out: set[str] = set()
        for name in self.class_names():
            cls = self._sv.get_class(name)
            if cls is None or cls.abstract:
                continue
            if annotation_value(cls, HIPPO_APPEND_ONLY):
                out.add(name)
        return out

    def validate(self, instance: dict, target_class: str) -> list[str]:
        """Validate an instance dict; return a list of error messages (empty=valid).

        Kept for backward compatibility. New code should call
        :meth:`validate_envelope` to get the sec9 §9.9 envelope with
        tier-annotated failures.
        """
        report = self._validator.validate(instance, target_class)
        return [r.message for r in report.results]

    def validate_envelope(
        self, instance: dict, target_class: str
    ) -> "list[ValidationFailure]":
        """Validate an instance dict; return a list of ``ValidationFailure``
        objects with ``tier="linkml"`` for every schema-shape violation.

        Per sec9 §9.9 this is the LinkML-native tier output — types,
        patterns, enums, ranges, required, multivalued, unique_keys.
        """
        from hippo.core.validation.validators import ValidationFailure

        report = self._validator.validate(instance, target_class)
        failures: list[ValidationFailure] = []
        for r in report.results:
            # LinkML's ``ValidationResult`` carries ``.instantiates`` (the
            # class), ``.type`` (rule category), and ``.message``. The
            # rule string is derived from the type; the field from the
            # message prefix when available.
            rule = getattr(r, "type", None) or "schema_violation"
            failures.append(
                ValidationFailure(
                    tier="linkml",
                    rule=str(rule),
                    message=r.message,
                    field=getattr(r, "source", None),
                    details={"target_class": target_class},
                )
            )
        return failures
