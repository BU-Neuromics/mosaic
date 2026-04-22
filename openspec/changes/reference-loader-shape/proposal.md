# Reference Loader Shape

## Why

`ReferenceLoader` was declared in `hippo_core` during Wave 1's
`hippo-core-schema` as a placeholder with only a `name` slot. sec9 §9.5
flagged two design questions that must be resolved before the shape is
finalized. This change resolves them and lands the full slot inventory.

Parallel-trackable with Wave 2 changes; depends only on
`hippo-core-schema`.

## What Changes

### Resolve the two open design questions

1. **Multi-class loaders.** `entity_type` must be multivalued — a single
   loader commonly populates several classes (ontology loaders are the
   canonical example). Decision needed on: ordered vs. set cardinality;
   whether per-class metadata (count estimate, dependencies) is carried
   alongside each entry or lives on separate records.
2. **Referential boundary of `schema_fragment`.** A `ReferenceLoader`
   instance may reference classes declared in its own `schema_fragment`.
   Those classes don't exist in the merged SchemaView until the plugin's
   fragment is installed. Decide: when is the fragment merged, when is
   the ReferenceLoader instance validated, and what is the error surface
   if validation fails?

### Full slot inventory

After resolution, declare `ReferenceLoader` with the finalized slots in
`hippo_core.yaml`. Bump `hippo_core` minor version.

### Migration of existing loaders

Audit any existing plugins registered under `hippo.reference_loaders`.
Each declares a `schema_fragment` and populates entities. Update to the
new shape.

## Capabilities

### New Capabilities

- `reference-loader-full-shape` — finalized `ReferenceLoader` slot
  inventory and load-order contract.

### Modified Capabilities

- `hippo-core-schema` — gains the finalized ReferenceLoader.
- `hippo-reference-loaders` plugin entry point — contracts reshaped
  around the LinkML class.

## Dependencies

- **Blocked by:** `hippo-core-schema`.
- **Parallel to:** Wave 2 changes (`provenance-as-linkml-class`,
  `computed-temporal-fields`).

## Acceptance

- Two design questions resolved and documented in `sec9_decisions.md`.
- `ReferenceLoader` finalized in `hippo_core.yaml` with the full slots.
- Existing reference-loader plugins migrated and passing their tests.
- Introspection exposes the installed loaders via `SchemaRegistry` and
  REST (`GET /schemas/reference_loaders` or similar).
- Full suite green.
