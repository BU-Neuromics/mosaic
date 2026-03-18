# Hippo API Reference

## SDK Validation API

Validation runs automatically when you call `create`, `update`, or `delete` on `HippoClient`. The pipeline executes registered validators in order and raises `ValidationFailure` on the first failure. You do not need to call validators directly unless you are building custom validation logic.

### ValidationPipeline

The `ValidationPipeline` class provides sequential execution of validators with fail-fast behavior.

```python
from hippo.core.pipeline import ValidationPipeline, create_pipeline
from hippo.core.validation import WriteOperation, WriteValidator, ValidationResult
```

**Core Methods:**

| Method | Description |
|--------|-------------|
| `add_validator(validator)` | Register a validator to the pipeline |
| `execute(operation)` | Execute validators in fail-fast mode (stop on first failure) |
| `execute_all(operation)` | Execute all validators and report all failures |
| `get_validators()` | Get list of registered validators in order |
| `get_validator_count()` | Get number of registered validators |
| `clear_validators()` | Clear all registered validators |

**Usage Example:**

```python
# Create a pipeline
pipeline = ValidationPipeline()

# Add validators
class RequiredFieldsValidator(WriteValidator):
    def validate(self, operation: WriteOperation) -> ValidationResult:
        if not operation.data.get("name"):
            return ValidationResult(is_valid=False, errors=["name is required"])
        return ValidationResult(is_valid=True)

class UniqueIdValidator(WriteValidator):
    def validate(self, operation: WriteOperation) -> ValidationResult:
        # Check for duplicate IDs
        return ValidationResult(is_valid=True)

pipeline.add_validator(RequiredFieldsValidator())
pipeline.add_validator(UniqueIdValidator())

# Validate an operation (fail-fast)
operation = WriteOperation(
    operation="insert",
    entity_type="Sample",
    data={"id": "123", "name": "Test"}
)
result = pipeline.execute(operation)

# Validate all (report all failures)
result = pipeline.execute_all(operation)
```

**Fail-Fast Behavior:**
- `execute()` stops on first validation failure and returns immediately
- `execute_all()` runs all validators and aggregates all errors

### HippoClient

The main SDK client for Hippo with integrated validation pipeline support.

```python
from hippo import HippoClient
```

**Constructor:**

```python
client = HippoClient(
    pipeline=None,           # Optional ValidationPipeline instance
    bypass_validation=False  # DEPRECATED: Skip validation
)
```

**Methods:**

| Method | Description |
|--------|-------------|
| `validate(operation)` | Validate a write operation using the pipeline |
| `add_validator(validator)` | Add a validator to the client's pipeline |
| `create(entity_type, data, bypass_validation=None)` | Create an entity with validation |
| `update(entity_type, entity_id, data, bypass_validation=None)` | Update an entity with validation |
| `delete(entity_type, entity_id, bypass_validation=None)` | Delete an entity with validation |

**Usage Example:**

```python
from hippo import HippoClient
from hippo.core.pipeline import ValidationPipeline
from hippo.core.validation import WriteOperation, WriteValidator, ValidationResult

# Create a client with a pipeline
pipeline = ValidationPipeline()
pipeline.add_validator(MyCustomValidator())
client = HippoClient(pipeline=pipeline)

# Create an entity (validation runs automatically)
try:
    entity = client.create("Sample", {"id": "123", "name": "Test"})
except ValidationFailure as e:
    print(f"Validation failed: {e.format_detailed_message()}")

# Update an entity
entity = client.update("Sample", "123", {"name": "Updated"})

# Delete an entity
client.delete("Sample", "123")
```

### ValidationFailure

Exception raised when a write operation fails validation.

```python
from hippo.core.exceptions import ValidationFailure
```

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `message` | `str` | Error message |
| `rule_id` | `str \| None` | Identifier of the validation rule that failed |
| `input_context` | `dict` | Input data that caused the failure |
| `entity_type` | `str \| None` | Type of entity being validated |
| `entity_id` | `str \| None` | ID of entity being validated |

**Methods:**

| Method | Description |
|--------|-------------|
| `format_detailed_message()` | Returns formatted string with all failure details |

**Usage Example:**

```python
from hippo.core.exceptions import ValidationFailure

try:
    client.create("Sample", {"id": "123"})
except ValidationFailure as e:
    print(f"Rule: {e.rule_id}")
    print(f"Message: {e.message}")
    print(f"Context: {e.input_context}")
    print(f"Detailed: {e.format_detailed_message()}")
```

