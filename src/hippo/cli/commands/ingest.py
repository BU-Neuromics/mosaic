"""LinkML-native instance YAML ingest for the Hippo CLI.

``hippo ingest`` accepts a tree-root LinkML instance bundle: a YAML mapping
whose top-level keys are class accessors (``samples:``, ``projects:`` etc.)
and whose values are lists of instance dicts. Identity is by the
``id`` slot on each instance; re-ingest of an existing id updates that
entity in place. There is no separate wrapper format and no top-level
``external_id`` field — register external IDs by including ``external_ids:``
entries in the same bundle (see ``hippo_core.ExternalID``).

CSV/JSON operational data files are not accepted here; those belong to
Cappella.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from hippo.core.exceptions import EntityNotFoundError


class IngestError(Exception):
    """Raised when an instance YAML file is invalid or cannot be processed."""


@dataclass
class IngestResult:
    """Result of a LinkML-native instance ingest operation."""

    source_file: str
    created: int = 0
    updated: int = 0
    errors: int = 0
    error_messages: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "created": self.created,
            "updated": self.updated,
            "errors": self.errors,
            "error_messages": self.error_messages,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


def ingest_linkml_yaml(
    path: Path | str,
    client: Any,
    registry: Any,
) -> IngestResult:
    """Ingest a LinkML-native instance YAML bundle.

    The file must be a YAML mapping whose keys are tree-root accessor
    slots (one per concrete class in ``registry``) and whose values are
    lists of instance dicts. The bundle is validated against the
    registry's synthesized tree-root class before any writes occur; if
    validation fails the function raises :class:`IngestError` and writes
    nothing.

    Per-instance writes go through :meth:`HippoClient.put`. Identity is
    by the ``id`` slot on each instance: when ``id`` matches an existing
    entity, ``put`` updates it in place; otherwise a new entity is
    created.

    Args:
        path: Path to the YAML file.
        client: ``HippoClient`` instance.
        registry: ``SchemaRegistry`` whose tree-root class and accessor
            slot mapping describe the bundle shape.

    Returns:
        :class:`IngestResult` with per-entity counts.

    Raises:
        IngestError: If the file is missing, not a YAML mapping, or
            fails LinkML validation against the tree-root.
    """
    path = Path(path)

    if not path.exists():
        raise IngestError(f"File not found: {path}")

    try:
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise IngestError(f"Failed to parse YAML: {exc}") from exc

    if not isinstance(parsed, dict):
        raise IngestError(
            f"Instance file must be a YAML mapping (tree-root bundle); got "
            f"{type(parsed).__name__}. Note: CSV/JSON data files are not "
            "accepted by 'hippo ingest' — use Cappella for operational data."
        )

    tree_root = registry.tree_root_class_name()
    errors = registry.validate(parsed, tree_root)
    if errors:
        raise IngestError(
            f"Bundle does not validate against {tree_root}: "
            + "; ".join(errors)
        )

    slot_to_class: dict[str, str] = {
        slot.name: slot.range for slot in registry.tree_root_slots()
    }

    result = IngestResult(source_file=str(path))

    for slot_name, instances in parsed.items():
        declared_range = slot_to_class.get(slot_name)
        if declared_range is None:
            # Tree-root validation already rejects unknown slots in
            # closed-schema mode; guard against schema drift just in case.
            result.errors += 1
            result.error_messages.append(
                f"Unknown tree-root slot {slot_name!r}"
            )
            continue
        if not isinstance(instances, list):
            result.errors += 1
            result.error_messages.append(
                f"Slot {slot_name!r}: expected a list, got "
                f"{type(instances).__name__}"
            )
            continue
        for idx, instance in enumerate(instances):
            if not isinstance(instance, dict):
                result.errors += 1
                result.error_messages.append(
                    f"{slot_name}[{idx}]: expected a mapping, got "
                    f"{type(instance).__name__}"
                )
                continue
            try:
                target_class = _dispatch_class(
                    registry, declared_range, instance
                )
                _upsert_instance(client, target_class, instance, result)
            except Exception as exc:
                result.errors += 1
                result.error_messages.append(
                    f"{slot_name}[{idx}] ({declared_range}): {exc}"
                )

    return result


def _dispatch_class(
    registry: Any,
    declared_range: str,
    instance: dict[str, Any],
) -> str:
    """Resolve the concrete class to instantiate for a single instance.

    When ``declared_range`` is a polymorphic base — it declares a
    ``designates_type`` slot (e.g. ``Sample.category``) — the instance's
    discriminator value selects the concrete subclass it is stored as, so
    subclass-specific fields persist and the instance is queryable as its
    real type (issue #80). When there is no designator the declared range is
    used directly.

    Raises:
        IngestError: if the discriminator value resolves to no subclass of
            ``declared_range``, names an abstract class, or if the declared
            range is itself abstract and the instance carries no designator.
    """
    designator = registry.type_designator_slot(declared_range)
    if designator is not None:
        value = instance.get(designator.name)
        if value is not None:
            resolved = registry.resolve_designated_class(
                declared_range, str(value)
            )
            if resolved is None:
                raise IngestError(
                    f"{designator.name}={value!r} does not name {declared_range!r} "
                    f"or any of its subclasses"
                )
            cls = registry.get_class(resolved)
            if cls is not None and getattr(cls, "abstract", False):
                raise IngestError(
                    f"{designator.name}={value!r} names abstract class "
                    f"{resolved!r}, which cannot be instantiated"
                )
            return resolved

    cls = registry.get_class(declared_range)
    if cls is not None and getattr(cls, "abstract", False):
        raise IngestError(
            f"Cannot ingest into abstract class {declared_range!r}: each "
            f"instance must carry a type designator naming a concrete subclass"
        )
    return declared_range


def _upsert_instance(
    client: Any,
    entity_type: str,
    data: dict[str, Any],
    result: IngestResult,
) -> None:
    """Write a single instance via ``client.put``, updating result counts."""
    entity_id = data.get("id")
    if entity_id is None:
        client.put(entity_type=entity_type, data=data)
        result.created += 1
        return

    try:
        client.get(entity_type, entity_id)
        existed = True
    except EntityNotFoundError:
        existed = False

    client.put(entity_type=entity_type, data=data, entity_id=entity_id)
    if existed:
        result.updated += 1
    else:
        result.created += 1
