# Hippo Quickstart

This guide walks you through setting up Hippo for a real-world bioinformatics research scenario: tracking brain tissue donors, samples, and RNA-seq data files from a small Alzheimer's disease study.

By the end, you'll understand how to define schemas, run migrations, use the REST API, and work with the Python SDK.

## Prerequisites

- **Hippo installed**: `pip install hippo-mts`
- **curl** or **HTTPie** for REST API examples
- (Optional) Python 3.10+ for SDK examples

## Step 1: Initialize a Project

Create a new Hippo project with the default template:

```bash
hippo init --path brain_study
```

Expected output:

```
✓ Created project directory: brain_study/
✓ Created schemas/ directory
✓ Created config/ directory
✓ Created data/ directory
✓ Project initialized with 'basic' template
```

This creates the following structure:

```
brain_study/
├── config/
│   └── hippo.yaml
├── data/
│   └── hippo.db (created after migration)
├── schemas/
│   └── .gitkeep
└── hippo.yaml
```

## Step 2: Define Schemas

Create a schema file that defines the entities for your Alzheimer's research study. Hippo schemas use YAML with an `entities` key at the top level.

Create `schemas/brain_study.yaml`:

```yaml
entities:
  - name: Donor
    version: '1.0'
    fields:
      - name: donor_id
        type: string
        required: true
        unique: true
      - name: name
        type: string
        required: true
      - name: age
        type: integer
        required: true
      - name: sex
        type: string
        required: true
        allowed_values:
          - M
          - F
      - name: diagnosis
        type: string
        required: true
        allowed_values:
          - Control
          - Alzheimer's Disease
          - Mild Cognitive Impairment
      - name: brain_region
        type: string
        required: true
        allowed_values:
          - Hippocampus
          - Frontal Cortex
          - Temporal Cortex
          - Occipital Cortex
          - Cerebellum

  - name: Sample
    version: '1.0'
    fields:
      - name: sample_id
        type: string
        required: true
        unique: true
      - name: donor_id
        type: string
        required: true
      - name: tissue_type
        type: string
        required: true
        allowed_values:
          - Brain Tissue
          - Blood
          - CSF
      - name: brain_region
        type: string
        required: true
        allowed_values:
          - Hippocampus
          - Frontal Cortex
          - Temporal Cortex
          - Occipital Cortex
          - Cerebellum
      - name: collection_date
        type: date
        required: true
      - name: rin_score
        type: float
        required: false
        description: RNA Integrity Number (RIN), 1-10 scale
      - name: notes
        type: string
        required: false

  - name: DataFile
    version: '1.0'
    fields:
      - name: file_id
        type: string
        required: true
        unique: true
      - name: sample_id
        type: string
        required: true
      - name: file_path
        type: string
        required: true
      - name: file_type
        type: string
        required: true
        allowed_values:
          - FASTQ
          - BAM
          - VCF
          - CSV
          - JSON
          - TSV
      - name: size_bytes
        type: integer
        required: true
      - name: checksum
        type: string
        required: false
      - name: pipeline_version
        type: string
        required: false
      - name: description
        type: string
        required: false
```

This schema defines three entity types:
- **Donor**: Brain tissue donors with demographics and diagnosis
- **Sample**: Brain tissue samples with collection details and RNA quality metrics
- **DataFile**: Sequencing output files linked to samples

## Step 3: Run Migrations

Apply the schema to create database tables:

```bash
cd brain_study && hippo migrate
```

Expected output:

```
✓ Loaded 3 entity definitions from schemas/brain_study.yaml
✓ Created table: donors (v1.0)
✓ Created table: samples (v1.0)
✓ Created table: data_files (v1.0)
✓ Created relationship tables
✓ Migration complete: v1.0
```

The database is now ready to store entities.

## Step 4: Start the Server

Start the Hippo REST API server:

```bash
cd brain_study && hippo serve --port 8000
```

Expected output:

