## 1. Infrastructure & Utilities

- [x] 1.1 Add max_batch_size and flatten_nested configuration to SchemaConfig
- [x] 1.2 Implement flatten_dict() utility for nested JSON flattening (1 level, dot-notation)
- [x] 1.3 Implement parse_csv_with_errors() for error-tolerant CSV parsing

## 2. CSV Ingestion

- [x] 2.1 Add ingest_csv(file_path, entity_type) method to IngestionPipeline
- [x] 2.2 Implement header validation (fail if no headers)
- [x] 2.3 Implement row parsing with error collection for malformed rows
- [x] 2.4 Implement empty file handling (return zero counts)
- [x] 2.5 Implement batch size limit check

## 3. JSON Ingestion

- [x] 3.1 Add ingest_json(file_path, entity_type) method to IngestionPipeline
- [x] 3.2 Implement JSON array parsing with error collection
- [x] 3.3 Implement nested JSON flattening using flatten_dict()
- [x] 3.4 Implement malformed JSON error handling (skip and continue)

## 4. JSONL Ingestion

- [x] 4.1 Add ingest_jsonl(file_path, entity_type) method to IngestionPipeline
- [x] 4.2 Implement JSONL line-by-line parsing
- [x] 4.3 Implement missing external ID error handling

## 5. Upsert Logic

- [x] 5.1 Implement ExternalID-based upsert in QueryEngine or IngestionPipeline
- [x] 5.2 Track created count (new ExternalID)
- [x] 5.3 Track updated count (existing ExternalID with changed data)
- [x] 5.4 Track unchanged count (existing ExternalID with identical data)
- [x] 5.5 Handle duplicate ExternalIDs within same batch

## 6. Error Handling & Testing

- [x] 6.1 Add comprehensive error messages for all failure modes
- [x] 6.2 Add unit tests for flatten_dict() utility
- [x] 6.3 Add unit tests for CSV parsing with malformed rows
- [x] 6.4 Add unit tests for JSON/JSONL parsing
- [x] 6.5 Add integration tests for upsert scenarios
- [x] 6.6 Add tests for batch size limit enforcement
