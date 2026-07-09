# Why Mosaic?

Mosaic is a runtime for LinkML schemas. Point it at a schema and you get a typed Python SDK, a REST API, a relational database with append-only provenance, and CEL-based dynamic validation — without writing any of that infrastructure. The schema is the application; Mosaic runs it.

This framing matters because it places Mosaic in the correct comparison space. Mosaic is not a metadata tracking service competing with OpenSpecimen or Gen3 — it is an engine that *runs* whatever schema you give it. Metadata tracking is one application; a bibliography, a software inventory, or a clinical registry are equally valid ones. The engine doesn't know which it is running.

## Three Things That Set Mosaic Apart

!!! abstract "Schema evolution with provenance preservation"
    Because `ProvenanceRecord` is a typed, DDL-generated table — not an event log retrofitted onto an existing schema — a Mosaic deployment can evolve its schema across years without losing the ability to answer "what did this entity look like in 2022?" Migrations run forward; the history stays intact. This is structurally impossible to retrofit into systems whose schemas are hardcoded in application code or bound to a consortium's controlled vocabulary.

!!! abstract "PROV-O-native, not PROV-O-adjacent"
    Most systems emit PROV serializations as an *export* format applied after the fact. Mosaic's provenance graph *is* a PROV graph: `ProvenanceRecord` carries `class_uri: prov:Activity` and its fields map directly to PROV-O predicates. A Mosaic deployment can publish its full provenance as RDF or JSON-LD with no transformation step — directly consumable by W3C PROV reasoners, lineage tools, and RO-Crate packagers. "PROV-compatible" means you can export to PROV. Mosaic means you can't avoid it.

!!! abstract "SDK-first, transport-agnostic"
    The REST API wraps an embedded Python `app` object; it is not the primary interface. This means Mosaic runs in three modes that application platforms structurally can't match: as a Python library imported directly into a Nextflow or Snakemake process, as a REST service, or embedded in-process inside a Jupyter notebook. The same code path runs in all three — the code that works in your notebook works unchanged in production.

---

Not sure whether Mosaic fits your use case? See **[How Mosaic Compares](comparison.md)** — including honest pointers to when another tool is the right choice.
