## 1. CLI Infrastructure

- [ ] 1.1 Add CLI command group for 'hippo reference' with install and list subcommands
- [ ] 1.2 Add CLI command for 'hippo ingest' 
- [ ] 1.3 Create base CLI error handling for user-friendly messages

## 2. Reference Loader Management

- [ ] 2.1 Implement reference loader discovery via entry points (`hippo.reference_loaders`)
- [ ] 2.2 Create references directory management (create if not exists)
- [ ] 2.3 Implement `hippo reference install <package>` command
- [ ] 2.4 Implement package download and installation logic
- [ ] 2.5 Implement `hippo reference list` command with package info display
- [ ] 2.6 Add error handling for non-existent packages

## 3. Data Ingestion

- [ ] 3.1 Create data source configuration schema (YAML/JSON)
- [ ] 3.2 Implement configuration file loading
- [ ] 3.3 Add validation for configured data sources
- [ ] 3.4 Implement `hippo ingest` command to process sources
- [ ] 3.5 Create ingestion pipeline framework
- [ ] 3.6 Add error handling for no configured sources

## 4. Integration Tests

- [ ] 4.1 Add CLI tests for reference install with valid package
- [ ] 4.2 Add CLI tests for reference install with invalid package
- [ ] 4.3 Add CLI tests for reference list with installed loaders
- [ ] 4.4 Add CLI tests for reference list with no loaders
- [ ] 4.5 Add CLI tests for ingest with configured sources
- [ ] 4.6 Add CLI tests for ingest with no configured sources
