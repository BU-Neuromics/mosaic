"""LinkML-backed schema loading, introspection, and validation.

Thin wrapper around ``linkml_runtime.SchemaView`` and ``linkml.validator`` that
exposes the handful of projections Hippo needs. Hippo-specific slot metadata is
carried via LinkML annotations under flat ``hippo_<name>`` keys (e.g.
``hippo_search: fts5``). User-authored schema YAML stays 100% valid LinkML.
"""

from __future__ import annotations

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


def _annotation_value(element: Any, key: str) -> Optional[Any]:
    ann = getattr(element, "annotations", None)
    if ann is None or key not in ann:
        return None
    return ann[key].value


class SchemaRegistry:
    """Hippo-facing schema registry backed by a LinkML ``SchemaView``."""

    def __init__(self, schema_view: SchemaView) -> None:
        self._sv = schema_view
        self._validator = Validator(
            schema=schema_view.schema,
            validation_plugins=[JsonschemaValidationPlugin(closed=True)],
        )

    @classmethod
    def from_path(cls, path: Union[str, Path]) -> "SchemaRegistry":
        return cls(SchemaView(str(path)))

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
            mode = _annotation_value(slot, HIPPO_SEARCH)
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
            if _annotation_value(slot, HIPPO_INDEX):
                partial = bool(_annotation_value(slot, HIPPO_INDEX_PARTIAL))
                out.append((slot, partial))
        return out

    def unique_slot_names(self, class_name: str) -> list[str]:
        return [
            s.name
            for s in self.induced_slots(class_name)
            if _annotation_value(s, HIPPO_UNIQUE)
        ]

    def validate(self, instance: dict, target_class: str) -> list[str]:
        """Validate an instance dict; return a list of error messages (empty=valid)."""
        report = self._validator.validate(instance, target_class)
        return [r.message for r in report.results]
