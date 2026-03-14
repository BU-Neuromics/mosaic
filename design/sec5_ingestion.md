## 5. Ingestion & Integration

**Document status:** Draft v0.1
**Depends on:** sec2_architecture.md, sec3_data_model.md, sec6_provenance.md
**Feeds into:** sec4_api_layer.md

---

### 5.1 Overview

Hippo provides three ingestion paths, corresponding to the three data categories defined in
the platform architecture:

| Path | Mechanism | Data category | Cappella required? |
|---|---|---|---|
| Flat-file ingestion | `hippo ingest <file>` CLI + `IngestionPipeline` SDK | Config data | No |
| Reference data | `hippo reference install/update` CLI + `ReferenceLoader` | Reference data | No |
| External system integration | `ExternalSourceAdapter` implementations + Cappella trigger engine | Operational data | Yes |

All three paths converge on the same `EntityStore.put()` write path and are subject to the
same schema validation and write validator pipeline described in sec2 §2.13.

---

### 5.2 Flat-File Ingestion

The `hippo ingest` command and its underlying `IngestionPipeline` SDK class handle batch
ingestion from flat files. This is the primary path for loading config data (cohort
definitions, protocol catalogs, controlled vocabularies) and for one-off data loads.

**Supported file formats:**

| Format | Notes |
|---|---|
| CSV | Header row required; column names map to entity field names |
| TSV | Same as CSV but tab-delimited |
| JSON | Array of objects at root |
| JSONL | One JSON object per line |

**CLI usage:**

```bash
# Ingest into a named entity type
hippo ingest --entity-type Sample samples.csv

# Ingest with a custom field mapping file
hippo ingest --entity-type Sample --mapping mapping.yaml samples.csv

# Dry run: validate without writing
hippo ingest --entity-type Sample --dry-run samples.csv
```

**Field mapping file (`mapping.yaml`):** Maps source file column names to Hippo schema field
names. Optional — if omitted, column names must match field names exactly.

```yaml
# mapping.yaml
field_mappings:
  specimen_id: external_id
  tissue: tissue_type
  collected_on: collection_date
```

**`IngestionPipeline` SDK class:**

```python
from hippo.core.ingestion import IngestionPipeline, IngestOptions

pipeline = IngestionPipeline(client, options=IngestOptions(
    entity_type="Sample",
    actor="admin",
    dry_run=False,
    on_error="skip",      # "skip" | "stop" — default "stop"
    batch_size=500,
))

result = pipeline.ingest_file("samples.csv", mapping={"specimen_id": "external_id"})
# IngestResult(created=42, updated=5, skipped=2, errors=[...])
```

**Transaction semantics:**

Flat-file ingestion processes records in batches. Each batch is committed atomically. If a
batch fails:
- `on_error="stop"` (default): the ingestion halts; all previously committed batches are
  retained (partial ingest is possible); a detailed error report is returned
- `on_error="skip"`: the failing record is skipped and logged; ingestion continues

**Opinionated decision:** `on_error="stop"` is the default to prevent silent partial imports.
Users who want permissive ingestion must opt in explicitly.

---

### 5.3 Upsert Behaviour and Idempotency

All ingestion paths use **upsert-by-ExternalID** as the core idempotency strategy.

When a record arrives with an identifiable external ID (from any source system), the
ingestion pipeline:
1. Looks up the ExternalID in Hippo's `external_ids` table
2. **Found** → compare incoming field values to current entity state field-by-field
   - Any field differs → write updated entity + `EntityUpdated` provenance event
   - All fields identical → skip write; no provenance event recorded (true no-op)
3. **Not found** → create new entity + `EntityCreated` provenance event + `ExternalIdAdded`
   provenance event

This means re-running the same ingestion file or sync batch is always safe. Identical data
produces no writes. Changed data produces targeted updates with full provenance.

**Atomic upsert operation:**

```python
result = client.upsert(
    entity_type="Sample",
    external_system="starlims",
    external_id="STARLIMS:12345",
    fields={"tissue_type": "brain", "collection_date": "2024-03-01"},
    actor="cappella-sync",
    provenance_context={"sync_run_id": "..."}
)
# UpsertResult(action="created"|"updated"|"unchanged", entity_id="uuid")
```

`upsert()` is an atomic SDK operation — not a separate "check then write". The storage
adapter implements it as a single transaction to prevent race conditions in concurrent
deployments.

**Field comparison for upsert:** Only user-defined fields are compared. System fields
(`id`, `is_available`, `created_at`, `updated_at`) are never overwritten by upsert.

---

### 5.4 Batch Ingestion Transactions