### RelationshipManager

The `RelationshipManager` class provides methods for managing relationships between entities.

```python
from hippo.core import RelationshipManager
```

**Constructor:**

```python
manager = RelationshipManager(
    storage=sqlite_adapter,  # Optional: SQLiteAdapter instance
    user_context="user-123"   # Optional: User ID for audit
)
```

**Access via HippoClient:**

```python
from hippo import HippoClient

client = HippoClient(storage=sqlite_adapter)
manager = client.relationships
```

**Methods:**

| Method | Description |
|--------|-------------|
| `relate(source_id, target_id, relationship_type, metadata=None)` | Create a relationship between two entities |
| `unrelate(source_id, target_id, relationship_type)` | Remove a relationship between entities |
| `traverse(source_id, relationship_type=None, max_depth=10)` | Traverse relationships from a starting entity |
| `find_relationships(source_id=None, target_id=None, relationship_type=None)` | Find relationships matching criteria |

**relate()**

Creates a relationship between two entities.

```python
result = client.relationships.relate(
    source_id="entity-1",
    target_id="entity-2",
    relationship_type="contains",
    metadata={"note": "Primary container"}
)
```

**unrelate()**

Removes a relationship between entities.

```python
client.relationships.unrelate(
    source_id="entity-1",
    target_id="entity-2",
    relationship_type="contains"
)
```

**traverse()**

Traverses relationships from a starting entity using recursive query.

```python
results = client.relationships.traverse(
    source_id="entity-1",
    relationship_type="contains",  # Optional: filter by type
    max_depth=5                     # Optional: limit depth (default: 10, max: 100)
)
```

**Exceptions:**

| Exception | Description |
|-----------|-------------|
| `EntityNotFoundError` | Source or target entity doesn't exist |
| `RelationshipExistsError` | Relationship already exists (if duplicate check needed) |
| `RelationshipNotFoundError` | Relationship doesn't exist when trying to remove |

## Error Handling

All Hippo SDK exceptions inherit from `HippoError`. Catch the base class to handle any SDK error, or catch specific subclasses for finer-grained control.

**Exception Hierarchy:**

| Exception | Parent | Description |
|-----------|--------|-------------|
| `HippoError` | `Exception` | Base class for all Hippo SDK errors |
| `ConfigError` | `HippoError` | Configuration loading and validation errors |
| `SchemaError` | `HippoError` | Schema parsing and processing errors |
| `ValidationError` | `HippoError` | Internal data validation errors |
| `EntityNotFoundError` | `HippoError` | Entity not found in the system |
| `AdapterError` | `HippoError` | Storage or external adapter errors |
| `ValidationFailure` | `HippoError` | Write operation failed validation pipeline |

**Example:**

```python
from hippo import HippoClient
from hippo.core.exceptions import HippoError, EntityNotFoundError, ValidationFailure

client = HippoClient()

# Catch any SDK error
try:
    entity = client.get("Sample", "sample-123")
except HippoError as e:
    print(f"Hippo error: {e.message}")

# Catch specific errors
try:
    entity = client.get("Sample", "sample-123")
except EntityNotFoundError as e:
    print(f"Entity not found: {e.entity_type} / {e.entity_id}")

try:
    client.create("Sample", {"id": "123"})
except ValidationFailure as e:
    print(f"Validation failed: {e.format_detailed_message()}")
    print(f"  Rule:    {e.rule_id}")
    print(f"  Context: {e.input_context}")
```

## REST API

All REST endpoints (except health checks) require authentication via Bearer token header:

```
Authorization: Bearer <token>
```

Requests missing this header or using an invalid format receive a `401 Unauthorized` response.

### Health

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Service health check |
| GET | `/` | API root with version info |

**GET /health**

Returns health status of the service.

*Response:*
```json
{
  "status": "healthy",
  "service": "hippo"
}
```

