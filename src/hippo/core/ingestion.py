"""Data ingestion utilities and IngestionPipeline for CSV/JSON/JSONL files."""

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from hippo.core.exceptions import (
    IngestionError,
    IngestionValidationError,
    ValidationFailure,
)
from hippo.core.validation.validators import WriteOperation


def flatten_dict(data: dict[str, Any], delimiter: str = ".") -> dict[str, Any]:
    """Flatten a nested dictionary to one level with dot-notation keys.

    Args:
        data: The dictionary to flatten.
        delimiter: The delimiter to use for nested keys (default: '.'').

    Returns:
        A flattened dictionary with dot-notation keys.

    Example:
        >>> flatten_dict({"address": {"city": "Boston"}})
        {"address.city": "Boston"}
    """
    result: dict[str, Any] = {}

    def _flatten(obj: Any, prefix: str = "") -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_key = f"{prefix}{delimiter}{key}" if prefix else key
                _flatten(value, new_key)
        else:
            result[prefix] = obj

    _flatten(data)
    return result


def extract_fts_content(data: dict[str, Any], fts_fields: list[str]) -> Optional[str]:
    """Extract content from entity data for FTS indexing.

    Args:
        data: The entity data.
        fts_fields: List of field names to include in FTS index.

    Returns:
        Space-separated content string, or None if no fields are present.
    """
    content_parts = []
    for field_name in fts_fields:
        if field_name in data and data[field_name] is not None:
            content_parts.append(str(data[field_name]))

    return " ".join(content_parts) if content_parts else None


@dataclass
class IngestResult:
    """Result of an ingestion operation."""

    entity_type: str
    total_rows: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    errors: int = 0
    error_messages: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source_file: str = ""
    record_errors: list[dict[str, Any]] = field(default_factory=list)

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
            "record_errors": self.record_errors,
        }


