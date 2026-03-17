## 1. CLI Infrastructure

- [x] 1.1 Add CLI command group for 'hippo reference' with install and list subcommands
- [x] 1.2 Add CLI command for 'hippo ingest' 
- [x] 1.3 Create base CLI error handling for user-friendly messages

## 2. Reference Loader Management

- [x] 2.1 Implement reference loader discovery via entry points (`hippo.reference_loaders`)
- [x] 2.2 Create references directory management (create if not exists)
- [x] 2.3 Implement `hippo reference install <package>` command
- [x] 2.4 Implement package download and installation logic
- [x] 2.5 Implement `hippo reference list` command with package info display
- [x] 2.6 Add error handling for non-existent packages

## 3. Data Ingestion

- [x] 3.1 Create data source configuration schema (YAML/JSON)
- [x] 3.2 Implement configuration file loading
- [x] 3.3 Add validation for configured data sources
- [x] 3.4 Implement `hippo ingest` command to process sources
- [x] 3.5 Create ingestion pipeline framework
- [x] 3.6 Add error handling for no configured sources

## 4. Integration Tests

- [x] 4.1 Add CLI tests for reference install with valid package
- [x] 4.2 Add CLI tests for reference install with invalid package
- [x] 4.3 Add CLI tests for reference list with installed loaders
- [x] 4.4 Add CLI tests for reference list with no loaders
- [x] 4.5 Add CLI tests for ingest with configured sources
- [x] 4.6 Add CLI tests for ingest with no configured sources
