# Hippo — A LinkML Runtime Engine

Hippo is a runtime for LinkML schemas. Point it at a LinkML schema and you get a typed Python SDK, a REST API, a relational database with append-only PROV-O provenance, CEL-based dynamic validation, and standards-compliant interop endpoints — without writing any of that infrastructure yourself. The schema defines the application; Hippo runs it.

One common application is metadata tracking: recording entities, their fields, relationships, and change history over time. That was the origin use case. But Hippo doesn't know it's tracking metadata — it knows it's running a schema. The same engine given a bibliography schema tracks papers and citations. Given an omics schema it tracks biospecimens and data files. Given a software inventory schema it tracks packages and versions.

## What Hippo Gives You From a Schema

Define your entities in LinkML:

```yaml
classes:
  Author:
    is_a: Entity
    attributes:
      name: {required: true}
      orcid: {}
  Publication:
    is_a: Entity
    attributes:
      title: {required: true}
      year: {range: integer}
  Citation:
    is_a: Entity
    attributes:
      citing_id: {range: Publication, required: true}
      cited_id:  {range: Publication, required: true}
```

From that schema, Hippo runs:

- **Typed Python SDK** — `client.create("Author", {...})`, `client.query("Publication")`, `client.get("Citation", id)`
- **REST API** — `POST /ingest`, `GET /entities?entity_type=Author`, `GET /entities/{id}`, and the full OpenAPI surface
- **Relational storage** — DDL-generated tables with referential integrity; no boilerplate schema code
- **Append-only provenance** — every write records who changed what and when; nothing is ever hard-deleted
- **Dynamic validation** — three tiers: LinkML-native shape checks → CEL sandboxed cross-entity rules → Python plugin escape hatch

See the **[Quickstart](quickstart.md)** to have this running in five minutes.

## Three Architectural Properties Worth Knowing Up Front

### 1. Schema evolution with provenance preservation

Hippo is an open-source, configurable metadata tracking service. It gives you a unified, queryable registry of entities, their fields, and the relationships between them — so that downstream systems, analysis pipelines, and data portals can reliably locate and filter metadata without manually managing spreadsheets or bespoke file manifests. See the [Comparison Guide](comparison.md) to evaluate Hippo against alternatives.
Because provenance is a typed, DDL-generated table — not an event log bolted on after the fact — a Hippo deployment can evolve its schema across years without losing the ability to answer "what did this entity look like in 2022?" This is the property that matters most at production scale: the schema grows, the history stays intact.

### 2. PROV-O-native, not PROV-O-adjacent

Most systems emit PROV serializations as an export format. Hippo's provenance graph *is* a PROV graph: `ProvenanceRecord` is a LinkML class with `class_uri: prov:Activity`. A Hippo deployment can publish its provenance as RDF or JSON-LD with no transformation — directly consumable by W3C reasoners, lineage tools, and RO-Crate packagers.

### 3. SDK-first, transport-agnostic

The REST API wraps an embedded Python `app` object; it is not the primary interface. This means Hippo works three ways: as a Python library imported directly into a script or notebook, as a REST service, or in-process inside a larger application. Same code path in all three.

For a full discussion of these properties, see **[Design Principles](design-principles.md)** and **[How Hippo Compares](comparison.md)**.

## Who Is Hippo For?

- **Schema authors** — if you have a data model in LinkML and want it running as a service without wiring up storage, provenance, and validation yourself, Hippo is the runtime.
- **Data engineers and pipeline authors** — if you need a queryable, provenance-tracked registry that pipelines (Nextflow, Snakemake, custom Python) can write to and read from at runtime, Hippo provides this via a direct Python SDK import.
- **Researchers and data managers** — if you need a queryable record of what entities exist, their current state, and their full change history, Hippo provides this without requiring a custom database layer.

## One Application: Metadata Tracking

Hippo's first production deployment is at the VA National PTSD Brain Bank, where it tracks biospecimens, experimental data files, and the derivation chains between them. That deployment shaped the engine's design — the provenance model, the schema-evolution tooling, and the validation tiers all reflect years of real constraints from an evolving biomedical metadata operation.

Hippo carries no domain knowledge from that deployment. There are no hardcoded biomedical entity types, ontology bindings, or sample-tracking conventions in the engine. The brain bank works because it supplies a LinkML schema that describes biomedical entities — exactly as a bibliography deployment supplies a schema describing papers and citations.

Metadata tracking is one application of the engine. The engine is general.

## What Hippo Does Not Do

Hippo is deliberately scoped to running schemas and recording what happens. It does not:

- Store, move, copy, or manage the data files or objects that entities describe
- Execute or schedule pipelines or workflows
- Provide a data portal, web UI, or visualization layer
- Manage authentication or authorization — this belongs in the transport layer
- Replace upstream source-of-truth systems (LIMS, EHR, clinical databases, file stores)

## Where Hippo Sits in the LinkML Toolchain

LinkML's own tools — `gen-pydantic`, `gen-sqlddl`, `linkml-validate` — take a schema and produce code artifacts. They stop at code generation. Hippo picks up where they stop: it takes the same schema and runs it as a live service, handling storage, provenance, validation, and the REST surface without requiring you to wire together the generated artifacts yourself.

```
LinkML schema
      │
      ├── gen-pydantic  →  Pydantic models  (generated code, not a running service)
      ├── gen-sqlddl    →  DDL              (generated code, not a running service)
      └── Hippo         →  running service: SDK + REST API + provenance + validation
```

## Deployment: Same Code Everywhere

The same Hippo codebase runs from a notebook to a production cluster. You choose the deployment tier through configuration — no code changes required.

| Tier | How it works | When to use |
|---|---|---|
| **Local / single-user** | `pip install hippo`, local SQLite file, import directly in Python. No server needed. | Exploratory work, notebook-first development |
| **Small team** | `hippo serve` on a shared host, SQLite or PostgreSQL backend. | Lab group, shared project server |
| **Production** | Container deployment, managed PostgreSQL, auth middleware at the transport layer. | Multi-team, long-running production service |

The code you write against the Python SDK in a notebook is the same code that runs in production. There is no "notebook SDK" and "production SDK" — the transport is the only thing that changes.

## Next Steps

- **[Quickstart](quickstart.md)** — bibliography schema to running service in 5 minutes
- **[Data Model](data-model.md)** — entity types, relationships, provenance, and schema design
- **[Schema Guide](schema-guide.md)** — writing and evolving LinkML schemas for Hippo
- **[How Hippo Compares](comparison.md)** — when Hippo is the right choice, and honest pointers to when it isn't
- **[Design Principles](design-principles.md)** — the six architectural commitments behind the engine
- **[CLI Reference](cli-reference.md)** — complete reference for the `hippo` command-line tool
- **[API Reference](api-reference.md)** — REST API reference
