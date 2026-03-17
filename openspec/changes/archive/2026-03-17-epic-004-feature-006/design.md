## Context

The `IngestionPipeline` in `hippo/core/ingestion.py` currently provides basic tracking of ingestion results via the `IngestResult` dataclass. It tracks `created`, `updated`, `unchanged`, and `errors` counts, but lacks:
1. Timestamp tracking for each ingestion run
2. Source file path in error messages
3. Proper record ID context in error messages

The Hippo system needs to support reporting and analytics over multiple ingestion cycles, requiring temporal data.

## Goals / Non-Goals

**Goals:**
- Add timestamp tracking to `IngestResult` for temporal reporting
- Include source file path in error context for traceability
- Ensure all count types accurately sum to total records processed
- Support historical analysis of ingestion results

**Non-Goals:**
- Persistent storage of IngestResult history (future enhancement)
- Real-time streaming of progress (future enhancement)
- Multi-file batch ingestion in single call (out of scope)

## Decisions

1. **Timestamp field**: Add `timestamp: datetime` field to `IngestResult` populated at creation time in `_upsert_records`. Alternative was to add it to the method call, but embedding at result creation is simpler and more consistent.

2. **Error context**: Enhance error messages to include source file path. The `IngestResult` will store a `source_file` field set from the input file path.

3. **Record ID in errors**: Store failed record identifiers (external_id) alongside error messages rather than just string messages. This enables programmatic error handling.

## Risks / Trade-offs

- **Risk**: Adding new fields to `IngestResult` could break existing consumers
- **Mitigation**: New fields have defaults, existing `to_dict()` will include them with sensible defaults

- **Risk**: Timestamp format compatibility
- **Mitigation**: Use ISO 8601 format in `to_dict()` serialization for broad compatibility

- **Trade-off**: Error detail verbosity vs. storage size - storing full error context increases memory but provides better debugging

## Migration Plan

1. Add optional fields to `IngestResult` with defaults (backward compatible)
2. Update `_upsert_records` to populate new fields
3. Existing code continues to work without changes
4. No database migrations needed (in-memory result object only)

## Open Questions

- Should IngestResult implement `__post_init__` validation?
- Do we need to serialize to specific formats (JSON, Protobuf) beyond `to_dict()`?