```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000
```

The server is now running. In a separate terminal, you can test the endpoints.

## Step 5: REST API Walkthrough

All requests below use the header `Authorization: Bearer dev-token`. The dev server accepts any Bearer token.

### Create a Donor

```bash
curl -s -X POST http://127.0.0.1:8000/ingest \
  -H "Authorization: Bearer dev-token" \
  -H "Content-Type: application/json" \
  -d '{
    "entity_type": "Donor",
    "data": {
      "donor_id": "AD-001",
      "name": "Subject AD-001",
      "age": 78,
      "sex": "M",
      "diagnosis": "Alzheimer's Disease",
      "brain_region": "Hippocampus"
    }
  }'
```

Response:

```json
{
  "id": "donor-1",
  "entity_type": "Donor",
  "data": {
    "donor_id": "AD-001",
    "name": "Subject AD-001",
    "age": 78,
    "sex": "M",
    "diagnosis": "Alzheimer's Disease",
    "brain_region": "Hippocampus"
  },
  "version": 1,
  "created_at": "2026-03-17T10:30:00Z",
  "updated_at": "2026-03-17T10:30:00Z",
  "is_available": true
}
```

Save the returned entity `id` (e.g., `donor-1`) for use in subsequent operations.

### Create a Brain Tissue Sample

```bash
curl -s -X POST http://127.0.0.1:8000/ingest \
  -H "Authorization: Bearer dev-token" \
  -H "Content-Type: application/json" \
  -d '{
    "entity_type": "Sample",
    "data": {
      "sample_id": "SMPL-AD-001-HC",
      "donor_id": "AD-001",
      "tissue_type": "Brain Tissue",
      "brain_region": "Hippocampus",
      "collection_date": "2025-11-15",
      "rin_score": 8.4,
      "notes": "Left hemisphere, posterior hippocampus"
    }
  }'
```

### Create an RNA-seq Data File

```bash
curl -s -X POST http://127.0.0.1:8000/ingest \
  -H "Authorization: Bearer dev-token" \
  -H "Content-Type: application/json" \
  -d '{
    "entity_type": "DataFile",
    "data": {
      "file_id": "RNASEQ-AD-001-HC-R1",
      "sample_id": "SMPL-AD-001-HC",
      "file_path": "/storage/alzheimer study/2025/AD-001/RNAseq/fastq/sample_R1_001.fastq.gz",
      "file_type": "FASTQ",
      "size_bytes": 15234000000,
      "checksum": "sha256:a3f2b1c9d8e5f...",
      "pipeline_version": "rnaseq-v2.1.0",
      "description": "RNA-seq FASTQ, forward reads"
    }
  }'
```

### List Entities

```bash
curl -s "http://127.0.0.1:8000/entities?entity_type=Donor&limit=10" \
  -H "Authorization: Bearer dev-token"
```

```bash
curl -s "http://127.0.0.1:8000/entities?entity_type=Sample&limit=10" \
  -H "Authorization: Bearer dev-token"
```

### Update an Entity

```bash
curl -s -X PUT http://127.0.0.1:8000/entities/donor-1 \
  -H "Authorization: Bearer dev-token" \
  -H "Content-Type: application/json" \
  -d '{
    "entity_type": "Donor",
    "data": {
      "donor_id": "AD-001",
      "name": "Subject AD-001",
      "age": 78,
      "sex": "M",
      "diagnosis": "Alzheimer's Disease",
      "brain_region": "Temporal Cortex"
    }
  }'
```

### Search with Full-Text Search

```bash
curl -s "http://127.0.0.1:8000/search?entity_type=Donor&q=alzheimer" \
  -H "Authorization: Bearer dev-token"
```

```bash
curl -s "http://127.0.0.1:8000/search?entity_type=Sample&q=hippocampus" \
  -H "Authorization: Bearer dev-token"
```

## Step 6: Relationships via REST API

### Link Donor to Sample

