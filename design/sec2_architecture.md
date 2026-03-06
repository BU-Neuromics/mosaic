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
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────────────┐    │
│  │   STARLIMS  │  │    HALO     │  │   Donor DB           │    │
│  │  (future)   │  │  (future)   │  │   (future)           │    │
│  └─────────────┘  └─────────────┘  └──────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Package Structure

```
hippo/
│
├── core/                        # All business logic — no I/O
│   ├── client.py                # HippoClient: primary public interface
│   ├── query.py                 # QueryEngine: filter, join, resolve
│   ├── ingestion.py             # IngestionPipeline: validate & write entities
│   ├── provenance.py            # ProvenanceManager: change tracking
│   ├── schema.py                # SchemaConfig: load & validate YAML schema
│   └── models.py                # Pydantic models for all core entities
│
├── adapters/
│   ├── base.py                  # Abstract base classes (EntityStore, ExternalSource)
│   ├── storage/
│   │   ├── sqlite.py            # SQLite adapter (v0.1)
│   │   ├── postgres.py          # PostgreSQL adapter (future, stub in v0.1)
│   │   └── dynamodb.py          # DynamoDB adapter (future, stub in v0.1)
│   └── external/                # Ingest-only adapters for upstream systems
│       ├── base.py              # ExternalSourceAdapter ABC
│       ├── starlims.py          # STARLIMS placeholder
│       ├── halo.py              # HALO placeholder
│       └── donor_db.py          # Donor DB placeholder
│
├── rest/
│   ├── app.py                   # FastAPI app object (primary artifact)
│   ├── routers/
│   │   ├── donors.py
│   │   ├── samples.py
│   │   ├── datafiles.py
│   │   └── datasets.py
│   ├── dependencies.py          # Dependency injection (SDK client, config)
│   ├── auth.py                  # Auth middleware stub (no-op in v0.1)
│   └── schemas.py               # Pydantic request/response models
│
├── graphql/                     # Future — empty package in v0.1
│   └── __init__.py
│
├── cli/
│   └── main.py                  # Typer CLI: init, serve, ingest, validate
│
├── config/
│   ├── loader.py                # Config file loading & validation
│   └── defaults.py              # Default config values
│
└── schema/
    └── default_schema.yaml      # Bundled default schema for omics datasets
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
    def query(self, entity_type: str, filters: list[Filter]) -> list[dict]: ...

    @abstractmethod
    def put(self, entity_type: str, entity: dict, actor: str) -> ProvenanceRecord: ...

    @abstractmethod
    def history(self, entity_type: str, entity_id: str) -> list[ProvenanceRecord]: ...
```

**ExternalSourceAdapter ABC** (external ingestion adapters must implement):

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

#### Plugin System

Hippo supports third-party adapter packages via Python entry points (`importlib.metadata`).
This allows the community to develop, publish, and share adapters as standalone pip-installable
packages without forking Hippo or contributing to the core repository.

**Declaring a plugin adapter** (in the third-party package's `pyproject.toml`):

```toml
[project.entry-points."hippo.storage_adapters"]
myadapter = "mypkg.adapters.storage:MyStorageAdapter"

[project.entry-points."hippo.external_adapters"]
myinstitution_lims = "mypkg.adapters.lims:MyLIMSAdapter"
```

Once the package is `pip install`ed alongside Hippo, the adapter type becomes available in
`hippo.yaml` with no other registration step:

```yaml
adapter:
  type: myadapter
  myadapter:
    some_setting: value
```

**Adapter discovery at startup:** Hippo's adapter registry loads all entry points under the
`hippo.storage_adapters` and `hippo.external_adapters` groups on initialization. Built-in
adapters (sqlite, postgres, dynamodb, and the bundled external placeholders) are registered
via the same entry points mechanism in Hippo's own `pyproject.toml` — there is no separate
internal registration path. If two installed packages register the same adapter type name, Hippo
raises a `ConfigError` at startup with a clear conflict message.

**Interface stability and versioning:** The `EntityStore` and `ExternalSourceAdapter` ABCs are
part of Hippo's public API. Once v1.0 is released, breaking changes to these interfaces
constitute a semver-major version bump. Pre-1.0 minor versions may make breaking changes with
deprecation notices in the changelog. Plugin authors should pin to compatible Hippo versions
using `hippo>=0.x,<0.(x+1)` until v1.0 is reached.

**Community adapter registry:** A curated list of known community adapters will be maintained
in the Hippo repository README, following the convention established by projects like pytest
and Flask.

### 2.4 Config System

All Hippo configuration lives in a single YAML file (`hippo.yaml` by default, overridable via
`HIPPO_CONFIG` environment variable). The config file has three top-level sections:

```yaml
# hippo.yaml

adapter:                         # Which storage backend to use and its settings
  type: sqlite
  sqlite:
    path: ./hippo.db

schema:                          # Path to entity schema definition (see Section 3)
  path: ./schema.yaml            # Defaults to bundled default_schema.yaml if omitted

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

# hippo/rest/routers/samples.py
@router.get("/samples")
def list_samples(filters: SampleQuery, client: HippoClient = Depends(get_client)):
    return client.query.samples(filters)
```

For local SDK usage, the caller instantiates `HippoClient` directly:

```python
from hippo import HippoClient, HippoConfig

client = HippoClient(HippoConfig.from_file("hippo.yaml"))
results = client.query.samples(brain_region="hippocampus", modality="RNASeq")
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
| `hippo init` | Scaffold a new `hippo.yaml` config and schema file in the current directory |
| `hippo serve` | Start the REST API server using settings from `hippo.yaml` |
| `hippo ingest <source> <file>` | Run a batch ingestion from a flat file against a named source adapter |
| `hippo validate` | Validate config and schema files without starting the server |
| `hippo migrate` | Apply any pending schema migrations to the current storage backend |
| `hippo status` | Show current config, adapter type, entity counts, and schema version |

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
├── ValidationError           # Entity failed schema validation
├── IngestError               # Batch ingestion failure (with row context)
├── AdapterError              # Storage backend error (wraps underlying exception)
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

**SQLite adapter (v0.1, included in core):**

| Package | Purpose |
|---|---|
| (stdlib `sqlite3`) | No additional dependency — uses Python standard library |

**REST API (optional install extra):**

| Package | Purpose |
|---|---|
| `fastapi` | REST framework |
| `uvicorn[standard]` | ASGI server |

**Installation extras:**

```bash
pip install hippo                  # Core SDK + SQLite only
pip install hippo[rest]            # Adds REST API server
pip install hippo[postgres]        # Adds PostgreSQL adapter (future)
pip install hippo[all]             # Everything
```

**Plugin adapter packages:**

Third-party adapters are distributed as independent packages and installed alongside Hippo.
Hippo discovers them automatically via entry points — no manual registration required:

```bash
pip install hippo hippo-adapter-redshift   # hypothetical community adapter
```

Plugin packages should follow the naming convention `hippo-adapter-<name>` for discoverability.
The Hippo repository provides a `hippo-adapter-template` cookiecutter for bootstrapping new
adapter packages with the correct entry point declarations, ABC implementations, and test
scaffolding pre-wired.

---

