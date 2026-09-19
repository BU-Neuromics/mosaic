# ADR-0011: `inverse`-declared slots are virtual reverse edges over the forward foreign key

- **Status:** Proposed
- **Date:** 2026-09-11
- **Deciders:** labadorf (pending); clandaverde (issue analysis)
- **Related:** ADR-0002 (multivalued reference slots persist as relationships — the storage
  rule this ADR carves an exception out of); ADR-0005 (edge-only GraphQL references);
  ADR-0006 (typed filter contract — M5a/M5b relationship predicates, whose SQL this ADR
  extends with a third edge shape); ADR-0009 (capability manifest + `QuerySpec`, the consumer
  that surfaced the gap); **Aperture ADR-0035** (`QuerySpec`); `mosaic-demo-small`'s
  `APERTURE_EXON_CONTRACT.md` Decision 8 (the planner re-validates through Mosaic's validator,
  so a reverse edge the validator rejects can never reach a `proposal` turn).
- **Tracking issue:** [#204](https://github.com/BU-Neuromics/mosaic/issues/204).

## Context

A `QuerySpec` `RelatedCondition.edge` can only name a reference slot the **anchor** class
itself holds — a *forward* edge. Given `Sample.donor: {range: Donor}` there is no way to anchor
on `Donor` and quantify over "the samples that point at this donor", even though the reverse
lookup is a plain equality filter on a single FK column. `mosaic-demo-small`'s chat grounding
needs exactly that shape for its flagship example ("show me the donors of those samples
instead"), and because Exon's `QuerySpec` is re-validated in-process before any `proposal` turn
(ADR-0010), the direction cannot be offered client-side without matching server support.

Where the forward-only assumption actually lives was checked against the current head with a
scratch schema, and it is narrower than the issue first described:

- The **validator and compiler are manifest-driven and already pass** a reverse edge as soon
  as the schema declares one. With `Donor.samples: {range: Sample, multivalued: true,
  inverse: donor}` present, `build_capability_manifest` classifies `samples` as a filterable
  multivalued `REFERENCE`, `validate_query_spec` returns valid, and `compile_query_spec` emits
  the storage layer's to-many node `{edge: "samples", quantifier: "some", where: …}`.
- The **storage adapters are the only failing step**: `_reference_edge` resolves every
  multivalued edge against the ADR-0002 `relationships` link table, which the reverse side of
  an FK never writes, so the query returns zero rows. `count_relationship` and read-time
  hydration have the same blind spot.
- Nothing under `src/mosaic` reads LinkML's `SlotDefinition.inverse`, but the attribute
  **survives `class_induced_slots`**, so the registry can consume it directly — no new
  `hippo_*` annotation is needed.
- A hand-authored `inverse:` slot does **not** create a shadow link table: LinkML's
  `SQLTableGenerator` emits one, and `DDLGenerator.generate` already drops every table that is
  not a concrete class. The real hazard is different and worse: ADR-0002 treats the slot as a
  *stored* multivalued reference, so a write carrying `samples: [...]` materializes
  relationship rows — a second, independently writable encoding of the one fact
  `Sample.donor` already stores.

Two constraints frame the decision:

1. **One physical encoding per fact.** LinkML binds `inverse` to `owl:inverseOf`: the reverse
   direction is *entailed* by the forward slot, never asserted independently. Whatever Mosaic
   does must not let the two directions drift.
2. **Every transport derives from one type model** (`schema_typing`). If `Donor.samples`
   appears there as a reference, GraphQL grows a `samples` resolver, a `DonorFilter.samples`
   some/none input and a `samplesCount` field; REST/OpenAPI and the TUI list it; the MCP
   capability resource advertises it. A fix that serves only the `QuerySpec` path would leave
   every other consumer silently returning nothing.

## Decision

**Mosaic will implement LinkML `inverse`-declared slots as virtual (computed) reverse edges
resolved through the forward slot's stored FK column — no column, no link table, no
relationship rows of their own.** The declaring slot is a full member of the type model and
capability manifest, marked `inverse_of: <forward slot>`, and every read, filter, and count
through it delegates to the forward column, so there is exactly one storage encoding of the
relationship regardless of which slot a query traverses.

Concretely:

1. **Declaration.** Schema authors use LinkML's own construct:

   ```yaml
   Donor:
     attributes:
       samples:
         range: Sample
         multivalued: true
         inverse: donor        # Sample.donor is the stored FK; this side is derived
   ```

2. **Load-time validation** (`SchemaError`, aggregated like `hippo_*` annotation failures).
   `inverse` must name a slot induced on the range class whose own range is the declaring
   class or one of its ancestors; that forward slot must be **single-valued**; the declaring
   slot must be `multivalued: true` and must not be `required`, `identifier`, or
   `inlined`/`inlined_as_list`; the range must be an entity class, not a value type.
   **A reverse of a multivalued (relationships-backed) forward slot is rejected** with a
   message saying so — the scope boundary issue #204 draws, stated as an error rather than
   left undefined.

3. **Storage contract.** The slot is excluded from `multivalued_reference_slots` (so
   `_materialize_multivalued_refs` never sees it) and from the Postgres DDL / `schema_diff`
   column walks. Reads hydrate `data[slot]` from the forward column in one batched query per
   page, at the same call sites as ADR-0002 hydration, returning only **available** targets.
   A write payload carrying the slot is **accepted and ignored** — it is derived, so dropping
   it is the definition, not data loss; a get-then-put round-trip therefore stays stable.
   The edge predicate compiles to one correlated `EXISTS` on the target table keyed by the
   forward column (`some`), negated for `none`; `count_relationship` becomes a `COUNT(*)` on
   the target table. As-of reads never carry the slot (it appears in no provenance patch);
   as-of plus a relationship predicate is already a coded error (ADR-0006), unchanged.

4. **Type model and manifest.** `SlotModel` gains `inverse_of: Optional[str]`, set by
   `_classify_slot`. `FieldCapability.predicate` is true when the target is exposed, exactly
   as for forward references. `inverse_of` is serialized in the MCP `schema`/`capabilities`
   resources and GraphQL's `MosaicSlotInfo` so a planner can offer the reverse direction and
   describe it truthfully. GraphQL create/update inputs omit the slot; OpenAPI marks it
   `readOnly`.

5. **Validator and compiler are unchanged.** They gain tests, not code.

6. **No auto-detection of hand-authored pairs.** Two reference slots between the same classes
   can legitimately be two different facts; only an explicit `inverse:` says "one fact, two
   views". A schema-lint *warning* for plausible un-linked pairs is a follow-up, not part of
   this decision.

## Consequences

- `QuerySpec` (and the GraphQL `where:` surface it compiles to) can traverse FK-backed
  relationships in both directions once the schema declares the reverse. Unblocks
  `mosaic-demo-small`'s `add-aperture-chat-panel` Phase 2.
- ADR-0002's rule "multivalued reference slot ⇒ relationship rows" acquires one carve-out:
  a multivalued reference slot **with `inverse`** is virtual. The four consumers of
  `multivalued_reference_slots` (both adapters, `pg_ddl_generator`, `schema_diff`) share the
  exclusion so they cannot drift.
- The relationship-predicate SQL gains a third edge shape (to-one FK, to-many link table,
  **reverse FK**) in both adapters and in `count_relationship`.
- Read amplification: hydrating the reverse id list into `data` on every read is the
  ADR-0002 contract and keeps every transport correct with no transport-specific code, but a
  very high-fanout parent pays for it on each `get`. Acceptable for current deployments; an
  opt-out annotation is a small later addition if a real schema hits it.
- Polymorphism: the reverse predicate joins only the named target table, matching the existing
  to-many predicate (which likewise does not fan across per-subclass tables). Shared
  limitation, recorded not solved.
- The demo repo can model `Sample.donor`'s reverse idiomatically instead of hand-adding a
  second slot and keeping it in sync in `generate.py`.

## Alternatives considered

- **Hand-author a plain back-reference slot** (`Donor.samples: {range: Sample, multivalued:
  true}` with no `inverse`). Rejected: under ADR-0002 that is a second, independently
  writable encoding of one fact (FK column *and* relationship rows) with nothing tying them
  together — drift by construction, and every schema wanting reverse traversal would have to
  repeat the manual synchronization.
- **Semijoin at the `QuerySpec` layer** (resolve the reverse edge with a `storage.find()` on
  the target, then filter the anchor with `id IN [...]`), as the graph-neighborhood resolver
  already does. Rejected: it gives up `compile_query_spec`'s purity (it would execute queries
  or force its caller into a second round trip) and fixes only the MCP path, while the type
  model would still expose the slot to GraphQL filters, resolvers, and counts that would
  silently return nothing. Only the storage layer can give every transport one encoding.
- **A Mosaic-specific annotation** (`hippo_inverse`) instead of LinkML's `inverse`. Rejected:
  LinkML already has the idiomatic construct with the right semantics (`owl:inverseOf`), it
  survives slot induction, and reusing it keeps schemas portable to other LinkML tooling.
- **Auto-detect equivalent slot pairs and treat them as inverses.** Rejected as unsound (see
  Decision item 6).
- **Support reverse traversal of multivalued forward slots too.** Deferred: no consumer needs
  it (no GraphQL query exists to compensate against those either), and the link-table reverse
  is a different SQL shape. Explicitly rejected at load so the boundary is legible.

## Notes / open sub-questions

- Whether `inverse` should also be honoured on the *forward* side (LinkML allows declaring it
  on either slot). This ADR reads it only on the multivalued, derived side; a forward slot
  carrying `inverse` is left alone.
- Whether the reverse id list should be hydrated eagerly (this ADR) or resolved lazily per
  transport — revisit only if read amplification shows up in a real deployment.
