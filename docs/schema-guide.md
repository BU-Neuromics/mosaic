# Hippo Schema Writer's Guide

A practical guide for writing `schema.yaml` files for your lab. This document covers the most common schema patterns with real examples. For the full field reference, see [Configuration Reference](configuration.md).

---

## Quick Start

A minimal schema with two linked entity types:

```yaml
entities:
  - name: Donor
    version: "1.0"
    fields:
      - name: external_id
        type: string
        required: true
      - name: diagnosis
        type: string
        required: true
      - name: sex
        type: string
      - name: age_at_death
        type: integer

  - name: Sample
    version: "1.0"
    fields:
      - name: external_id
        type: string
        required: true
      - name: tissue
        type: string
        required: true
      - name: donor_id
        type: string
        required: true
        references:
          entity_type: Donor    # ← links this field to the Donor entity type
```

Save this as `schema.yaml`, then point your `HippoConfig` at it:

```python
from hippo.config import HippoConfig
config = HippoConfig(schema_path="schema.yaml", db_path="my_lab.db")
```

---

## Entity Types

Each entity type is a named, versioned schema. Bump the version string when you change fields.

```yaml
entities:
  - name: SequencingDataset
    version: "1.2"         # bump when schema changes
    description: "An RNA-seq or ATAC-seq dataset"
    fields:
      ...
```

**Rules:**
- `name` must be unique across your schema
- `version` is any string (use semver: `"1.0"`, `"2.1.3"`)
- `description` is optional but recommended

---

## Fields

### Basic Fields

```yaml
fields:
  - name: sample_id
    type: string
    required: true           # raises ValidationFailure if missing on create

  - name: quality_score
    type: float
    required: false          # optional, defaults to null

  - name: read_count
    type: integer

  - name: is_paired
    type: boolean

  - name: collected_at
    type: date               # YYYY-MM-DD
  
  - name: processed_at
    type: datetime           # ISO 8601: 2026-03-01T14:30:00Z

  - name: file_uri
    type: uri                # URI/URL string

  - name: tags
    type: list               # list of values (stored as JSON)

  - name: metadata
    type: dict               # arbitrary key-value dict (stored as JSON)
```

### Enum Fields

Restrict a field to a fixed set of values:

```yaml
  - name: assay
    type: enum
    enum_values:
      - RNASeq
      - ATACSeq
      - ChIPSeq
      - WGS
    required: true
```

Validation raises `ValidationFailure` if an entity is created with a value not in `enum_values`.

### Default Values

```yaml
  - name: status
    type: string
    default: "pending"

  - name: priority
    type: integer
    default: 0
```

---

## Linking Entities (Foreign Keys)

Use `references:` to declare that a field points to another entity type. This is the foundation for entity graph traversal in Cappella and explicit relationship queries.

```yaml
  - name: donor_id
    type: string
    required: true
    references:
      entity_type: Donor    # the entity type this field points to
```

