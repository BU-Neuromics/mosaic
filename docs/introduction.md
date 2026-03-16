# Hippo — Metadata Tracking Service

Hippo is an open-source metadata tracking service for multi-modal omics datasets. It gives you a unified, queryable registry of biological samples, donors, data files, and the relationships between them — so that pipelines, analysis tools, and data portals can reliably locate and filter datasets without manually managing spreadsheets or bespoke file manifests.

## Who Is Hippo For?

- **Pipeline authors** who need to resolve file paths and sample metadata at runtime (e.g., from Nextflow or Snakemake)
- **Researchers** who want a queryable record of what data exists, where it lives, and what it describes
- **Data managers** who need to track the provenance, lifecycle, and relationships of samples and files across a project

## What Hippo Does

Hippo tracks *where data lives* and *what it describes* — not the data itself. Raw files (fastq, BAM, VCF, images, etc.) remain in place on your filesystem or object store; Hippo stores the metadata and file locations needed to find and interpret them.

Specifically, Hippo tracks:

- **Subjects (donors)** and their associated metadata
- **Samples** derived from subjects, including tissue type, collection date, and derivation relationships
- **Data files** at known locations (S3 URIs, local paths, HTTPS URLs), tagged with modality, file type, and genome build
- **Datasets** — named, versioned logical collections of data files
- **Workflows and workflow runs** — pipeline definitions and individual executions linking input files to output files
- **Relationships** between all of the above, including derivation chains and supersession history
- **Full provenance** — every write is versioned, nothing is ever hard-deleted, and complete change history is always available

## What Hippo Does NOT Do

Hippo is deliberately scoped. It does not:

- Store, move, copy, or manage raw data files
- Execute or schedule analysis pipelines
- Perform any biological analysis, QC, or data processing
- Provide a data portal, web UI, or visualization layer
- Manage authentication or authorization (this is delegated to the transport layer or a future middleware component)
- Replace upstream source systems such as LIMS, EHR, or clinical databases

## How Hippo Fits into the BASS Platform

Hippo is the foundational data layer of the BASS platform. Other BASS components depend on Hippo; Hippo has no dependencies on them.

```
┌──────────────────────────────────────────────────────┐
│                  Omics Data Platform                 │
│                                                      │
│  ┌─────────┐  ┌──────────┐  ┌──────────────────┐    │
│  │  Hippo  │  │  Tissue  │  │  Digital         │    │
│  │  (MTS)  │  │  Registry│  │  Histology Store │    │
│  │  ◄ HERE │  │ (future) │  │  (future)        │    │
│  └────┬────┘  └──────────┘  └──────────────────┘    │
│       │                                              │
│  ┌────▼──────────────────────────────────────────┐   │
│  │         Data Portal / GraphQL Layer (future)  │   │
│  └───────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────┘
```

BASS-Cappella (workflow engine) uses Hippo to look up input files and register output files. BASS-Aperture (interface layer) queries Hippo to present data to users. BASS-Bridge (integration middleware) coordinates cross-component operations.

## Deployment Options

Hippo is designed to run at any scale using the same codebase. You choose your deployment tier through configuration alone — no code changes required.

| Tier | How it works | Typical use |
|---|---|---|
| **Local / single-user** | Install via `pip`, point at a local SQLite file, query from a Python script or notebook. No server required. | Individual researcher, exploratory analysis |
| **Small team** | Run the REST API service (`hippo serve`) on a shared host, backed by SQLite or PostgreSQL. | Lab group, shared project server |
| **Enterprise / cloud** | Deploy on AWS with a managed PostgreSQL or DynamoDB backend, container orchestration, and authentication middleware. | Production platform, multi-team environment |

## Error Handling

Hippo provides a structured exception hierarchy for robust error handling. All exceptions inherit from `HippoError`, allowing you to catch specific error types or handle all Hippo-related errors uniformly.

### Exception Hierarchy

| Exception | Description |
|-----------|-------------|
| `HippoError` | Base exception for all Hippo errors |
| `ConfigError` | Configuration loading and validation errors |
| `SchemaError` | Schema parsing and processing errors |
| `ValidationError` | Data validation errors |
| `EntityNotFoundError` | Entity lookup failures |
| `AdapterError` | Adapter-specific errors |

### Usage Example

```python
from hippo.core.exceptions import (
    HippoError,
    ConfigError,
    EntityNotFoundError,
)

try:
    config = load_hippo_config("hippo.yaml")
except ConfigError as e:
    print(f"Configuration error: {e.field_name}")
except EntityNotFoundError as e:
    print(f"Entity not found: {e.entity_type} {e.entity_id}")
except HippoError as e:
    print(f"General error: {e.message}")
```

## Next Steps

- **[Quickstart](quickstart.md)** — Get Hippo running locally in under 5 minutes
- **[Installation Guide](installation.md)** — Full installation instructions for all deployment tiers
- **[Data Model](data-model.md)** — Learn about Hippo's entity types, relationships, and schema system
- **[CLI Reference](cli-reference.md)** — Complete reference for the `hippo` command-line tool
- **[API Reference](api-reference.md)** — REST API reference
- **[Design Specification](../design/INDEX.md)** — Internal engineering specification for developers building or extending Hippo
