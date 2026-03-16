## ADDED Requirements

### Requirement: EntityStore ABC defines create method signature
The EntityStore abstract base class SHALL define an abstract `create` method with the signature `create(self, entity: T) -> T` where T is a type parameter bounded by Entity. The method MUST accept an entity instance and return the created entity with any generated identifiers populated.

#### Scenario: Create method accepts entity and returns populated entity
- **WHEN** a developer implements the EntityStore ABC and calls create with an entity instance
- **THEN** the method accepts the entity as a parameter and returns the entity with any auto-generated fields (e.g., id, created_at) populated

#### Scenario: Create method enforces entity type
- **WHEN** a concrete adapter extends EntityStore with a type parameter
- **THEN** the create method MUST only accept entities of the specified type T

### Requirement: EntityStore ABC defines read method signature
The EntityStore abstract base class SHALL define an abstract `read` method with the signature `read(self, entity_id: str) -> Optional[T]`. The method MUST accept an entity ID and return the entity if found, or None if not found.

#### Scenario: Read method returns entity by ID
- **WHEN** a developer calls read with a valid entity ID
- **THEN** the method returns the entity instance with all fields populated

#### Scenario: Read method returns None for non-existent entity
- **WHEN** a developer calls read with an ID that does not exist
- **THEN** the method returns None

### Requirement: EntityStore ABC defines update method signature
The EntityStore abstract base class SHALL define an abstract `update` method with the signature `update(self, entity: T) -> T`. The method MUST accept an entity with an existing ID and return the updated entity.

#### Scenario: Update method modifies existing entity
- **WHEN** a developer calls update with an entity that has a valid ID
- **THEN** the method updates the stored entity and returns the updated entity with updated timestamps

#### Scenario: Update method requires existing entity
- **WHEN** a developer calls update with an entity that has no existing ID
- **THEN** the method MUST raise an exception indicating the entity does not exist

### Requirement: EntityStore ABC defines delete method signature
The EntityStore abstract base class SHALL define an abstract `delete` method with the signature `delete(self, entity_id: str) -> bool`. The method MUST accept an entity ID and return True if deletion succeeded, False if the entity did not exist.

#### Scenario: Delete method removes entity
- **WHEN** a developer calls delete with a valid entity ID
- **THEN** the method removes the entity and returns True

#### Scenario: Delete method handles non-existent entity
- **WHEN** a developer calls delete with an ID that does not exist
- **THEN** the method returns False
