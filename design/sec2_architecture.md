## 2. Architecture

### 2.1 Component Overview

Hippo is structured as three concentric layers. The Core SDK contains all business logic and is
the only layer required for local deployment. The Transport Layer is optional and adds network
accessibility. The Infrastructure Layer is optional and adds cloud-scale storage backends.

```
┌─────────────────────────────────────────────────────────────────┐
│                        Transport Layer (optional)               │
│                                                                 │
│   ┌─────────────────────────┐   ┌───────────────────────────┐  │
│   │      REST API           │   │    GraphQL API (future)   │  │
│   │  hippo.rest (FastAPI)   │   │   hippo.graphql           │  │
│   │  `hippo serve`          │   │                           │  │
│   └────────────┬────────────┘   └─────────────┬─────────────┘  │
└────────────────│─────────────────────────────│─────────────────┘
                 │  both call SDK directly      │
┌────────────────▼─────────────────────────────▼─────────────────┐
│                         Core Python SDK                         │
│                                                                 │
│   ┌──────────────┐  ┌──────────────┐  ┌─────────────────────┐  │
│   │  QueryEngine │  │IngestionPipe │  │  ProvenanceManager  │  │
│   └──────────────┘  └──────────────┘  └─────────────────────┘  │
│   ┌──────────────┐  ┌──────────────┐  ┌─────────────────────┐  │
│   │ SchemaConfig │  │  EntityStore │  │  HippoClient        │  │
│   │  (YAML)      │  │  (interface) │  │  (public API)       │  │
│   └──────────────┘  └──────┬───────┘  └─────────────────────┘  │
└──────────────────────────── │ ───────────────────────────────── ┘
                              │  adapter interface
┌─────────────────────────────▼───────────────────────────────────┐
│                    Infrastructure Layer (adapters)              │
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────────────┐    │
│  │   SQLite    │  │  PostgreSQL │  │  DynamoDB (future)   │    │
│  │  (v0.1)     │  │  (future)   │  │                      │    │
│  └─────────────┘  └─────────────┘  └──────────────────────┘    │
│                                                                 │
│  (External system connectors live in Cappella, not Hippo.        │
│   Hippo defines ExternalSourceAdapter ABC only — see §2.3)       │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Package Structure

```
hippo/
│
├── core/                        # All business logic — no I/O
│   ├── client.py                # HippoClient: primary public interface
│   ├── query.py                 # QueryEngine: filter, join, resolve, search
│   ├── ingestion.py             # IngestionPipeline: validate & write entities
│   ├── provenance.py            # ProvenanceManager: change tracking
│   ├── schema.py                # SchemaConfig: load, validate, inheritance resolution
│   └── models.py                # Pydantic models for all core entities
│
├── adapters/
│   ├── base.py                  # Abstract base classes (EntityStore, ExternalSourceAdapter)
│   └── storage/
│       ├── sqlite.py            # SQLite adapter (v0.1)
│       ├── postgres.py          # PostgreSQL adapter (future, stub in v0.1)
│       └── dynamodb.py          # DynamoDB adapter (future, stub in v0.1)
│       # External system connectors (STARLIMS, HALO, etc.) live in Cappella, not here.
│       # Hippo defines ExternalSourceAdapter ABC in base.py only.
│
├── validators/
│   ├── base.py                  # WriteValidator ABC, WriteOperation, ValidationResult
│   ├── registry.py              # Validator registry: entry point discovery + config instantiation
│   ├── cel_engine.py            # CEL evaluation: expand path resolution, context building
│   ├── expander.py              # Entity graph expander: path parsing, batch fetch, cycle detection
│   └── builtins/
│       ├── ref_check.py         # ref_check preset
│       ├── count_constraint.py  # count_constraint preset
│       ├── immutable_field.py   # immutable_field preset
│       ├── field_required_if.py # field_required_if preset
│       └── no_self_ref.py       # no_self_ref preset
│
├── reference/
│   ├── base.py                  # ReferenceLoader ABC, LoadResult
│   └── registry.py              # Reference loader entry point discovery + version tracking
│
├── rest/
│   ├── app.py                   # FastAPI app object (primary artifact)
│   ├── routers/
│   │   ├── entities.py          # Generic entity CRUD — dispatches by entity_type
│   │   ├── relationships.py     # Relationship operations
│   │   ├── search.py            # Fuzzy search endpoints
│   │   └── ingestion.py         # Batch ingestion endpoints
│   ├── dependencies.py          # Dependency injection (SDK client, config)
│   ├── auth.py                  # Auth middleware stub (no-op in v0.1)
│   └── schemas.py               # Pydantic request/response models
│
├── graphql/                     # Future — empty package in v0.1
│   └── __init__.py
│
├── cli/
│   └── main.py                  # Typer CLI: init, serve, ingest, validate, reference
│
├── config/
│   ├── loader.py                # Config file loading & validation
│   └── defaults.py              # Default config values
│
└── schema/
    └── example_schema.yaml      # Example schema for reference