**GET /**

Returns API information.

*Response:*
```json
{
  "service": "Hippo API",
  "version": "0.1.0",
  "docs": "/docs"
}
```

*Error Codes: None (unauthenticated)*

---

### Entities

| Method | Path | Description |
|--------|------|-------------|
| GET | `/entities` | List entities with filtering |
| GET | `/entities/{entity_id}` | Get entity by ID |
| DELETE | `/entities/{entity_id}` | Soft delete an entity |

**GET /entities**

List entities with optional filtering and pagination.

*Query Parameters:*
| Parameter | Type | Description |
|-----------|------|-------------|
| `entity_type` | string | Filter by entity type |
| `limit` | int | Max results (1-1000, default: 100) |
| `offset` | int | Results to skip (default: 0) |

*Response:*
```json
{
  "items": [],
  "total": 0,
  "limit": 100,
  "offset": 0
}
```

**GET /entities/{entity_id}**

Get an entity by ID.

*Path Parameters:*
| Parameter | Type | Description |
|-----------|------|-------------|
| `entity_id` | string | Entity ID |

*Query Parameters:*
| Parameter | Type | Description |
|-----------|------|-------------|
| `expand` | string | Expand path for related entities |

*Response:* Entity object with all fields

*Error Codes:* `404` - Entity not found

**DELETE /entities/{entity_id}**

Soft delete an entity (sets `is_available` to false).

*Path Parameters:*
| Parameter | Type | Description |
|-----------|------|-------------|
| `entity_id` | string | Entity ID |

*Response:*
```json
{
  "status": "deleted",
  "entity_id": "entity-123"
}
```

*Error Codes:* `404` - Entity not found

---

### Search

| Method | Path | Description |
|--------|------|-------------|
| GET | `/search` | Full-text search of entities |

**GET /search**

Search entities using full-text search.

*Query Parameters:*
| Parameter | Type | Description |
|-----------|------|-------------|
| `entity_type` | string | Entity type to search (required) |
| `q` | string | Search query string (required) |
| `limit` | int | Max results (1-1000, default: 100) |
| `offset` | int | Results to skip (default: 0) |

*Response:* Array of matching entities

---

### History

| Method | Path | Description |
|--------|------|-------------|
| GET | `/entities/{entity_id}/history` | Get entity change history |

**GET /entities/{entity_id}/history**

Get the change history/provenance log for an entity.

*Path Parameters:*
| Parameter | Type | Description |
|-----------|------|-------------|
| `entity_id` | string | Entity ID |

*Response:* Array of history records with timestamps and changes

*Error Codes:* `404` - Entity not found

---

### Relationships

| Method | Path | Description |
|--------|------|-------------|
| GET | `/entities/{entity_id}/relationships` | List entity relationships |
| POST | `/entities/{entity_id}/relationships` | Create a relationship |
| DELETE | `/entities/{entity_id}/relationships/{rel_id}` | Delete a relationship |

**GET /entities/{entity_id}/relationships**

Get all relationships for an entity.

*Path Parameters:*
| Parameter | Type | Description |
|-----------|------|-------------|
| `entity_id` | string | Entity ID |

*Response:* Array of relationship objects

*Error Codes:* `404` - Entity not found

**POST /entities/{entity_id}/relationships**

Create a relationship between two entities.

*Path Parameters:*
| Parameter | Type | Description |
|-----------|------|-------------|
| `entity_id` | string | Source entity ID |

*Request Body:*
```json
{
  "target_entity_id": "entity-456",
  "relationship_type": "contains"
}
```

*Response:*
```json
{
  "id": "entity-123->entity-456:contains",
  "source_entity_id": "entity-123",
  "target_entity_id": "entity-456",
  "relationship_type": "contains"
}
```

*Error Codes:* `404` - Source or target entity not found

**DELETE /entities/{entity_id}/relationships/{rel_id}**

Delete a relationship by its ID.

*Path Parameters:*
| Parameter | Type | Description |
|-----------|------|-------------|
| `entity_id` | string | Source entity ID |
| `rel_id` | string | Relationship ID (e.g. `entity-123->entity-456:contains`) |

*Response:*
```json
{
  "status": "deleted",
  "relationship_id": "entity-123->entity-456:contains"
}
```

---

### Ingest

| Method | Path | Description |
|--------|------|-------------|
| POST | `/ingest` | Create a new entity |

**POST /ingest**

Create a new entity via the ingestion endpoint.

*Request Body:*
```json
{
  "entity_type": "Sample",
  "data": {
    "id": "sample-123",
    "name": "Test Sample",
    "status": "active"
  }
}
```

*Response:* Created entity with generated ID and timestamps

*Error Codes:*
- `400` - Invalid JSON format
- `422` - Missing required fields or validation failure

---

### Schemas

| Method | Path | Description |
|--------|------|-------------|
| GET | `/schemas` | List all schemas |
| GET | `/schemas/{name}` | Get schema by name |
| POST | `/schemas` | Create a new schema |

**GET /schemas**

List all available entity schemas.

*Response:* Array of schema definitions

**GET /schemas/{name}**

Get a schema by name.

*Path Parameters:*
| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Schema name |

*Response:* Schema definition with fields

*Error Codes:* `404` - Schema not found

**POST /schemas**

Create a new schema.

*Request Body:*
```json
{
  "name": "Sample",
  "version": "1.0",
  "fields": [
    {"name": "id", "field_type": "string", "required": true},
    {"name": "name", "field_type": "string", "required": true}
  ]
}
```

*Response:*
```json
{
  "name": "Sample",
  "version": "1.0",
  "status": "created"
}
```

---

### Supersession

| Method | Path | Description |
|--------|------|-------------|
| POST | `/entities/{entity_id}/supersede` | Supersede an entity's external ID |
| GET | `/entities/{entity_id}/superseded` | Get superseded external IDs |

**POST /entities/{entity_id}/supersede**

Supersede an entity's external ID with a new one.

*Path Parameters:*
| Parameter | Type | Description |
|-----------|------|-------------|
| `entity_id` | string | Entity ID |

*Request Body:*
```json
{
  "old_external_id": "EXT-001",
  "new_external_id": "EXT-002"
}
```

*Response:* New external ID record

*Error Codes:* `404` - Entity not found

**GET /entities/{entity_id}/superseded**

Get superseded external IDs for an entity.

*Path Parameters:*
| Parameter | Type | Description |
|-----------|------|-------------|
| `entity_id` | string | Entity ID |

*Response:* Array of superseded external ID records

*Error Codes:* `404` - Entity not found

---

### External IDs

| Method | Path | Description |
|--------|------|-------------|
| GET | `/external-ids/{id_type}/{external_id}` | Get entity by external ID |
| GET | `/entities/{entity_id}/external-ids` | List entity's external IDs |
| POST | `/entities/{entity_id}/external-ids` | Register external ID |

**GET /external-ids/{id_type}/{external_id}**

Get an entity by its external ID.

*Path Parameters:*
| Parameter | Type | Description |
|-----------|------|-------------|
| `id_type` | string | External ID type (e.g., "lims", "barcode") |
| `external_id` | string | External ID value |

*Response:* Entity object

*Error Codes:* `404` - Entity not found

**GET /entities/{entity_id}/external-ids**

List all external IDs for an entity.

*Path Parameters:*
| Parameter | Type | Description |
|-----------|------|-------------|
| `entity_id` | string | Entity ID |

*Query Parameters:*
| Parameter | Type | Description |
|-----------|------|-------------|
| `include_superseded` | bool | Include superseded IDs (default: false) |

*Response:* Array of external ID records

*Error Codes:* `404` - Entity not found

**POST /entities/{entity_id}/external-ids**

Register an external ID for an entity.

*Path Parameters:*
| Parameter | Type | Description |
|-----------|------|-------------|
| `entity_id` | string | Entity ID |

*Request Body:*
```json
{
  "external_id": "LIMS-12345"
}
```

*Response:* Created external ID record

*Error Codes:* `404` - Entity not found

---

### Availability

| Method | Path | Description |
|--------|------|-------------|
| GET | `/entities/{entity_id}/availability` | Get entity availability status |
| POST | `/entities/{entity_id}/availability` | Set entity availability status |

**GET /entities/{entity_id}/availability**

Get the availability status of an entity.

*Path Parameters:*
| Parameter | Type | Description |
|-----------|------|-------------|
| `entity_id` | string | Entity ID |

*Response:*
```json
{
  "entity_id": "entity-123",
  "is_available": true
}
```

*Error Codes:* `404` - Entity not found

**POST /entities/{entity_id}/availability**

Set the availability status of an entity.

*Path Parameters:*
| Parameter | Type | Description |
|-----------|------|-------------|
| `entity_id` | string | Entity ID |

*Request Body:*
```json
{
  "is_available": false
}
```

*Response:*
```json
{
  "entity_id": "entity-123",
  "is_available": false
}
```

*Error Codes:* `404` - Entity not found

---

### Error Codes Summary

| Code | Description |
|------|-------------|
| `400` | Bad Request - Invalid JSON format |
| `401` | Unauthorized - Missing or invalid Bearer token |
| `404` | Not Found - Entity/Schema not found |
| `422` | Unprocessable Entity - Validation failed |
| `500` | Internal Server Error |
