# Hippo API Reference

REST API reference for the Hippo metadata tracking service.

> 🚧 This section is under development. See [API Layer design spec](../design/sec4_api_layer.md) for API design documentation.

## SDK Validation API

### ValidationResult

The `ValidationResult` dataclass represents the outcome of a validation operation.

```python
from hippo.core.validation import ValidationResult
```

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `is_valid` | `bool` | Whether validation passed (`True`) or failed (`False`) |
| `errors` | `list[str]` | List of error messages if validation failed |
| `entity_id` | `str \| None` | Optional entity ID for context |

**Example:**

```python
result = ValidationResult(
    is_valid=False,
    errors=["Field 'name' is required"],
    entity_id="entity-123"
)
```

### SchemaValidator

The `SchemaValidator` validates write operations against defined schema configurations.

```python
from hippo.core.validation import SchemaValidator, SchemaValidationConfig
from hippo.config.models import SchemaConfig, FieldDefinition
```

**Usage Example:**

```python
# Define a schema
schema = SchemaConfig(
    name="Sample",
    version="1.0",
    fields=[
        FieldDefinition(name="id", type="string", required=True),
        FieldDefinition(name="name", type="string", required=True),
        FieldDefinition(
            name="status",
            type="enum",
            references={"values": ["active", "archived"]}
        ),
    ]
)

# Create validation config
config = SchemaValidationConfig(
    schemas={"Sample": schema},
    entity_exists_fn=lambda et, eid: True  # Optional: check entity exists
)

# Validate an operation
validator = SchemaValidator(config)
operation = WriteOperation(
    operation="insert",
    entity_type="Sample",
    data={"id": "123", "name": "Test"}
)
result = validator.validate(operation)

if not result.is_valid:
    print(f"Validation failed: {result.errors}")
```

**Error Message Patterns:**

| Scenario | Error Message Format |
|----------|---------------------|
| Required field missing | `Field 'fieldName' is required` |
| Invalid string type | `Expected string type for field 'fieldName'` |
| Invalid number type | `Expected integer/number type for field 'fieldName'` |
| Invalid boolean type | `Expected boolean type for field 'fieldName'` |
| Invalid timestamp | `Expected ISO 8601 timestamp format for field 'fieldName'` |
| Invalid enum value | `Invalid enum value 'value' for field 'fieldName'. Expected one of [values]` |
| Non-existent reference | `Reference to non-existent entity 'entityType' with ID 'entityId'` |
| Nested reference | `Reference to non-existent entity 'entityType' in field 'nested.field'` |

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
