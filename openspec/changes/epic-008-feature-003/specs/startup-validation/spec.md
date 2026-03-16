## ADDED Requirements

### Requirement: Startup validates schema search modes against adapter capabilities
Hippo SHALL validate at startup that all search modes declared in the schema are supported by the active adapter.

#### Scenario: Schema with supported search mode succeeds
- **GIVEN** the SQLite adapter is active
- **AND** a schema declares a field with `search: fts`
- **WHEN** HippoClient initializes
- **THEN** startup SHALL succeed with no error
- **AND** the client SHALL be ready to serve requests

#### Scenario: Schema with unsupported search mode fails
- **GIVEN** the SQLite adapter is active
- **AND** a schema declares a field with `search: embedding`
- **WHEN** HippoClient initializes
- **THEN** a `SearchCapabilityError` SHALL be raised
- **AND** the error SHALL be raised before any requests are served
- **AND** the error message SHALL indicate the unsupported search mode

#### Scenario: Inactive adapter with schema search mode
- **GIVEN** the SQLite adapter is inactive (not configured)
- **AND** a schema declares a field with `search: fts`
- **WHEN** HippoClient initializes
- **THEN** startup SHALL succeed with no error

#### Scenario: Inactive adapter with unsupported search mode
- **GIVEN** the SQLite adapter is inactive (not configured)
- **AND** a schema declares a field with `search: embedding`
- **WHEN** HippoClient initializes
- **THEN** no error SHALL be raised during startup

#### Scenario: Validation compares normalized search mode
- **GIVEN** the SQLite adapter is active
- **AND** a schema declares a field with `search: fts5`
- **WHEN** HippoClient initializes
- **THEN** startup SHALL succeed (fts5 normalizes to fts)
- **AND** the adapter's `search_capabilities()` return value of `'fts'` SHALL match