For Cappella sync runs that write many entities, the `BatchIngestionSession` provides
explicit transaction control:

```python
with client.batch_session(actor="cappella-sync", provenance_context={...}) as session:
    for record in adapter.fetch_batch():
        session.upsert(
            entity_type=record["__type__"],
            external_system="starlims",
            external_id=record["id"],
            fields=record["fields"],
        )
    # Commits atomically on __exit__; rolls back on exception
```

**Transaction semantics:**
- All writes in a `BatchIngestionSession` commit together or not at all
- The provenance context is attached to every event in the session
- Session size is bounded by `batch_size` (default: 500 records); larger sessions are
  automatically split into multiple committed batches

**Partial failure handling:** If a batch within a session fails validation, the behaviour
is controlled by `on_error`:
- `stop` (default): rolls back the current batch; committed prior batches are retained;
  detailed `IngestError` is raised with row-level context
- `skip`: the failing record is logged and skipped; the batch continues

---

### 5.5 ExternalSourceAdapter Integration

The `ExternalSourceAdapter` ABC (defined in `hippo/adapters/external/base.py`) defines the
contract for external system connectors. Implementations live in Cappella, not Hippo.

```python
class ExternalSourceAdapter(ABC):
    name: str           # e.g. "starlims", "halo", "redcap"

    @abstractmethod
    def fetch_batch(self, since: datetime | None = None) -> list[dict]: ...
    # Returns records from the source system.
    # `since` is the last successful sync timestamp — enables incremental fetches.
    # Returns ALL records if since=None (full sync).

    @abstractmethod
    def to_hippo_records(self, raw: list[dict]) -> list[HippoRecord]: ...
    # Applies field mapping and transformation to produce Hippo-ready records.
    # Each HippoRecord carries: entity_type, external_system, external_id, fields.

    @abstractmethod
    def validate(self, record: HippoRecord) -> ValidationResult: ...
    # Adapter-level validation before passing to Hippo's write path.
    # Hippo schema validation runs separately and cannot be bypassed.
```

The separation between `fetch_batch` (raw source data) and `to_hippo_records` (transformed
data) is intentional: it makes adapters testable in isolation without a live source system.

---

### 5.6 Reference Data Ingestion

See sec2 §2.14 for the `ReferenceLoader` ABC and `hippo reference install` lifecycle.

Key properties:
- Reference data is ingested via the standard `EntityStore.put()` path — no special write mode
- All reference writes carry `actor: "hippo-reference-<name>"` and a structured provenance
  context recording the loader name and version
- Reference entity types are identical to user-defined types at the storage level — they are
  distinguished only by their origin (installed by a loader vs. created by a user)
- The installed loader version is recorded in `hippo_meta` under key `reference_versions`

**Updating reference data** (`hippo reference update <name> --version <v>`):
1. Fetch the new schema fragment from the loader
2. Diff against the current deployed schema; run `hippo migrate` for any schema changes
3. Re-ingest all data at the new version using `upsert()` — entities that haven't changed
   produce no write; changed terms produce `EntityUpdated` events with provenance context
   recording the version transition
4. Update `hippo_meta.reference_versions`

---

### 5.7 Ingestion Provenance

Every ingestion operation produces provenance events via the standard `ProvenanceManager`.
No separate ingestion audit log is maintained — the provenance log is the record.

The `provenance_context` field on write operations should carry ingestion-specific metadata:

```json
{
  "source": "flat-file",
  "filename": "samples.csv",
  "ingest_run_id": "uuid"
}
```

```json
{
  "source": "cappella",
  "adapter": "starlims",
  "trigger": "nightly_sync",
  "sync_run_id": "uuid"
}
```

```json
{
  "source": "hippo-reference",
  "loader": "fma",
  "version": "3.3",
  "reference_run_id": "uuid"
}
```

This enables audit queries like:
```python
# What was loaded in the last starlims sync?
client.events_by_context("sync_run_id", "uuid-of-sync-run")

# What changed when we updated FMA from 3.2 to 3.3?
client.events_by_context("loader", "fma")
```

---

### 5.8 Open Questions

| Question | Priority | Notes |
|---|---|---|
| Ingestion idempotency for live webhook integrations | High | Full design deferred from MVP. ExternalID upsert handles batch re-runs; webhook retry deduplication (digest cache + TTL) is the planned extension. Out-of-order delivery protection requires source-side timestamps; optional per-adapter config field when scoped. |
| `BatchIngestionSession` isolation level | Medium | Should concurrent sessions be isolated from each other? SQLite WAL handles reads; concurrent writes need a short-lived advisory lock or serialisation at the SDK level. Revisit at PostgreSQL adapter. |

---