```

### 2.3 Adapter Pattern

All storage and external system integrations implement abstract base classes defined in
`hippo/adapters/base.py`. The active adapter is selected at runtime based on the `adapter.type`
field in the Hippo config file — no code changes required to switch backends.

**EntityStore ABC** (storage adapters must implement):

```python
class EntityStore(ABC):
    @abstractmethod
    def get(self, entity_type: str, entity_id: str) -> dict: ...

    @abstractmethod
    def query(self, entity_type: str, filters: list[Filter],
              include_unavailable: bool = False) -> list[dict]: ...

    @abstractmethod
    def put(self, entity_type: str, entity: dict, actor: str,
            provenance_context: dict | None = None) -> ProvenanceRecord: ...

    @abstractmethod
    def history(self, entity_type: str, entity_id: str) -> list[ProvenanceRecord]: ...

    @abstractmethod
    def search(self, entity_type: str, field: str, query: str,
               limit: int = 10, min_score: float = 0.0) -> list[ScoredMatch]: ...

    @abstractmethod
    def search_capabilities(self) -> set[str]: ...
    # Returns supported search modes e.g. {"fts", "embedding", "synonym"}
    # Hippo validates at startup that all schema-declared search modes are in this set.
```

`ScoredMatch` is a core SDK type (adapter-agnostic):

```python
@dataclass
class ScoredMatch:
    entity_id: str
    entity_type: str
    field: str
    value: str
    score: float          # 0.0–1.0
    match_mode: str       # "fts" | "embedding" | "synonym" | "exact"
```

**ExternalSourceAdapter ABC** (external ingestion adapters must implement — implementations
live in Cappella, not Hippo; this ABC defines the contract only):

```python
class ExternalSourceAdapter(ABC):
    @abstractmethod
    def fetch_batch(self, since: datetime | None = None) -> list[dict]: ...

    @abstractmethod
    def validate(self, record: dict) -> ValidationResult: ...
```

Adapters are registered in a central registry keyed by adapter type string. When Hippo loads
its config, it resolves the configured adapter type to its implementation class and instantiates
it with the adapter-specific config block:

```yaml
# hippo.yaml
adapter:
  type: sqlite
  sqlite:
    path: /data/hippo.db

