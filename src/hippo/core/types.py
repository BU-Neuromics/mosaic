"""Core SDK types for Hippo."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class FilterOperator(str, Enum):
    """Comparison operators for filter conditions."""

    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"


class FilterCondition(BaseModel):
    """A single filter condition."""

    field: str = Field(description="The field name to filter on")
    operator: FilterOperator = Field(description="The comparison operator")
    value: Any = Field(description="The value to compare against")


class LogicalOperator(str, Enum):
    """Logical operators for combining filter conditions."""

    AND = "and"
    OR = "or"


class FilterGroup(BaseModel):
    """A group of filter conditions combined with a logical operator."""

    conditions: list["FilterCondition"] = Field(default_factory=list)
    groups: list["FilterGroup"] = Field(default_factory=list)
    logical_operator: LogicalOperator = Field(default=LogicalOperator.AND)


class Filter(BaseModel):
    """Filter type for querying data with multiple conditions.

    Supports nested condition groups with AND/OR logic for complex queries.
    """

    root: FilterGroup = Field(default_factory=FilterGroup)

    def model_dump(self, **kwargs) -> dict[str, Any]:
        """Serialize the filter to a dictionary."""
        return super().model_dump(**kwargs)


class PaginatedResult(BaseModel):
    """Paginated result type with metadata.

    Used for returning paged query results with pagination information.
    """

    items: list[Any] = Field(default_factory=list, description="The items on this page")
    total: int = Field(description="Total number of items across all pages")
    page: int = Field(description="Current page number (1-indexed)")
    page_size: int = Field(description="Number of items per page")


class ScoredMatch(BaseModel):
    """Scored match type for search results with relevance scoring.

    Used when returning search results that include relevance scores.
    """

    score: float = Field(description="Relevance score (higher is more relevant)")
    match_data: dict[str, Any] = Field(
        default_factory=dict, description="The matched data"
    )
    matched_fields: list[str] = Field(
        default_factory=list, description="Fields that matched the query"
    )


class WriteOperation(BaseModel):
    """Write operation result type with success status and metadata.

    Used for data insertion, update, and delete operations.
    """

    success: bool = Field(description="Whether the operation succeeded")
    operation: str = Field(description="Type of operation (insert, update, delete)")
    entity_type: str = Field(description="The type of entity affected")
    entity_id: Optional[str] = Field(default=None, description="ID of affected entity")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional operation metadata"
    )


class ValidationError(BaseModel):
    """A single validation error."""

    field: str = Field(description="The field that failed validation")
    message: str = Field(description="Human-readable error message")


class ValidationResult(BaseModel):
    """Validation result type with success/failure status and errors.

    Used for validating data before write operations.
    """

    valid: bool = Field(description="Whether validation passed")
    errors: list[ValidationError] = Field(
        default_factory=list, description="List of validation errors if any"
    )

    @property
    def is_valid(self) -> bool:
        """Alias for valid property."""
        return self.valid


class ProvenanceRecord(BaseModel):
    """Provenance record for tracking data lineage.

    Records the source, timestamp, and operation that created or modified data.
    """

    source: str = Field(description="Origin system or entity")
    timestamp: datetime = Field(description="When the operation occurred")
    operation: str = Field(
        description="Type of operation (create, update, read, delete)"
    )
    entity_type: Optional[str] = Field(
        default=None, description="Type of entity affected"
    )
    entity_id: Optional[str] = Field(default=None, description="ID of entity")
    user_context: Optional[str] = Field(
        default=None, description="User or system context that initiated the operation"
    )
    payload: dict[str, Any] = Field(
        default_factory=dict, description="Complete entity state as JSON"
    )


class IngestStatus(str, Enum):
    """Status of an ingestion operation."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class IngestResult(BaseModel):
    """Ingest result type with status, counts, and errors.

    Used for data ingestion operations that process multiple items.
    """

    status: IngestStatus = Field(description="Overall ingestion status")
    total_processed: int = Field(description="Total items processed")
    successful: int = Field(description="Number of successfully processed items")
    failed: int = Field(description="Number of failed items")
    errors: list[dict[str, Any]] = Field(
        default_factory=list, description="List of error details for failed items"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional result metadata"
    )
