# Hippo Configuration Reference

Complete reference for configuring Hippo, the Metadata Tracking Service (MTS) for the BASS platform.

## Overview

Hippo uses two primary configuration files:

1. **`hippo.yaml`** — Main application configuration that specifies the schema path and storage settings
2. **Schema files (YAML)** — Define entity types, fields, validators, and inheritance

Configuration is loaded via `load_hippo_config()` from `hippo.yaml`, and schemas are loaded via `SchemaParser` or `load_schema()`.

Environment variable substitution is supported in all YAML files using `${VAR_NAME}` or `${VAR_NAME:-default}` syntax.

---

## HippoConfig

The main configuration model for the Hippo application. Loaded from `hippo.yaml`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `schema_path` | `Path` | *(required)* | Path to the schema directory or file containing entity definitions |
| `storage_backend` | `str` | `None` | Storage backend to use (e.g., `"sqlite"`, `"postgresql"`). If `None`, uses default backend |
| `database_url` | `str` | `None` | Connection string for the database. For SQLite: `hippo.db` or absolute path |
| `validation_enabled` | `bool` | `true` | Enable validation of entity data against schema rules |
| `validation_fail_fast` | `bool` | `true` | Stop validation on first error. If `false`, collects all validation errors |
| `write_path_validation_enabled` | `bool` | `true` | Enable validation of write paths (entity location paths) |
| `write_path_validation_timeout` | `float` | `None` | Timeout in seconds for write path validation. `None` = no timeout |
| `validators_path` | `Path` | `None` | Path to custom `validators.yaml` file. If `None`, uses default location |

### Example hippo.yaml

```yaml
schema_path: ./schemas
storage_backend: sqlite
database_url: ./data/hippo.db
validation_enabled: true
validation_fail_fast: true
write_path_validation_enabled: true
validators_path: ./validators.yaml
```

---

## SchemaConfig

Defines an entity type schema. Loaded from schema YAML files in the schema directory.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | *(required)* | Unique name of the entity schema (e.g., `"Donor"`, `"Sample"`) |
| `version` | `str` | *(required)* | Schema version string (e.g., `"1.0.0"`) |
| `description` | `str` | `None` | Human-readable description of the entity |
| `fields` | `list[FieldDefinition]` | `[]` | List of field definitions for this entity |
| `base` | `str \| list[str]` | `None` | Parent schema(s) to inherit from. Single string or list for multiple inheritance |
| `metadata` | `dict[str, Any]` | `None` | Arbitrary metadata dict for documentation or custom use |
| `unique_constraints` | `list[list[str]]` | `None` | List of field combinations that must be unique. Each entry is a list of field names |
| `indexes` | `list[dict[str, Any]]` | `None` | Custom index definitions beyond field-level indexes |
| `validators` | `list[ValidatorDefinition]` | `[]` | Validators to apply to this entity type |
| `max_batch_size` | `int` | `10000` | Maximum number of entities that can be created/updated in a single batch operation |
| `flatten_nested` | `bool` | `true` | Whether to flatten nested dict/list fields in storage |

### Schema Inheritance

Schemas support inheritance via the `base` field:

```yaml
# Base schema
name: BiologicalEntity
version: "1.0.0"
fields:
  - name: id
    type: string
    primary_key: true
  - name: created_at
    type: datetime

# Child schema
name: Donor
version: "1.0.0"
base: BiologicalEntity
fields:
  - name: donor_id
    type: string
    required: true
  - name: species
    type: string
```

Multiple inheritance is supported:

```yaml
name: BrainSample
version: "1.0.0"
base:
  - Sample
  - BrainEntity
fields:
  - name: brain_region
    type: string
```

---

## FieldDefinition

Defines a single field within a schema.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | *(required)* | Field name (must be non-empty, whitespace-trimmed) |
| `type` | `str` | *(required)* | Data type. Must be one of the valid type system values |
| `required` | `bool` | `false` | Whether the field is required (non-null) |
| `description` | `str` | `None` | Human-readable description |
| `default` | `Any` | `None` | Default value if not provided |
| `primary_key` | `bool` | `false` | Whether this field is the primary key |
| `unique` | `bool` | `false` | Whether values must be unique across entities |
| `index` | `bool` | `false` | Whether to create a database index on this field |
| `index_partial` | `bool` | `false` | Create a partial index (only for non-null values) |
| `search` | `str` | `None` | Full-text search mode: `"fts"`, `"fts5"`, or `"embedding"` |
| `references` | `dict[str, Any]` | `None` | Foreign key reference to another entity type |

### Type System

Valid field types:

| Type | Description |
|------|-------------|
| `string` | Text data |
| `integer` | Integer numbers |
| `float` | Floating-point numbers |
| `boolean` | True/false values |
| `date` | Date (YYYY-MM-DD) |
| `datetime` | Date and time (ISO 8601) |
| `list` | List of values |
| `dict` | Dictionary/object (JSON) |
| `uri` | URI/URL string |
| `enum` | Enumerated value (limited set of allowed strings) |

### Search Modes

The `search` field enables full-text search indexing:

| Value | Description |
|-------|-------------|
| `fts` | SQLite FTS3 full-text search |
| `fts5` | SQLite FTS5 full-text search (recommended) |
| `embedding` | Vector embedding for semantic search |

### References (Foreign Keys)

Define relationships to other entity types:

```yaml
fields:
  - name: donor_id
    type: string
    references:
      entity: Donor
      field: donor_id
```

---

## ValidatorDefinition