# Future postgres example:
# adapter:
#   type: postgres
#   postgres:
#     host: localhost
#     port: 5432
#     database: hippo
#     pool_size: 10
```

New storage backends can be added by implementing `EntityStore` and registering the class — no
changes to core SDK logic required.

**Multi-instance adapter contract:** Storage adapters used in multi-instance deployments
(i.e. any adapter other than SQLite) **must** implement entity creation and ExternalID
registration as atomic server-side upserts — not as application-level read-then-write
sequences. Specifically:

- Entity creation: `INSERT ... ON CONFLICT (id) DO UPDATE` (PostgreSQL) or equivalent
  conditional write (DynamoDB)
- ExternalID registration: atomic on `(entity_id, system, external_id)` uniqueness constraint

This requirement exists because multiple Hippo instances can receive concurrent writes for the
same entity or ExternalID. Application-level read-then-write creates a race window that leads
to duplicate records. The SQLite adapter is exempt because SQLite's single-writer WAL mode
serialises all writes naturally — concurrent multi-instance use of SQLite is not supported
(see sec7 §7.3).

#### Plugin System

Hippo supports third-party adapter packages via Python entry points (`importlib.metadata`).
This allows the community to develop, publish, and share adapters as standalone pip-installable
packages without forking Hippo or contributing to the core repository.

Hippo defines four entry point groups. Third-party packages can contribute to any of them:

| Entry point group | Purpose | Naming convention |
|---|---|---|
| `hippo.storage_adapters` | Storage backend implementations | `hippo-adapter-<name>` |
| `hippo.external_adapters` | External system connector implementations (Cappella ships these) | `cappella-adapter-<name>` |
| `hippo.write_validators` | Write-path business rule validators | `hippo-validators-<name>` |
| `hippo.reference_loaders` | Reference ontology data loaders | `hippo-reference-<name>` |

**Declaring plugins** (in the third-party package's `pyproject.toml`):

```toml
[project.entry-points."hippo.storage_adapters"]
myadapter = "mypkg.adapters.storage:MyStorageAdapter"

[project.entry-points."hippo.write_validators"]
my_rules = "mypkg.validators:MyBusinessRuleValidator"

[project.entry-points."hippo.reference_loaders"]
my_ontology = "mypkg.reference:MyOntologyLoader"
```

Once the package is `pip install`ed alongside Hippo, its contributions are available with no
other registration step:

```yaml
adapter:
  type: myadapter
  myadapter:
    some_setting: value
```

**Discovery and conflict handling:** All four entry point groups are loaded at startup via
`importlib.metadata`. Built-in contributions (sqlite adapter, bundled write validators,
bundled reference loaders) are registered via the same entry points mechanism in Hippo's own
`pyproject.toml` — no separate internal registration path. If two packages register the same
name within the same group, Hippo raises a `ConfigError` at startup with a clear conflict
message identifying both packages.

**Startup validation:** After loading all plugins, Hippo performs cross-validation:
- Schema-declared `search:` modes are checked against `adapter.search_capabilities()` — fail
  fast if a mode is declared but not supported by the active adapter
- Schema-declared `requires:` loader names are checked against installed reference loaders —
  fail fast with a clear install suggestion if a required loader is missing

**Interface stability:** The ABCs for all four plugin groups are part of Hippo's public API.
Once v1.0 is released, breaking changes constitute a semver-major bump. Pre-1.0, breaking
changes may occur with deprecation notices. Plugin authors should pin to compatible Hippo
versions using `hippo>=0.x,<0.(x+1)` until v1.0 is reached.

**Community registry:** A curated list of known community plugins will be maintained in the
Hippo repository README. The naming conventions above (`hippo-adapter-<name>`,
`hippo-reference-<name>`, etc.) ensure discoverability via PyPI search.

### 2.4 Config System

All Hippo configuration lives in a single YAML file (`hippo.yaml` by default, overridable via
`HIPPO_CONFIG` environment variable). The config file has three top-level sections:

```yaml
# hippo.yaml

adapter:                         # Which storage backend to use and its settings
  type: sqlite
  sqlite:
    path: ./hippo.db

schema:                          # Path to entity schema definition (required — see Section 3)
  path: ./schema.yaml            # Hippo DSL; no default schema is bundled

validators:                      # Path to business rule validators config (optional)
  path: ./validators.yaml        # If omitted, only schema-level validation runs

server:                          # REST API server settings (only needed for hippo serve)
  host: 0.0.0.0
  port: 8000
  workers: 4
```

Config is loaded once at startup, validated against a Pydantic model, and injected throughout
the SDK via a `HippoConfig` object. Components never read config files directly — they receive
a config object at instantiation. This keeps components testable in isolation.

### 2.5 Dependency Injection

The `HippoClient` is the single entry point to all SDK functionality. It is instantiated with
a `HippoConfig` and internally constructs the appropriate adapter, query engine, and provenance
manager. In the REST layer, a single `HippoClient` instance is created at server startup and
injected into route handlers via FastAPI's dependency system:

```python
# hippo/rest/dependencies.py
def get_client() -> HippoClient:
    return _client  # module-level singleton initialized at startup

