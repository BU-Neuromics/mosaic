# Comparison Guide

Hippo is a LinkML runtime engine: point it at a LinkML schema and you get a typed Python SDK, a REST API, a relational database, and append-only PROV-O provenance — without writing any of that infrastructure yourself. This page helps you decide whether Hippo is the right tool for your situation, and where to look if it isn't.

---

## When Hippo is the right choice

- **You are working with LinkML schemas.** You want to author your data model once in LinkML YAML and have a runtime materialize it into a typed SDK, REST endpoints, and a relational database — without writing boilerplate infrastructure.
- **You need PROV-O–native provenance.** Every write must produce an immutable `prov:Activity` record that maps to PROV-O predicates, serializable to RDF or JSON-LD without a transformation step — not just an audit log bolted on after the fact.
- **You need schema evolution without losing history.** When you add a field or rename a type, `hippo migrate` applies the change while preserving the `schema_version` recorded at every prior write, so you can reconstruct any entity's shape at any point in time.
- **You want the same code path from notebook to production.** `HippoClient` is the same object whether called in a Jupyter notebook or behind `hippo serve`. Exploratory notebook code is production-ready the moment you point it at a running service — no refactoring required.

---

## When something else is the right choice

| Alternative | Use it instead of Hippo when… |
|---|---|
| **[OpenSpecimen](https://www.openspecimen.org/)** | You need a purpose-built biobank LIMS with sample request workflows, tube-level tracking, consent management, and built-in clinical data collection forms. Hippo has no workflow engine and no built-in UI. |
| **[NIMP](https://www.biccn.org/)** | You're contributing to the BICAN consortium's brain cell atlas. NIMP is the designated tracking system for BICAN data types and submission protocols; Hippo won't speak those consortium conventions. |
| **[BioSamples](https://www.ebi.ac.uk/biosamples/)** | You need to deposit sample metadata into a globally accessible, EBI-hosted registry for journal submission or data-sharing compliance. Hippo is not a public registry. |
| **[Gen3](https://gen3.org/)** | You need cloud-scale data commons with fine-grained access control, data submission portals, and FAIR data sharing at petabyte scale. Hippo has no built-in access-control or public sharing layer. |
| **[Synapse](https://www.synapse.org/)** | Your consortium already uses Synapse for hosted data sharing, project management, and provenance through its web UI. Synapse is a complete SaaS solution; Hippo requires you to deploy and operate your own instance. |
| **[NMDC](https://microbiomedata.org/)** | Your work targets the National Microbiome Data Collaborative's registry and schema standards. NMDC has purpose-built submission workflows and uses its own metadata standards; Hippo can model NMDC-compatible schemas but cannot submit to NMDC's infrastructure. |

---

## What Hippo combines that few others do

Most tracking systems address provenance, schema management, and API design separately. Hippo integrates all three at the architectural level:

**Schema evolution with provenance preservation.** When you add a field and run `hippo migrate`, the engine records the `schema_version` at every write so you can reconstruct any entity's shape at any prior timestamp. Schema evolution and audit history are not separate concerns bolted together — they are linked by construction.

**PROV-O–native provenance.** Hippo's `ProvenanceRecord` is a first-class LinkML class with `class_uri: prov:Activity`. Its fields map directly to PROV-O predicates (`prov:wasGeneratedBy`, `prov:wasAttributedTo`, `prov:startedAtTime`). The internal representation *is* a PROV graph — serializable to RDF or JSON-LD and loadable into any W3C PROV reasoner or RO-Crate packager with no transformation step. Systems that say they are "PROV-compatible" typically mean they can export to PROV formats; Hippo means it can't not.

**SDK-first, transport-agnostic design.** `HippoClient` is the system. REST route handlers call the same `HippoClient` methods you call from a notebook — there is no separate server code path. Bugs are fixed once. Switching between embedded library use and a `hippo serve` instance requires no changes to the code that calls Hippo. Adding a new transport (GraphQL, gRPC) means a new adapter on top of the SDK, not a new implementation of the business logic.

---

## Adjacent tools you may also want

These tools complement Hippo rather than compete with it:

| Tool | How it fits with Hippo |
|---|---|
| **[LinkML](https://linkml.io/)** | Hippo is a runtime for LinkML schemas; LinkML is the modeling language. Use LinkML's own tooling (`gen-pydantic`, `gen-sqlddl`, `linkml-validate`) alongside Hippo for schema linting and code generation. |
| **[RO-Crate](https://www.researchobject.org/ro-crate/)** | A packaging standard for FAIR research objects. Hippo's PROV-O provenance graph can be serialized into an RO-Crate package to make data deposits machine-readable and interoperable. |
| **[GA4GH DRS](https://ga4gh.github.io/data-repository-service-schemas/)** | The Data Repository Service standard API for accessing data objects. Hippo tracks *where* files live; DRS standardizes *how* to fetch them. |
| **[OpenLineage](https://openlineage.io/)** | A standard for capturing data lineage from pipelines (Airflow, Spark, dbt). Pipeline lineage events can be ingested into Hippo as provenance records, connecting pipeline history to entity history. |
| **[CEDAR Workbench](https://metadatacenter.org/)** | A web UI for designing metadata templates. If your team needs guided template authoring before formalizing in LinkML, CEDAR can help structure a schema that Hippo then executes. |
| **[DataHarmonizer](https://github.com/cidgoh/DataHarmonizer)** | A template-driven spreadsheet tool for collecting and validating metadata. DataHarmonizer helps researchers fill in metadata according to a standard; Hippo stores and versions that metadata after collection. |
