"""Exposure-report tool (sec11 §11.6.1 / Doc 2 §6.1).

Answers, *before* a migration runs: **given a proposed base-package
migration, which elements of an installed extension does the migration's
write-set touch?**

Inputs:

* the base migration's **structural delta** — the classes and slots that
  differ between the old and new merged schema (:func:`compute_write_set`,
  the programmatic form of ``hippo schema-diff <old> <new>``);
* the extension's **referenced elements** — the base classes it extends
  (``is_a``), the base slots it refines (``slot_usage``) or lists
  (``slots``), and the base elements its added slots depend on (a slot's
  ``range``) (:func:`extension_referenced_elements`).

Output: the intersection (:func:`exposure_report`). **Empty** ⇒ the base
migration is safe to apply without an extension step. **Non-empty** ⇒ the
lab must supply a complementary ``evolve`` step covering those elements,
*or* the end-to-end gate (:func:`~hippo.core.loaders.orchestrator.run_end_to_end_gate`)
will block the migration with a record-level failure. The report *warns*
in advance; the gate *guarantees* no silent corruption.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SchemaElement:
    """A referenceable schema element — a ``"class"`` or a ``"slot"``."""

    kind: str
    name: str


@dataclass
class SchemaWriteSet:
    """The structural delta of a base migration (old → new merged schema).

    ``added`` / ``removed`` / ``changed`` each hold the
    :class:`SchemaElement`\\ s of that disposition. :meth:`elements` is the
    union — every element the migration *touches*, the footprint an
    extension is intersected against.
    """

    added: set[SchemaElement] = field(default_factory=set)
    removed: set[SchemaElement] = field(default_factory=set)
    changed: set[SchemaElement] = field(default_factory=set)

    def elements(self) -> set[SchemaElement]:
        return self.added | self.removed | self.changed

    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.changed)


# ---------------------------------------------------------------------------
# Schema introspection
# ---------------------------------------------------------------------------


def _classes(schema: dict[str, Any]) -> dict[str, dict]:
    return dict(schema.get("classes") or {})


def _slot_names(schema: dict[str, Any]) -> dict[str, dict]:
    """All slot definitions reachable in a fragment, by name.

    Merges top-level ``slots:`` with every class's inline ``attributes:``
    (the slot's definition wins from the most specific place it appears).
    """
    slots: dict[str, dict] = dict(schema.get("slots") or {})
    for cls in _classes(schema).values():
        for slot_name, slot_def in (cls.get("attributes") or {}).items():
            slots[slot_name] = slot_def or {}
    return slots


def compute_write_set(
    old_schema: dict[str, Any], new_schema: dict[str, Any]
) -> SchemaWriteSet:
    """Structural delta between two merged schemas — the migration footprint.

    Classes/slots present only in ``new`` are *added*, only in ``old`` are
    *removed*, and in both but with a differing definition are *changed*.
    This is the programmatic equivalent of ``hippo schema-diff`` over the
    old and new *merged* schema dirs.
    """
    ws = SchemaWriteSet()

    old_classes, new_classes = _classes(old_schema), _classes(new_schema)
    for name in new_classes.keys() - old_classes.keys():
        ws.added.add(SchemaElement("class", name))
    for name in old_classes.keys() - new_classes.keys():
        ws.removed.add(SchemaElement("class", name))
    for name in old_classes.keys() & new_classes.keys():
        if old_classes[name] != new_classes[name]:
            ws.changed.add(SchemaElement("class", name))

    old_slots, new_slots = _slot_names(old_schema), _slot_names(new_schema)
    for name in new_slots.keys() - old_slots.keys():
        ws.added.add(SchemaElement("slot", name))
    for name in old_slots.keys() - new_slots.keys():
        ws.removed.add(SchemaElement("slot", name))
    for name in old_slots.keys() & new_slots.keys():
        if old_slots[name] != new_slots[name]:
            ws.changed.add(SchemaElement("slot", name))

    return ws


def extension_referenced_elements(
    extension_fragment: dict[str, Any],
) -> set[SchemaElement]:
    """Base elements an extension fragment references (its dependency set).

    * ``is_a`` (and ``mixins``) targets → referenced *classes*.
    * ``slot_usage`` keys and ``slots`` list entries → referenced *slots*
      (the base slots the extension refines or pulls in).
    * an added slot's ``range`` pointing at a class → referenced *class*
      (the added-slot dependency).

    The extension's *own* newly-introduced classes/slots are not references
    to the base, so they are excluded from the dependency set.
    """
    refs: set[SchemaElement] = set()
    classes = _classes(extension_fragment)
    own_classes = set(classes)

    for cls in classes.values():
        parent = cls.get("is_a")
        if parent and parent not in own_classes:
            refs.add(SchemaElement("class", parent))
        for mixin in cls.get("mixins") or []:
            if mixin not in own_classes:
                refs.add(SchemaElement("class", mixin))
        for slot_name in cls.get("slot_usage") or {}:
            refs.add(SchemaElement("slot", slot_name))
        for slot_name in cls.get("slots") or []:
            refs.add(SchemaElement("slot", slot_name))
        for slot_def in (cls.get("attributes") or {}).values():
            rng = (slot_def or {}).get("range")
            if rng and rng not in own_classes:
                # An added slot whose range is a (base) class is a dependency
                # on that class; primitive ranges (string/integer/…) are not.
                if rng and rng[0].isupper():
                    refs.add(SchemaElement("class", rng))

    for slot_name in extension_fragment.get("slot_usage") or {}:
        refs.add(SchemaElement("slot", slot_name))

    return refs


@dataclass
class ExposureReport:
    """Result of intersecting a base write-set with an extension's refs."""

    extension: str
    exposed: set[SchemaElement] = field(default_factory=set)

    @property
    def is_safe(self) -> bool:
        """True ⇒ the base migration touches nothing the extension uses."""
        return not self.exposed

    @property
    def exposed_classes(self) -> list[str]:
        return sorted(e.name for e in self.exposed if e.kind == "class")

    @property
    def exposed_slots(self) -> list[str]:
        return sorted(e.name for e in self.exposed if e.kind == "slot")

    def render(self) -> str:
        if self.is_safe:
            return (
                f"exposure: extension {self.extension!r} is unaffected — the "
                f"base migration touches none of its referenced elements; "
                f"safe to apply without a complementary step."
            )
        parts = []
        if self.exposed_classes:
            parts.append(f"classes={self.exposed_classes}")
        if self.exposed_slots:
            parts.append(f"slots={self.exposed_slots}")
        return (
            f"exposure: extension {self.extension!r} references elements in "
            f"the base migration's write-set ({'; '.join(parts)}); supply a "
            f"complementary evolve step or the end-to-end gate will block it."
        )


def exposure_report(
    write_set: SchemaWriteSet,
    extension_fragment: dict[str, Any],
    *,
    extension_name: str,
) -> ExposureReport:
    """Intersect a base migration's write-set with an extension's references.

    Returns an :class:`ExposureReport`; ``report.is_safe`` is the empty-
    intersection case (base migration safe as-is), otherwise the report
    names the exposed classes/slots the extension must cover.
    """
    refs = extension_referenced_elements(extension_fragment)
    return ExposureReport(
        extension=extension_name, exposed=refs & write_set.elements()
    )
