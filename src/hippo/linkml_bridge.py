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

HIPPO_ANNOTATION_PREFIX = "hippo_"
_CLASS_ANNOTATION_SUBSET = "class_annotation"
_SLOT_ANNOTATION_SUBSET = "slot_annotation"


def annotation_value(element: Any, key: str) -> Optional[Any]:
    """Return the ``.value`` of a named annotation, or ``None`` if absent."""
    ann = getattr(element, "annotations", None)
    if ann is None or key not in ann:
        return None
    return ann[key].value


# ---------------------------------------------------------------------------
# hippo_ext annotation vocabulary — loaded once, used by SchemaRegistry to
# validate every hippo_* annotation in a user schema at construction time.
# ---------------------------------------------------------------------------

_HIPPO_EXT_SV: Optional[SchemaView] = None


def _load_hippo_ext_schema() -> SchemaView:
    resource = importlib.resources.files("hippo.schemas").joinpath("hippo_ext.yaml")
    return SchemaView(str(resource))


def _hippo_ext_schema_view() -> SchemaView:
    global _HIPPO_EXT_SV
    if _HIPPO_EXT_SV is None:
        _HIPPO_EXT_SV = _load_hippo_ext_schema()
    return _HIPPO_EXT_SV


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


class SchemaRegistry:
    """Hippo-facing schema registry backed by a LinkML ``SchemaView``."""

    def __init__(self, schema_view: SchemaView) -> None:
        _validate_hippo_annotations(schema_view)
        self._sv = schema_view
        self._validator = Validator(
            schema=schema_view.schema,
            validation_plugins=[JsonschemaValidationPlugin(closed=True)],
        )

    @classmethod
    def from_path(cls, path: Union[str, Path]) -> "SchemaRegistry":
        p = Path(path)
        if p.is_dir():
            return cls._from_directory(p)
        return cls(SchemaView(str(p)))

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
        return cls(SchemaView(yaml.safe_dump(data)))

    @classmethod
    def from_yaml(cls, yaml_text: str) -> "SchemaRegistry":
        return cls(SchemaView(yaml_text))

    @property
    def schema_view(self) -> SchemaView:
        return self._sv

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

    def validate(self, instance: dict, target_class: str) -> list[str]:
        """Validate an instance dict; return a list of error messages (empty=valid)."""
        report = self._validator.validate(instance, target_class)
        return [r.message for r in report.results]
