# Hippo — Metadata Tracking Service

Hippo is an open-source, configurable metadata tracking service. It gives you a unified, queryable registry of entities, their fields, and the relationships between them — so that downstream systems, analysis pipelines, and data portals can reliably locate and filter metadata without manually managing spreadsheets or bespoke file manifests.

Hippo is domain-agnostic: the entity types, fields, and relationships it tracks are defined entirely by a schema config file authored for each deployment.

## Who Is Hippo For?

- **Pipeline authors** who need to resolve file paths and sample metadata at runtime (e.g., from Nextflow or Snakemake)
- **Researchers** who want a queryable record of what data exists, where it lives, and what it describes
- **Data managers** who need to track the provenance, lifecycle, and relationships of samples and files across a project

## What Hippo Does

Hippo tracks *where data lives* and *what it describes* — not the data itself. Raw data files remain in place on your filesystem or object store; Hippo stores the metadata and file locations needed to find and interpret them.

Specifically, Hippo tracks:

- **Entities** of any type defined in your schema config (for example: subjects, samples, and data files in an omics deployment; batches, components, and inspections in a manufacturing deployment)
- **Relationships** between entities, including derivation chains and supersession history
- **Full provenance** — every write is versioned, nothing is ever hard-deleted, and complete change history is always available

## What Hippo Does NOT Do

Hippo is deliberately scoped. It does not:

- Store, move, copy, or manage raw data files
- Execute or schedule analysis pipelines
- Perform any biological analysis, QC, or data processing
- Provide a data portal, web UI, or visualization layer
- Manage authentication or authorization (this is delegated to the transport layer or a future middleware component)
- Replace upstream source systems such as LIMS, EHR, or clinical databases

## How Hippo Fits into the Larger Platform

Hippo is designed as the first independently deliverable module of a modular platform. Other platform modules depend on Hippo; Hippo has no dependencies on them.

```
┌──────────────────────────────────────────────────────┐
│                    Platform                           │
│                                                      │
│  ┌─────────┐  ┌──────────┐  ┌──────────────────┐    │
│  │  Hippo  │  │ Module B │  │  Module C        │    │
│  │  (MTS)  │  │ (future) │  │  (future)        │    │
│  │  ◄ HERE │  │          │  │                  │    │
│  └────┬────┘  └──────────┘  └──────────────────┘    │
│       │                                              │
│  ┌────▼──────────────────────────────────────────┐   │
│  │         Data Portal / GraphQL Layer (future)  │   │
│  └───────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────┘
```

Downstream analysis pipelines use Hippo to look up input files and register output files. Data portals query Hippo to present metadata to users. Integration middleware coordinates cross-module operations.

## Deployment Options

Hippo is designed to run at any scale using the same codebase. You choose your deployment tier through configuration alone — no code changes required.

| Tier | How it works | Typical use |
|---|---|---|
| **Local / single-user** | Install via `pip`, point at a local SQLite file, query from a Python script or notebook. No server required. | Individual researcher, exploratory analysis |
| **Small team** | Run the REST API service (`hippo serve`) on a shared host, backed by SQLite or PostgreSQL. | Lab group, shared project server |
| **Enterprise / cloud** | Deploy on AWS with a managed PostgreSQL or DynamoDB backend, container orchestration, and authentication middleware. | Production platform, multi-team environment |

## Next Steps

- **[Quickstart](quickstart.md)** — Get Hippo running locally in under 5 minutes
- **[Installation Guide](installation.md)** — Full installation instructions for all deployment tiers
- **[Data Model](data-model.md)** — Learn about Hippo's entity types, relationships, and schema system
- **[CLI Reference](cli-reference.md)** — Complete reference for the `hippo` command-line tool
- **[API Reference](api-reference.md)** — REST API reference
- **[Design Specification](../design/INDEX.md)** — Internal engineering specification for developers building or extending Hippo
