# Hippo Design Decisions (ADRs)

Hippo records design decisions as **ADRs** following the **platform-wide convention** — the
canonical process and template live in the parent repo at
[`platform/design/decisions/README.md`](../../../platform/design/decisions/README.md) (see also
the root [`../CLAUDE.md`](../../CLAUDE.md)). ADR files live in this directory;
[`_template.md`](./_template.md) is a local copy of the canonical template for convenience.

## Hybrid adoption (2026-06-17)

Hippo is a mature component with a large body of already-settled, shipped decisions recorded in
the **Key Decisions Log** of [`../INDEX.md`](../INDEX.md). Hippo therefore adopts ADRs
**forward-only**:

- **New, non-trivial, or still-in-flux decisions** get an ADR here, indexed from the INDEX.
- The existing **Key Decisions Log remains the scannable index** of record for the settled,
  shipped decisions and is **backfilled only opportunistically** — when a settled decision is
  revisited and capturing its alternatives is worthwhile — never as a mass migration.

The supersede-don't-delete discipline already used in the Key Decisions Log (entries gain a
`Superseded by` pointer rather than disappearing) matches the ADR lifecycle exactly.

## Index

| ADR | Decision | Status |
|---|---|---|
| [0001](./ADR-0001-graph-level-as-of-query.md) | Graph-level / query-spanning as-of reconstruction | 🟡 Proposed |
| [0002](./ADR-0002-multivalued-reference-slots-as-relationships.md) | Multivalued reference slots persist as relationships (issue #79) | 🟡 Proposed |
| [0003](./ADR-0003-polymorphic-tree-root-ingest.md) | Polymorphic tree-root ingest via `designates_type` dispatch (issue #80) | 🟡 Proposed |
| [0004](./ADR-0004-rename-hippo-to-mosaic.md) | Rename the Hippo component to **Mosaic** (music/art naming convention; PyPI-saturation dissolved by platform ADR-0002) | ✅ Accepted |
