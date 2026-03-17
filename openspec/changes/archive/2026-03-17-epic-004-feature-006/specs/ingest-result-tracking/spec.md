## ADDED Requirements

### Requirement: IngestResult tracks created record count
The IngestResult SHALL include a `created` field that accurately tracks the number of new records added during ingestion.

#### Scenario: New records are created
- **WHEN** an ingestion process inserts new records that did not previously exist
- **THEN** the IngestResult.created field equals the number of new records added

### Requirement: IngestResult tracks updated record count
The IngestResult SHALL include an `updated` field that accurately tracks the number of existing records modified during ingestion.

#### Scenario: Existing records are updated
- **WHEN** an ingestion process modifies existing records with different data
- **THEN** the IngestResult.updated field equals the number of records modified

### Requirement: IngestResult tracks unchanged record count
The IngestResult SHALL include an `unchanged` field that accurately tracks the number of records that remained unmodified during ingestion.

#### Scenario: Unchanged records are detected
- **WHEN** an ingestion process encounters records where external ID exists and data is identical
- **THEN** the IngestResult.unchanged field equals the number of records not modified

### Requirement: IngestResult tracks error count
The IngestResult SHALL include an `errors` field that accurately tracks the number of failed records during ingestion.

#### Scenario: Errors are counted
- **WHEN** an ingestion process encounters records that fail to process
- **THEN** the IngestResult.errors field equals the number of failed records

### Requirement: IngestResult includes error context with record identifier
The IngestResult SHALL include error messages that contain the record identifier and error details for failed records.

#### Scenario: Error includes record ID and message
- **WHEN** an ingestion process encounters an error during processing
- **THEN** the error information includes the record's external ID and a descriptive error message

### Requirement: IngestResult includes source file path in error context
The IngestResult SHALL include the source file path when logging errors to enable traceability to the input file.

#### Scenario: Error includes source file information
- **WHEN** an ingestion process is initiated with invalid data and encounters errors
- **THEN** the error information includes the source file path and error type

### Requirement: IngestResult preserves counts for historical reporting
The IngestResult object SHALL preserve all count values after ingestion completes to support historical analysis.

#### Scenario: Counts are preserved after ingestion
- **WHEN** multiple ingestion runs occur
- **THEN** each IngestResult preserves its created, updated, unchanged, and errors counts for reporting

### Requirement: IngestResult includes timestamp for temporal reporting
The IngestResult SHALL include a timestamp field that records when the ingestion completed to enable temporal reporting.

#### Scenario: Timestamp is recorded
- **WHEN** an ingestion process completes
- **THEN** the IngestResult includes a timestamp indicating when the ingestion finished

### Requirement: IngestResult counts sum to total records processed
The IngestResult SHALL ensure that created + updated + unchanged + errors equals the total number of records processed.

#### Scenario: Counts sum correctly for mixed results
- **WHEN** an ingestion process completes with mixed results (some created, updated, unchanged, and errors)
- **THEN** all count types are accurately tracked and the sum equals total records processed
