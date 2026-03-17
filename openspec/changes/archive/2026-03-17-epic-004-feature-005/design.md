## Context

The Hippo Metadata Tracking Service needs to support data ingestion from file-based formats (CSV, JSON, JSONL). Currently, there is no built-in capability to ingest bulk data from files. The IngestionPipeline class exists but lacks CSV/JSON processing functionality.

This change will add file parsing and upsert capabilities to the IngestionPipeline, enabling external systems to bulk-load data with external ID-based deduplication.

## Goals / Non-Goals

**Goals:**
- Enable CSV file ingestion with header validation
- Enable JSON array file ingestion with upsert-by-ExternalID
- Enable JSONL (JSON Lines) file ingestion
- Implement proper error handling for malformed files
- Support batch processing with accurate created/updated/unchanged counts
- Handle duplicate external IDs via upsert logic

**Non-Goals:**
- Real-time streaming ingestion (future enhancement)
- GraphQL-based ingestion API (future enhancement)
- Integration with external LIMS systems (future work)
- Transformation/pipeline stages beyond basic parsing

## Decisions

### Decision 1: Flatten nested JSON structures
**Choice**: Flatten nested objects to dot-notation keys (e.g., `{"address": {"city": "Boston"}}` → `{"address.city": "Boston"}`)

**Rationale**: Simplifies storage and querying. Maintains readability while enabling flat schema storage.

**Alternative considered**: Store nested JSON as-is as JSON column type. Rejected due to complexity in querying and indexing.

### Decision 2: Upsert strategy
**Choice**: Use ExternalID as the unique key for upsert operations. Created = new ExternalID, Updated = existing ExternalID with changed data, Unchanged = existing ExternalID with identical data.

**Rationale**: ExternalID is already the canonical identifier pattern in Hippo. Simpler than composite keys.

**Alternative considered**: Use composite key (entity_type + external_id). Rejected as it adds complexity without clear benefit.

### Decision 3: Batch processing approach
**Choice**: Process entire file as a single batch, returning aggregate counts (created, updated, unchanged, errors).

**Rationale**: Matches current IngestionPipeline architecture. Enables simple error summary.

**Alternative considered**: Chunked processing for large files. Deferred to future optimization once basic flow works.

### Decision 4: Error handling strategy
**Choice**: Continue processing on non-critical errors (malformed rows), collect all errors, return summary at end. Fail completely on critical errors (missing headers, invalid format).

**Rationale**: Allows partial success. Matches user expectation from acceptance criteria.

**Alternative considered**: Fail-fast on any error. Rejected as it prevents valid records from being processed when one row is bad.

## Risks / Trade-offs

| Risk | Impact | Mitigation |
|------|--------|------------|
| Large file memory usage | High | Add max row count validation (configurable) |
| Nested JSON complexity | Medium | Limit to 1 level of flattening, warn on deeper |
| External ID collisions | Medium | Use upsert semantics, track updated vs created |
| Invalid CSV without headers | Medium | Validate headers exist before processing |
| Missing ExternalID in records | Medium | Log error, skip record, continue processing |

## Migration Plan

1. Add new methods to IngestionPipeline class:
   - `ingest_csv(file_path, entity_type)`
   - `ingest_json(file_path, entity_type)`
   - `ingest_jsonl(file_path, entity_type)`

2. Add helper utilities:
   - `flatten_dict()` for nested JSON
   - `parse_csv_with_errors()` for error-tolerant CSV parsing

3. Add configuration:
   - `max_batch_size` - maximum rows allowed in single batch
   - `flatten_nested` - toggle nested JSON flattening

4. No database migration needed - using existing ExternalID column

**Rollback**: Remove new methods, revert to previous IngestionPipeline version.

## Open Questions

1. Should we support streaming/chunked processing for files > 10K rows?
2. What should be the default `max_batch_size`? (Proposal suggests 10000)
3. Should we add validation against entity schema before upsert?
