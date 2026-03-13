## Appendix A: Example Schema — Omics Research Deployment

**Document status:** Draft v0.1
**Depends on:** sec3_data_model.md

---

> **This is an example deployment configuration, not part of the Hippo system spec.**
> The entity types, fields, and relationships below illustrate how a multi-modal omics
> research group might configure Hippo for tracking biological samples, sequencing data
> files, and analysis workflows. A deployment targeting a different domain (e.g.,
> manufacturing QC, environmental monitoring, clinical trials) would author an entirely
> different schema using the same Hippo DSL features documented in sec3. Hippo's core
> behavior is identical regardless of schema content.

---

### A.1 Entity Types

The following six entity types form a complete omics metadata tracking schema. Fields
listed are **user-defined fields only** — system fields (sec3 §3.2) and availability
(sec3 §3.3) are present on all entities implicitly and are not repeated here.

#### Subject

A biological subject who contributed one or more samples.

| Field | Type | Required | Indexed | Notes |
|---|---|---|---|---|
| `external_id` | string | yes | yes | ID from upstream subject registry |
| `species` | enum | yes | no | Values: Homo sapiens, Mus musculus, Rattus norvegicus |
| `biological_sex` | enum | no | no | Values: male, female, unknown |
| `age_at_collection` | float | no | no | Age in years at time of sample collection |
| `diagnosis` | string | no | yes | Primary clinical diagnosis |

#### Sample

A piece of biological material derived from a Subject. May be derived from another Sample
(e.g., dissection, aliquoting).

| Field | Type | Required | Indexed | Notes |
|---|---|---|---|---|
| `external_id` | string | yes | yes | ID from upstream sample registry |
| `tissue_type` | string | yes | yes | Tissue of origin |
| `tissue_region` | string | no | yes | Sub-region within tissue (e.g., hippocampus) |
| `collection_date` | date | no | no | |
| `passage` | int | no | no | For cell lines |

#### Datafile

A file at a known location containing data derived from one or more Samples.

| Field | Type | Required | Indexed | Notes |
|---|---|---|---|---|
| `uri` | uri | yes | yes | S3 URI, local path, or HTTPS URL |
| `file_type` | enum | yes | yes | Values: fastq, bam, vcf, tsv, h5ad, idat, ... |
| `modality` | enum | yes | yes | Values: RNASeq, WGBS, WGS, ATAC, genotyping, ... |
| `file_size_bytes` | int | no | no | |
| `checksum_md5` | string | no | no | Integrity verification |
| `read_count` | int | no | no | For sequencing files |
| `genome_build` | string | no | yes | e.g., GRCh38 |
| `is_primary` | bool | no | yes | True if raw/unprocessed |

#### Dataset

A named, versioned logical collection of Datafiles.

| Field | Type | Required | Indexed | Notes |
|---|---|---|---|---|
| `name` | string | yes | yes | Human-readable name |
| `version` | string | yes | no | Semver or date string |
| `description` | string | no | no | |
| `is_public` | bool | no | yes | Placeholder for future auth layer |

#### Workflow

A versioned analysis pipeline definition from which WorkflowRuns are instantiated.

| Field | Type | Required | Indexed | Notes |
|---|---|---|---|---|
| `name` | string | yes | yes | Pipeline name |
| `version` | string | yes | yes | Semver or git SHA |
| `description` | string | no | no | |
| `repository_uri` | uri | no | no | Git repository of pipeline definition |
| `language` | enum | no | no | Values: nextflow, snakemake, wdl, cwl, ... |

#### WorkflowRun

A single execution of a Workflow, consuming input Datafiles and producing output Datafiles.
The `instance_of` relationship links a WorkflowRun to its Workflow definition. Execution
state is tracked via the `execution_state` field.

| Field | Type | Required | Indexed | Notes |
|---|---|---|---|---|
| `execution_state` | enum | yes | yes | Values: pending, running, succeeded, failed |
| `executor` | string | no | no | Nextflow run ID, AWS Batch job ID, etc. |
| `started_at` | datetime | no | no | |
| `completed_at` | datetime | no | no | |
| `parameters` | json | yes | no | Full parameter set used for this run |

---

### A.2 Relationship Declarations (Hippo DSL)

```yaml
relationships:
  - name: donated
    from: Subject
    to: Sample
    cardinality: one-to-many
    description: "A subject donated one or more samples"

  - name: derived_from
    from: Sample
    to: Sample
    cardinality: many-to-many
    description: "A sample derived from another (e.g. dissection, aliquot)"
    properties:
      method: {type: string}

  - name: generated
    from: Sample
    to: Datafile
    cardinality: one-to-many

  - name: input_to
    from: Datafile
    to: WorkflowRun
    cardinality: many-to-many

  - name: output_of
    from: Datafile
    to: WorkflowRun
    cardinality: many-to-many

  - name: instance_of
    from: WorkflowRun
    to: Workflow
    cardinality: many-to-one
    required: true

  - name: contains
    from: Dataset
    to: Datafile
    cardinality: many-to-many
```

---

### A.3 Entity Relationship Graph

```
                    ┌─────────────┐
                    │   Subject   │
                    └──────┬──────┘
                           │ donated (1:many)
                    ┌──────▼──────┐
               ┌────│   Sample    │◄──────────────┐
               │    └──────┬──────┘  derived_from  │
               │           │         (many:many,   │
               │           │          self-ref)    │
               │           │ generated (1:many)
               │    ┌──────▼──────┐
               │    │  Datafile   │
               │    └──┬──────┬───┘
               │       │      │
               │       │      │ output_of (many:many)
               │       │      │
               │       │  ┌───▼──────────────────────────┐
               │       │  │        WorkflowRun            │
               │       │  │  (parameters, executor)       │
               │       │  └───▲──────────┬────────────────┘
               │       │      │          │ instance_of (many:1)
               │       │      │   ┌──────▼──────┐
               │       │      │   │  Workflow   │
               │       │      │   │  (name,     │
               │       │      │   │   version)  │
               │       │      │   └─────────────┘
               │       │      │
               │       └──────┘
               │       input_to (many:many)
               │
               │    ┌─────────────┐
               └───►│   Dataset   │
                    │  (contains  │
                    │  Datafiles) │
                    └─────────────┘

System relationships (built-in, available on all entity types):
  [any entity] ──superseded_by──► [any entity]
```

---
