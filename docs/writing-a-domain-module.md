# Writing a Domain Module

This guide walks through building a **`DomainModule`** — the first-party, mutable-data species of `SchemaPackage` — and authoring a versioned data migration that Hippo runs with full provenance behind a hard validation gate.

> **Who this is for:** Python developers who own a deployment's locally authored operational data (samples, donors, projects — the lab's authoritative records) and need to evolve its *shape* across schema versions. If you distribute externally maintained reference datasets instead, read [Writing a Reference Loader](writing-a-reference-loader.md).

> **`DomainModule` is one kind of `SchemaPackage`.** Both `DomainModule` and `ReferenceLoader` are *species* of the genus `SchemaPackage` (`hippo.core.loaders.schema_package`), which captures the reusable part — *"contribute a versioned, pinnable schema fragment"* (`name`, `description`, `versions()`, `schema_fragment()`, `depends_on()`, optional `validate()`, and the `provision`/`evolve`/`deprovision` lifecycle hooks).
>
> - A **reference loader** wraps *external, reconstructible* data; its `deprovision` prunes willingly.
> - A **domain module** owns *first-party, mutable* data and migrates it **in place**. Because those records are the deployment's authoritative data, the migration is append-only, id-keyed, and provenanced — every step is auditable and replay-recoverable.

---

## How a domain migration differs from `hippo migrate`

| | `hippo migrate` (DDL) | `DomainModule.evolve` (data) |
|---|---|---|
| Handles | *Additive* schema changes (new optional column, new class) | *Semantic* data transformations (split a field, re-root a value set, change units) |
| Touches | Table structure | Row contents |
| Trigger | Automatic on schema reconcile | A declared `(from_version → to_version)` migration step |

They are complementary. Reach for a `DomainModule` migration only when the *data* must change shape, not just the table.

---

## Project layout

```
hippo-domain-mylab/
├── pyproject.toml
└── src/
    └── hippo_domain_mylab/
        ├── __init__.py
        └── module.py      # DomainModule subclass (required)
```

---

## 1. The module class

Subclass `DomainModule` from `hippo.core.loaders.domain_module`. Implement the two genus abstract methods (`versions()`, `schema_fragment()`) plus `migration_steps()`. `provision`/`deprovision` are inherited genus no-ops — domain data arrives via `hippo ingest`, not at schema-install time.

```python
# src/hippo_domain_mylab/module.py
from hippo.core.loaders.domain_module import (
    DomainModule,
    MigrationContext,
    MigrationStep,
)


class MyLabModule(DomainModule):
    name = "mylab"                       # must match the entry point key
    description = "MyLab operational domain data"

    def versions(self) -> list[str]:
        return ["v1", "v2"]

    def populates_types(self) -> list[str]:
        # Declarative — which classes this module fills with first-party data.
        return ["Specimen"]

    def schema_fragment(self) -> dict:
        return {
            "id": "https://example.org/hippo/mylab",
            "name": "mylab",
            "default_prefix": "mylab",   # REQUIRED — must match name
            "prefixes": {"mylab": "https://example.org/hippo/mylab/"},
            "classes": {
                "Specimen": {
                    "is_a": "Entity",
                    "attributes": {
                        # v2 shape: `kind` is now required
                        "label": {"range": "string"},
                        "kind":  {"range": "string", "required": True},
                    },
                },
            },
        }

    def migration_steps(self) -> list[MigrationStep]:
        return [
            MigrationStep(
                from_version="v1",
                to_version="v2",
                transform=self._v1_to_v2,
                description="derive `kind` from legacy `label`",
            ),
        ]

    def _v1_to_v2(self, ctx: MigrationContext) -> None:
        # Read old-shape records, stage new-shape records that supersede them.
        for old in ctx.client.query("Specimen").items:
            data = old["data"]
            ctx.plan.migrate(
                "Specimen",
                old["id"],
                {"label": data.get("label"), "kind": _infer_kind(data)},
            )
```

The `schema_fragment()` contract is identical to a reference loader's: `default_prefix` **must** equal `name`, and Hippo auto-injects `provided_by: <name>@<version>` on every introduced element.

---

## 2. The migration model: read-old → write-new → supersede-old

A migration **transform** receives a `MigrationContext` and stages its intended changes onto `ctx.plan`. It must **not** write to the client directly — staging is what keeps the validation gate ahead of every committed write.

