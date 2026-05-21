# Writing a Reference Loader

This guide walks through building a `hippo-reference-<name>` package from scratch. By the end you will have a loader that installs, upgrades, integrates with the CLI, and passes hermetic CI tests.

> **Who this is for:** Python developers building or maintaining a `hippo-reference-*` package. Users who only want to *use* reference data should read [Reference Loaders](reference-loaders.md) instead.

---

## Project layout

```
hippo-reference-myontology/
├── pyproject.toml
├── src/
│   └── hippo_reference_myontology/
│       ├── __init__.py
│       ├── loader.py      # ReferenceLoader subclass (required)
│       ├── cli.py         # Typer sub-app (optional)
│       └── fixtures/
│           └── tiny.tar.gz   # bundled "test" fixture dataset
```

Use `hippo_reference_<name>` as the Python package name and `hippo-reference-<name>` as the distribution name. This naming convention makes your loader discoverable via PyPI search.

---

## 1. The loader class

Subclass `ReferenceLoader` from `hippo.core.loaders.reference`. At minimum you must implement four abstract methods: `versions()`, `entity_types()`, `schema_fragment()`, and `load()`.

```python
# src/hippo_reference_myontology/loader.py
from hippo.core.loaders.reference import LoadResult, ReferenceLoader
from hippo.core.client import HippoClient


class MyOntologyLoader(ReferenceLoader):
    name = "myontology"             # must match the entry point key
    description = "My Ontology terms (v2023+)"

    def versions(self) -> list[str]:
        # Return opaque slugs in any order. Include "test" for CI.
        return ["test", "2023-01", "2024-01"]

    def entity_types(self) -> list[str]:
        # Declarative — tells Hippo what classes this loader writes.
        # Does NOT control ingestion order; your load() code does that.
        return ["MyTerm"]

    def schema_fragment(self) -> dict:
        return {
            "id": "https://example.org/hippo/myontology",
            "name": "myontology",
            "default_prefix": "myontology",            # REQUIRED — must match name
            "prefixes": {
                "myontology": "https://example.org/hippo/myontology/",
            },
            "classes": {
                "MyTerm": {
                    "is_a": "Entity",
                    "attributes": {
                        "label":  {"range": "string", "required": True},
                        "code":   {"range": "string", "required": True},
                        "parent": {"range": "MyTerm"},
                    },
                },
            },
        }

    def load(
        self,
        client: HippoClient,
        version: str,
        params=None,
    ) -> LoadResult:
        if version == "test":
            return self._load_fixture(client)
        archive = client.cached_fetch(
            f"https://myontology.example.org/releases/{version}.tar.gz",
            loader_name=self.name,
        )
        return self._ingest_archive(client, archive)

    def _load_fixture(self, client: HippoClient) -> LoadResult:
        import importlib.resources, tarfile, json
        fixture = importlib.resources.files("hippo_reference_myontology.fixtures").joinpath("tiny.tar.gz")
        entity_ids: list[str] = []
        with tarfile.open(str(fixture)) as tar:
            for member in tar.getmembers():
                row = json.loads(tar.extractfile(member).read())
                result = client.put("MyTerm", row)
                entity_ids.append(result["id"])
        return LoadResult(created=len(entity_ids), entity_type="MyTerm", entity_ids=entity_ids)

    def _ingest_archive(self, client: HippoClient, archive_path) -> LoadResult:
        import tarfile, json
        entity_ids: list[str] = []
        with tarfile.open(str(archive_path)) as tar:
            for member in tar.getmembers():
                row = json.loads(tar.extractfile(member).read())
                result = client.put("MyTerm", row)
                entity_ids.append(result["id"])
        return LoadResult(created=len(entity_ids), entity_type="MyTerm", entity_ids=entity_ids)
```

### The `schema_fragment()` contract

The `default_prefix` key **must** be set to the loader name. This namespaces all classes and slots under `<name>:`, so user schemas reference them as `myontology:MyTerm`. Two loaders declaring the same prefix cause a `ConfigError` at install time.

Do **not** redeclare `linkml:types` or prefixes already present in the deployed Hippo schema — Hippo strips colliding top-level imports automatically (D2.14.G Rule 2). Loader-private imports (URLs unique to this loader) pass through unchanged.

Hippo automatically injects `annotations: { provided_by: <name>@<version> }` on every class and slot your fragment introduces, so `hippo status` and runtime introspection can show which loader owns which types.

