## 1. Overview & Scope

### 1.1 What Is Hippo?

Hippo is an open source, configurable metadata tracking service. It provides a unified,
queryable registry of entities, their fields, and their relationships — enabling downstream
systems, analysis pipelines, and data portals to reliably locate and filter metadata without
manually managing spreadsheets or bespoke file manifests.

Hippo is designed as the first module of a larger platform. It tracks *where data lives*
and *what it describes* — not the data itself. Raw data files remain in place (e.g., S3,
local filesystem); Hippo stores the metadata and file locations needed to find and interpret
them.

Hippo is domain-agnostic: the entity types, fields, and relationships it tracks are defined
entirely by a schema config file authored for each deployment. For example, an omics research
deployment might define entity types like Subject, Sample, and Datafile, while a manufacturing
deployment might define Batch, Component, and Inspection.

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

Hippo is the first independently deliverable module of a modular platform. It is designed so
that other platform modules can be built independently and integrated later via well-defined
interfaces.

Hippo itself has no dependencies on those future modules. They will depend on Hippo.

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

### 1.4 Non-Goals

Hippo explicitly does not:

- Store, move, or manage raw data files
- Execute or schedule analysis pipelines
- Perform domain-specific analysis or QC
- Provide a user-facing data portal or visualization layer
- Manage authentication or authorization (delegated to transport layer)
- Serve as the system of record for upstream source systems (those are separate modules with
  placeholder ingestion interfaces in Hippo)
- Replace or replicate LIMS, EHR, or other upstream source systems

### 1.5 Delivery Scope (v0.1)

The initial four-week delivery targets a functional development environment containing:

- Core Python SDK with SQLite backend adapter
- Config-driven schema system supporting arbitrary entity types
- Full provenance and audit trail on all writes
- REST API service (FastAPI) wrapping the SDK
- Batch ingestion interface for loading metadata from flat files
- Placeholder ingestion adapters for future external systems
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

- **Analysis pipelines** (e.g., Nextflow): resolve file paths and entity metadata at runtime
- **Future data portal**: browse and filter entities via the GraphQL layer
- **Future platform modules**: look up entities related to other modules' data

### 1.8 Glossary

| Term | Definition |
|---|---|
| **Entity** | Any top-level object tracked by Hippo. Entity types are defined in schema config (e.g., Project, Item, Attachment). |
| **Schema config** | A YAML or JSON file defining the entity types, fields, and relationships for a Hippo deployment. Authored in Hippo DSL or LinkML. |
| **Field** | A named, typed attribute on an entity type, declared in schema config. See sec3 §3.5 for supported types. |
| **Relationship** | A directional, typed edge connecting two entities. Declared in schema config with cardinality constraints. |
| **External ID** | An identifier from an upstream system mapped to a Hippo entity UUID. Enables cross-system lookups. |
| **Adapter** | A pluggable implementation of a storage or integration interface. |
| **Provenance record** | An immutable record of a change to any entity, including what changed, when, and by whom. |

---