```bash
curl -s -X POST http://127.0.0.1:8000/entities/donor-1/relationships \
  -H "Authorization: Bearer dev-token" \
  -H "Content-Type: application/json" \
  -d '{
    "target_entity_id": "sample-1",
    "relationship_type": "donated"
  }'
```

### Link Sample to Data File

```bash
curl -s -X POST http://127.0.0.1:8000/entities/sample-1/relationships \
  -H "Authorization: Bearer dev-token" \
  -H "Content-Type: application/json" \
  -d '{
    "target_entity_id": "datafile-1",
    "relationship_type": "generated_from"
  }'
```

### Traverse Relationships

```bash
curl -s "http://127.0.0.1:8000/entities/donor-1/relationships" \
  -H "Authorization: Bearer dev-token"
```

```bash
curl -s "http://127.0.0.1:8000/entities/donor-1/relationships?relationship_type=donated&max_depth=3" \
  -H "Authorization: Bearer dev-token"
```

## Step 7: View Provenance/History

```bash
curl -s "http://127.0.0.1:8000/entities/donor-1/history" \
  -H "Authorization: Bearer dev-token"
```

Response shows every change made to the entity:

```json
[
  {
    "version": 1,
    "operation": "CREATE",
    "timestamp": "2026-03-17T10:30:00Z",
    "changed_by": "system",
    "changes": {}
  },
  {
    "version": 2,
    "operation": "UPDATE",
    "timestamp": "2026-03-17T10:45:00Z",
    "changed_by": "user@example.com",
    "changes": {
      "brain_region": {
        "old": "Hippocampus",
        "new": "Temporal Cortex"
      }
    }
  }
]
```

## Step 8: Python SDK Usage

The following self-contained script demonstrates the full Python SDK capabilities. Save this as `example_sdk_usage.py`:

