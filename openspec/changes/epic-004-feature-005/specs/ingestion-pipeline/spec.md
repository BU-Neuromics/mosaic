## ADDED Requirements

### Requirement: CSV File Ingestion
The system SHALL allow users to ingest data from CSV files into the Hippo metadata store.

#### Scenario: Valid CSV with headers
- **WHEN** a valid CSV file with headers exists and the ingestion pipeline is invoked
- **THEN** each record is parsed correctly and inserted into the system

#### Scenario: Malformed row handling
- **WHEN** a CSV file contains malformed rows during ingestion
- **THEN** the malformed rows are logged as errors and valid rows continue to be processed

#### Scenario: CSV without headers
- **WHEN** an invalid CSV file without proper headers is provided
- **THEN** an error is thrown with an appropriate error message indicating invalid format

#### Scenario: Empty CSV file
- **WHEN** an empty CSV file is provided
- **THEN** no processing occurs and zero counts are returned in the response

### Requirement: JSON File Ingestion
The system SHALL allow users to ingest data from JSON files containing arrays of records.

#### Scenario: Valid JSON array
- **WHEN** a valid JSON file containing an array of structured data exists and the ingestion pipeline is invoked
- **THEN** each record is processed and upserted based on the external ID field provided in the record

#### Scenario: Malformed JSON data
- **WHEN** a JSON file with malformed data structure is provided
- **THEN** records are skipped with errors logged and processing continues for valid records

#### Scenario: Nested JSON flattening
- **WHEN** a JSON file with nested object structures is provided
- **THEN** nested fields are flattened appropriately using dot-notation for storage

### Requirement: JSONL File Ingestion
The system SHALL allow users to ingest data from JSONL (JSON Lines) files.

#### Scenario: Valid JSONL file
- **WHEN** a valid JSONL file exists and the ingestion pipeline is invoked
- **THEN** each line is parsed as a separate JSON object and processed

#### Scenario: Missing external ID in JSONL
- **WHEN** a JSONL file contains records with missing external ID fields
- **THEN** records are processed with proper handling of missing IDs and appropriate error logging

### Requirement: Upsert by External ID
The system SHALL support upsert operations based on external ID, distinguishing between created, updated, and unchanged records.

#### Scenario: New external IDs
- **WHEN** a batch of records contains new external IDs that do not exist in the system
- **THEN** new records are created for each unique external ID

#### Scenario: Existing external IDs
- **WHEN** a batch of records contains external IDs that already exist in the system
- **THEN** existing records are updated with the new data

#### Scenario: Mixed new and existing IDs
- **WHEN** a batch of records includes both new and existing external IDs
- **THEN** new records are created and existing records are updated as expected

#### Scenario: Duplicate external IDs in batch
- **WHEN** a batch of records contains duplicate external IDs
- **THEN** records are properly upserted with accurate counts for created, updated, and unchanged records

#### Scenario: Unchanged records
- **WHEN** a record with an existing external ID has identical data to the existing record
- **THEN** the record is counted as unchanged and not modified

### Requirement: Batch Size Limits
The system SHALL enforce maximum batch size limits to prevent memory issues.

#### Scenario: Exceeding max row count
- **WHEN** a CSV file exceeding the maximum allowed row count is provided
- **THEN** processing fails gracefully with an appropriate error message indicating the row limit was exceeded
