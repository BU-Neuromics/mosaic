"""Entity YAML ingest command implementation for Hippo CLI.

`hippo ingest` accepts structured entity YAML files that declare entities
to create or upsert. It does NOT accept raw CSV/JSON data files — those are
Cappella's responsibility.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from hippo.core.exceptions import EntityNotFoundError


class IngestError(Exception):
    """Raised when an entity ingest file is invalid or cannot be processed."""


@dataclass
class IngestResult:
    """Result of an entity ingest operation."""

    source_file: str
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    errors: int = 0
    error_messages: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "errors": self.errors,
            "error_messages": self.error_messages,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


def ingest_entity_file(path: Path | str, client: Any) -> IngestResult:
    """Ingest an entity YAML file into Hippo via client.

    The file must have a top-level ``entities`` key. Each entry must have:
    - ``type`` (str): entity type
    - ``data`` (dict): field values
    - ``external_id`` (str, optional): enables idempotent upsert

    When no ``external_id`` is present the entity is always created (not idempotent).

    Args:
        path: Path to the YAML file.
        client: HippoClient instance.

    Returns:
        IngestResult with per-entity counts.

    Raises:
        IngestError: If the file is not found, not valid YAML, or has
                     structural errors (missing 'entities', 'type', or 'data').
    """
    path = Path(path)

    if not path.exists():
        raise IngestError(f"File not found: {path}")

    try:
        raw = path.read_text(encoding="utf-8")
        parsed = yaml.safe_load(raw)
    except Exception as exc:
        raise IngestError(f"Failed to parse YAML: {exc}") from exc

    if not isinstance(parsed, dict) or "entities" not in parsed:
        raise IngestError(
            f"Entity file must have a top-level 'entities' key. Got: {type(parsed).__name__}. "
            "Note: CSV/JSON data files are not accepted by 'hippo ingest' — use Cappella for operational data."
        )

    entities = parsed["entities"]
    if not isinstance(entities, list):
        raise IngestError("'entities' must be a list of entity declarations.")

    result = IngestResult(source_file=str(path))

    for idx, entry in enumerate(entities):
        if not isinstance(entry, dict):
            result.errors += 1
            result.error_messages.append(f"Entry {idx}: must be a dict, got {type(entry).__name__}")
            continue

        if "type" not in entry:
            raise IngestError(f"Entry {idx}: missing 'type' field")

        if "data" not in entry:
            raise IngestError(f"Entry {idx}: missing 'data' field")

        entity_type = entry["type"]
        data = entry["data"]
        external_id = entry.get("external_id")

        try:
            _upsert_entity(client, entity_type, data, external_id, result)
        except Exception as exc:
            result.errors += 1
            result.error_messages.append(f"Entry {idx} ({entity_type}): {exc}")

    return result


def _upsert_entity(
    client: Any,
    entity_type: str,
    data: dict[str, Any],
    external_id: str | None,
    result: IngestResult,
) -> None:
    """Upsert a single entity, updating result counts in-place."""
    if external_id is None:
        client.put(entity_type=entity_type, data=data)
        result.created += 1
        return

    try:
        existing = client.get_by_external_id(external_id, include_archived=False)
        existing_data = existing.get("data", {})
        if existing_data == data:
            result.unchanged += 1
        else:
            client.put(entity_type=entity_type, data=data, entity_id=existing["id"])
            result.updated += 1
    except EntityNotFoundError:
        created = client.put(entity_type=entity_type, data=data)
        client.register_external_id(created["id"], external_id)
        result.created += 1