```python
#!/usr/bin/env python3
"""
Hippo Python SDK Example: Alzheimer's Study Data Management

This script demonstrates:
- Setting up HippoClient with SQLiteAdapter
- Creating, updating, and querying entities
- Full-text search
- Relationships
- History/provenance tracking
- Custom validation
"""

import yaml
from datetime import date

from hippo.core.client import HippoClient
from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter
from hippo.core.pipeline import ValidationPipeline
from hippo.core.validation.validators import WriteValidator, WriteOperation, ValidationResult
from hippo.core.exceptions import ValidationFailure


# Define schemas programmatically (normally loaded from YAML)
SCHEMAS = {
    "brain_study": """
entities:
  - name: Donor
    version: '1.0'
    fields:
      - name: donor_id
        type: string
        required: true
      - name: name
        type: string
        required: true
      - name: age
        type: integer
        required: true
      - name: sex
        type: string
        required: true
      - name: diagnosis
        type: string
        required: true
      - name: brain_region
        type: string
        required: true

  - name: Sample
    version: '1.0'
    fields:
      - name: sample_id
        type: string
        required: true
      - name: donor_id
        type: string
        required: true
      - name: tissue_type
        type: string
        required: true
      - name: brain_region
        type: string
        required: true
      - name: collection_date
        type: date
        required: true
      - name: rin_score
        type: float
        required: false

  - name: DataFile
    version: '1.0'
    fields:
      - name: file_id
        type: string
        required: true
      - name: sample_id
        type: string
        required: true
      - name: file_path
        type: string
        required: true
      - name: file_type
        type: string
        required: true
      - name: size_bytes
        type: integer
        required: true
      - name: checksum
        type: string
        required: false
      - name: pipeline_version
        type: string
        required: false
"""
}


class RINScoreValidator(WriteValidator):
    """Custom validator: RIN scores must be between 1.0 and 10.0."""

    def validate(self, operation: WriteOperation, data: dict) -> ValidationResult:
        if operation == WriteOperation.CREATE or operation == WriteOperation.UPDATE:
            if 'rin_score' in data:
                rin = data['rin_score']
                if not (1.0 <= rin <= 10.0):
                    return ValidationResult(
                        valid=False,
                        errors=[f"RIN score must be between 1.0 and 10.0, got {rin}"]
                    )
        return ValidationResult(valid=True, errors=[])


def main():
    # Initialize storage adapter (in-memory SQLite for this example)
    adapter = SQLiteAdapter(':memory:')
    adapter.initialize()

    # Parse schemas
    schemas = {}
    for name, yaml_content in SCHEMAS.items():
        schemas[name] = yaml.safe_load(yaml_content)

    # Set up validation pipeline with custom validators
    pipeline = ValidationPipeline()
    pipeline.add_validator(RINScoreValidator())

    # Create HippoClient
    client = HippoClient(
        storage=adapter,
        schemas=schemas,
        pipeline=pipeline
    )

    # Create a donor
    donor = client.create("Donor", {
        "donor_id": "AD-002",
        "name": "Subject AD-002",
        "age": 82,
        "sex": "F",
        "diagnosis": "Alzheimer's Disease",
        "brain_region": "Frontal Cortex"
    })
    print(f"Created donor: {donor['id']}")
    donor_id = donor['id']

    # Create a sample
    sample = client.create("Sample", {
        "sample_id": "SMPL-AD-002-FC",
        "donor_id": "AD-002",
        "tissue_type": "Brain Tissue",
        "brain_region": "Frontal Cortex",
        "collection_date": "2025-12-01",
        "rin_score": 7.9
    })
    print(f"Created sample: {sample['id']}")
    sample_id = sample['id']

    # Create a data file
    datafile = client.create("DataFile", {
        "file_id": "RNASEQ-AD-002-FC-R1",
        "sample_id": "SMPL-AD-002-FC",
        "file_path": "/storage/alzheimer study/2025/AD-002/RNAseq/fastq/R1.fastq.gz",
        "file_type": "FASTQ",
        "size_bytes": 14890000000,
        "pipeline_version": "rnaseq-v2.1.0"
    })
    print(f"Created data file: {datafile['id']}")
    datafile_id = datafile['id']

    # Query with filters
    print("\n--- Query: Donors with Alzheimer's ---")
    donors = client.query("Donor", filters=[
        {"field": "diagnosis", "operator": "eq", "value": "Alzheimer's Disease"}
    ])
    for d in donors:
        print(f"  {d['data']['donor_id']}: {d['data']['name']}")

    # Full-text search
    print("\n--- Search: Samples in hippocampus ---")
    results = client.search("Sample", "hippocampus")
    for r in results:
        print(f"  {r['data']['sample_id']}: {r['data']['brain_region']}")

    # Create relationships
    print("\n--- Relationships ---")
    client.relationships.relate(donor_id, sample_id, "donated")
    print(f"Linked donor {donor_id} -> sample {sample_id} (donated)")

    client.relationships.relate(sample_id, datafile_id, "generated_from")
    print(f"Linked sample {sample_id} -> datafile {datafile_id} (generated_from)")

    # Traverse relationships
    print("\n--- Traverse relationships from donor ---")
    graph = client.relationships.traverse(donor_id, max_depth=2)
    print(f"  Depth 0: donor {donor_id}")
    for rel in graph:
        print(f"  -> {rel['target_id']} ({rel['relationship_type']})")

    # View history
    print("\n--- History for donor ---")
    history = client.history(donor_id)
    for record in history:
        print(f"  v{record['version']}: {record['operation']} at {record['timestamp']}")

    # Update with validation
    print("\n--- Update sample with RIN score ---")
    updated_sample = client.update(sample_id, {
        "sample_id": "SMPL-AD-002-FC",
        "donor_id": "AD-002",
        "tissue_type": "Brain Tissue",
        "brain_region": "Frontal Cortex",
        "collection_date": "2025-12-01",
        "rin_score": 8.2
    })
    print(f"Updated sample to RIN: {updated_sample['data']['rin_score']}")

    # Try invalid RIN (should fail validation)
    print("\n--- Validation: Invalid RIN score ---")
    try:
        client.update(sample_id, {
            "sample_id": "SMPL-AD-002-FC",
            "donor_id": "AD-002",
            "tissue_type": "Brain Tissue",
            "brain_region": "Frontal Cortex",
            "collection_date": "2025-12-01",
            "rin_score": 15.0  # Invalid: exceeds 10.0
        })
    except ValidationFailure as e:
        print(f"  Validation failed (expected): {e.errors}")

    # Get single entity
    print("\n--- Get single entity ---")
    donor = client.get("Donor", donor_id)
    print(f"  Retrieved: {donor['data']['donor_id']}, diagnosis: {donor['data']['diagnosis']}")

    # Soft delete (availability management)
    print("\n--- Soft delete (set unavailable) ---")
    client.delete(donor_id)  # Soft delete
    print(f"  Donor {donor_id} marked as unavailable")

    # Check availability
    availability = client.get(f"{donor_id}/availability")
    print(f"  is_available: {availability['is_available']}")


if __name__ == "__main__":
    main()
```

