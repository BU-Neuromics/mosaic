"""Base classes for the unified ingestion loader framework."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator

# Type aliases for clarity
RawRecord = dict[str, Any]
TransformedRecord = dict[str, Any]


@dataclass
class IngestResult:
    """Result of an ingestion run through IngestPipeline."""

    entity_type: str
    total_rows: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    errors: int = 0
    error_messages: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source_file: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "total_rows": self.total_rows,
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "errors": self.errors,
            "error_messages": self.error_messages,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "source_file": self.source_file,
        }


class EntityLoader(ABC):
    """Base class for all data loading into Mosaic.

    Subclass this to implement reference loaders, Cappella adapters, or any
    custom data source. The three required pieces are:
    - ``name``: a string identifier (e.g. "csv", "ensembl")
    - ``entity_types``: the entity type(s) this loader produces
    - ``fetch()``: yields RawRecord dicts from the source
    - ``transform()``: maps a RawRecord to a TransformedRecord
    """

    name: str
    entity_types: list[str]
    supports_incremental: bool = False

    @abstractmethod
    def fetch(self, since: datetime | None = None, **kwargs) -> Iterator[RawRecord]:
        """Pull records from the source.

        Args:
            since: Optional lower bound for incremental loads. None = full load.

        Yields:
            RawRecord dicts as received from the source.
        """
        ...

    @abstractmethod
    def transform(self, record: RawRecord) -> TransformedRecord:
        """Map a source record to the Mosaic entity schema.

        Args:
            record: Raw record from fetch().

        Returns:
            TransformedRecord ready for upsert into Mosaic.
        """
        ...

    def validate(self, record: TransformedRecord, client: Any) -> list[str]:
        """Optional cross-record validation against live Mosaic state.

        Args:
            record: Transformed record about to be written.
            client: Live MosaicClient (for lookups).

        Returns:
            List of error strings. Empty list means valid.
        """
        return []

    def health_check(self) -> dict[str, Any]:
        """Optional connectivity check for the source.

        Returns:
            Dict with at least a ``status`` key.
        """
        return {"status": "unknown"}


class ConfigurableLoader(EntityLoader):
    """EntityLoader with config-driven field renaming and vocabulary normalization.

    This is the base for all generic built-in loaders (CSV, JSON, SQL) and for
    simple reference loaders that only need column mapping.

    Config keys:
        entity_type (str): The Mosaic entity type to write to.
        external_id_field (str): Source field that holds the external ID.
        field_map (dict[str, str]): Rename source keys to Mosaic field names.
        vocabulary_map (dict[str, dict[str, str]]): Normalize field values.
        trust_level (int): Data trust level 0–100 (default 50).
    """

    def __init__(self, config: dict[str, Any]):
        self.entity_type: str = config.get("entity_type", "unknown")
        self.external_id_field: str = config.get("external_id_field", "external_id")
        self.field_map: dict[str, str] = config.get("field_map", {})
        self.vocabulary_map: dict[str, dict[str, str]] = config.get("vocabulary_map", {})
        self.trust_level: int = config.get("trust_level", 50)
        self.entity_types: list[str] = [self.entity_type]

    def transform(self, record: RawRecord) -> TransformedRecord:
        """Apply field_map renaming then vocabulary_map normalization."""
        result: TransformedRecord = {}
        for src_key, value in record.items():
            dest_key = self.field_map.get(src_key, src_key)
            vocab = self.vocabulary_map.get(dest_key, {})
            if vocab and value in vocab:
                value = vocab[value]
            result[dest_key] = value
        return result