class IngestionPipeline:
    """Pipeline for ingesting data from CSV, JSON, and JSONL files.

    Provides methods to ingest data from various file formats with
    upsert-by-ExternalID functionality.
    """

    def __init__(
        self,
        client,
        max_batch_size: int = 10000,
        flatten_nested: bool = True,
        validator_executor: Optional[Any] = None,
        validation_enabled: bool = True,
    ):
        """Initialize IngestionPipeline.

        Args:
            client: HippoClient instance for data operations.
            max_batch_size: Maximum number of rows to process in a single batch.
            flatten_nested: Whether to flatten nested JSON structures.
            validator_executor: Optional ValidatorExecutor for write-path validation.
            validation_enabled: Whether to enable write-path validation.
        """
        self._client = client
        self._max_batch_size = max_batch_size
        self._flatten_nested = flatten_nested
        self._validator_executor = validator_executor
        self._validation_enabled = validation_enabled

    def set_validator_executor(self, executor: Any) -> None:
        """Set the validator executor for write-path validation.

        Args:
            executor: The ValidatorExecutor to use for validation.
        """
        self._validator_executor = executor

    def enable_validation(self, enabled: bool = True) -> None:
        """Enable or disable write-path validation.

        Args:
            enabled: Whether to enable validation.
        """
        self._validation_enabled = enabled

    def before_write_validation(
        self,
        entity_type: str,
        data: dict[str, Any],
        operation: str = "create",
    ) -> None:
        """Validate data before writing to the database.

        Args:
            entity_type: The type of entity being written.
            data: The data to validate.
            operation: The operation type (create, update, delete).

        Raises:
            ValidationFailure: If validation fails.
        """
        if not self._validation_enabled or self._validator_executor is None:
            return

        write_operation = WriteOperation(
            operation=operation,
            entity_type=entity_type,
            data=data,
        )

        result = self._validator_executor.execute(write_operation)

        if not result.is_valid:
            error_messages = result.errors
            raise ValidationFailure(
                message="; ".join(error_messages),
                input_context=data,
                entity_type=entity_type,
                entity_id=data.get("id"),
            )

    def ingest_csv(
        self,
        file_path: str | Path,
        entity_type: str,
        external_id_field: str = "external_id",
    ) -> IngestResult:
        """Ingest data from a CSV file.

        Args:
            file_path: Path to the CSV file.
            entity_type: The entity type to ingest data as.
            external_id_field: The field name containing the external ID.

        Returns:
            IngestResult with counts for created, updated, unchanged, and errors.

        Raises:
            IngestionError: If the file cannot be read or parsed.
            IngestionValidationError: If the CSV has no headers.
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise IngestionError(
                message=f"File not found: {file_path}",
                input_context={"file_path": str(file_path)},
                entity_type=entity_type,
            )

        if file_path.stat().st_size == 0:
            return IngestResult(entity_type=entity_type, total_rows=0)

        valid_rows, error_rows = parse_csv_with_errors(file_path)

        if len(valid_rows) > self._max_batch_size:
            raise IngestionError(
                message=f"Batch size {len(valid_rows)} exceeds maximum allowed {self._max_batch_size}",
                input_context={
                    "file_path": str(file_path),
                    "row_count": len(valid_rows),
                    "max_batch_size": self._max_batch_size,
                },
                entity_type=entity_type,
            )

        return self._upsert_records(
            valid_rows, entity_type, external_id_field, error_rows, str(file_path)
        )

    def ingest_json(
        self,
        file_path: str | Path,
        entity_type: str,
        external_id_field: str = "external_id",
    ) -> IngestResult:
        """Ingest data from a JSON file containing an array of records.

        Args:
            file_path: Path to the JSON file.
            entity_type: The entity type to ingest data as.
            external_id_field: The field name containing the external ID.

        Returns:
            IngestResult with counts for created, updated, unchanged, and errors.

        Raises:
            IngestionError: If the file cannot be read or parsed.
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise IngestionError(
                message=f"File not found: {file_path}",
                input_context={"file_path": str(file_path)},
                entity_type=entity_type,
            )

        if file_path.stat().st_size == 0:
            return IngestResult(entity_type=entity_type, total_rows=0)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise IngestionError(
                message=f"Invalid JSON: {e}",
                input_context={"file_path": str(file_path)},
                entity_type=entity_type,
            )

        if not isinstance(data, list):
            raise IngestionError(
                message="JSON file must contain an array of records",
                input_context={"file_path": str(file_path)},
                entity_type=entity_type,
            )

        valid_rows: list[dict[str, Any]] = []
        error_rows: list[dict[str, Any]] = []

        for idx, record in enumerate(data):
            if not isinstance(record, dict):
                error_rows.append(
                    {
                        "row": idx,
                        "error": "Record must be an object",
                        "data": record,
                    }
                )
                continue

            if self._flatten_nested:
                record = flatten_dict(record)

            valid_rows.append(record)

        if len(valid_rows) > self._max_batch_size:
            raise IngestionError(
                message=f"Batch size {len(valid_rows)} exceeds maximum allowed {self._max_batch_size}",
                input_context={
                    "file_path": str(file_path),
                    "row_count": len(valid_rows),
                    "max_batch_size": self._max_batch_size,
                },
                entity_type=entity_type,
            )

        return self._upsert_records(
            valid_rows, entity_type, external_id_field, error_rows, str(file_path)
        )

    def ingest_jsonl(
        self,
        file_path: str | Path,
        entity_type: str,
        external_id_field: str = "external_id",
    ) -> IngestResult:
        """Ingest data from a JSONL (JSON Lines) file.

        Args:
            file_path: Path to the JSONL file.
            entity_type: The entity type to ingest data as.
            external_id_field: The field name containing the external ID.

        Returns:
            IngestResult with counts for created, updated, unchanged, and errors.

        Raises:
            IngestionError: If the file cannot be read or parsed.
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise IngestionError(
                message=f"File not found: {file_path}",
                input_context={"file_path": str(file_path)},
                entity_type=entity_type,
            )

        if file_path.stat().st_size == 0:
            return IngestResult(entity_type=entity_type, total_rows=0)

        valid_rows: list[dict[str, Any]] = []
        error_rows: list[dict[str, Any]] = []

        with open(file_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue

                try:
                    record = json.loads(line)
                except json.JSONDecodeError as e:
                    error_rows.append(
                        {
                            "row": line_num,
                            "error": f"Invalid JSON: {e}",
                            "data": line,
                        }
                    )
                    continue

                if not isinstance(record, dict):
                    error_rows.append(
                        {
                            "row": line_num,
                            "error": "Record must be an object",
                            "data": record,
                        }
                    )
                    continue

                if external_id_field not in record:
                    error_rows.append(
                        {
                            "row": line_num,
                            "error": f"Missing external ID field: {external_id_field}",
                            "data": record,
                        }
                    )
                    continue

                if self._flatten_nested:
                    record = flatten_dict(record)

                valid_rows.append(record)

        if len(valid_rows) > self._max_batch_size:
            raise IngestionError(
                message=f"Batch size {len(valid_rows)} exceeds maximum allowed {self._max_batch_size}",
                input_context={
                    "file_path": str(file_path),
                    "row_count": len(valid_rows),
                    "max_batch_size": self._max_batch_size,
                },
                entity_type=entity_type,
            )

        return self._upsert_records(
            valid_rows, entity_type, external_id_field, error_rows, str(file_path)
        )

    def _upsert_records(
        self,
        records: list[dict[str, Any]],
        entity_type: str,
        external_id_field: str,
        initial_errors: list[dict[str, Any]],
        source_file: str = "",
    ) -> IngestResult:
        """Upsert records based on external ID.

        Args:
            records: List of records to upsert.
            entity_type: The entity type.
            external_id_field: The field containing the external ID.
            initial_errors: Any initial errors from parsing.
            source_file: Path to the source file being ingested.

        Returns:
            IngestResult with counts.
        """
        result = IngestResult(
            entity_type=entity_type,
            total_rows=len(records),
            errors=len(initial_errors),
            source_file=source_file,
        )

        for err in initial_errors:
            result.error_messages.append(f"Row {err['row']}: {err['error']}")
            result.record_errors.append(
                {
                    "record_id": err.get("row"),
                    "source_file": source_file,
                    "error": err["error"],
                }
            )

        seen_external_ids: dict[str, dict[str, Any]] = {}

        for idx, record in enumerate(records):
            external_id = record.get(external_id_field)

            if external_id is None:
                result.errors += 1
                error_msg = f"Row {idx}: Missing external ID field: {external_id_field}"
                result.error_messages.append(error_msg)
                result.record_errors.append(
                    {
                        "record_id": None,
                        "source_file": source_file,
                        "error": error_msg,
                    }
                )
                continue

            if external_id in seen_external_ids:
                result.errors += 1
                error_msg = f"Row {idx}: Duplicate external ID in batch: {external_id}"
                result.error_messages.append(error_msg)
                result.record_errors.append(
                    {
                        "record_id": external_id,
                        "source_file": source_file,
                        "error": error_msg,
                    }
                )
                continue

            seen_external_ids[external_id] = record

        for external_id, record in seen_external_ids.items():
            try:
                existing = self._client.get_by_external_id(
                    external_id, include_archived=False
                )

                existing_data = existing.get("data", {})
                record_without_id = {
                    k: v for k, v in record.items() if k != external_id_field
                }

                if existing_data == record_without_id:
                    result.unchanged += 1
                else:
                    self.before_write_validation(
                        entity_type, record_without_id, "update"
                    )
                    self._client.put(
                        entity_type=entity_type,
                        data=record_without_id,
                        entity_id=existing["id"],
                    )
                    result.updated += 1

            except Exception as e:
                if "not found" in str(e).lower():
                    record_without_id = {
                        k: v for k, v in record.items() if k != external_id_field
                    }
                    self.before_write_validation(
                        entity_type, record_without_id, "create"
                    )
                    created = self._client.put(
                        entity_type=entity_type,
                        data=record_without_id,
                    )
                    self._client.register_external_id(created["id"], external_id)
                    result.created += 1
                else:
                    result.errors += 1
                    error_msg = f"External ID {external_id}: {str(e)}"
                    result.error_messages.append(error_msg)
                    result.record_errors.append(
                        {
                            "record_id": external_id,
                            "source_file": source_file,
                            "error": str(e),
                        }
                    )

        return result

    def process_source(self, source_config, client):
        """
        Process a data source configuration from the loaded data and perform ingestion.

        This method orchestrates processing of a configured data source.

        Args:
            source_config: DataSourceConfig object with source information
            client: HippoClient for database operations

        Returns:
            dict with results of processing the single source
        """
        # For now, this is a placeholder that shows where more complex logic would go
        return {
            "source": source_config.name,
            "type": source_config.type,
            "processed": True,
            "message": f"Processed '{source_config.name}' of type '{source_config.type}'",
        }


def parse_csv_with_errors(
    path: "Path | str",
    *,
    encoding: str = "utf-8",
) -> tuple[list[dict], list[dict[str, Any]]]:
    """Parse a CSV file, returning (rows, errors).

    Each row is a dict keyed by the header row values.
    Errors collects malformed-row messages; the parse continues on error.
    """
    import csv
    from pathlib import Path as _Path

    rows: list[dict] = []
    errors: list[dict[str, Any]] = []
    try:
        with open(_Path(path), newline="", encoding=encoding) as fh:
            reader = csv.DictReader(fh)
            for i, row in enumerate(reader, start=2):  # row 1 is headers
                try:
                    rows.append(dict(row))
                except Exception as exc:  # noqa: BLE001
                    errors.append({"row": i, "error": str(exc)})
    except OSError as exc:
        raise IngestionError(f"Cannot open CSV {path}: {exc}") from exc
    return rows, errors
