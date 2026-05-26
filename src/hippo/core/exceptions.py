"""Exception classes for Hippo SDK."""

from typing import Any, Optional


class HippoError(Exception):
    """Base exception class for all Hippo SDK errors."""

    def __init__(self, message: str, **context: Any):
        self.message = message
        self.context = context
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        if self.context:
            context_str = ", ".join(f"{k}={v!r}" for k, v in self.context.items())
            return f"{self.message} ({context_str})"
        return self.message


class ConfigError(HippoError):
    """Exception raised for configuration loading and validation errors."""

    def __init__(
        self,
        message: str,
        field_name: Optional[str] = None,
        **context: Any,
    ):
        self.field_name = field_name
        context["field_name"] = field_name
        super().__init__(message, **context)


class SchemaError(HippoError):
    """Exception raised for schema parsing and processing errors."""

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        field_name: Optional[str] = None,
        cycle_path: Optional[list[str]] = None,
        **context: Any,
    ):
        self.error_code = error_code
        self.field_name = field_name
        self.cycle_path = cycle_path or []
        context["error_code"] = error_code
        context["field_name"] = field_name
        context["cycle_path"] = cycle_path
        super().__init__(message, **context)


class ValidationError(HippoError):
    """Exception raised for data validation errors."""

    def __init__(
        self,
        message: str,
        expected_type: Optional[str] = None,
        actual_value: Optional[Any] = None,
        field_name: Optional[str] = None,
        **context: Any,
    ):
        self.expected_type = expected_type
        self.actual_value = actual_value
        self.field_name = field_name
        context["expected_type"] = expected_type
        context["actual_value"] = actual_value
        context["field_name"] = field_name
        super().__init__(message, **context)


class EntityNotFoundError(HippoError):
    """Exception raised when an entity is not found in the system."""

    def __init__(
        self,
        message: str,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        **context: Any,
    ):
        self.entity_type = entity_type
        self.entity_id = entity_id
        context["entity_type"] = entity_type
        context["entity_id"] = entity_id
        super().__init__(message, **context)


class EntityAlreadySupersededError(HippoError):
    """Exception raised when supersede_entity() is called on an already-superseded entity.

    Raised before any writes are performed, ensuring no state change occurs.
    """

    def __init__(
        self,
        message: str,
        entity_id: Optional[str] = None,
        superseded_by: Optional[str] = None,
        **context: Any,
    ):
        self.entity_id = entity_id
        self.superseded_by = superseded_by
        context["entity_id"] = entity_id
        context["superseded_by"] = superseded_by
        super().__init__(message, **context)


class AdapterError(HippoError):
    """Exception raised for adapter-specific errors."""

    def __init__(
        self,
        message: str,
        adapter_name: Optional[str] = None,
        adapter_type: Optional[str] = None,
        **context: Any,
    ):
        self.adapter_name = adapter_name
        self.adapter_type = adapter_type
        context["adapter_name"] = adapter_name
        context["adapter_type"] = adapter_type
        super().__init__(message, **context)


class ValidationFailure(HippoError):
    """Exception raised when a write operation fails validation.

    Contains detailed information about the validation failure including
    the rule that failed, the error message, and the input context.
    """

    def __init__(
        self,
        message: str,
        rule_id: Optional[str] = None,
        input_context: Optional[dict[str, Any]] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        **context: Any,
    ):
        self.rule_id = rule_id
        self.input_context = input_context or {}
        self.entity_type = entity_type
        self.entity_id = entity_id
        context["rule_id"] = rule_id
        context["input_context"] = input_context
        context["entity_type"] = entity_type
        context["entity_id"] = entity_id
        super().__init__(message, **context)

    def format_detailed_message(self) -> str:
        """Format a detailed failure message with all context.

        Returns:
            Human-readable string with all failure details.
        """
        parts = [self.message]

        if self.rule_id:
            parts.append(f"Rule: {self.rule_id}")

        if self.entity_type:
            entity_info = f"Entity type: {self.entity_type}"
            if self.entity_id:
                entity_info += f" (ID: {self.entity_id})"
            parts.append(entity_info)

        if self.input_context:
            context_str = ", ".join(f"{k}={v!r}" for k, v in self.input_context.items())
            parts.append(f"Context: {context_str}")

        return " | ".join(parts)


class ValidationFailed(HippoError):
    """Raised by typed-client write methods when validation fails.

    Carries the full sec9 §9.9 envelope (``ValidationResult``) so callers
    can introspect per-tier failures rather than parsing concatenated
    error strings. The REST layer catches this and maps to HTTP 400/422
    with a structured body (see ``hippo.api.app``).
    """

    def __init__(
        self,
        message: str,
        result: Any = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        **context: Any,
    ):
        self.result = result
        self.entity_type = entity_type
        self.entity_id = entity_id
        context["entity_type"] = entity_type
        context["entity_id"] = entity_id
        super().__init__(message, **context)