Run the script:

```bash
python example_sdk_usage.py
```

Expected output:

```
Created donor: donor-1
Created sample: sample-1
Created data file: datafile-1

--- Query: Donors with Alzheimer's ---
  AD-002: Subject AD-002

--- Search: Samples in hippocampus ---

--- Relationships ---
Linked donor donor-1 -> sample sample-1 (donated)
Linked sample sample-1 -> datafile datafile-1 (generated_from)

--- Traverse relationships from donor ---
  Depth 0: donor donor-1
  -> sample sample-1 (donated)

--- History for donor ---
  v1: CREATE at 2026-03-17T10:30:00Z
  v2: UPDATE at 2026-03-17T10:35:00Z

--- Update sample with RIN score ---
Updated sample to RIN: 8.2

--- Validation: Invalid RIN score ---
  Validation failed (expected): ['RIN score must be between 1.0 and 10.0, got 15.0']

--- Get single entity ---
  Retrieved: AD-002, diagnosis: Alzheimer's Disease

--- Soft delete (set unavailable) ---
  Donor donor-1 marked as unavailable
  is_available: False
```

## Step 9: Availability Management (Soft Delete)

Hippo never hard-deletes data. The `delete()` method sets `is_available` to `false`:

```bash
# Mark entity as unavailable
curl -s -X PUT http://127.0.0.1:8000/entities/donor-1/availability \
  -H "Authorization: Bearer dev-token" \
  -H "Content-Type: application/json" \
  -d '{"is_available": false}'
```

```bash
# Check availability status
curl -s http://127.0.0.1:8000/entities/donor-1/availability \
  -H "Authorization: Bearer dev-token"
```

Response:

```json
{
  "is_available": false,
  "changed_at": "2026-03-17T11:00:00Z"
}
```

To restore:

```bash
curl -s -X PUT http://127.0.0.1:8000/entities/donor-1/availability \
  -H "Authorization: Bearer dev-token" \
  -H "Content-Type: application/json" \
  -d '{"is_available": true}'
```

## Next Steps

Now that you've completed the quickstart, explore these resources to deepen your understanding:

- **[Data Model](data-model.md)** — Deep dive into entity types, relationships, and schema design
- **[CLI Reference](cli-reference.md)** — Complete reference for all `hippo` commands
- **[API Reference](api-reference.md)** — Full REST API documentation
- **[Configuration](configuration.md)** — Configure Hippo for different deployment scenarios
- **[Design Specification](../design/INDEX.md)** — Internal engineering specification

For larger studies, consider:
- Using PostgreSQL instead of SQLite for production (`hippo serve` with PostgreSQL backend)
- Setting up external adapters to sync with STARLIMS or HALO
- Configuring the GraphQL layer for complex queries
