# ADR-0009: Mosaic hosts an MCP boundary over a server-derived capability manifest and the QuerySpec artifact

- **Status:** Proposed
- **Date:** 2026-08-28
- **Deciders:** labadorf (pending), proposed via cross-repo design session
  (`BU-Neuromics/mosaic-demo-small`)
- **Related:** ADR-0004 (Hippo → Mosaic rename), ADR-0006 (typed GraphQL filter contract —
  `where:`, issue #153), ADR-0007 (aggregation & ordering surface, issue #154); **Aperture
  ADR-0035** (Accepted 2026-08-19 — cross-class queries are a typed `QuerySpec` artifact,
  co-designed against this repo's ADR-0006/0007); `mosaic-demo-small`'s
  `openspec/changes/add-mosaic-mcp-boundary/` (`proposal.md`, `design.md`, `tasks.md`, spec
  deltas — the full, detailed spec this ADR summarizes for ratification purposes); mosaic
  issue #54 Part A (authn/authz, referenced not resolved by this ADR).
- **Tracking issue:** [#177](https://github.com/BU-Neuromics/mosaic/issues/177) (original,
  bundled scope; superseded by the split issues this ADR proposes filing — see Consequences).

## Context

Three places currently maintain independent, drifting ideas of "what can this Mosaic deployment
do": Mosaic itself has no capability-manifest concept beyond raw `hippoSchema` introspection
(`graphql/resolvers.py`'s `hippoSchema` resolver, `serve/routers/schema.py`'s `GET /schemas`);
`mosaic-demo-small`'s Exon hand-maintains a JSON file built by probing a running instance from
outside; Aperture derives its own `Capabilities` object from live introspection independently
(`web/src/data/capabilities.ts`). This is not hypothetical: Aperture's own accepted ADR-0029
already asserts "no facet counts, no server sort, no range filters" against Mosaic — an
assumption `mosaic-demo-small`'s own live verification found already false, since ADR-0006/0007's
rollout (issues #153–#158, all closed) shipped exactly those capabilities.

Separately, `mosaic-demo-small`'s Exon project built its own typed query IR, `QueryPlan` — an
ordered, multi-step pipeline with a bounded `relatedTo` fan-out, designed before this repo's
`where:` relationship-predicate support existed (issue #148). Aperture's `QuerySpec` (ADR-0035)
was designed *with* this repo's ADR-0006/0007 rollout and already expresses everything
`QueryPlan` does, plus selection semantics (`columns`, with an explicit `aggregate`-vs-`explode`
choice on to-many paths) `QueryPlan` lacks entirely. Exon was not part of that co-design loop.

An issue (#177) proposing an MCP (Model Context Protocol) server for this repo — a fourth
transport alongside REST/GraphQL/CLI, giving any LLM-driven client (Exon today; a planned Reel
engine; a generic coding agent; the MCP Inspector) one shared, validated way to query Mosaic
without hand-maintaining a capability copy — was filed bundling six scope items as one issue. A
triage review of that issue correctly declined to pick it up as-is: no ADR existed yet for
capability-manifest computation or the new transport (against this repo's own stated convention
that new framework-level machinery gets an ADR first, the same way `QuerySpec`'s shape went
through Aperture's ADR-0035 and this repo's ADR-0006/0007), and the issue bundled six items that
should be separately reviewable, mirroring how the ADR-0006/0007 rollout was split (#153/#155,
#154/#156). This ADR is that missing design doc, proposed for ratification before the
implementation issues it unblocks are filed.

## Decision

Mosaic will host an MCP server as a new, optional transport (`mosaic/mcp/`, alongside the
existing `mosaic/serve/` REST and `mosaic/graphql/` GraphQL modules, mounted the same
conditional way via a new `--mcp` flag on `mosaic serve`, sharing the same `MosaicClient`/
`SchemaRegistry` every other transport already uses — no new data-access path). It exposes:

1. **A server-derived capability manifest**, computed from `SchemaRegistry`/`hippoSchema` and
   exposed as an MCP resource (alongside a schema resource re-exposing `hippoSchema` itself):
   supported filter ops per field kind, enum values per enum-backed field, relationship-predicate
   support, and aggregation/sort/search availability — replacing the need for any consumer to
   hand-maintain or independently re-derive this.
2. **`QuerySpec` as the canonical typed query artifact this boundary accepts** (Aperture's
   ADR-0035 shape: `v`, `anchor`, `mode`, `criteria`, `columns`, `sort`, `asOf`) — not a
   Mosaic-invented shape, and not `QueryPlan`. A Python implementation ports the same discipline
   Aperture's client-side `validateQuerySpec()` (`web/src/query/querySpec.ts`) already
   demonstrates: total, introspection-driven, every anchor/slot/op/edge checked against what the
   endpoint actually advertises, with `enumValues` and the rest of the schema available
   in-process (no introspection round-trip).
3. **`validate_query_spec`/`execute_query_spec` MCP tools**, `execute_query_spec` validating
   unconditionally before compiling a validated `QuerySpec` into this repo's existing `where:`/
   aggregation/search GraphQL surface (or calling internal resolvers directly — an implementation
   detail, not part of this decision). Validation errors are specific and actionable
   per-criterion (naming the offending slot/op/edge and, for enum/op mismatches, the valid set) —
   load-bearing, not cosmetic, since it is what lets a generic MCP client (not just a bespoke
   planner) converge on a correct query through validate → read error → fix → retry alone.
4. **A `construct-query-spec` MCP Prompt** carrying procedural "how to" guidance a raw schema/
   capability dump doesn't convey — resolve field names as LinkML slot names, never camelCase;
   express relationship existence/predicates as a single `RelatedCondition`, never a client-side
   per-id fan-out; a to-many `columns` path needs an explicit `aggregate`-vs-`explode` choice;
   `asOf` cannot combine with a `RelatedCondition` on the same `QuerySpec`. Without this, every
   future MCP client independently reinvents (or fails to reinvent) this knowledge.
5. **No write or mutation tool of any kind on this surface.** Beyond that hard constraint, this
   ADR takes no position on authn/authz — that remains issue #54 Part A's decision. This surface
   must not ship in a way that implies the existing `X-Mosaic-Actor` provenance header is
   authentication or authorization.

## Consequences

- A fourth transport exists with the same trust boundary (or lack thereof) as REST/GraphQL today
  — this ADR does not change or improve on the current no-authn/authz state, it only constrains
  the new surface to not make it worse (item 5).
- The capability-manifest computation becomes a piece of framework-level machinery other
  consumers (REST, a future admin UI, the TUI) could eventually read from too, though nothing
  beyond the MCP resource is in scope here.
- `QuerySpec` becomes a second consumer-facing typed-query artifact this repo's team should be
  aware it is now committed to supporting alongside the raw `where:` GraphQL argument — it is not
  a new wire format invented here, but this repo now has validator/executor code that must track
  Aperture's ADR-0035 if that artifact's shape changes.
- **Unblocks filing the split implementation issues** this ADR's ratification was blocking,
  replacing the original bundled #177 (see the tracking issue note above): one per scope item
  above, each independently reviewable and implementable, mirroring #153/#155 and #154/#156.
- Does not resolve, and explicitly defers: whether `ColumnSpec`'s `explode` output on a to-many
  path can be scoped to match a `RelatedCondition`'s own sub-criteria on the same edge (ADR-0035
  itself: "field-level schema lives with the implementation" — unresolved even in the source
  ADR); exact MCP resource/tool naming; transport choice (stdio vs. Streamable HTTP) for local
  development vs. any future deployed use.

## Alternatives considered

- **Host the MCP boundary inside `mosaic-demo-small`'s Exon instead of Mosaic** (the original
  design, `mosaic-demo-small`'s now-superseded `add-exon-mcp-boundary` proposal). Rejected: it
  perpetuates the exact three-way capability-manifest duplication this ADR exists to close, and
  requires every future consumer (a Reel engine, a generic coding agent) to either route through
  Exon specifically or reimplement the same validator/executor independently.
- **Invent a new typed query IR for this boundary** rather than adopting `QuerySpec`. Rejected:
  `QuerySpec` was already co-designed against this repo's own ADR-0006/0007 rollout and already
  expresses more than any alternative this repo's team would need to design from scratch —
  building a fourth IR (after `where:`, `QueryPlan`, and `QuerySpec`) when two repos have already
  jointly designed and shipped the real solution would be pure duplication.
- **No MCP surface; consumers keep talking to REST/GraphQL directly.** Rejected: this doesn't
  address the capability-manifest duplication (the actual, evidenced problem), and Aperture's
  own architecture already treats "capabilities derived from live introspection" as a core
  principle this repo is best positioned to serve directly rather than have every consumer
  re-derive.
- **Ship the original bundled issue #177 as one PR.** Rejected per the triage review: six scope
  items of framework-level machinery is design work, not a bounded fix, and should follow this
  repo's own convention of ADR-first for new framework-level concepts, split into separately
  reviewable increments the way ADR-0006/0007 were.

## Notes / open sub-questions

- Exact MCP resource/tool/prompt naming (`mosaic://schema`, `mosaic://capabilities`,
  `construct-query-spec`, etc.) is illustrative, not mandated by this ADR — pick names that fit
  current MCP conventions and this codebase at implementation time.
- Transport: stdio (matching local MCP dev conventions, e.g. the MCP Inspector) is the likely
  default for initial implementation; Streamable HTTP is deferred until an actual deployed-service
  use case exists. Not binding — an implementation-time call.
- Whether the capability-manifest computation should be exposed beyond the MCP resource (e.g. a
  REST endpoint) is out of scope for this ADR; nothing here precludes it later.
- The full, detailed spec (data shapes, validator behavior scenario-by-scenario, task breakdown)
  lives in `mosaic-demo-small`'s `openspec/changes/add-mosaic-mcp-boundary/` — this ADR
  summarizes it for ratification purposes but that repo's spec is the source of truth for
  implementation detail.