**Important:** The `references:` declaration does NOT enforce referential integrity at write time (Hippo does not reject creates where the referenced entity doesn't exist). It is used for:
- Schema introspection (`HippoClient.schema_references()`)
- Cappella collection resolver entity graph traversal
- Documentation and tooling (validators can enforce integrity if you need it — see [Validators](#validators))

### Self-Referential Links

```yaml
  - name: parent_id
    type: string
    references:
      entity_type: Sample   # links back to the same type
```

### Multi-Level Chains

Build graph traversal paths by chaining references:

```yaml
entities:
  - name: Donor
    ...

  - name: Sample
    fields:
      - name: donor_id
        type: string
        references: {entity_type: Donor}   # Sample → Donor

  - name: SequencingDataset
    fields:
      - name: sample_id
        type: string
        references: {entity_type: Sample}  # Dataset → Sample → Donor
```

With this schema, Cappella can traverse `Dataset.sample_id → Sample.donor_id → Donor` automatically when you pass criteria like `donor.diagnosis=CTE`.

---

## Searching and Indexing

### Full-Text Search

Mark a field for full-text search (FTS5 is recommended):

```yaml
  - name: notes
    type: string
    search: fts5

  - name: description
    type: string
    search: fts5
```

Query via `HippoClient.search()` or the REST API:
```python
results = client.search("Sample", "hippocampus cortex")
```

### Database Indexes

Speed up exact lookups on frequently-queried fields:

```yaml
  - name: diagnosis
    type: string
    index: true              # adds a B-tree index

  - name: batch_id
    type: string
    index_partial: true      # index only non-null values (smaller index)
```

### Unique Constraints

```yaml
  - name: barcode
    type: string
    unique: true             # raises error if duplicate barcode on create
```

---

## Schema Inheritance

Use `base:` to inherit all fields from a parent entity type. The child type is queryable both as itself and as the parent type.

```yaml
entities:
  - name: File
    version: "1.0"
    fields:
      - name: uri
        type: uri
        required: true
      - name: checksum_sha256
        type: string

  - name: AlignmentFile
    version: "1.0"
    base: File               # inherits uri and checksum_sha256
    fields:
      - name: aligner
        type: string
      - name: genome_build
        type: string
        references:
          entity_type: GenomeBuild
```

`client.query("File")` returns both `File` and `AlignmentFile` entities. `client.query("AlignmentFile")` returns only alignment files.

### Multiple Inheritance

```yaml
  - name: AnnotatedAlignmentFile
    version: "1.0"
    base:
      - AlignmentFile
      - QCAnnotation       # inherits from both
```

---

## Validators

CEL-based validators enforce data quality at write time. Define them in `validators.yaml` (separate from the schema).

```yaml
# validators.yaml
validators:
  - name: sample_name_format
    entity_type: Sample
    operations: [create, update]
    condition: 'entity.external_id.matches("^S[0-9]{3,}$")'
    message: "external_id must match S followed by 3+ digits"

  - name: age_plausible
    entity_type: Donor
    operations: [create]
    condition: 'entity.age_at_death >= 18 && entity.age_at_death <= 120'
    message: "age_at_death must be between 18 and 120"
```

### Referential Integrity Validator

Since Hippo doesn't enforce foreign keys at the storage level, use a validator if you need hard enforcement:

```yaml
validators:
  - name: donor_must_exist
    entity_type: Sample
    operations: [create]
    expand: donor_id        # pre-fetches the referenced entity
    condition: 'has(entity.donor_id) && entity.donor_id != ""'
    message: "Sample must have a non-empty donor_id"
```

Full cross-entity validation (checking the referenced entity actually exists) requires using the `ref_check` built-in validator preset:

```yaml
  - name: valid_donor_ref
    entity_type: Sample
    preset: ref_check
    field: donor_id
    ref_entity_type: Donor
```

---

## Namespaces

Group entity types from different domains into named namespaces to avoid collisions:

```yaml
namespace: clinical

entities:
  - name: Assessment        # fully qualified: clinical.Assessment
    version: "1.0"
    fields:
      ...
```

Reference across namespaces using fully-qualified names:

```yaml
  - name: sample_id
    type: string
    references:
      entity_type: tissue.Sample    # namespace.EntityType
```

Root namespace entities (no namespace declared) can be referenced without qualification.

---

## Complete Example: Neuroscience Study

```yaml
# schema.yaml — example for a brain tissue bank

entities:
  - name: Donor
    version: "1.0"
    description: "A research subject (human)"
    fields:
      - name: external_id
        type: string
        required: true
        unique: true
        index: true
      - name: sex
        type: enum
        enum_values: [M, F, Unknown]
        required: true
      - name: age_at_death
        type: integer
      - name: diagnosis
        type: string
        required: true
        index: true
        search: fts5
      - name: notes
        type: string
        search: fts5

  - name: Sample
    version: "1.0"
    description: "A tissue sample from a donor"
    fields:
      - name: external_id
        type: string
        required: true
        unique: true
      - name: donor_id
        type: string
        required: true
        index: true
        references:
          entity_type: Donor
      - name: tissue
        type: enum
        enum_values: [DLPFC, HC, SN, CB, STR]
        required: true
      - name: brain_region
        type: string

  - name: SequencingDataset
    version: "1.0"
    description: "A sequencing run for a sample"
    fields:
      - name: external_id
        type: string
        required: true
      - name: sample_id
        type: string
        required: true
        index: true
        references:
          entity_type: Sample
      - name: assay
        type: enum
        enum_values: [RNASeq, ATACSeq, WGS, WES]
        required: true
      - name: platform
        type: string
      - name: read_count
        type: integer

  - name: GenomeBuild
    version: "1.0"
    description: "A reference genome assembly"
    fields:
      - name: name
        type: string
        required: true
        unique: true
      - name: source
        type: string         # ensembl, ucsc, t2t
      - name: release
        type: string
      - name: source_uri
        type: uri
      - name: uri
        type: uri            # local/S3 path after Canon materializes it

  - name: AlignmentFile
    version: "1.0"
    base: File               # if you have a base File entity
    fields:
      - name: dataset_id
        type: string
        required: true
        references:
          entity_type: SequencingDataset
      - name: genome_build_id
        type: string
        required: true
        references:
          entity_type: GenomeBuild
      - name: aligner
        type: string
      - name: aligner_version
        type: string
```

---

## Common Mistakes

**Using `entity:` instead of `entity_type:` in references**  
The schema parses either, but `HippoClient.schema_references()` and Cappella's collection resolver only read `entity_type:`. Always use:
```yaml
references:
  entity_type: Donor    # ✅ correct
```
Not:
```yaml
references:
  entity: Donor         # ❌ won't be picked up by schema_references()
```

**Forgetting `index: true` on foreign-key fields**  
Queries filtering on `donor_id` will be slow without an index. Add `index: true` to any field you filter on frequently.

**Not bumping the version after field changes**  
Hippo tracks schema versions on entities. Bumping the version when you add or change fields helps provenance queries understand what schema was active when an entity was written.
