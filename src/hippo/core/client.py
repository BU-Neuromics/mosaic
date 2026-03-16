"""HippoClient - Main SDK client for Hippo Metadata Tracking Service."""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from hippo.core.batch_fetcher import BatchFetcher
from hippo.core.cycle_detector import CycleDetector, validate_no_cycle
from hippo.core.exceptions import (
    EntityNotFoundError,
    ValidationFailure,
)
from hippo.core.expand_path_parser import (
    ExpandPathParser,
    MaxSizeExceededError,
    ParserConfig,
    ParsingError,
)
from hippo.core.ingestion import extract_fts_content
from hippo.core.pipeline import ValidationPipeline
from hippo.core.relationship import RelationshipManager
from hippo.core.storage import Query
from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter, SQLiteEntity
from hippo.core.storage.fts import FTSTableMetadata
from hippo.core.validation.validators import (
    ValidationResult,
    WriteOperation,
    WriteValidator,
)
from hippo.config.models import SchemaConfig


class HippoClient:
    """Main client for Hippo Metadata Tracking Service.

    Provides methods for reading, creating, updating, and deleting entities
    with built-in validation pipeline support.
    """

    def __init__(
        self,
        pipeline: Optional[ValidationPipeline] = None,
        bypass_validation: bool = False,
        storage: Optional[SQLiteAdapter] = None,
        schemas: Optional[dict[str, SchemaConfig]] = None,
    ) -> None:
        """Initialize HippoClient.

        Args:
            pipeline: Optional validation pipeline. If not provided,
                a default pipeline will be created when needed.
            bypass_validation: DEPRECATED. If True, skips validation pipeline.
                This parameter is deprecated and will be removed in a future version.
            storage: Storage adapter for persistence. If not provided,
                a default SQLite adapter will be created.
            schemas: Dictionary of schema configurations keyed by entity type.
                Used for search capability validation at startup.
        """
        self._pipeline = pipeline
        self._bypass_validation = bypass_validation
        self._storage = storage
        self._schemas = schemas
        self._fts_table_metadata: dict[str, list[FTSTableMetadata]] = {}
        self._build_fts_metadata()
        self._validate_search_capabilities()

    @property
    def storage(self) -> Optional[SQLiteAdapter]:
        """Get the storage adapter."""
        return self._storage

    @storage.setter
    def storage(self, value: Optional[SQLiteAdapter]) -> None:
        """Set the storage adapter."""
        self._storage = value

    @property
    def pipeline(self) -> Optional[ValidationPipeline]:
        """Get the validation pipeline.

        Returns:
            The validation pipeline, or None if not configured.
        """
        return self._pipeline

    @pipeline.setter
    def pipeline(self, value: Optional[ValidationPipeline]) -> None:
        """Set the validation pipeline.

        Args:
            value: The validation pipeline to use.
        """
        self._pipeline = value

    def _build_fts_metadata(self) -> None:
        """Populate _fts_table_metadata from self._schemas."""
        if not self._schemas:
            return
        for entity_type, schema in self._schemas.items():
            fts_tables = []
            for field in schema.fields:
                if field.search and "fts" in field.search.lower():
                    meta = FTSTableMetadata.from_field(field, entity_type=entity_type)
                    fts_tables.append(meta)
            if fts_tables:
                self._fts_table_metadata[entity_type] = fts_tables

    def _validate_search_capabilities(self) -> None:
        """Validate that the storage adapter supports all search modes declared in schemas.

        Raises:
            SearchCapabilityError: If schema declares unsupported search modes
                and the adapter is active.
        """
        from hippo.core.exceptions import SearchCapabilityError

        if self._storage is None:
            return

        if self._schemas is None:
            return

        adapter_capabilities = self._storage.search_capabilities()

        declared_modes: set[str] = set()
        for schema in self._schemas.values():
            for field in schema.fields:
                if field.search is not None:
                    normalized_mode = (
                        "fts" if field.search in ("fts", "fts5") else field.search
                    )
                    declared_modes.add(normalized_mode)

        unsupported_modes = declared_modes - adapter_capabilities
        if unsupported_modes:
            raise SearchCapabilityError(
                message=f"Storage adapter does not support search modes: {', '.join(sorted(unsupported_modes))}",
                unsupported_modes=list(unsupported_modes),
            )

    def _get_fts_tables_for_entity_type(
        self, entity_type: str
    ) -> list[FTSTableMetadata]:
        """Get FTS table metadata for an entity type.

        Args:
            entity_type: The entity type.

        Returns:
            List of FTS table metadata.
        """
        return self._fts_table_metadata.get(entity_type, [])

    def _sync_entity_to_fts(
        self,
        entity_id: str,
        entity_type: str,
        data: dict[str, Any],
        is_available: bool = True,
    ) -> None:
        """Sync an entity to its FTS tables.

        Args:
            entity_id: The entity ID.
            entity_type: The entity type.
            data: The entity data.
            is_available: Whether the entity is available.
        """
        if self._storage is None:
            return

        fts_tables = self._get_fts_tables_for_entity_type(entity_type)
        if not fts_tables:
            return

        with self._storage._transaction() as conn:
            fts_store = self._storage._get_fts_store(conn)

            for fts_meta in fts_tables:
                table_name = fts_meta.table_name
                fts_fields = fts_meta.get_fts_columns()

                # Skip gracefully if the FTS virtual table has not been
                # created yet (e.g. before `hippo migrate` has been run, or
                # in test fixtures that don't set up FTS tables).
                from hippo.core.storage.fts import fts_table_exists
                if not fts_table_exists(conn.cursor(), table_name):
                    continue

                content = extract_fts_content(data, fts_fields)

                if is_available and content:
                    fts_store.sync_entity_to_fts(table_name, entity_id, content)
                else:
                    fts_store.remove_entity_from_fts(table_name, entity_id)

    @property
    def relationships(self) -> RelationshipManager:
        """Get the relationship manager.

        Returns:
            The relationship manager instance.
        """
        if not hasattr(self, "_relationship_manager"):
            self._relationship_manager = RelationshipManager(storage=self._storage)
        return self._relationship_manager

    @relationships.setter
    def relationships(self, value: RelationshipManager) -> None:
        """Set the relationship manager.

        Args:
            value: The relationship manager to use.
        """
        self._relationship_manager = value

    def add_validator(self, validator: WriteValidator) -> None:
        """Add a validator to the pipeline.

        If no pipeline exists, creates one automatically.

        Args:
            validator: The validator to add.
        """
        if self._pipeline is None:
            self._pipeline = ValidationPipeline()
        self._pipeline.add_validator(validator)

    def validate(self, operation: WriteOperation) -> ValidationResult:
        """Validate a write operation using the validation pipeline.

        Args:
            operation: The write operation to validate.

        Returns:
            ValidationResult indicating success or failure.

        Raises:
            ValidationFailure: If validation fails and strict mode is enabled.
        """
        if self._bypass_validation or self._pipeline is None:
            return ValidationResult(is_valid=True, errors=[])

        return self._pipeline.execute(operation)

    def put(
        self,
        entity_type: str,
        data: dict[str, Any],
        entity_id: Optional[str] = None,
        bypass_validation: Optional[bool] = None,
    ) -> dict[str, Any]:
        """Create or update an entity.

        If entity_id is provided and the entity exists, it will be updated.
        If entity_id is not provided, a new entity will be created with a generated UUID.
        If entity_id is provided but doesn't exist, a new entity will be created.

        Args:
            entity_type: The type of entity.
            data: The entity data.
            entity_id: Optional entity ID. If not provided, a UUID will be generated.
            bypass_validation: Deprecated. Use client-level setting instead.

        Returns:
            The created/updated entity data with metadata.

        Raises:
            ValidationFailure: If validation fails.
        """
        if data is None or (isinstance(data, dict) and len(data) == 0):
            raise ValidationFailure(
                message="Entity data cannot be null or empty",
                input_context=data,
                entity_type=entity_type,
                entity_id=entity_id,
            )

        should_bypass = (
            bypass_validation
            if bypass_validation is not None
            else self._bypass_validation
        )

        if not should_bypass:
            operation = WriteOperation(
                operation="insert" if entity_id is None else "update",
                entity_type=entity_type,
                data=data,
            )
            result = self.validate(operation)
            if not result.is_valid:
                error_messages = [
                    e.message if hasattr(e, "message") else str(e)
                    for e in result.errors
                ]
                raise ValidationFailure(
                    message="; ".join(error_messages),
                    input_context=data,
                    entity_type=entity_type,
                    entity_id=entity_id,
                )

        if entity_id is None and isinstance(data, dict) and "id" in data:
            entity_id = data["id"]

        return self._put_internal(entity_type, data, entity_id)

    def _put_internal(
        self,
        entity_type: str,
        data: dict[str, Any],
        entity_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Internal put implementation."""
        if self._storage is None:
            final_id = entity_id or str(uuid.uuid4())
            return {
                "id": final_id,
                "entity_type": entity_type,
                "data": data,
                "version": 1,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

        if hasattr(self._storage, "read"):
            return self._put_with_sqlite(entity_type, data, entity_id)

        if (
            entity_id
            and hasattr(self._storage, "exists")
            and self._storage.exists(entity_type, entity_id)
        ):
            return self._update_internal(entity_type, entity_id, data)
        return self._create_internal(entity_type, data)

    def _put_with_sqlite(
        self,
        entity_type: str,
        data: dict[str, Any],
        entity_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Internal put implementation for SQLite storage."""
        final_id = entity_id or str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        existing = self._storage.read(final_id)

        if existing is not None:
            new_version = existing.version + 1
            entity = SQLiteEntity(
                id=final_id,
                entity_type=entity_type,
                is_available=True,
                version=new_version,
                data=data,
                created_at=existing.created_at,
                updated_at=now,
            )
            with self._storage._transaction() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """UPDATE entities SET data = ?, version = ?, updated_at = ?
                       WHERE id = ? AND is_available = 1""",
                    (json.dumps(data), new_version, now, final_id),
                )

                provenance = self._storage._get_provenance_store(conn)
                provenance.record(
                    entity_id=final_id,
                    entity_type=entity_type,
                    operation_type="UPDATE",
                    user_context=None,
                    payload=data,
                )

                self._sync_entity_to_fts(final_id, entity_type, data, is_available=True)

            return {
                "id": final_id,
                "entity_type": entity_type,
                "data": data,
                "version": new_version,
                "created_at": existing.created_at,
                "updated_at": now,
            }
        else:
            entity = SQLiteEntity(
                id=final_id,
                entity_type=entity_type,
                is_available=True,
                version=1,
                data=data,
                created_at=now,
                updated_at=now,
            )
            self._storage.create(entity)

            self._sync_entity_to_fts(final_id, entity_type, data, is_available=True)

            return {
                "id": final_id,
                "entity_type": entity_type,
                "data": data,
                "version": 1,
                "created_at": now,
                "updated_at": now,
            }

    def get(
        self,
        entity_type: str,
        entity_id: str,
        expand: Optional[str] = None,
    ) -> dict[str, Any]:
        """Get an entity by its ID.

        Args:
            entity_type: The type of entity.
            entity_id: The ID of the entity to retrieve.
            expand: Optional expand path for fetching related entities
                (e.g., "user.profile.settings").

        Returns:
            The entity data with metadata. If expand is specified,
            includes expanded related entities under the "_expanded" key.

        Raises:
            EntityNotFoundError: If the entity doesn't exist.
            ParsingError: If the expand path is malformed.
            MaxSizeExceededError: If the expand path exceeds maximum size.
            CycleDetectionError: If the expand path contains a cycle.
        """
        if self._storage is None:
            raise EntityNotFoundError(
                message=f"Entity not found: {entity_id}",
                entity_type=entity_type,
                entity_id=entity_id,
            )

        entity = self._storage.read(entity_id)

        if entity is None or entity.entity_type != entity_type:
            raise EntityNotFoundError(
                message=f"Entity not found: {entity_id}",
                entity_type=entity_type,
                entity_id=entity_id,
            )

        result = {
            "id": entity.id,
            "entity_type": entity.entity_type,
            "data": entity.data,
            "version": entity.version,
            "created_at": entity.created_at,
            "updated_at": entity.updated_at,
        }

        if expand:
            parsed = self._parse_and_validate_expand(expand)
            fetcher = BatchFetcher(storage=self._storage)
            fetch_result = fetcher.fetch(parsed, entity_id)
            result["_expanded"] = fetch_result.expanded_data

        return result

    def _parse_and_validate_expand(self, expand: str) -> Any:
        """Parse and validate an expand path.

        Args:
            expand: The expand path string.

        Returns:
            Parsed expand path result.

        Raises:
            ParsingError: If the expand path is malformed.
            MaxSizeExceededError: If the expand path exceeds maximum size.
            CycleDetectionError: If the expand path contains a cycle.
        """
        parser = ExpandPathParser()
        parsed = parser.parse(expand)
        validate_no_cycle(parsed)
        return parsed

    def query(
        self,
        entity_type: str,
        filters: Optional[list[dict[str, Any]]] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        """Query entities with filter criteria.

        Args:
            entity_type: The type of entity to query.
            filters: List of filter conditions (key-value pairs).
            date_from: Optional start date for filtering (ISO format).
            date_to: Optional end date for filtering (ISO format).
            limit: Maximum number of results to return.
            offset: Number of results to skip (for pagination).

        Returns:
            List of matching entities with metadata, sorted by created_at ascending.
            Returns empty list if no matches.
        """
        if self._storage is None:
            return []

        query = Query(
            entity_type=entity_type,
            filters=filters or [],
        )

        results = list(self._storage.find(query))

        filtered = []
        for entity in results:
            if date_from and entity.created_at < date_from:
                continue
            if date_to and entity.created_at > date_to:
                continue

            filtered.append(
                {
                    "id": entity.id,
                    "entity_type": entity.entity_type,
                    "data": entity.data,
                    "version": entity.version,
                    "created_at": entity.created_at,
                    "updated_at": entity.updated_at,
                }
            )

        filtered.sort(key=lambda x: x["created_at"])

        if offset:
            filtered = filtered[offset:]
        if limit:
            filtered = filtered[:limit]

        return filtered

    def create(
        self,
        entity_type: str,
        data: dict[str, Any],
        bypass_validation: Optional[bool] = None,
    ) -> dict[str, Any]:
        """Create a new entity.

        Args:
            entity_type: The type of entity to create.
            data: The entity data.
            bypass_validation: Deprecated. Use client-level setting instead.

        Returns:
            The created entity data.

        Raises:
            ValidationFailure: If validation fails.
        """
        return self.put(entity_type, data, bypass_validation=bypass_validation)

    def update(
        self,
        entity_type: str,
        entity_id: str,
        data: dict[str, Any],
        bypass_validation: Optional[bool] = None,
    ) -> dict[str, Any]:
        """Update an existing entity.

        Args:
            entity_type: The type of entity to update.
            entity_id: The ID of the entity to update.
            data: The updated entity data.
            bypass_validation: Deprecated. Use client-level setting instead.

        Returns:
            The updated entity data.

        Raises:
            ValidationFailure: If validation fails.
        """
        return self.put(entity_type, data, entity_id, bypass_validation)

    def delete(
        self,
        entity_type: str,
        entity_id: str,
        bypass_validation: Optional[bool] = None,
    ) -> bool:
        """Delete an entity.

        Args:
            entity_type: The type of entity to delete.
            entity_id: The ID of the entity to delete.
            bypass_validation: Deprecated. Use client-level setting instead.

        Returns:
            True if deleted successfully.

        Raises:
            ValidationFailure: If validation fails.
        """
        should_bypass = (
            bypass_validation
            if bypass_validation is not None
            else self._bypass_validation
        )

        if not should_bypass:
            operation = WriteOperation(
                operation="delete",
                entity_type=entity_type,
                data={"id": entity_id},
            )
            result = self.validate(operation)
            if not result.is_valid:
                raise ValidationFailure(
                    message="; ".join(result.errors),
                    input_context={"id": entity_id},
                    entity_type=entity_type,
                    entity_id=entity_id,
                )

        return self._delete_internal(entity_type, entity_id)

    def _create_internal(
        self, entity_type: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Internal create implementation.

        This is a placeholder for the actual storage implementation.
        """
        return {"id": data.get("id"), "entity_type": entity_type, "data": data}

    def _update_internal(
        self, entity_type: str, entity_id: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Internal update implementation.

        This is a placeholder for the actual storage implementation.
        """
        return {"id": entity_id, "entity_type": entity_type, "data": data}

    def _delete_internal(self, entity_type: str, entity_id: str) -> bool:
        """Internal delete implementation."""
        if self._storage is None:
            return True

        if hasattr(self._storage, "delete"):
            entity = self._storage.read(entity_id)
            data = entity.data if entity else {}

            result = self._storage.delete(entity_id)

            self._sync_entity_to_fts(entity_id, entity_type, data, is_available=False)

            return result

        return True

    def search(
        self,
        entity_type: str,
        query: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Search entities using full-text search.

        Args:
            entity_type: The type of entity to search.
            query: The FTS5 query string.
            limit: Maximum number of results to return.

        Returns:
            List of matching entities with metadata.
        """
        if self._storage is None:
            return []

        fts_tables = self._get_fts_tables_for_entity_type(entity_type)
        if not fts_tables:
            return []

        results = []
        for fts_meta in fts_tables:
            fts_results = self._storage.search_fts(
                table_name=fts_meta.table_name,
                query=query,
                limit=limit,
            )
            for fts_result in fts_results:
                entity_id = fts_result["entity_id"]
                try:
                    entity = self.get(entity_type, entity_id)
                    results.append(entity)
                except EntityNotFoundError:
                    pass

        return results[:limit]

    def register_external_id(self, entity_id: str, external_id: str) -> dict[str, Any]:
        """Register an external ID for an entity.

        Args:
            entity_id: The internal ID of the entity.
            external_id: The external identifier to register.

        Returns:
            The created external ID record with metadata.

        Raises:
            EntityNotFoundError: If the entity doesn't exist.
        """
        if self._storage is None:
            raise EntityNotFoundError(
                message=f"Entity not found: {entity_id}",
                entity_type="unknown",
                entity_id=entity_id,
            )

        entity = self._storage.read(entity_id)
        if entity is None:
            raise EntityNotFoundError(
                message=f"Entity not found: {entity_id}",
                entity_type="unknown",
                entity_id=entity_id,
            )

        with self._storage._transaction() as conn:
            external_id_store = self._storage._get_external_id_store(conn)
            record = external_id_store.create_external_id(entity_id, external_id)

        return {
            "id": record.id,
            "entity_id": record.entity_id,
            "external_id": record.external_id,
            "created_at": record.created_at,
            "superseded_at": record.superseded_at,
        }

    def supersede(
        self, entity_id: str, old_external_id: str, new_external_id: str
    ) -> dict[str, Any]:
        """Supersede an entity's external ID with a new one.

        Args:
            entity_id: The internal ID of the entity.
            old_external_id: The external ID to supersede.
            new_external_id: The new external ID to use.

        Returns:
            The new external ID record with metadata.

        Raises:
            EntityNotFoundError: If the entity doesn't exist.
        """
        if self._storage is None:
            raise EntityNotFoundError(
                message=f"Entity not found: {entity_id}",
                entity_type="unknown",
                entity_id=entity_id,
            )

        entity = self._storage.read(entity_id)
        if entity is None:
            raise EntityNotFoundError(
                message=f"Entity not found: {entity_id}",
                entity_type="unknown",
                entity_id=entity_id,
            )

        with self._storage._transaction() as conn:
            external_id_store = self._storage._get_external_id_store(conn)
            record = external_id_store.supersede_external_id(
                entity_id, old_external_id, new_external_id
            )

        return {
            "id": record.id,
            "entity_id": record.entity_id,
            "external_id": record.external_id,
            "created_at": record.created_at,
            "superseded_at": record.superseded_at,
        }

    def get_by_external_id(
        self, external_id: str, include_archived: bool = False
    ) -> dict[str, Any]:
        """Get an entity by its external ID.

        Returns the entity with the latest created_at timestamp for the given external_id.

        Args:
            external_id: The external identifier to search for.
            include_archived: If True, include archived entities in the search.

        Returns:
            The entity data with metadata.

        Raises:
            EntityNotFoundError: If no entity is found with the given external ID.
        """
        if self._storage is None:
            raise EntityNotFoundError(
                message=f"No entity found with external ID: {external_id}",
                entity_type="unknown",
                entity_id="unknown",
            )

        with self._storage._transaction() as conn:
            external_id_store = self._storage._get_external_id_store(conn)
            record = external_id_store.get_entity_by_external_id(
                external_id, include_archived=include_archived
            )

        if record is None:
            raise EntityNotFoundError(
                message=f"No entity found with external ID: {external_id}",
                entity_type="unknown",
                entity_id="unknown",
            )

        if include_archived:
            cursor = self._storage._get_connection().cursor()
            cursor.execute(
                "SELECT id, entity_type, is_available, version, data, created_at, updated_at FROM entities WHERE id = ?",
                (record.entity_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise EntityNotFoundError(
                    message=f"Entity not found: {record.entity_id}",
                    entity_type="unknown",
                    entity_id=record.entity_id,
                )
            import json

            entity_data = json.loads(row["data"]) if row["data"] else {}
            entity = type(
                "Entity",
                (),
                {
                    "id": row["id"],
                    "entity_type": row["entity_type"],
                    "is_available": bool(row["is_available"]),
                    "version": row["version"],
                    "data": entity_data,
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                },
            )()
        else:
            entity = self._storage.read(record.entity_id)
            if entity is None:
                raise EntityNotFoundError(
                    message=f"Entity not found: {record.entity_id}",
                    entity_type="unknown",
                    entity_id=record.entity_id,
                )

        return {
            "id": entity.id,
            "entity_type": entity.entity_type,
            "data": entity.data,
            "version": entity.version,
            "created_at": entity.created_at,
            "updated_at": entity.updated_at,
            "external_id": record.external_id,
            "external_id_created_at": record.created_at,
        }

    def list_external_ids(
        self, entity_id: str, include_superseded: bool = False
    ) -> list[dict[str, Any]]:
        """List all external IDs for an entity.

        Args:
            entity_id: The internal ID of the entity.
            include_superseded: If True, include superseded external IDs.

        Returns:
            List of external ID records.

        Raises:
            EntityNotFoundError: If the entity doesn't exist.
        """
        if self._storage is None:
            raise EntityNotFoundError(
                message=f"Entity not found: {entity_id}",
                entity_type="unknown",
                entity_id=entity_id,
            )

        entity = self._storage.read(entity_id)
        if entity is None:
            raise EntityNotFoundError(
                message=f"Entity not found: {entity_id}",
                entity_type="unknown",
                entity_id=entity_id,
            )

        with self._storage._transaction() as conn:
            external_id_store = self._storage._get_external_id_store(conn)
            records = list(
                external_id_store.list_external_ids_for_entity(
                    entity_id, include_superseded=include_superseded
                )
            )

        return [
            {
                "id": r.id,
                "entity_id": r.entity_id,
                "external_id": r.external_id,
                "created_at": r.created_at,
                "superseded_at": r.superseded_at,
            }
            for r in records
        ]

    def history(self, entity_id: str) -> list[dict[str, Any]]:
        """Get the change history for an entity.

        Args:
            entity_id: The ID of the entity.

        Returns:
            List of history records in chronological order (oldest first).
            Each record contains:
            - operation_id: Unique identifier for this operation
            - entity_id: The entity ID
            - entity_type: The type of entity
            - operation_type: Type of operation (CREATE, UPDATE, SOFT_DELETE)
            - timestamp: ISO format timestamp of the operation
            - user_id: User who performed the operation
            - previous_state_hash: SHA-256 hash of the previous state
            - state_snapshot: The entity state at this point in time

        Raises:
            EntityNotFoundError: If the entity doesn't exist.
        """
        if self._storage is None:
            raise EntityNotFoundError(
                message=f"Entity not found: {entity_id}",
                entity_type="unknown",
                entity_id=entity_id,
            )

        entity = self._storage.read(entity_id)
        if entity is None:
            raise EntityNotFoundError(
                message=f"Entity not found: {entity_id}",
                entity_type="unknown",
                entity_id=entity_id,
            )

        return self._storage.history(entity_id)

    def state_at(self, entity_id: str, timestamp: str) -> Optional[dict[str, Any]]:
        """Get the entity state at a specific point in time.

        Args:
            entity_id: The ID of the entity.
            timestamp: ISO format timestamp to query (e.g., "2024-01-15T10:30:00+00:00").

        Returns:
            The entity state at that time, including:
            - entity_id: The entity ID
            - state: The entity data at that time
            - timestamp: The timestamp of the state

        Raises:
            EntityNotFoundError: If the entity doesn't exist at that point in time.
            TemporalQueryError: If the timestamp is before entity creation.
        """
        if self._storage is None:
            raise EntityNotFoundError(
                message=f"Entity not found: {entity_id}",
                entity_type="unknown",
                entity_id=entity_id,
            )

        entity = self._storage.read(entity_id)
        if entity is None:
            raise EntityNotFoundError(
                message=f"Entity not found: {entity_id}",
                entity_type="unknown",
                entity_id=entity_id,
            )

        return self._storage.state_at(entity_id, timestamp)
