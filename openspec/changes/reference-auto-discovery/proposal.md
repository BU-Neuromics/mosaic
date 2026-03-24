# Reference Package Auto-Discovery and Improved CLI

## Why

Currently `hippo reference install <name>` requires users to know the package name in
advance. There is no way to discover which reference packages are available in the current
Python environment without reading documentation. This creates friction and makes it easy
to miss available packages.

Additionally, there is no built-in mechanism for upgrading reference packages when new
versions are released — users must manually re-run `hippo reference install` after
updating a package.

## What Changes

### Auto-discovery

`hippo` discovers all installed reference loader packages automatically via the
`hippo.reference_loaders` entry point group at CLI startup. No configuration required —
any installed Python package that registers this entry point is immediately discoverable.

### New CLI commands

```bash
# List all discoverable reference packages (installed Python packages with entry points)
# Shows: name, description, installed version, applied version (if any), status
hippo reference list

# Install/apply one package to this Hippo deployment (schema migration + data load)
hippo reference install <name>

# Install/apply all discoverable packages
hippo reference install all

# Upgrade a package to the newly installed version (re-runs migration + data refresh)
hippo reference upgrade <name>

# Upgrade all packages with newer versions available
hippo reference upgrade all

# Show which packages are applied to this deployment and at what version
hippo reference status
```

### `hippo reference list` output

```
Available reference packages:
  canon          v0.1.0   ✅ applied (v0.1.0)   Canon entity types (Tool, ToolVersion, WorkflowRun...)
  ensembl        v111.0   ✅ applied (v111.0)   Ensembl gene identifiers
  fma            v4.14    ❌ not applied         Foundational Model of Anatomy terms
  gencode        v43      ❌ not applied         GENCODE gene annotation releases
  rnaseq         v1.0.0   ⬆️  upgrade available  RNA-seq domain entity types (v0.9.0 applied)
```

### Upgrade behavior

When a reference package is upgraded:
- The loader's `schema_fragment()` is diffed against the currently applied schema
- Additive changes (new entity types, new fields) → non-interactive migration
- Structural changes (renamed fields, type changes) → confirmation prompt
- The applied version is updated in Hippo's `hippo_meta` table
- Reference data is refreshed for packages that provide bulk data (e.g. Ensembl genes)

### `hippo_meta` tracking

The `hippo_meta` key-value table (already defined in sec3b) stores:
```
key: "reference.canon.version"       value: "0.1.0"
key: "reference.ensembl.version"     value: "111.0"
key: "reference.fma.version"         value: null  (not applied)
```

## Capabilities

### Modified Capabilities
- `reference-install` — enhanced with auto-discovery, `list`, `upgrade`, `status` subcommands
- `reference-list` — replaces manual listing with auto-discovery output

## Impact

- `ReferenceLoader` ABC gains `version()` and `description()` abstract methods
- New `ReferenceRegistry` class: discovers entry points, checks applied versions
- CLI reference commands refactored to subcommand group: `hippo reference <subcommand>`
- `hippo_meta` table used to track applied package versions
- Fully backwards compatible — `hippo reference install <name>` still works unchanged

## Open Questions

### Confirmation for bulk data refresh on upgrade
Should `hippo reference upgrade` prompt before re-downloading and re-loading large
reference datasets (e.g. full Ensembl gene set)? Probably yes for interactive use,
with `--yes` flag for automation.
