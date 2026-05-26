"""HippoClient - Main SDK client for Hippo Metadata Tracking Service."""

import hashlib
import os
import urllib.request
from pathlib import Path
from typing import Any, Optional

from hippo.core.ingestion_service import IngestionService
from hippo.core.pipeline import ValidationPipeline
from hippo.core.provenance_service import ProvenanceService
from hippo.core.query_service import QueryService
from hippo.core.relationship import RelationshipManager
from hippo.core.schema_manager import SchemaManager
from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter
from hippo.core.storage.fts import FTSTableMetadata
from hippo.core.validation.validators import (
    ValidationResult,
    WriteOperation,
    WriteValidator,
)
from hippo.linkml_bridge import SchemaRegistry
from hippo.core.typed_client import (
    Namespace,
    build_typed_surface,
    generate_pydantic_models,
)
from hippo.models import populate as _populate_models


class HippoClient:
    """Main client for Hippo Metadata Tracking Service.

    Thin coordinator that delegates to domain facades:
    - SchemaManager: schema loading, validation, FTS metadata
    - ProvenanceService: version history, audit trail, supersession
    - QueryService: entity queries, FTS search, relationship traversal
    - IngestionService: entity writes (create, update, upsert, delete)
    """

    def __init__(
        self,
        pipeline: Optional[ValidationPipeline] = None,
        bypass_validation: bool = False,
        storage: Optional[SQLiteAdapter] = None,
        registry: Optional[SchemaRegistry] = None,
    ) -> None:
        """Initialize HippoClient.

        Args:
            pipeline: Optional validation pipeline. If not provided,
                a default pipeline will be created when needed.
            bypass_validation: DEPRECATED. If True, skips validation pipeline.
                This parameter is deprecated and will be removed in a future version.
            storage: Storage adapter for persistence.
            registry: LinkML-backed schema registry. Used for schema
                introspection, write-time validation, and FTS metadata.
        """
        self._schema_manager = SchemaManager(
            registry=registry,
            pipeline=pipeline,
            bypass_validation=bypass_validation,
            storage=storage,
        )

        # Plumb schema_version into the storage adapter so new
        # ProvenanceRecord rows carry it (sec9 §9.6 / Decision 9.6.F).
        # Derivation: prefer the merged schema's `version` field; fall
        # back to "unversioned" when the user schema doesn't set one.
        # Reaches into adapter-private attributes (`_schema_version`,
        # `_provenance_store`) deliberately — a public setter is a
        # future cleanup once the three adapter implementations agree
        # on a shared interface.
        if storage is not None and registry is not None:
            sv = registry.schema_view.schema.version or "unversioned"
            # Only overwrite an adapter's schema_version if the adapter
            # wasn't given one explicitly at construction.
            if not getattr(storage, "_schema_version", "") and hasattr(
                storage, "_schema_version"
            ):
                storage._schema_version = sv
                # Invalidate cached provenance_store so the next write
                # picks up the new schema_version.
                if hasattr(storage, "_provenance_store"):
                    storage._provenance_store = None

        self._provenance_service = ProvenanceService(storage=storage)
        self._query_service = QueryService(
            storage=storage,
            schema_manager=self._schema_manager,
            provenance_service=self._provenance_service,
        )
        self._ingestion_service = IngestionService(
            storage=storage,
            schema_manager=self._schema_manager,
        )

        self._storage = storage
        self._pipeline = pipeline
        self._bypass_validation = bypass_validation
        self._registry = registry
        self._fts_table_metadata = self._schema_manager.fts_table_metadata

        # sec9 §9.8 typed-client surface. Generated at load time when a
        # registry is available. Pydantic class generation is best-
        # effort — failures yield empty models and the accessor tree
        # still works against plain dicts.
        self._typed_root: Optional[Namespace] = None
        self._models: dict[str, type] = {}
        if registry is not None:
            self._models = generate_pydantic_models(registry)
            self._typed_root = build_typed_surface(
                self, registry, models=self._models
            )
            self._install_typed_accessors()
            _populate_models(self._typed_root)

    def _install_typed_accessors(self) -> None:
        """Expose typed accessors on ``self`` for flat root access, plus
        the explicit ``self.root`` alias. Non-root namespaces land as
        nested attributes (``self.tissue.samples.create(...)``).
        """
        if self._typed_root is None:
            return
        root = self._typed_root
        # Flat root-namespace access
        for name, accessor in root._accessors.items():
            setattr(self, name, accessor)
        for name, sub in root._subnamespaces.items():
            setattr(self, name, sub)
        # Explicit `client.root` alias for root-namespace classes only —
        # presents the same accessors without the sub-namespaces.
        root_alias = Namespace("root")
        for name, accessor in root._accessors.items():
            root_alias._accessors[name] = accessor
            setattr(root_alias, name, accessor)
        self.root = root_alias  # type: ignore[attr-defined]

    # -- Reference loader cache surface (sec2 §2.14.3, D2.14.E) --

    @staticmethod
    def _reference_cache_root() -> Path:
        """Resolve the root directory holding per-loader reference caches.

        ``$HIPPO_CACHE_DIR`` wins when set (the deployment opts into a
        custom location, e.g. a CI mount); otherwise we default to
        ``~/.cache/hippo/references/``. The directory is NOT created
        here — :meth:`cache_dir_for` handles per-loader mkdir.
        """
        env = os.environ.get("HIPPO_CACHE_DIR")
        if env:
            return Path(env)
        return Path.home() / ".cache" / "hippo" / "references"

    def cache_dir_for(self, loader_name: str) -> Path:
        """Return the per-loader cache directory, creating it on demand.

        Resolves to ``$HIPPO_CACHE_DIR/<loader_name>/`` when the env var
        is set, else ``~/.cache/hippo/references/<loader_name>/``. The
        accessor is stateless: per-loader scoping happens via the
        ``loader_name`` argument so a single ``HippoClient`` instance can
        serve many loaders without per-loader binding (see PTS-225
        rationale on §2.14.3).
        """
        if not loader_name:
            raise ValueError("loader_name must be a non-empty string")
        path = self._reference_cache_root() / loader_name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def cached_fetch(
        self,
        url: str,
        *,
        expected_sha256: Optional[str] = None,
        loader_name: str,
    ) -> Path:
        """Content-addressable HTTP fetch for reference data.

        Files are keyed by the sha256 of the request URL inside the
        loader's cache directory so repeated calls return a stable path.
        When ``expected_sha256`` is supplied the digest is verified on
        download AND on cache hit (a corrupt cached file MUST NOT pass
        silently); mismatches raise :class:`CacheIntegrityError` and the
        offending file is removed so the next call re-downloads cleanly.
        """
        from hippo.core.exceptions import CacheIntegrityError

        cache_dir = self.cache_dir_for(loader_name)
        url_key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        target = cache_dir / url_key

        if target.exists():
            if expected_sha256 is not None:
                actual = self._sha256_file(target)
                if actual.lower() != expected_sha256.lower():
                    target.unlink(missing_ok=True)
                    raise CacheIntegrityError(
                        "Cached file failed sha256 verification",
                        url=url,
                        path=str(target),
                        expected_sha256=expected_sha256,
                        actual_sha256=actual,
                    )
            return target

        # Download to a sibling tmp path then rename so partial files
        # never satisfy a later cache hit.
        tmp = target.with_suffix(target.suffix + ".part")
        try:
            with urllib.request.urlopen(url) as resp, open(tmp, "wb") as fh:
                while True:
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    fh.write(chunk)
            if expected_sha256 is not None:
                actual = self._sha256_file(tmp)
                if actual.lower() != expected_sha256.lower():
                    tmp.unlink(missing_ok=True)
                    raise CacheIntegrityError(
                        "Downloaded file failed sha256 verification",
                        url=url,
                        path=str(target),
                        expected_sha256=expected_sha256,
                        actual_sha256=actual,
                    )
            tmp.replace(target)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        return target

    @staticmethod
    def _sha256_file(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(64 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    # -- Property accessors (backwards compatibility) --

    @property
    def storage(self) -> Optional[SQLiteAdapter]:
        """Get the storage adapter."""
        return self._storage

    @storage.setter
    def storage(self, value: Optional[SQLiteAdapter]) -> None:
        """Set the storage adapter.

        Note: Phase 2 will propagate this to facades. Currently a known
        limitation — setting storage after init does not update facades.
        """
        self._storage = value

    @property
    def pipeline(self) -> Optional[ValidationPipeline]:
        """Get the validation pipeline."""
        return self._schema_manager.pipeline

    @pipeline.setter
    def pipeline(self, value: Optional[ValidationPipeline]) -> None:
        """Set the validation pipeline."""
        self._pipeline = value
        self._schema_manager.pipeline = value

    @property
    def relationships(self) -> RelationshipManager:
        """Get the relationship manager."""
        return self._query_service.relationships

    @relationships.setter
    def relationships(self, value: RelationshipManager) -> None:
        """Set the relationship manager."""
        self._query_service.relationships = value

    # -- SchemaManager delegations --

    def _build_fts_metadata(self) -> None:
        self._schema_manager._build_fts_metadata()

    def _validate_search_capabilities(self) -> None:
        self._schema_manager._validate_search_capabilities()

    def schema_references(self, entity_type: str) -> list[dict]:
        return self._schema_manager.schema_references(entity_type)

    def _get_fts_tables_for_entity_type(
        self, entity_type: str
    ) -> list[FTSTableMetadata]:
        return self._schema_manager.get_fts_tables_for_entity_type(entity_type)

    def add_validator(self, validator: WriteValidator) -> None:
        self._schema_manager.add_validator(validator)

    def validate(self, operation: WriteOperation) -> ValidationResult:
        return self._schema_manager.validate(operation)

    # -- Ingestion methods --
    # These keep the original call chain (put -> _put_internal -> _create_internal etc.)
    # on HippoClient so subclass overrides of private methods continue to work.
    # The IngestionService facade exists for direct standalone use.

    def _sync_entity_to_fts(
        self,
        entity_id: str,
        entity_type: str,
        data: dict[str, Any],
        is_available: bool = True,
    ) -> None:
        self._ingestion_service._sync_entity_to_fts(
            entity_id, entity_type, data, is_available
        )

    def put(
        self,
        entity_type: str,
        data: dict[str, Any],
        entity_id: Optional[str] = None,
        bypass_validation: Optional[bool] = None,
    ) -> dict[str, Any]:
        """Create or update an entity."""
        from hippo.core.exceptions import ValidationFailure

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
        import uuid
        from datetime import datetime, timezone

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
            return self._ingestion_service._put_with_sqlite(entity_type, data, entity_id)

        if (
            entity_id
            and hasattr(self._storage, "exists")
            and self._storage.exists(entity_type, entity_id)
        ):
            return self._update_internal(entity_type, entity_id, data)
        return self._create_internal(entity_type, data)

    def _create_internal(
        self, entity_type: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Internal create implementation (overridable by subclasses)."""
        return {"id": data.get("id"), "entity_type": entity_type, "data": data}

    def _update_internal(
        self, entity_type: str, entity_id: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Internal update implementation (overridable by subclasses)."""
        return {"id": entity_id, "entity_type": entity_type, "data": data}

    def _delete_internal(self, entity_type: str, entity_id: str) -> bool:
        """Internal delete implementation (overridable by subclasses)."""
        if self._storage is None:
            return True

        if hasattr(self._storage, "delete"):
            entity = self._storage.read(entity_id)
            data = entity.data if entity else {}
            result = self._storage.delete(entity_id)
            self._sync_entity_to_fts(entity_id, entity_type, data, is_available=False)
            return result

        return True

    def replace(
        self,
        entity_type: str,
        entity_id: str,
        data: dict[str, Any],
        bypass_validation: Optional[bool] = None,
    ) -> dict[str, Any]:
        """Full replacement of an existing entity (PUT semantics).

        Unlike update/put which merge or upsert, replace requires the entity
        to already exist and overwrites all fields. Records a 'replaced'
        provenance event. Returns 404 if entity does not exist.
        """
        return self._ingestion_service.replace(
            entity_type, entity_id, data, bypass_validation
        )

    def create(
        self,
        entity_type: str,
        data: dict[str, Any],
        bypass_validation: Optional[bool] = None,
    ) -> dict[str, Any]:
        """Create a new entity."""
        return self.put(entity_type, data, bypass_validation=bypass_validation)

    def update(
        self,
        entity_type: str,
        entity_id: str,
        data: dict[str, Any],
        bypass_validation: Optional[bool] = None,
    ) -> dict[str, Any]:
        """Update an existing entity."""
        from hippo.core.exceptions import EntityNotFoundError

        if self._storage is not None and hasattr(self._storage, "read"):
            existing = self._storage.read(entity_id)
            if existing is None:
                raise EntityNotFoundError(
                    message=f"Entity not found: {entity_id}",
                    entity_type=entity_type,
                    entity_id=entity_id,
                )
        return self.put(entity_type, data, entity_id, bypass_validation)

    def delete(
        self,
        entity_type: str,
        entity_id: str,
        bypass_validation: Optional[bool] = None,
    ) -> bool:
        """Delete an entity."""
        from hippo.core.exceptions import ValidationFailure

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

    def set_availability_bulk(
        self,
        entity_type: str,
        entity_ids: list[str],
        is_available: bool,
        reason: Optional[str] = None,
        actor: Optional[str] = None,
    ) -> dict[str, Any]:
        """Change availability status for multiple entities at once.

        Returns a summary with per-entity successes and failures.
        Records provenance events for each changed entity.
        """
        return self._ingestion_service.set_availability_bulk(
            entity_type, entity_ids, is_available, reason, actor
        )

    # -- QueryService delegations --

    def get(
        self,
        entity_type: str,
        entity_id: str,
        expand: Optional[str] = None,
        include_unavailable: bool = False,
    ) -> dict[str, Any]:
        """Get an entity by its ID."""
        return self._query_service.get(
            entity_type, entity_id, expand, include_unavailable
        )

    def resolve_type(self, entity_id: str) -> Optional[str]:
        """Resolve a UUID to its entity_type via the storage adapter.

        Per sec9 §9.5's identity model — given only a UUID, return the entity
        class (FQN in the merged schema). Returns None when the UUID is not
        known to the storage. The concrete resolution mechanism is
        adapter-specific; relational adapters query the `entities` table's
        type discriminator, future graph adapters use labels.
        """
        if self._storage is None or not hasattr(self._storage, "resolve_type"):
            return None
        return self._storage.resolve_type(entity_id)

    def resolve_types(self, entity_ids: list[str]) -> dict[str, str]:
        """Batch variant of ``resolve_type``; one round-trip to the adapter.

        Returns a dict mapping id → entity_type for every known id. Unknown
        ids are absent from the result; callers can compute the missing set
        by diffing the input list against the returned keys.
        """
        if (
            self._storage is None
            or not hasattr(self._storage, "resolve_types")
            or not entity_ids
        ):
            return {}
        return self._storage.resolve_types(entity_ids)

    def query(
        self,
        entity_type: str,
        filters: Optional[list[dict[str, Any]]] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        filter_mode: str = "and",
    ) -> "PaginatedResult":
        """Query entities with filter criteria.

        Args:
            filter_mode: How to combine filters — "and" (all must match,
                default) or "or" (any may match).
        """
        return self._query_service.query(
            entity_type, filters, date_from, date_to, limit, offset, filter_mode
        )

    def search(
        self,
        entity_type: str,
        query: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Search entities using full-text search."""
        return self._query_service.search(entity_type, query, limit)

    # -- ProvenanceService delegations --

    def _get_provenance_summary_map(self, entity_type: str) -> dict[str, dict]:
        return self._provenance_service.get_provenance_summary_map(entity_type)

    def register_external_id(
        self,
        entity_id: str,
        external_id: str,
        source_system: str = "default",
    ) -> dict[str, Any]:
        """Register an external ID for an entity.

        ``source_system`` defaults to ``"default"`` for backward
        compatibility with legacy two-argument callers. Callers managing
        multiple source systems should pass the parameter explicitly so
        the ``(source_system, value)`` uniqueness constraint applies
        within the correct scope.
        """
        return self._provenance_service.register_external_id(
            entity_id, external_id, source_system=source_system
        )

    def supersede(
        self,
        entity_id: str,
        old_external_id: str,
        new_external_id: str,
        source_system: str = "default",
    ) -> dict[str, Any]:
        """Supersede an entity's external ID with a new one.

        The supersede operation is scoped to one ``source_system``;
        legacy two-argument callers default to ``"default"``.
        """
        return self._provenance_service.supersede(
            entity_id,
            old_external_id,
            new_external_id,
            source_system=source_system,
        )

    def supersede_entity(
        self,
        entity_id: str,
        replacement_id: str,
        reason: Optional[str] = None,
        actor: Optional[str] = None,
    ) -> dict[str, Any]:
        """Mark an entity as superseded by a replacement entity."""
        return self._provenance_service.supersede_entity(
            entity_id, replacement_id, reason, actor
        )

    def get_by_external_id(
        self, external_id: str, include_archived: bool = False
    ) -> dict[str, Any]:
        """Get an entity by its external ID."""
        return self._provenance_service.get_by_external_id(
            external_id, include_archived
        )

    def list_external_ids(
        self, entity_id: str, include_superseded: bool = False
    ) -> list[dict[str, Any]]:
        """List all external IDs for an entity."""
        return self._provenance_service.list_external_ids(
            entity_id, include_superseded
        )

    def history(self, entity_id: str) -> list[dict[str, Any]]:
        """Get the change history for an entity."""
        return self._provenance_service.history(entity_id)

    def state_at(self, entity_id: str, timestamp: str) -> Optional[dict[str, Any]]:
        """Get the entity state at a specific point in time."""
        return self._provenance_service.state_at(entity_id, timestamp)
