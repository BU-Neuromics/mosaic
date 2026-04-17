"""SchemaManager — schema access, validation pipeline, and FTS metadata facade.

Operates on a LinkML-backed :class:`SchemaRegistry`. All schema introspection
(FTS slots, reference slots, search capabilities) reads from LinkML
``annotations:`` via the registry.
"""

from __future__ import annotations

from typing import Optional

from hippo.core.pipeline import ValidationPipeline
from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter
from hippo.core.storage.fts import FTSFieldMetadata, FTSTableMetadata
from hippo.core.validation.validators import (
    ValidationResult,
    WriteOperation,
    WriteValidator,
)
from hippo.linkml_bridge import SchemaRegistry


class SchemaManager:
    """Owns schema access, the write-validation pipeline, and FTS metadata."""

    def __init__(
        self,
        registry: Optional[SchemaRegistry] = None,
        pipeline: Optional[ValidationPipeline] = None,
        bypass_validation: bool = False,
        storage: Optional[SQLiteAdapter] = None,
    ) -> None:
        self._registry = registry
        self._pipeline = pipeline
        self._bypass_validation = bypass_validation
        self._storage = storage
        self._fts_table_metadata: dict[str, list[FTSTableMetadata]] = {}
        self._build_fts_metadata()
        self._validate_search_capabilities()

    @property
    def registry(self) -> Optional[SchemaRegistry]:
        return self._registry

    @property
    def pipeline(self) -> Optional[ValidationPipeline]:
        return self._pipeline

    @pipeline.setter
    def pipeline(self, value: Optional[ValidationPipeline]) -> None:
        self._pipeline = value

    @property
    def bypass_validation(self) -> bool:
        return self._bypass_validation

    @property
    def fts_table_metadata(self) -> dict[str, list[FTSTableMetadata]]:
        return self._fts_table_metadata

    def _non_abstract_class_names(self) -> list[str]:
        if self._registry is None:
            return []
        sv = self._registry.schema_view
        return [
            name
            for name in self._registry.class_names()
            if not (sv.get_class(name) and sv.get_class(name).abstract)
        ]

    def _build_fts_metadata(self) -> None:
        if self._registry is None:
            return
        for class_name in self._non_abstract_class_names():
            fts_tables: list[FTSTableMetadata] = []
            for slot, mode in self._registry.searchable_slots(class_name):
                fts_tables.append(
                    FTSTableMetadata(
                        table_name=FTSTableMetadata.generate_table_name(
                            class_name, slot.name
                        ),
                        source_entity_type=class_name,
                        fts_version=mode,
                        content_table="entities",
                        content_rowid="rowid",
                        fields=[
                            FTSFieldMetadata(
                                field_name=slot.name,
                                field_type=slot.range or "string",
                                search_type=mode,
                                source_entity_type=class_name,
                            )
                        ],
                    )
                )
            if fts_tables:
                self._fts_table_metadata[class_name] = fts_tables

    def _validate_search_capabilities(self) -> None:
        from hippo.core.exceptions import SearchCapabilityError

        if self._storage is None or self._registry is None:
            return

        adapter_capabilities = self._storage.search_capabilities()
        declared_modes: set[str] = set()
        for class_name in self._non_abstract_class_names():
            for _slot, mode in self._registry.searchable_slots(class_name):
                normalized = "fts" if mode in ("fts", "fts5") else mode
                declared_modes.add(normalized)

        unsupported = declared_modes - adapter_capabilities
        if unsupported:
            raise SearchCapabilityError(
                message=(
                    "Storage adapter does not support search modes: "
                    + ", ".join(sorted(unsupported))
                ),
                unsupported_modes=list(unsupported),
            )

    def schema_references(self, entity_type: str) -> list[dict]:
        if self._registry is None or not self._registry.has_class(entity_type):
            return []
        return [
            {"field": slot_name, "target_entity_type": target}
            for slot_name, target in self._registry.reference_slots(entity_type)
        ]

    def get_fts_tables_for_entity_type(
        self, entity_type: str
    ) -> list[FTSTableMetadata]:
        return self._fts_table_metadata.get(entity_type, [])

    def add_validator(self, validator: WriteValidator) -> None:
        if self._pipeline is None:
            self._pipeline = ValidationPipeline()
        self._pipeline.add_validator(validator)

    def validate(self, operation: WriteOperation) -> ValidationResult:
        if self._bypass_validation or self._pipeline is None:
            return ValidationResult(is_valid=True, errors=[])
        return self._pipeline.execute(operation)
