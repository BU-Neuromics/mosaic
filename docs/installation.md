# Installation

Mosaic is a LinkML runtime. This guide covers installing Mosaic in production and development environments.

## Upgrading from Hippo

Mosaic is the new name of the component previously distributed as **Hippo**
(ADR-0004). Upgrading is a dependency swap — `pip install datahelix-mosaic`
(the `hippo` distribution is retired at 0.10.x) — and nothing else has to
change on day one:

- **Imports:** `import hippo` still works; it is a shim that emits one
  `DeprecationWarning` and aliases every `hippo.*` module to the identical
  `mosaic.*` module object, so `isinstance` checks and module identity hold
  across both spellings. `HippoClient` remains available as an alias of
  `MosaicClient`.
- **CLI:** the `hippo` command still works; it prints a deprecation notice to
  stderr and delegates to `mosaic`.
- **Config:** `mosaic.yaml` is preferred; an existing `hippo.yaml` /
  `hippo.yml` is still auto-detected (with a warning). When both exist,
  `mosaic.yaml` wins. A config-less deployment whose database lives at the
  old default `data/hippo.db` is still picked up; new deployments default to
  `data/mosaic.db`.
- **Environment variables:** `MOSAIC_CACHE_DIR`, `MOSAIC_RECIPE_CACHE`,
  `MOSAIC_TUI_TOKEN`, and `MOSAIC_DATABASE_URL` are preferred; the `HIPPO_*`
  spellings are honored as a fallback (one warning per variable).
- **Plugins:** entry points are read from the `mosaic.*` groups *and* the
  legacy `hippo.*` groups (deduplicated by name), so existing
  `hippo-reference-*` packages remain discoverable. New plugins should
  register under `mosaic.*` and follow the `mosaic-reference-<name>` /
  `mosaic-adapter-<name>` naming convention.
- **No data migration.** Schema-layer names (`hippo_core`, `hippo_ext`,
  `hippo_*` annotations), the `hippo_meta` table, and on-disk provenance are
  intentionally unchanged.

The `hippo` aliases will be removed no sooner than two minor releases after
0.11.0, via a future ADR.

## Requirements

- Python 3.11 or later
- pip or uv package manager (uv recommended for faster installs)

## Install Methods

### Using pip

```bash
pip install datahelix-mosaic
```

### Using uv

```bash
uv add datahelix-mosaic
```

## Development Install

To set up Mosaic for local development:

1. Clone the repository:
   ```bash
   git clone https://github.com/your-org/mosaic.git
   cd hippo
   ```

2. Install with development dependencies:
   ```bash
   uv sync --extra dev
   ```

3. Verify the installation by running the test suite:
   ```bash
   uv run pytest
   ```

## Verify Installation

After installation, verify the CLI is working:

```bash
mosaic --help
```

This should display the Mosaic CLI help message with available commands.
