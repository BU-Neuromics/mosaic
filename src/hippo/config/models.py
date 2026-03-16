from pathlib import Path
from typing import Any, Optional, Union

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class ValidatorDefinition(BaseModel):
    """Definition of a validator in schema configuration."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str
    type: str
    enabled: bool = True
    priority: int = 0
    config: Optional[dict[str, Any]] = None


class HippoConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    schema_path: Path
    storage_backend: Optional[str] = None
    database_url: Optional[str] = None
    validation_enabled: bool = True
    validation_fail_fast: bool = True
    write_path_validation_enabled: bool = True
    write_path_validation_timeout: Optional[float] = None
    validators_path: Optional[Path] = None

    @field_validator("schema_path", mode="before")
    @classmethod
    def validate_schema_path(cls, v):
        if isinstance(v, str):
            return Path(v)
        return v


class FieldDefinition(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str
    type: str
    required: bool = False
    description: Optional[str] = None
    default: Optional[Any] = None
    primary_key: bool = False
    unique: bool = False
    index: bool = False
    index_partial: bool = False
    search: Optional[str] = None
    references: Optional[dict[str, Any]] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Field name cannot be empty")
        return v.strip()

    @field_validator("type")
    @classmethod
    def validate_type(cls, v):
        valid_types = {
            "string",
            "integer",
            "float",
            "boolean",
            "date",
            "datetime",
            "list",
            "dict",
            "uri",
            "enum",
        }
        if v not in valid_types:
            raise ValueError(f"Invalid field type: {v}. Must be one of {valid_types}")
        return v

    @field_validator("search")
    @classmethod
    def validate_search(cls, v):
        if v is not None and v not in {"fts", "fts5", "embedding"}:
            raise ValueError("search must be either 'fts', 'fts5', or 'embedding'")
        return v


class SchemaConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    name: str
    version: str
    description: Optional[str] = None
    fields: list[FieldDefinition] = []
    base: Optional[Union[str, list[str]]] = None
    metadata: Optional[dict[str, Any]] = None
    unique_constraints: Optional[list[list[str]]] = None
    indexes: Optional[list[dict[str, Any]]] = None
    validators: list[ValidatorDefinition] = []
    max_batch_size: int = 10000
    flatten_nested: bool = True

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Schema name cannot be empty")
        return v.strip()

    @field_validator("version")
    @classmethod
    def validate_version(cls, v):
        if not v or not v.strip():
            raise ValueError("Schema version cannot be empty")
        return v.strip()

    @model_validator(mode="after")
    def validate_base(self):
        if self.base is not None:
            if isinstance(self.base, str) and not self.base.strip():
                raise ValueError("Base schema reference cannot be empty")
            if isinstance(self.base, list):
                for b in self.base:
                    if not b or not b.strip():
                        raise ValueError("Base schema reference cannot be empty")
        return self

    def get_bases(self) -> list[str]:
        if self.base is None:
            return []
        if isinstance(self.base, str):
            return [self.base]
        return list(self.base)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SchemaConfig":
        return cls(**data)

    def get_fts_fields(self) -> list[FieldDefinition]:
        """Get all fields marked for full-text search indexing."""
        return [field for field in self.fields if field.search is not None]

    def get_fts_field_names(self) -> list[str]:
        """Get names of all fields marked for full-text search indexing."""
        return [field.name for field in self.get_fts_fields()]

    def is_fts_field(self, field_name: str) -> bool:
        """Check if a field is marked for full-text search indexing."""
        return any(
            field.name == field_name and field.search is not None
            for field in self.fields
        )

    def get_fts_field(self, field_name: str) -> Optional[FieldDefinition]:
        """Get a field definition by name if it has FTS indexing."""
        for field in self.fields:
            if field.name == field_name and field.search is not None:
                return field
        return None
