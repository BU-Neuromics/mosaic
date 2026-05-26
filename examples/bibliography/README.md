# Bibliography Worked Example

A complete Hippo example using a citation-graph domain. Exercises every major
SDK feature: polymorphism, full-text search, validators, supersession, and
provenance history.

## What's in this directory

| File | Purpose |
|---|---|
| `schemas/bibliography.yaml` | LinkML schema (Author, Publication hierarchy, Citation, Authorship) |
| `config.json` | Hippo configuration pointing at SQLite and the validators file |
| `validators.yaml` | CEL validator: DOI format check on JournalArticle |
| `sdk_example.py` | Python script — runs the complete demo end-to-end |
| `rest_example.md` | Equivalent operations as `curl` snippets against `hippo serve` |
| `provenance_example.md` | How to walk the PROV-O provenance chain after supersession |

## Schema overview

```
Entity (abstract, hippo_core)
├── Author            name*, orcid (indexed), email
├── Publication (abstract)
│   ├── JournalArticle  title* (fts5), year, doi (indexed), journal, volume, pages
│   ├── Preprint        title* (fts5), year, doi, server (fts5), preprint_id (indexed)
│   └── ConferencePaper title* (fts5), year, doi, conference_name (fts5)
├── Venue             name* (fts5), issn (indexed), country
├── Authorship        author_id (indexed), publication_id (indexed), position*
└── Citation          citing_id (indexed), cited_id (indexed)
```

`*` = required field.  `(fts5)` = full-text-search indexed.  `(indexed)` = B-tree indexed.

**Polymorphism note**: `Publication` is abstract and has no backing table.
To query all publications you must iterate each concrete subtype and merge
the results. See `sdk_example.py §7 — Polymorphic queries`.

## Prerequisites

```bash
pip install hippo-sdk          # production install
# or for development:
pip install -e ../../           # install from source tree
```

## Run the SDK example

```bash
cd examples/bibliography
python sdk_example.py
```

The script creates a fresh SQLite database at `./data/hippo.db` on every run.

Expected output:

```
=== Hippo Bibliography Example ===

Created authors: 4d04f383…, 5a860923…, e1f0d5d4…

Created Preprint: e941d21b…  (arXiv:1706.03762)
Created JournalArticle: 5cdfb56f…  doi:10.5555/3295222.3295349
Created Citation: BERT (897021b9…) → Transformer (5cdfb56f…)
Updated BERT preprint abstract

--- Polymorphic query: all Publications ---
  [JournalArticle]     Attention Is All You Need
  [Preprint]           Attention Is All You Need
  [Preprint]           BERT: Pre-training of Deep Bidirectional Transformers f
Total publications: 3

--- FTS search: 'transformer' ---
  Attention Is All You Need

--- FTS search: 'BERT' across Preprint ---
  BERT: Pre-training of Deep Bidirectional Transformers for La
(Note: FTS indexes each write; deduplicate by id if an entity was updated)

get(Preprint, e941d21b…):
  title   : Attention Is All You Need
  server  : arXiv
  version : 1

--- Supersession: arXiv preprint → NeurIPS article ---
Preprints visible after supersede: 1
Preprint still in DB (include_unavailable=True): id=e941d21b…

--- Provenance history for the preprint ---
  create        2026-05-26T...  {"title": "Attention Is All You Need", ...}
  supersede     2026-05-26T...  {"reason": "Published as NeurIPS 2017 proceedings paper"}

--- Done ---
```

## Validate the schema

`linkml-validate` cannot resolve the bundled `hippo_core` import without
a custom importmap, so schema validation runs via Hippo's own loader:

```python
from hippo.linkml_bridge import SchemaRegistry
registry = SchemaRegistry.from_path("./schemas")
print("Classes:", sorted(registry.schema_view.all_classes().keys()))
# → ['Author', 'Authorship', 'Citation', 'ConferencePaper', 'Entity',
#    'ExternalID', 'JournalArticle', 'Preprint', 'Process',
#    'ProvenanceRecord', 'Publication', 'ReferenceLoader', 'Validator', 'Venue']
```

`SchemaRegistry.from_path()` raises `SchemaError` on first load if the
schema is structurally invalid (bad `is_a`, unresolved ranges, etc.).

## Key SDK patterns demonstrated

### Client initialisation

```python
from hippo.linkml_bridge import SchemaRegistry
from hippo.core.client import HippoClient
from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter
from hippo.core.pipeline import ValidationPipeline
from hippo.core.validators.write_validator import CELWriteValidator

registry = SchemaRegistry.from_path("./schemas")
storage  = SQLiteAdapter("./data/hippo.db", schema_registry=registry)
pipeline = ValidationPipeline()
pipeline.add_validator(CELWriteValidator(validators_path="./validators.yaml"))
client   = HippoClient(storage=storage, registry=registry, pipeline=pipeline)
```

### Polymorphic queries

Because `Publication` is abstract, query each concrete subtype:

```python
publications = []
for subtype in ("JournalArticle", "Preprint", "ConferencePaper"):
    publications.extend(client.query(subtype).items)
```

### Entity supersession (SDK only)

```python
# Mark the preprint superseded by the published article.
# REST does not expose entity-level supersession; use the SDK directly.
client.supersede_entity(
    entity_id=preprint_id,
    replacement_id=article_id,
    reason="Published as NeurIPS 2017 proceedings paper",
    actor=vaswani_id,
)
```

### Provenance history

```python
history = client.history(preprint_id)
for entry in history:
    print(entry["operation_type"], entry["timestamp"])
```

## REST API

See `rest_example.md` for `curl` snippets covering ingest, get, list,
full-text search, external ID management, and soft delete.

## Provenance walk

See `provenance_example.md` for a PROV-O-aligned interpretation of the
preprint → article supersession chain.