---

## 2. Declaring entry points

Both entry points are registered in `pyproject.toml`. The `hippo.reference_loader_cli` entry point is optional; omit it if your loader has no subcommands.

```toml
[project.entry-points."hippo.reference_loaders"]
myontology = "hippo_reference_myontology.loader:MyOntologyLoader"

# Optional — only needed if you expose a Typer sub-app:
[project.entry-points."hippo.reference_loader_cli"]
myontology = "hippo_reference_myontology.cli:app"
```

The entry point key (`myontology`) must match `ReferenceLoader.name`. Hippo validates this at registration and raises `ReferenceLoaderRegistrationError` if the entry point does not resolve to a concrete `ReferenceLoader` subclass.

---

## 3. Runtime load parameters (optional)

Loaders that accept runtime parameters declare a Pydantic v2 model as `load_params_schema`. Hippo auto-renders `--flag` arguments from this model and validates user input before invoking `load()`.

```python
from pydantic import BaseModel, Field

class MyOntologyParams(BaseModel):
    organism: str = "human"
    include_deprecated: bool = False
    term_types: list[str] = Field(default_factory=lambda: ["class"])

class MyOntologyLoader(ReferenceLoader):
    load_params_schema = MyOntologyParams

    def load(self, client, version, params=None):
        p = params or MyOntologyParams()
        # p.organism, p.include_deprecated, p.term_types are validated
        ...
```

CLI rendering:
```bash
hippo reference install myontology \
    --organism mouse \
    --include-deprecated \
    --term-types class --term-types instance
```

**Supported field types:** `str`, `int`, `bool`, `list[str]`, and `Optional` wrappers of any of those. Fields of any other type cause a `ReferenceLoaderRegistrationError` at startup.

- `bool` fields render as `--<name>` / `--no-<name>`.
- `list[str]` fields accept repeated `--<name>` flags; user-provided values **replace** the model default (they do not extend it).
- Required fields (no default) must be supplied by the user; optional fields default to the model value.

`load()` always receives a validated model instance when `load_params_schema` is declared, or `None` when it is not.

---

## 4. The `"test"` fixture

Include `"test"` in `versions()` and make it load a small, deterministic, network-free dataset bundled in the package:

```python
def versions(self) -> list[str]:
    return ["test", "2023-01", "2024-01"]

def load(self, client, version, params=None):
    if version == "test":
        return self._load_fixture(client)
    ...
```

Keep the fixture dataset tiny (a few dozen rows). Its only purpose is letting downstream consumers do hermetic CI installs:

```bash
hippo reference install myontology --version test
```

The fixture should be stable across package versions — no external data fetches, no version-dependent behavior.

**Convention:** bundle the fixture as `<package>/fixtures/tiny.tar.gz` and load it with `importlib.resources` so it works correctly when the package is installed from a wheel.

---

## 5. Caching downloaded files

Use `client.cached_fetch` for any download larger than ~1 MB. This enables `hippo reference clean-cache`, CI cache mounts, and content-addressable reproducibility.

```python
def load(self, client, version, params=None):
    # Content-addressable: repeated calls return the cached file
    archive = client.cached_fetch(
        f"https://myontology.example.org/releases/{version}.tar.gz",
        loader_name=self.name,
        expected_sha256="abc123...",   # optional but recommended
    )
    return self._ingest_archive(client, archive)
```

`client.cached_fetch` returns a `Path` to the local file. It verifies the sha256 on both download and cache hit when `expected_sha256` is supplied; a mismatch raises `CacheIntegrityError` and removes the stale file so the next call re-downloads cleanly.

The cache location resolves to `$HIPPO_CACHE_DIR/<loader_name>/` when set, else `~/.cache/hippo/references/<loader_name>/`. Use `client.cache_dir_for(self.name)` if you need to inspect or pre-warm the directory.

**Rule:** loaders MUST use `client.cached_fetch` for all large network downloads. Never roll a private download path.

---

## 6. Loader-specific subcommands (optional)

Expose a `typer.Typer` app via the `hippo.reference_loader_cli` entry point to add subcommands under `hippo reference <name> ...`.

```python
# src/hippo_reference_myontology/cli.py
import typer

app = typer.Typer(name="myontology", help="MyOntology loader commands.")

@app.command()
def search(term: str = typer.Argument(..., help="Search term.")):
    """Search the MyOntology index."""
    typer.echo(f"Searching for: {term}")
```