Defines a validator applied to entity data. Used within `SchemaConfig.validators`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | *(required)* | Unique name for this validator |
| `type` | `str` | *(required)* | Validator type (e.g., `"cel"` for CEL expressions) |
| `enabled` | `bool` | `true` | Whether this validator is active |
| `priority` | `int` | `0` | Execution order (higher runs first). Negative for pre-schema validation |
| `config` | `dict[str, Any]` | `None` | Type-specific configuration |

### Validator Types

Validators are loaded from `validators.yaml` with the CEL (Common Expression Language) engine:

```yaml
validators:
  - name: sample_name_required
    type: cel
    enabled: true
    priority: 0
    config:
      entity_types: [Sample]
      on: [create, update]
      condition: 'entity.name != ""'
      error: "Sample {entity_id}: name is required"
```

---

## Complete Example

### hippo.yaml

```yaml
schema_path: ./schemas
storage_backend: sqlite
database_url: ./data/hippo.db
validation_enabled: true
validation_fail_fast: false
write_path_validation_enabled: true
validators_path: ./validators.yaml
```

### schemas/base.yaml — Base Entity

```yaml
name: BiologicalEntity
version: "1.0.0"
description: Base entity for all biological samples
fields:
  - name: id
    type: string
    primary_key: true
    description: Unique entity identifier
  - name: external_id
    type: string
    unique: true
    description: External system identifier
  - name: created_by
    type: string
    description: User who created this entity
  - name: created_at
    type: datetime
    description: Creation timestamp
  - name: updated_at
    type: datetime
    description: Last update timestamp
  - name: is_available
    type: boolean
    default: true
    description: Soft-delete flag (false = deleted)
unique_constraints:
  - [external_id]
```

### schemas/donor.yaml — Donor Entity

```yaml
name: Donor
version: "1.0.0"
description: Human donor information
base: BiologicalEntity
metadata:
  department: Oncology
  pi: Dr. Smith
fields:
  - name: donor_id
    type: string
    required: true
    unique: true
    index: true
    description: Internal donor identifier
  - name: species
    type: string
    required: true
    default: "Homo sapiens"
    description: Species of the donor
  - name: sex
    type: enum
    required: true
    description: Biological sex
  - name: date_of_birth
    type: date
    description: Date of birth
  - name: ethnicity
    type: string
    description: Ethnicity information
  - name: consent_obtained
    type: boolean
    default: false
    description: Whether donor consent is on file
  - name: consent_date
    type: date
    description: Date consent was obtained
  - name: diagnosis
    type: list
    description: List of diagnoses
  - name: demographics
    type: dict
    description: Additional demographic data
  - name: medical_record_number
    type: string
    index: true
    description: Hospital MRN
  - name: notes
    type: string
    search: fts5
    description: Free-text notes for searching
validators:
  - name: donor_id_required
    type: cel
    enabled: true
    priority: 10
    config:
      entity_types: [Donor]
      on: [create, update]
      condition: 'entity.donor_id != ""'
      error: "Donor {entity_id}: donor_id is required"
  - name: consent_required
    type: cel
    enabled: true
    priority: 5
    config:
      entity_types: [Donor]
      on: [create]
      condition: 'entity.consent_obtained == true'
      error: "Donor {entity_id}: consent is required for enrollment"
unique_constraints:
  - [donor_id]
  - [medical_record_number]
indexes:
  - fields: [species, is_available]
    name: idx_donor_species_active
```

### schemas/sample.yaml — Sample Entity

```yaml
name: Sample
version: "1.0.0"
description: Biological sample from a donor
base: BiologicalEntity
fields:
  - name: sample_id
    type: string
    required: true
    unique: true
    index: true
    description: Internal sample identifier
  - name: donor_id
    type: string
    required: true
    index: true
    references:
      entity: Donor
      field: donor_id
    description: Reference to donor
  - name: sample_type
    type: enum
    required: true
    description: Type of biological sample
  - name: tissue_type
    type: string
    description: Tissue of origin
  - name: collection_date
    type: datetime
    description: Date/time of sample collection
  - name: quantity_ng
    type: float
    description: Sample quantity in nanograms
  - name: quality_score
    type: float
    description: Sample quality metric (0-1)
  - name: storage_location
    type: string
    description: Physical storage location
  - name: barcode
    type: string
    unique: true
    index: true
    description: Sample barcode
  - name: metadata
    type: dict
    flatten_nested: true
    description: Sample-specific metadata
validators:
  - name: sample_donor_exists
    type: cel
    enabled: true
    priority: 20
    config:
      entity_types: [Sample]
      on: [create]
      condition: 'entity.donor_id != ""'
      error: "Sample {entity_id}: must reference a donor"
unique_constraints:
  - [sample_id]
  - [barcode]
```

### validators.yaml

```yaml
validators:
  - name: donor_id_format
    entity_types: [Donor]
    'on': [create, update]
    condition: 'entity.donor_id.matches("^DON-\\d{6}$")'
    error: "Donor {entity_id}: donor_id must match format DON-123456"

  - name: sample_quantity_positive
    entity_types: [Sample]
    'on': [create, update]
    condition: 'entity.quantity_ng > 0'
    error: "Sample {entity_id}: quantity_ng must be positive"

  - name: sample_with_donor
    entity_types: [Sample]
    'on': [create]
    condition: 'entity.donor_id != ""'
    error: "Sample {entity_id}: must have an associated donor"
```

---

## Loading Configuration

```python
from hippo.config.loader import load_hippo_config, load_schema

# Load main configuration
config = load_hippo_config("hippo.yaml")

# Load a schema file
schema = load_schema("schemas/donor.yaml")

# Load all schemas from a directory
from hippo.config.loader import SchemaParser
parser = SchemaParser(schema_dir=Path("schemas"))
schemas = parser.load_schema_dir(Path("schemas"))
```