# hippo/rest/routers/entities.py
@router.get("/{entity_type}")
def list_entities(entity_type: str, filters: dict, client: HippoClient = Depends(get_client)):
    return client.query(entity_type, **filters)
```

For local SDK usage, the caller instantiates `HippoClient` directly:

```python
from hippo import HippoClient, HippoConfig

client = HippoClient(HippoConfig.from_file("hippo.yaml"))
results = client.query("Item", category="task", completion_state="pending")
```

### 2.6 Transport Layer

#### REST API

The REST API is a FastAPI application defined in `hippo/rest/app.py`. The `app` object is the
primary artifact — `hippo serve` is a thin CLI wrapper that runs it via Uvicorn:

```python
# hippo serve is equivalent to:
uvicorn hippo.rest.app:app --host 0.0.0.0 --port 8000 --workers 4
```

Embedding in a larger application is a first-class use case:

```python
# Future workflow executor or data portal:
from hippo.rest.app import app as hippo_app
platform_app.mount("/hippo", hippo_app)
```

The REST API exposes an OpenAPI schema automatically via FastAPI at `/docs` and `/openapi.json`.

#### GraphQL (future)

`hippo/graphql/` is an empty package in v0.1, reserved for a Strawberry-based GraphQL transport
adapter that will wrap the SDK directly — not via REST. Auth middleware will be shared between
REST and GraphQL transports (see 2.7).

### 2.7 Auth Placeholder

Authentication and authorization are explicitly out of scope for v0.1. The REST layer includes
a no-op auth middleware stub in `hippo/rest/auth.py` that passes all requests through. This
stub defines the interface that real auth middleware will implement, so adding JWT/RBAC in a
future version requires replacing the stub — not restructuring the app.

The SDK is auth-unaware by design. Auth is validated at the transport layer before the SDK is
called. The `actor` field on all write operations accepts a string identity passed in by the
transport layer (defaulting to `"anonymous"` in v0.1).

### 2.8 CLI

The Hippo CLI is implemented with Typer and installed as the `hippo` command:

| Command | Description |
|---|---|
| `hippo init` | Scaffold a new `hippo.yaml`, `schema.yaml`, and `validators.yaml` in the current directory |
| `hippo serve` | Start the REST API server using settings from `hippo.yaml` |
| `hippo ingest <source> <file>` | Run a batch ingestion from a flat file (CSV/JSON/JSONL) |
| `hippo validate [--schema <path>]` | Validate config, schema, and validators files without starting the server; `--schema` runs the full namespace graph validation pass (cross-namespace reference checks, duplicate entity detection, circular dependency detection) and reports all errors with file locations |
| `hippo migrate` | Apply any pending schema migrations to the current storage backend; includes namespace graph validation pass before applying any changes |
| `hippo status` | Show current config, adapter type, entity counts, schema version, and installed plugins |
| `hippo compile-schema` | Compile `schema.yaml` to LinkML on demand; output to `./schema.linkml.yaml` |
| `hippo reference list` | List all installed reference loaders and their installed versions |
| `hippo reference install <name> [--version <v>]` | Install a reference dataset; merges schema fragment and runs migrate |
| `hippo reference update <name> [--version <v>]` | Update an installed reference dataset to a newer release |

**Namespace validation in `hippo validate --schema`**

When `--schema` is provided (or the schema path is read from `hippo.yaml`), the validator
runs the full namespace graph validation pass:

1. Discovers all schema files recursively from the schema path (file or directory)
2. Builds the `NamespaceRegistry` from all discovered files
3. Checks for duplicate `(namespace, entity_name)` pairs across files
4. Validates all `references.entity_type` FQNs against the registry
5. Detects circular namespace dependencies via topological sort

Each error identifies the unresolved FQN or circular dependency path and the file where it
originates:

```
SchemaValidationError: Unresolved FQN reference 'ghost.Entity' in field 'sample.ghost_id'
  declared in: schemas/tissue.yaml

