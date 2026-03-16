## ADDED Requirements

### Requirement: EntityStore declares supported search modes
The EntityStore abstract base class SHALL declare a `search_capabilities()` method that returns a set of supported search mode strings.

#### Scenario: SQLite adapter returns fts capability
- **GIVEN** the SQLite adapter is active
- **WHEN** `search_capabilities()` is called on the adapter
- **THEN** it SHALL return a set containing `'fts'`

#### Scenario: Adapter returns set type
- **GIVEN** any adapter implementation
- **WHEN** `search_capabilities()` is called
- **THEN** it SHALL return a value of type `set`
- **AND** the set SHALL contain string values representing supported search modes

#### Scenario: EntityStore ABC defines search_capabilities
- **GIVEN** the EntityStore abstract base class
- **WHEN** the class is inspected
- **THEN** it SHALL define `search_capabilities()` as an abstract method
