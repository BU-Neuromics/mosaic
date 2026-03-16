## Context

This change implements data ingestion and reference loader management for Hippo. The goal is to enable:
1. Ingesting data from external sources via CLI
2. Managing reference loader packages through the CLI

This builds on feature-001 which likely provides the foundational infrastructure for this change.

## Goals / Non-Goals

**Goals:**
- Implement `hippo ingest` command to process and load data from configured external sources
- Implement `hippo reference install <package>` to add reference loader packages
- Implement `hippo reference list` to display available reference loaders
- Handle error cases gracefully (no sources configured, invalid packages, no installed loaders)

**Non-Goals:**
- Implementing specific external source adapters (STARLIMS, HALO, Donor DB are future work)
- Implementing the actual data transformation logic (pipeline framework only)
- Implementing a package registry or repository server

## Decisions

1. **CLI-first approach**: The reference management will be CLI-driven initially rather than a programmatic SDK API. This aligns with the current CLI pattern used in Hippo.

2. **Reference loaders as plugins**: Reference loaders will be discovered via entry points (`hippo.reference_loaders`), following the same pattern as storage and external adapters.

3. **Configuration-based ingestion**: Data sources will be defined in configuration files (YAML/JSON), allowing external systems to be configured without code changes.

4. **Error handling with user-friendly messages**: All error conditions will display clear, actionable messages rather than stack traces.

## Risks / Trade-offs

- **Risk**: No package index server exists yet for `hippo reference install`
  - **Mitigation**: Start with local package installation from filesystem paths; design can accommodate a future package index

- **Risk**: Ingestion pipeline design may need to evolve as real external sources are integrated
  - **Mitigation**: Build a flexible pipeline framework that can accommodate different source types

- **Risk**: Reference loader discovery relies on entry points which require package installation
  - **Mitigation**: Support both installed packages and local loader directories
