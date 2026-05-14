# Hippo — Metadata Tracking Service

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-634%20passing-green.svg)](https://github.com/anomalyco/hippo)

SDK-first, infrastructure-agnostic metadata tracking service for bioinformatics research.

## Table of Contents

- [Quick Start](#quick-start)
- [Documentation](#documentation)
- [Features](#features)
- [Validation Pipeline](#validation-pipeline)
- [Entity Relationships](#entity-relationships)
- [Development](#development)

## Quick Start

```bash
# Install Hippo
pip install hippo

# Initialize a new Hippo project (creates hippo.yaml + schema.yaml)
hippo init

# Apply schema migrations to your database
hippo migrate

# Start the REST API server (default: http://127.0.0.1:8000)
hippo serve

# Use the SDK
python -c "
from hippo import HippoClient

client = HippoClient()
sample = client.put('Sample', {'id': 'S001', 'name': 'Test Sample'})
print(f'Created: {sample[\"id\"]}')
"
```

## Documentation

| Guide | Description |
|-------|-------------|
| [Installation](docs/installation.md) | Installing Hippo and dependencies |
| [Quick Start](docs/quickstart.md) | Get up and running fast |
| [Configuration](docs/configuration.md) | Configuring Hippo for your project |
| [CLI Reference](docs/cli-reference.md) | Command-line interface documentation |
| [Data Model](docs/data-model.md) | Entity types, fields, and relationships |
| [API Reference](docs/api-reference.md) | Complete SDK and REST API docs |

## Features

- **Schema-driven entities** — Define entity types and fields in YAML/JSON
- **Validation pipeline** — Custom validators for data integrity
- **REST API** — HTTP endpoints for all operations
- **FTS full-text search** — Fast text search across entities
- **Relationship graph** — Typed relationships with traversal
- **Provenance/history** — Full audit trail of all changes
- **Availability management** — Soft deletes via `is_available` flag
- **External IDs** — Map to external systems (STARLIMS, HALO, Donor DB)
- **Schema diff/migration** — Version-controlled schema changes

## Validation Pipeline

Hippo validates all write operations against a LinkML schema. Two paths:

- **CLI** — `hippo validate` checks a schema file and/or an instance data bundle.
- **SDK** — custom `WriteValidator` subclasses run before every `client.put()`.

### Schema and Data Validation (CLI)

Schemas are standard [LinkML](https://linkml.io/) YAML files. Here is a minimal example:

```yaml
# schema.yaml
id: https://example.org/my-schema
name: my_schema
prefixes:
  linkml: https://w3id.org/linkml/
imports:
  - linkml:types
default_range: string

classes:
  Sample:
    attributes:
      sample_id:
        range: string
        required: true
        identifier: true
      name:
        range: string
        required: true
      collection_date:
        range: date
```

Instance data uses a **tree-root bundle** format — a YAML mapping whose top-level keys are the pluralized class names and whose values are lists of instances:

```yaml
# bundle.yaml
samples:
  - id: S001
    sample_id: SMPL-001
    name: Test Sample
    collection_date: "2024-03-15"
```

Validate the schema alone, or the schema together with a data bundle:

```bash
# Validate a LinkML schema file — exits non-zero on any LinkML error
hippo validate --schema schema.yaml

# Validate a data bundle against the schema
hippo validate --schema schema.yaml --data bundle.yaml
```

Pass `--validate-schema` to `hippo ingest` to validate the bundle before writing:

```bash
hippo ingest --file bundle.yaml --validate-schema schema.yaml
```

### Custom Write Validators (SDK)

Add application-level rules via `WriteValidator` subclasses. These run in the validation pipeline before every `client.put()`:

```python
from hippo import HippoClient, ValidationPipeline
from hippo.core.validation import WriteOperation, WriteValidator, ValidationResult

class RequiredFieldsValidator(WriteValidator):
    def validate(self, operation: WriteOperation) -> ValidationResult:
        if not operation.data.get("name"):
            return ValidationResult(is_valid=False, errors=["name is required"])
        return ValidationResult(is_valid=True)

pipeline = ValidationPipeline()
pipeline.add_validator(RequiredFieldsValidator())

client = HippoClient(pipeline=pipeline)

try:
    entity = client.put("Sample", {"id": "S001", "name": "Test"})
except ValidationFailure as e:
    print(f"Validation failed: {e.errors}")
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
