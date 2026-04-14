"""EntityYAMLLoader: load structured entity YAML into Hippo."""

from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

import yaml

from hippo.core.loaders.base import EntityLoader, RawRecord, TransformedRecord


class EntityYAMLLoader(EntityLoader):
    """Load entities from a structured entity YAML file.

    The YAML file must have a top-level ``entities`` key containing a list
    of entity declarations. Each declaration has:

    - ``type`` (required): Hippo entity type string
    - ``data`` (required): field dict to write
    - ``external_id`` (optional): if present, enables idempotent upsert

    Example::

        entities:
          - type: GenomeBuild
            external_id: ensembl_grch38_110
            data:
              name: GRCh38
              source: ensembl
              release: "110"

    When ``external_id`` is present the record is written to the
    ``external_id`` key in the transformed record so that IngestPipeline
    (or ingest_entity_file) can perform upsert-by-external-id.
    """

    name: str = "entity-yaml"
    entity_types: list[str] = []  # populated dynamically from file content
    supports_incremental: bool = False

    def __init__(self, source_file: str | Path):
        self._source_file = Path(source_file)

    def fetch(
        self,
        since: datetime | None = None,
        **kwargs: Any,
    ) -> Iterator[RawRecord]:
        """Parse the YAML file and yield one RawRecord per entity declaration."""
        with open(self._source_file, encoding="utf-8") as fh:
            parsed = yaml.safe_load(fh)

        if not isinstance(parsed, dict) or "entities" not in parsed:
            raise ValueError(
                f"EntityYAMLLoader: YAML must have a top-level 'entities' key (got: {type(parsed).__name__})"
            )

        for entry in parsed["entities"]:
            yield entry

    def transform(self, record: RawRecord) -> TransformedRecord:
        """Pass through the entity declaration — no field mapping applied.

        The raw record is the entity declaration dict from the YAML.
        Downstream (IngestPipeline / ingest_entity_file) handles the type/data
        split and external_id lookup.
        """
        return dict(record)