SchemaValidationError: Circular namespace dependency detected: tissue → omics → tissue
  first reference: schemas/omics.yaml field 'datafile.sample_id' (references tissue.Sample)

SchemaValidationError: Duplicate entity 'Sample' in namespace 'tissue'
  first declared in: schemas/tissue.yaml
  also declared in: schemas/tissue_legacy.yaml
```

**Namespace validation in `hippo migrate`**

`hippo migrate` runs the namespace graph validation pass before generating the migration
plan. If namespace validation fails, the migration is aborted and errors are reported before
any changes are applied. This ensures no schema with broken namespace references can be
applied to storage.

### 2.9 Deployment Tiers

| Tier | Storage Adapter | Transport | Auth | Typical Use |
|---|---|---|---|---|
| **Local** | SQLite | None (SDK direct) | None | Single researcher, notebook |
| **Single-host** | SQLite or PostgreSQL | REST (`hippo serve`) | None (v0.1) / JWT (future) | Small team, shared server |
| **Cloud (AWS)** | PostgreSQL (RDS) or DynamoDB | REST behind ALB | JWT + RBAC | Enterprise deployment |

All tiers use the same `hippo` Python package. Tier is determined entirely by config.

### 2.10 Concurrency Model

In v0.1 with the SQLite adapter, Hippo uses SQLite's WAL (Write-Ahead Logging) mode, which
supports concurrent reads with a single writer. The REST server runs with multiple Uvicorn
workers (configurable, default 4), each with its own SQLite connection. Write operations acquire
a short-lived lock. This is sufficient for the expected v0.1 workload of infrequent batch
writes and moderate concurrent reads from pipelines.

Connection behavior per adapter:

| Adapter | Concurrency Model |
|---|---|
| SQLite (v0.1) | WAL mode, per-worker connection, short write lock |
| PostgreSQL (future) | Connection pool via `psycopg2`, configurable pool size |
| DynamoDB (future) | Native AWS concurrent access, no connection management |

### 2.11 Error Handling

Errors propagate outward from adapter → SDK → transport layer in a consistent hierarchy:

```
HippoError (base)
├── EntityNotFoundError       # Requested entity does not exist
├── ValidationError           # Entity failed validation
│   ├── SchemaValidationError     # Failed schema-level field/type/enum check
│   └── RuleValidationError       # Failed a write validator rule (carries validator name)
├── IngestError               # Batch ingestion failure (with row context)
├── AdapterError              # Storage backend error (wraps underlying exception)
├── SearchCapabilityError     # Schema declares a search mode the active adapter doesn't support
└── ConfigError               # Invalid or missing configuration
```

The SDK raises typed `HippoError` subclasses. The REST layer catches these and maps them to
appropriate HTTP status codes (404, 422, 500, etc.) with a consistent JSON error body:

```json
{
  "error": "EntityNotFoundError",
  "message": "Sample 'abc-123' not found",
  "detail": {}
}
```

Raw adapter exceptions (e.g., SQLite errors) are always wrapped in `AdapterError` before
surfacing — internal implementation details never leak through the SDK boundary.

### 2.12 Dependencies

**Core SDK (required):**

| Package | Purpose |
|---|---|
| `pydantic>=2.0` | Entity models, config validation, schema enforcement |
| `pyyaml` | Config and schema file parsing |
| `typer` | CLI framework |
| `cel-python` | CEL expression language for config-driven validators |

**SQLite adapter (v0.1, included in core):**

| Package | Purpose |
|---|---|
| (stdlib `sqlite3`) | No additional dependency — uses Python standard library |

**REST API (optional install extra):**

| Package | Purpose |
|---|---|
| `fastapi` | REST framework |
| `uvicorn[standard]` | ASGI server |

**References extra (optional):**

| Package | Purpose |
|---|---|
| Bundled `hippo-reference-*` loaders | FMA, Ensembl, GO, etc. (each is a separate package) |

**Installation extras:**

```bash
pip install hippo                   # Core SDK + SQLite + CEL validators
pip install hippo[rest]             # Adds REST API server
pip install hippo[postgres]         # Adds PostgreSQL adapter (future)
pip install hippo[references]       # Adds bundled reference loader packages
pip install hippo[all]              # Everything

