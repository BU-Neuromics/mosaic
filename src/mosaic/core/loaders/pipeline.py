"""IngestPipeline: fetch → transform → validate → upsert loop for any EntityLoader."""

from datetime import datetime
from typing import Any

from mosaic.core.exceptions import EntityNotFoundError
from mosaic.core.loaders.base import EntityLoader, IngestResult


class IngestPipeline:
    """Orchestrates the full ingest loop for any EntityLoader.

    For each record yielded by the loader:
    1. transform() maps raw source data to Mosaic fields
    2. validate() runs optional cross-record checks
    3. upsert by external_id: create, update, or skip (unchanged)

    This is the replacement for the deprecated IngestionPipeline in
    mosaic.core.ingestion. It works with any EntityLoader subclass.
    """

    def __init__(self, client: Any, loader: EntityLoader):
        self._client = client
        self._loader = loader

    def run(
        self,
        since: datetime | None = None,
        dry_run: bool = False,
        **kwargs: Any,
    ) -> IngestResult:
        """Execute the full ingest loop.

        Args:
            since: Optional timestamp for incremental loads.
            dry_run: If True, compute what would happen but do not write.
            **kwargs: Passed through to loader.fetch().

        Returns:
            IngestResult with created/updated/unchanged/error counts.
        """
        entity_type = getattr(self._loader, "entity_type", "unknown")
        result = IngestResult(entity_type=entity_type)

        for raw in self._loader.fetch(since=since, **kwargs):
            result.total_rows += 1
            try:
                transformed = self._loader.transform(raw)
                validation_errors = self._loader.validate(transformed, self._client)
                if validation_errors:
                    result.errors += 1
                    result.error_messages.extend(validation_errors)
                    continue
                self._upsert(transformed, result, dry_run)
            except Exception as exc:
                result.errors += 1
                result.error_messages.append(str(exc))

        return result

    def _upsert(self, record: dict, result: IngestResult, dry_run: bool) -> None:
        external_id_field = getattr(self._loader, "external_id_field", "external_id")
        entity_type = getattr(self._loader, "entity_type", "unknown")
        external_id = record.get(external_id_field)
        record_without_id = {k: v for k, v in record.items() if k != external_id_field}

        if external_id is None:
            if not dry_run:
                self._client.put(entity_type=entity_type, data=record_without_id)
            result.created += 1
            return

        try:
            existing = self._client.get_by_external_id(external_id, include_archived=False)
            existing_data = existing.get("data", {})
            if existing_data == record_without_id:
                result.unchanged += 1
            else:
                if not dry_run:
                    self._client.put(
                        entity_type=entity_type,
                        data=record_without_id,
                        entity_id=existing["id"],
                    )
                result.updated += 1
        except EntityNotFoundError:
            if not dry_run:
                created = self._client.put(entity_type=entity_type, data=record_without_id)
                self._client.register_external_id(created["id"], external_id)
            result.created += 1
