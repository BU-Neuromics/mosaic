# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Component Overview

**Hippo** is the Metadata Tracking Service (MTS) for the BASS platform. It tracks *where data lives* and *what it describes* — not the data itself. See the root `../CLAUDE.md` for repo-wide conventions.

## Spec Structure

Design spec sections live in `design/` and are numbered sequentially. `design/INDEX.md` is the source of truth for section status, key decisions, and open questions — always check it before modifying or drafting spec content.

Current section status (check INDEX.md for latest):
- **sec1** (Overview) and **sec2** (Architecture): Complete and approved
- **sec3** (Data Model): In review — actively evolving
- **sec4–sec7**: Not started — stubs only

Each section declares `Depends on` / `Feeds into` headers. Read dependencies before editing a section.

## Architecture (for spec writing)

Hippo has three concentric layers — only the Core SDK is required:

1. **Core Python SDK** (`hippo/core/`): All business logic. Key classes: `HippoClient` (public API), `QueryEngine`, `IngestionPipeline`, `ProvenanceManager`, `SchemaConfig`.
2. **Transport Layer** (optional): REST via FastAPI (`hippo serve`), GraphQL (future). These are thin wrappers calling the SDK directly.
3. **Infrastructure Layer** (adapters): Storage backends (SQLite v0.1, PostgreSQL future) and external system adapters (STARLIMS, HALO, Donor DB — all future stubs).

Adapters are registered via entry points: `hippo.storage_adapters`, `hippo.external_adapters`.

## Data Model Essentials

- **Config-driven relational** storage with a **graph-shaped API** — entity types and relationships defined in LinkML schema, not hardcoded.
- Schemas are authored directly in **LinkML** format (no intermediate DSL or compilation step).
- System fields (`id`, `is_available`) live on entity tables; temporal fields (`created_at`, `updated_at`, `schema_version`) live exclusively in the provenance log and are computed at read time.
- **No hard deletes** — availability transitions (`is_available` boolean) replace deletion.
- Entity status values: `active`, `archived`, `superseded`, `deleted`, `distributed`, `removed`.

## Writing & Editing Guidelines

- User-facing docs live in `docs/`. Design specs in `design/` are internal engineering documents.
- When drafting new spec sections (sec4–sec7), follow the structure of sec1–sec3: numbered subsections, tables for structured data, ASCII diagrams for architecture.
- Keep the **SDK-first** principle consistent: business logic in SDK, transport layers are thin wrappers.
- Update `design/INDEX.md` whenever a section's status changes or a new key decision is made.
- The `images/` directory holds diagrams referenced by spec documents.
