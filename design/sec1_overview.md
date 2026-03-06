## 1. Overview & Scope

### 1.1 What Is Hippo?

Hippo is an open source metadata tracking service for multi-modal omics datasets. It provides a
unified, queryable registry of biological samples, donors, data files, and their relationships —
enabling downstream pipelines, analysis tools, and data portals to reliably locate and filter
datasets without manually managing spreadsheets or bespoke file manifests.

Hippo is designed as the first module of a larger omics data platform. It tracks *where data lives*
and *what it describes* — not the data itself. Raw data files remain in place (e.g., S3, local
filesystem); Hippo stores the metadata and file locations needed to find and interpret them.

### 1.2 Deployment Philosophy

Hippo is built to run at any scale from a single researcher's laptop to an enterprise cloud
deployment, using the same codebase throughout:

- **Local / single-user:** Install via `pip`, point at a local SQLite database, query from a
  Python script or notebook in minutes — no server required.
- **Small team:** Run the optional REST API service on a shared host backed by PostgreSQL.
- **Enterprise / cloud:** Deploy on AWS with managed database backends, container orchestration,
  and authentication middleware.

Scale is controlled entirely by configuration and backend adapter selection. No code changes are
required to move between deployment tiers.

### 1.3 Position in the Larger Platform

Hippo is the first independently deliverable module of a modular omics data platform. It is
designed so that other platform modules — including a subject/donor database, tissue registry,
digital histology store, and data portal — can be built independently and integrated later via
well-defined interfaces.

Hippo itself has no dependencies on those future modules. They will depend on Hippo.

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

### 1.4 Non-Goals

Hippo explicitly does not:

- Store, move, or manage raw data files (fastq, BAM, VCF, images, etc.)
- Execute or schedule analysis pipelines
- Perform any biological analysis or QC
- Provide a user-facing data portal or visualization layer
- Manage authentication or authorization (delegated to transport layer)
- Serve as the system of record for donor clinical data, tissue inventory, or histology metadata
  (those are separate future modules with placeholder ingestion interfaces in Hippo)
- Replace or replicate LIMS, EHR, or other upstream source systems

### 1.5 Delivery Scope (v0.1)

The initial four-week delivery targets a functional development environment containing:

- Core Python SDK with SQLite backend adapter
- Config-driven schema system supporting the primary omics entity types
- Full provenance and audit trail on all writes
- REST API service (FastAPI) wrapping the SDK
- Batch ingestion interface for loading metadata from flat files
- Placeholder ingestion adapters for future external systems (tissue registry, donor DB, etc.)
- Unit and integration test suite

The following are explicitly out of scope for v0.1:

- GraphQL transport layer
- Cloud-managed database adapters (PostgreSQL/RDS, DynamoDB)
- Authentication/authorization middleware
- Data portal or query UI
- Production deployment infrastructure (IaC, CI/CD)
- Bidirectional sync with external systems

### 1.6 Key Design Principles

| Principle | Description |
|---|---|
| **SDK-first** | All business logic lives in the Python SDK. REST and GraphQL are thin transport wrappers. |
| **Adapter pattern** | Storage backends, external system integrations, and transport layers are swappable via config. |
| **Config-driven schema** | Entity schemas are defined in YAML config, not hardcoded. New fields and entity types can be added without code changes. |
| **Provenance by default** | Every write is versioned. No data is ever hard-deleted. Full change history is always available. |
| **Local-first** | Zero infrastructure required for single-user deployment. |
| **Openplan-compatible** | This specification is structured to feed directly into the openplan Vision → Epic → Feature → OpenSpec pipeline. |

### 1.7 Intended Consumers

In v0.1, Hippo serves other applications only — there is no human-facing query interface:

- **Analysis pipelines** (e.g., Nextflow): resolve file paths and sample metadata at runtime
- **Future data portal**: browse and filter datasets via the GraphQL layer
- **Future platform modules**: look up omics datasets related to donors, tissues, or slides

### 1.8 Glossary

| Term | Definition |
|---|---|
| **Donor** | A biological subject who contributed samples. May have associated demographic and clinical metadata. |
| **Sample** | A biological specimen derived from a donor, associated with a specific tissue and collection event. |
| **DataFile** | A file (e.g., fastq, BAM, VCF) stored at a known location (S3 URI, local path) and associated with a Sample. |
| **Modality** | The type of omics assay (e.g., RNASeq, bisulfite sequencing, genotyping, ATAC-seq). |
| **BrainRegion** | An anatomical region of origin for a Sample. Generalizable to any tissue region. |
| **Dataset** | A named, versioned collection of Samples and DataFiles representing a cohort or experiment. |
| **Entity** | Any top-level object tracked by Hippo (Donor, Sample, DataFile, etc.). |
| **Adapter** | A pluggable implementation of a storage or integration interface. |
| **Provenance record** | An immutable record of a change to any entity, including what changed, when, and by whom. |

---

