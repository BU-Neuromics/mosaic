# Reference Loaders

Reference loaders install community-standard ontology and annotation data (Ensembl genes, FMA anatomy terms, Gene Ontology, etc.) as regular Hippo entities. Once installed, your schema can reference loader-provided entity types directly — no manual ETL required.

Reference loaders are distributed as `hippo-reference-<name>` packages on PyPI, discovered automatically when installed alongside Hippo.

## Installing a loader package

```bash
pip install hippo-reference-ensembl   # example: Ensembl gene annotations
```

After installation, the loader appears in `hippo reference list`. No further registration steps are needed.

## Commands

### `hippo reference list`

List all discoverable loaders and show which version (if any) is installed in the current Hippo database.

```bash
hippo reference list
```

Example output:

```
NAME       PACKAGE                   PKG VERSION  INSTALLED VERSION
ensembl    hippo-reference-ensembl   0.3.1        homo_sapiens.GRCh38.110
fma        hippo-reference-fma       1.0.0        —
go         hippo-reference-go        2.1.0        2024-01-15
```

---

### `hippo reference install`

Install a reference dataset. This merges the loader's schema fragment, runs a schema migration, and ingests the data.

```bash
hippo reference install <name> [--version <v>] [--flag ...]
```

| Argument / Option | Description |
|---|---|
| `<name>` | Loader name (matches the entry point key, e.g. `ensembl`) |
| `--version <v>` | Version slug to install. Defaults to the latest non-test version the loader reports. |
| `--<param> <val>` | Loader-specific flags auto-rendered from the loader's parameter schema (see below). |

**Examples:**

```bash
# Install the latest Ensembl version
hippo reference install ensembl

# Install a specific organism + release
hippo reference install ensembl --version mus_musculus.GRCm39.115

# Pass loader-specific parameters
hippo reference install ensembl --organism homo_sapiens --gene-biotypes protein_coding,lncRNA
```

Re-installing the same name + version is a silent no-op (`status: already_installed`).

---

### `hippo reference upgrade`

Upgrade an already-installed loader to a newer version.

```bash
hippo reference upgrade <name> [--version <v>] [--prune-old] [--flag ...]
```

| Option | Description |
|---|---|
| `--version <v>` | Target version slug. Defaults to the latest non-test version. |
| `--prune-old` | Deactivates the prior version's rows (sets `is_available = false`) so they no longer appear in default queries. The rows remain in the database and are recoverable via the provenance log. **Opt-in — changes the default queryable surface.** Without this flag the old rows remain queryable alongside the new ones. |
| `--<param> <val>` | Loader-specific flags (same as `install`). |

**Default (additive) behavior:** new entities are ingested alongside existing ones. Prior-version rows remain queryable — foreign-key references in your data that point at the old version continue to resolve. Use `--prune-old` only when you are certain no user data references the prior version's entities; it deactivates those rows (marks them unavailable and writes an `availability_change` provenance record) rather than removing them, so they remain auditable and recoverable.

!!! note "Atomic gating guarantee"
    `--prune-old` only runs after a fully clean load completes. If the new version fails mid-ingestion, the prior rows stay queryable — no deactivation occurs. This makes the flag safe to use: partial upgrades cannot leave you with both the old and new versions partially deactivated.

```bash
# Additive upgrade — old rows stay
hippo reference upgrade ensembl --version homo_sapiens.GRCh38.111

# Opt-in: deactivate prior version's entities after successful install
hippo reference upgrade ensembl --version homo_sapiens.GRCh38.111 --prune-old
```

---

### `hippo reference clean-cache`

Remove locally cached download files used by reference loaders.

```bash
# Clear cache for a single loader
hippo reference clean-cache ensembl

# Clear the entire reference cache
hippo reference clean-cache
```

Clearing the cache does not uninstall any data from the Hippo database — it only removes the on-disk download cache so the next `install` or `upgrade` will re-fetch source files.

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `HIPPO_CACHE_DIR` | `~/.cache/hippo/references/` | Root directory for all reference loader download caches. Set this to a shared path (e.g., an NFS mount or CI cache volume) to avoid redundant downloads across machines. |

Each loader gets its own subdirectory under the cache root: `$HIPPO_CACHE_DIR/<loader_name>/`.

---

## Declaring required loaders in your schema

Add a `requires:` block to `schema.yaml` to declare which reference loaders your schema depends on:

```yaml
# schema.yaml
requires:
  - hippo-reference-fma==3.3
  - hippo-reference-ensembl==mus_musculus.GRCm39.115
```

Only exact-match pins (`==`) are supported in v1. If you need a minimum version, pin the lowest acceptable release and upgrade explicitly with `hippo reference upgrade`.

`hippo validate` fails fast with a clear install suggestion if a required loader is missing. `hippo migrate` also checks `requires:` before applying any schema changes.

### Referencing loader-provided entity types

Loader-provided types are namespaced by loader name. Reference them in your schema using `<loader_name>:<TypeName>`:

```yaml
# schema.yaml
classes:
  SampleAnnotation:
    attributes:
      ensembl_gene_id:
        range: ensembl:Gene     # entity type provided by hippo-reference-ensembl
```

---

## The `"test"` version slug

Well-behaved loaders expose a `"test"` pseudo-version that installs a small, deterministic, network-free fixture dataset bundled with the package:

```bash
hippo reference install ensembl --version test
```

Use `--version test` in CI pipelines to avoid network dependencies and keep test runs hermetic and fast. The `"test"` slug is reserved — Hippo will never use it for a real release version.

---

## Tracking installed loaders

Hippo records installed loader versions in `hippo_meta` under the key `reference_versions`. `hippo status` surfaces this alongside other system information:

```
$ hippo status
...
Reference loaders:
  ensembl    homo_sapiens.GRCh38.110
  go         2024-01-15
```

The recorded version is what Hippo uses as the `from_version` baseline when you later run `hippo reference upgrade`.