class TemporalQueryError(HippoError):
    """Exception raised for temporal query errors.

    Raised when querying entity state at a point in time that is invalid,
    such as before the entity was created.
    """

    def __init__(
        self,
        message: str,
        entity_id: Optional[str] = None,
        requested_timestamp: Optional[str] = None,
        entity_creation_time: Optional[str] = None,
        **context: Any,
    ):
        self.entity_id = entity_id
        self.requested_timestamp = requested_timestamp
        self.entity_creation_time = entity_creation_time
        context["entity_id"] = entity_id
        context["requested_timestamp"] = requested_timestamp
        context["entity_creation_time"] = entity_creation_time
        super().__init__(message, **context)


class ProvenanceIntegrityError(HippoError):
    """Exception raised when provenance state is missing or inconsistent.

    Every mutation emits a ``ProvenanceRecord`` transactionally with the
    entity write (sec9 §9.6), so an entity that exists in the ``entities``
    table with no matching provenance is a data-integrity defect — not an
    expected degraded state. Per sec9 §9.2 (*Provenance integrity is
    transactional and loud*), the SDK refuses to return the entity.

    Also raised on other inconsistency shapes: a non-``create`` record as
    the earliest entry, a record with missing ``actor_id``, or a
    ``schema_version`` unrecognized by the merged view.
    """

    def __init__(
        self,
        message: str,
        entity_id: Optional[str] = None,
        inconsistency: Optional[str] = None,
        **context: Any,
    ):
        self.entity_id = entity_id
        self.inconsistency = inconsistency
        context["entity_id"] = entity_id
        context["inconsistency"] = inconsistency
        super().__init__(message, **context)


class IngestionError(HippoError):
    """Exception raised for data ingestion errors.

    Raised when file reading, parsing, or processing fails.
    """

    def __init__(
        self,
        message: str,
        input_context: Optional[dict[str, Any]] = None,
        entity_type: Optional[str] = None,
        **context: Any,
    ):
        self.input_context = input_context or {}
        self.entity_type = entity_type
        context["input_context"] = input_context
        context["entity_type"] = entity_type
        super().__init__(message, **context)


class IngestionValidationError(IngestionError):
    """Exception raised for data ingestion validation errors.

    Raised when input data fails validation checks (e.g., missing headers).
    """

    def __init__(
        self,
        message: str,
        input_context: Optional[dict[str, Any]] = None,
        entity_type: Optional[str] = None,
        **context: Any,
    ):
        super().__init__(
            message, input_context=input_context, entity_type=entity_type, **context
        )


class CacheIntegrityError(HippoError):
    """Raised when a cached or freshly downloaded file fails sha256 verification.

    Triggered by :meth:`HippoClient.cached_fetch` when ``expected_sha256`` is
    supplied and the computed digest does not match — either on the initial
    download or on a subsequent cache hit that has been corrupted out-of-band
    (sec2 §2.14.3, decision D2.14.E).
    """

    def __init__(
        self,
        message: str,
        url: Optional[str] = None,
        path: Optional[str] = None,
        expected_sha256: Optional[str] = None,
        actual_sha256: Optional[str] = None,
        **context: Any,
    ):
        self.url = url
        self.path = path
        self.expected_sha256 = expected_sha256
        self.actual_sha256 = actual_sha256
        context["url"] = url
        context["path"] = path
        context["expected_sha256"] = expected_sha256
        context["actual_sha256"] = actual_sha256
        super().__init__(message, **context)


class SearchCapabilityError(HippoError):
    """Exception raised when a search operation is attempted on a field
    that does not support full-text search.

    Raised when searching a field not declared with `search: fts` in the schema,
    or when the adapter does not support a search mode declared in the schema.
    """

    def __init__(
        self,
        message: str,
        field_name: Optional[str] = None,
        entity_type: Optional[str] = None,
        unsupported_modes: Optional[list[str]] = None,
        **context: Any,
    ):
        self.field_name = field_name
        self.entity_type = entity_type
        self.unsupported_modes = unsupported_modes or []
        context["field_name"] = field_name
        context["entity_type"] = entity_type
        context["unsupported_modes"] = self.unsupported_modes
        super().__init__(message, **context)

    def suggest_fts_enablement(self) -> str:
        """Suggest how to enable FTS for the field."""
        if self.field_name and self.entity_type:
            return f"To enable full-text search, add 'search: fts' to the '{self.field_name}' field definition in the {self.entity_type} entity schema."
        return "To enable full-text search, add 'search: fts' to the field definition in your schema."