# Community plugins installed alongside:
pip install hippo hippo-adapter-redshift    # hypothetical storage adapter
pip install hippo hippo-reference-reactome  # community reference loader
```

Plugin packages should follow the naming convention `hippo-adapter-<name>` for discoverability.
The Hippo repository provides a `hippo-adapter-template` cookiecutter for bootstrapping new
adapter packages with the correct entry point declarations, ABC implementations, and test
scaffolding pre-wired.

---


### 2.13 Validation Infrastructure

Hippo's write path enforces two tiers of validation before committing any change.

#### Tier 1: Schema validation (built-in)

Runs on every write. Enforces structural constraints declared in `schema.yaml`:
- Required fields present
- Field types and value ranges
- Enum values within declared set
- `ref` fields point to an existing, available entity of the correct type
- Relationship cardinality constraints

Raises `SchemaValidationError` on failure. Cannot be disabled.

#### Tier 2: Config-driven business rule validators (`validators.yaml`)

Optional. Loaded from the path declared in `hippo.yaml`. If the key is absent, this tier is
skipped entirely.

**`validators.yaml` config format:**

```yaml
validators:
  - name: <unique identifier used in error messages>
    entity_types: [EntityType, ...]     # omit or null to match all types
    on: [create, update, availability_change, relationship]  # default: all
    expand:                             # paths to pre-fetch before CEL evaluation
      - field_name
      - field_name.child
      - field_name[].child_field        # [] = iterate over relationship collection
    when: '<CEL expression>'            # skip this validator if false
    condition: '<CEL expression>'       # must be true to pass
    requires: [field_a, field_b]        # shorthand: fields must be non-null
    error: "message with {entity.field} and {existing.field} substitutions"
    max_expand_list_size: 200           # default 200, hard cap 1000
```

**CEL evaluation context:**

| Variable | Contents |
|---|---|
| `entity` | Proposed new state (with expand paths pre-fetched and populated in place) |
| `existing` | Current state before write; `null` for creates |

**Expand path mechanics:**
- `field` — scalar `ref` field: replaces the ID value with the full referenced entity dict
- `field.child` — chain: expands `child` on the fetched entity
- `field[]` — relationship collection: replaces list of IDs with list of entity dicts (one batch query)
- `field[].child` — expands `child` on each element of the collection
- Paths sharing a prefix are deduplicated — a shared entity is fetched only once
- Cycle detection via visited set prevents infinite loops on self-referential relationships
- `max_expand_list_size` prevents runaway expansion on large collections

**Write validator execution order:**
```
1. Schema validation (Tier 1, always first → SchemaValidationError on failure)
2. Config-driven validators (Tier 2, declaration order → RuleValidationError on failure)
3. Plugin validators (Tier 3, priority order → RuleValidationError on failure)
4. Commit write + record provenance event
```
The entire sequence is atomic — any failure rolls back the transaction and no provenance event
is written.

**`WriteValidator` ABC** (Tier 3 — Python plugin validators):

```python
class WriteValidator(ABC):
    name: str                           # used in error messages and logs
    entity_types: list[str] | None      # None = run for all types; subtype-aware
    priority: int = 0                   # lower runs first; schema validation = -1

    @abstractmethod
    def validate(self, operation: WriteOperation,
                 client: HippoClient) -> ValidationResult: ...

@dataclass
class WriteOperation:
    kind: Literal["create", "update", "availability_change", "relationship"]
    entity_type: str
    entity_id: str
    proposed: dict
    existing: dict | None               # None for creates
    actor: str
    provenance_context: dict | None     # structured context from caller (e.g. workflow run)