- **Read** old-shape records via `ctx.client` (e.g. `ctx.client.query("Specimen").items`). `query()` applies no default page limit, so this reads the whole set.
- **Stage** new-shape records via `ctx.plan`:

| Method | Use it for |
|---|---|
| `plan.migrate(entity_type, old_id, new_data)` | The common 1:1 case. Stages a **new** record (fresh id) and supersedes `old_id` by it. Returns the new id. |
| `plan.put(entity_type, new_data)` | A net-new record with no supersession (e.g. one half of a split). Returns the new id. |
| `plan.supersede(old_id, new_id)` | An explicit supersession edge (pairs with `put` for splits/merges). |

`migrate()` and `put()` fill in system fields for you: a fresh `id`, and `is_available: True` (a migration produces live records). You write only domain slots.

> **Why a new entity, not an in-place edit?** Each migrated record becomes a *new* entity that **supersedes** the old one. Supersession (not same-id upsert) is what emits the `supersede` provenance event and the `superseded_by` lineage edge. A consequence to keep in mind: after migration, anything referencing an old id now points at a superseded/unavailable entity — resolve via the `superseded_by` edge.

---

## 3. The staged dry-run validation gate

`DomainModule.evolve` runs the matching step, then — **before any committed write** — stages the transform's new-shape records and validates them against the **fully merged schema**. This is the in-process equivalent of:

```bash
hippo ingest --validate-schema <merged-dir> --dry-run
```

The migration **commits only on green**. If the staged output does not validate, `evolve` raises `MigrationGateError` and the deployment's data is left exactly as it was — no new rows, no supersessions, no provenance events.

```python
from hippo.core.exceptions import MigrationGateError

module = MyLabModule()
try:
    result = module.evolve(client, "v1", "v2")
except MigrationGateError as exc:
    # exc.errors carries the underlying LinkML validation messages.
    print(f"migration blocked: {exc.errors}")
else:
    print(f"migrated {result.created} record(s)")   # LoadResult
```

Only the **new** records are validated; the old superseded rows keep their v1 shape and are never re-validated. `evolve` returns a `LoadResult` whose `created` counts the new-shape records written.

> The gate requires a schema-backed client (one constructed with a `registry`). A migration against a schemaless client raises `MigrationGateError` rather than committing unvalidated writes.

---

## 4. Provenance & lineage

Every step produces a traceable, append-only audit trail:

- the **new** record gets a `create` provenance event;
- the **old** record gets a `supersede` event, tagged `actor=<module name>` and `reason="<name> migration <from>→<to>"` so the history reads as a migration, not a hand edit;
- a `superseded_by` relationship edge links old → new.

Inspect it with `client.history(entity_id)` or by following the `superseded_by` field (`client.get(entity_id, include_unavailable=True)`).

---

## 5. Declaring the entry point

Register the module under the genus group `hippo.schema_packages` (a `DomainModule` is not a reference loader, so it does **not** use `hippo.reference_loaders`):

```toml
[project.entry-points."hippo.schema_packages"]
mylab = "hippo_domain_mylab.module:MyLabModule"
```

The entry-point key must match `DomainModule.name`.

---

## 6. Scope: single-hop today, multi-hop next

This release runs **single-hop** migrations: `evolve(client, from_version, to_version)` resolves the one declared step whose `(from_version, to_version)` matches exactly. A hop with no directly declared step fails loud (`MigrationStepNotFoundError`) rather than silently doing nothing.

Multi-hop chaining — composing intermediate steps across a migration DAG, shortcut edges, and the below-floor fail-loud — is the next increment (sec11 §11.3). `MigrationStep` is already a bare DAG edge, so declaring several consecutive steps today is forward-compatible: each one is small and independently testable, and the resolver will compose them.

---

## Checklist

- [ ] `DomainModule.name` matches the `hippo.schema_packages` entry-point key
- [ ] `schema_fragment()` declares `default_prefix: <name>`
- [ ] Each `MigrationStep` covers one consecutive `(from_version → to_version)` hop
- [ ] The transform reads via `ctx.client` and stages via `ctx.plan` — it never writes to the client directly
- [ ] New-shape records validate against the merged schema (the gate enforces this; test it with both a valid and a deliberately invalid transform)
- [ ] `populates_types()` declares the classes the module owns
