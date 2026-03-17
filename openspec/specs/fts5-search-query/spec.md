# fts5-search-query Specification

## Purpose
TBD - created by archiving change epic-008-feature-002. Update Purpose after archive.
## Requirements
### Requirement: FTS5 search returns matching entities with scores
Given an entity with a fts-indexed field containing "prefrontal cortex", when client.search() is called with query "prefrontal", then the entity appears in results with score greater than 0.0.

#### Scenario: Search finds entity by partial term match
- **WHEN** an entity exists with an FTS-indexed field containing "prefrontal cortex"
- **AND** client.search() is called with query "prefrontal"
- **THEN** the entity MUST appear in the results with a score greater than 0.0

#### Scenario: Search is case-insensitive
- **WHEN** an entity exists with an FTS-indexed field containing "Analysis Results"
- **AND** client.search() is called with query "ANALYSIS"
- **THEN** the entity MUST appear in the results

### Requirement: Search results ordered by relevance score descending
Given multiple entities matching a query, when client.search() returns results, then they are ordered by score descending with score values between 0.0 and 1.0.

#### Scenario: Higher scored entity appears first
- **WHEN** entity A has 5 occurrences of the search term
- **AND** entity B has 2 occurrences of the search term
- **AND** client.search() is called
- **THEN** entity A MUST appear before entity B in the results

#### Scenario: Scores normalized to 0.0-1.0 range
- **WHEN** client.search() returns results
- **THEN** all scores MUST be between 0.0 and 1.0 (inclusive)

#### Scenario: Empty results for non-matching query
- **WHEN** no entities match the search query
- **AND** client.search() is called
- **THEN** an empty list MUST be returned

### Requirement: min_score parameter filters low-relevance results
Given a min_score parameter is passed to search(), when results are returned, then no result has a score below min_score.

#### Scenario: min_score filters out low-scored entities
- **WHEN** client.search() is called with min_score=0.5
- **AND** some entities have scores below 0.5
- **THEN** only entities with score >= 0.5 MUST be returned

#### Scenario: min_score=0.0 returns all matches
- **WHEN** client.search() is called with min_score=0.0
- **THEN** all matching entities MUST be returned (same as no filter)

### Requirement: limit parameter caps result count
Given a limit parameter is passed to search(), when results are returned, then at most limit results are returned.

#### Scenario: limit restricts result count
- **WHEN** client.search() is called with limit=5
- **AND** more than 5 entities match the query
- **THEN** exactly 5 entities MUST be returned

#### Scenario: limit defaults to reasonable maximum
- **WHEN** client.search() is called without limit parameter
- **THEN** a default limit of 100 MUST be applied

#### Scenario: limit higher than matches returns all
- **WHEN** client.search() is called with limit=1000
- **AND** only 10 entities match
- **THEN** all 10 entities MUST be returned

### Requirement: SearchCapabilityError raised for non-FTS fields
Given client.search() is called on a field not declared with search fts, when the query executes, then a SearchCapabilityError is raised.

#### Scenario: Searching non-FTS field raises error
- **WHEN** client.search() is called on a field that is NOT marked with `search: fts` in the schema
- **THEN** a SearchCapabilityError MUST be raised
- **AND** the error message MUST indicate the field is not FTS-indexed

#### Scenario: Error message suggests enabling FTS
- **WHEN** SearchCapabilityError is raised for field "description"
- **THEN** the error message SHOULD suggest adding `search: fts` to the schema

### Requirement: Search requires entity type parameter
Given client.search() is called, the caller MUST specify the entity type to search.

#### Scenario: Search by entity type returns only that type
- **WHEN** client.search() is called with entity_type="Sample"
- **THEN** only entities of type Sample MUST be returned
- **AND** entities of other types MUST NOT be included

### Requirement: Search requires field parameter
Given client.search() is called, the caller MUST specify which FTS-indexed field to search.

#### Scenario: Field parameter targets specific indexed field
- **WHEN** client.search() is called with field="notes"
- **AND** the "notes" field has `search: fts` in the schema
- **THEN** the search MUST be performed on the "notes" FTS table

#### Scenario: Searching non-existent field raises error
- **WHEN** client.search() is called with a field name that does not exist on the entity type
- **THEN** an appropriate validation error MUST be raised

