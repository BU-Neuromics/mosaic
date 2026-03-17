## ADDED Requirements

### Requirement: EntityStore ABC defines find method signature
The EntityStore abstract base class SHALL define an abstract `find` method with the signature `find(self, query: Query) -> Iterator[T]` where T is the entity type. The method MUST accept a Query object and return an iterator of matching entities.

#### Scenario: Find method accepts Query and returns iterator
- **WHEN** a developer implements the EntityStore ABC and calls find with a Query object
- **THEN** the method returns an Iterator of entities matching the query criteria

#### Scenario: Find method returns empty iterator for no matches
- **WHEN** a developer calls find with a Query that matches no entities
- **THEN** the method returns an empty Iterator

### Requirement: EntityStore ABC defines findAll method signature
The EntityStore abstract base class SHALL define an abstract `findAll` method with the signature `findAll(self) -> Iterator[T]`. The method MUST return an iterator of all entities of type T without any filtering.

#### Scenario: findAll returns all entities
- **WHEN** a developer calls findAll on an EntityStore implementation
- **THEN** the method returns an Iterator containing all entities of type T

#### Scenario: findAll returns empty iterator when no entities exist
- **WHEN** a developer calls findAll when no entities exist
- **THEN** the method returns an empty Iterator

### Requirement: EntityStore ABC defines findBy method signature
The EntityStore abstract base class SHALL define an abstract `findBy` method with the signature `findBy(self, **kwargs) -> Iterator[T]`. The method MUST accept keyword arguments representing field names and values to filter by, and return an iterator of matching entities.

#### Scenario: findBy filters by single field
- **WHEN** a developer calls findBy with a single keyword argument (e.g., findBy(name="test"))
- **THEN** the method returns an Iterator of entities where the specified field matches the value

#### Scenario: findBy filters by multiple fields
- **WHEN** a developer calls findBy with multiple keyword arguments (e.g., findBy(status="active", type="sample"))
- **THEN** the method returns an Iterator of entities matching ALL specified criteria (AND logic)

#### Scenario: findBy returns empty iterator for no matches
- **WHEN** a developer calls findBy with criteria that match no entities
- **THEN** the method returns an empty Iterator
