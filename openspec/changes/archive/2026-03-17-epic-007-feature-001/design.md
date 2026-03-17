## Context

Hippo is the Metadata Tracking Service (MTS) for the BASS platform. Currently, the system has SDK-level components (HippoClient, QueryEngine, etc.) but lacks a CLI interface for user interaction. This change establishes the foundational CLI infrastructure to enable users to interact with Hippo via command-line operations.

### Current State
- Core SDK exists in `hippo/core/` with business logic
- No CLI entry point currently available
- No project initialization mechanism

### Constraints
- Must use Typer for CLI framework (per proposal)
- Must integrate with existing SDK components
- Low complexity implementation

## Goals / Non-Goals

**Goals:**
- Establish CLI entry point with `hippo` command
- Implement all required commands: init, serve, migrate, validate, ingest, reference (install/update/list), compile-schema
- Wire CLI commands to underlying SDK services
- Enable project initialization

**Non-Goals:**
- Advanced CLI features (plugins, extensions)
- Shell completions (future enhancement)
- Interactive mode

## Decisions

| Decision | Rationale |
|----------|-----------|
| Use Typer framework | Type-safe, modern Python CLI framework with automatic help generation |
| Command grouping | Group related commands (reference install/update/list) under parent for clarity |
| Service wiring | Delegate to SDK classes (HippoClient, etc.) rather than duplicating logic |

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| SDK not ready for CLI consumption | Design CLI as thin wrapper; SDK should be stable |
| Command integration complexity | Start with basic wiring, expand as needed |