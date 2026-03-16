# Hippo — Metadata Tracking Service

SDK-first, infrastructure-agnostic metadata tracking service for bioinformatics research.

## Design Spec

See [`design/`](design/) for the full architecture and implementation specification.
Start with [`design/INDEX.md`](design/INDEX.md).

## Implementation Plan

See [`plan/`](plan/) for the OpenPlan roadmap, epics, and features.
OpenSpec feature specs live in [`plan/openspec/`](plan/openspec/).

## Quick Start

```bash
pip install hippo

hippo init          # scaffold hippo.yaml + schema.yaml
hippo serve         # start REST server (default: http://127.0.0.1:8000)
```

## Validation Pipeline

Hippo provides a built-in validation pipeline that ensures all write operations pass through registered validators before being processed.

### Basic Setup

```python
from hippo import HippoClient, ValidationPipeline
from hippo.core.validation import WriteOperation, WriteValidator, ValidationResult

# Create a validation pipeline
pipeline = ValidationPipeline()

# Add custom validators
class RequiredFieldsValidator(WriteValidator):
    def validate(self, operation: WriteOperation) -> ValidationResult:
        if not operation.data.get("name"):
            return ValidationResult(is_valid=False, errors=["name is required"])
        return ValidationResult(is_valid=True)

pipeline.add_validator(RequiredFieldsValidator())

# Create client with pipeline
client = HippoClient(pipeline=pipeline)

# Write operations automatically validate
try:
    entity = client.create("Sample", {"id": "123", "name": "Test"})
except ValidationFailure as e:
    print(f"Validation failed: {e.format_detailed_message()}")
```

### Configuration

Validation can also be configured via YAML/JSON schema:

```yaml
# schema.yaml
name: Sample
version: "1.0"
fields:
  - name: id
    type: string
    required: true
  - name: name
    type: string
    required: true
validators:
  - name: required-fields
    type: custom
    enabled: true
    priority: 10
```

## Entity Relationships

Hippo supports managing relationships between entities through the RelationshipManager API.

### Basic Operations

```python
from hippo import HippoClient

client = HippoClient(storage=sqlite_adapter)

# Create some entities
donor = client.put("Donor", {"name": "John Doe"})
sample = client.put("Sample", {"name": "Sample 001"})

# Create a relationship
client.relationships.relate(
    source_id=donor["id"],
    target_id=sample["id"],
    relationship_type="donated",
    metadata={"collection_date": "2024-01-15"}
)

# Traverse relationships
results = client.relationships.traverse(
    source_id=donor["id"],
    relationship_type="donated",
    max_depth=5
)

# Remove a relationship
client.relationships.unrelate(
    source_id=donor["id"],
    target_id=sample["id"],
    relationship_type="donated"
)
```

### Relationship Features

- **Typed relationships**: Any string relationship type (e.g., "contains", "belongs_to", "parent_of")
- **Metadata storage**: Optional JSON metadata with each relationship
- **Graph traversal**: Recursive CTE-based traversal with depth limiting
- **Audit trail**: All operations recorded in provenance log

See [`docs/api-reference.md`](docs/api-reference.md) for complete API documentation.

## Development

```bash
uv sync --extra dev
uv run pytest
```