Hippo mounts this app at startup so `hippo reference myontology search --help` works after the package is installed.

**HippoClient access:** subcommands that need to read or write Hippo data should instantiate a client from the standard config path. The sub-app and `load()` resolve the same `cache_dir_for(name)` because both go through `HippoClient`.

---

## 7. Efficient upgrades (optional)

The default `upgrade()` implementation delegates to `load(to_version, params)` — it re-ingests the full dataset. Override `upgrade()` when you can implement an efficient diff:

```python
def upgrade(self, client, from_version, to_version, params=None):
    # Fetch only the diff between from_version and to_version
    diff = client.cached_fetch(
        f"https://myontology.example.org/diffs/{from_version}_to_{to_version}.tar.gz",
        loader_name=self.name,
    )
    ...
    return LoadResult(created=added, updated=changed, entity_type="MyTerm", entity_ids=new_ids)
```

Populate `LoadResult.entity_ids` with the IDs written by the current version if you want `--prune-old` to work correctly.

---

## 8. User-side artifact validation (optional)

Implement `validate(user_artifact)` to let users validate their own data against your loader's schema. The method is optional; the CLI surfaces a clear "this loader does not implement validate()" message when it is absent.

```python
def validate(self, user_artifact) -> ValidationResult:
    # Check that user_artifact conforms to this loader's entity types
    ...
```

---

## 9. Cross-loader foreign keys (optional annotation)

If your fragment references entity types from another loader, annotate the fragment's `schema_fragment()` return value:

```yaml
# In your schema_fragment() return value
annotations:
  loader_depends_on:
    value: "fma"       # or comma-separated: "fma,go"
```

Hippo emits a **warning** (not an error) when a declared `loader_depends_on` loader is not installed. This is a documentation convention — v1 does not validate cross-loader foreign keys at the database level. Your `load()` code must handle missing foreign-key targets gracefully.

---

## 10. Canonical minimal example

The `FakeReferenceLoader` in `hippo.testing.fake_reference_loader` is the canonical minimal example used by Hippo's own test suite. It covers all required methods, `load_params_schema`, and the `"test"` version:

```python
from hippo.core.loaders.reference import LoadResult, ReferenceLoader
from pydantic import BaseModel

class FakeLoadParams(BaseModel):
    tag: str = "default"

class FakeReferenceLoader(ReferenceLoader):
    name = "fake"
    description = "In-memory fake reference loader (test fixture)"
    load_params_schema = FakeLoadParams

    _DATASET = {
        "test": [{"label": "alpha"}, {"label": "beta"}],
        "v1":   [{"label": "alpha"}, {"label": "beta"}, {"label": "gamma"}],
    }

    def versions(self):
        return list(self._DATASET.keys())

    def entity_types(self):
        return ["FakeTerm"]

    def schema_fragment(self):
        return {
            "id": "https://example.org/hippo/fake",
            "name": "fake",
            "default_prefix": "fake",
            "prefixes": {"fake": "https://example.org/hippo/fake/"},
            "classes": {
                "FakeTerm": {
                    "is_a": "Entity",
                    "attributes": {"label": {"range": "string", "required": True}},
                }
            },
        }

    def load(self, client, version, params=None):
        rows = self._DATASET.get(version, [])
        entity_ids = [client.put("FakeTerm", dict(r))["id"] for r in rows]
        return LoadResult(created=len(entity_ids), entity_type="FakeTerm", entity_ids=entity_ids)
```

The full source (including the Typer sub-app fixture and the all-types `RichParamsLoader`) lives in `hippo/src/hippo/testing/fake_reference_loader.py`.

---

## Checklist

- [ ] `ReferenceLoader.name` matches the `hippo.reference_loaders` entry point key
- [ ] `schema_fragment()` declares `default_prefix: <name>`
- [ ] `"test"` version returns a bundled, network-free fixture
- [ ] All downloads >1 MB go through `client.cached_fetch`
- [ ] `LoadResult.entity_ids` is populated (required for `--prune-old` support)
- [ ] `hippo.reference_loader_cli` entry point registered if a Typer sub-app is provided
- [ ] `load_params_schema` field types are limited to `str`, `int`, `bool`, `list[str]`, or `Optional` thereof