@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
```

**`entity_types` and schema inheritance:** With polymorphic inheritance, `entity_types: [Sample]`
covers `Sample` and all subtypes. `entity_types: [BrainSample]` targets only that subtype.
Redundant entries (child listed with parent) emit a startup warning.

**Built-in validator presets** (ergonomic shortcuts in `validators.yaml`, not separate code paths):

| Preset `type:` | Equivalent pattern |
|---|---|
| `ref_check` | `expand` + `condition` checking a referenced entity |
| `count_constraint` | `expand` with `[]` + `size()` CEL condition |
| `immutable_field` | `on: [update]` + `condition: entity.field == existing.field` |
| `field_required_if` | `when` pre-condition + `requires` |
| `no_self_ref` | `condition` checking entity does not reference itself |

---

### 2.14 Reference Loader System

Reference loaders install community-standard ontology data as regular Hippo entities.
Distributed as `hippo-reference-<name>` packages, discovered via `hippo.reference_loaders`
entry points.

**`ReferenceLoader` ABC:**

```python
class ReferenceLoader(ABC):
    name: str           # e.g. "fma", "ensembl", "go"
    description: str

    @abstractmethod
    def versions(self) -> list[str]: ...
    # Available version strings

    @abstractmethod
    def entity_types(self) -> list[str]: ...
    # Entity type names this loader creates

    @abstractmethod
    def schema_fragment(self) -> dict: ...
    # Entity type + relationship definitions in Hippo DSL.
    # Merged into the deployed schema on install.

    @abstractmethod
    def load(self, client: HippoClient, version: str, **kwargs) -> LoadResult: ...
    # Ingests the reference dataset at the given version.
```

**Install lifecycle (`hippo reference install <name> [--version <v>]`):**
1. Resolve loader from `hippo.reference_loaders` entry points
2. Call `loader.schema_fragment()` and merge into deployed schema
3. Run `hippo migrate` (additive = non-interactive; structural = prompt for confirmation)
4. Call `loader.load(client, version)` to ingest
5. Record `{loader_name: version}` in `hippo_meta` under key `reference_versions`

**User schema dependency declaration:**

```yaml
# schema.yaml
requires:
  - hippo-reference-fma>=3.3
  - hippo-reference-ensembl>=GRCh38.109
```

`hippo validate` fails fast with a clear install suggestion if a required loader is missing.
Users reference loader-provided entity types by name without redeclaring them.

**Collision detection:** Two packages declaring the same entity type name → `ConfigError` at
startup identifying both packages.

**Extending loader-provided types:** Deferred to post-v0.1.

---

### 2.15 Error Hierarchy

All Hippo exceptions inherit from `HippoError`. The full hierarchy is specified in
`appendix_b_implementation_guide.md §B.3`. Summary:

**Configuration errors (startup time):**

| Exception | Trigger | HTTP |
|---|---|---|
| `ConfigError` | Invalid/missing `hippo.yaml` fields; unknown config keys | — |
| `SchemaError` | Invalid `schema.yaml`; cycles; unknown type references | — |
| `MigrationError` | Destructive migration attempt | — |
| `SearchCapabilityError` | Schema declares unsupported search mode | — |
| `AdapterNotFoundError` | No adapter registered for configured type | — |

**Runtime errors (request time):**

| Exception | Trigger | HTTP |
|---|---|---|
| `ValidationError` | Write rejected by any validator tier | 422 |
| `EntityNotFoundError` | Entity UUID not found or unavailable | 404 |
| `RelationshipNotFoundError` | Relationship edge UUID not found | 404 |
| `ExternalIdNotFoundError` | No entity for `(system, external_id)` | 404 |
| `ExternalIdConflictError` | ExternalID already belongs to a different entity | 409 |
| `SchemaVersionMismatchError` | Instance schema differs from storage (future v0.2) | 503 |
| `AdapterError` | Storage backend failure; wraps underlying exception | 500 |

**Wrapping rule:** Adapters must catch all backend-specific exceptions and re-raise as
`AdapterError(cause=original)`. Raw `sqlite3` or `psycopg2` exceptions must never
reach the caller. See `appendix_b_implementation_guide.md §B.3` for full class definitions.

---
