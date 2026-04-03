# Hippo CLI Reference

Complete reference for all `hippo` CLI commands.

## Global Options

| Option | Description |
|--------|-------------|
| `--help` | Show help message and exit |
| `--version` | Show Hippo version (if available) |

## init

Initialize a new Hippo project with the specified template.

### Usage

```bash
hippo init [OPTIONS]
```

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--path`, `-p` | `string` | `None` | Project directory path |
| `--template`, `-t` | `string` | `"basic"` | Template to use: `basic`, `minimal`, or `full` |
| `--force`, `-f` | `boolean` | `false` | Force initialization even if directory exists |

### Example

```bash
# Initialize with default (basic) template
hippo init

# Initialize in a specific directory
hippo init --path /path/to/project

# Initialize with full template, overwriting existing
hippo init --template full --force
```

---

## serve

Start the Hippo REST API server.

### Usage

```bash
hippo serve [OPTIONS]
```

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--host`, `-h` | `string` | `"127.0.0.1"` | Host address to bind the server to |
| `--port`, `-p` | `integer` | `8000` | Port number to listen on |
| `--reload`, `-r` | `boolean` | `false` | Enable auto-reload during development |
| `--workers`, `-w` | `integer` | `None` | Number of worker processes to use |
| `--log-level`, `-l` | `string` | `"info"` | Logging level: `debug`, `info`, `warning`, `error` |

### Example

```bash
# Start with default configuration
hippo serve

# Start on custom port with debug logging
hippo serve --port 9000 --log-level debug

# Enable auto-reload for development
hippo serve --reload

# Run with multiple workers
hippo serve --workers 4
```

---

## migrate

Run schema migrations based on YAML schema definitions.

### Usage

```bash
hippo migrate [TARGET] [OPTIONS]
```

### Arguments

| Argument | Type | Description |
|-----------|------|-------------|
| `target` | `string` | Target version (not used in v0.1) |

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--dry-run`, `--preview` | `boolean` | `false` | Preview migrations without applying |
| `--schema-dir` | `string` | `"schemas/"` | Path to schema directory |
| `--db-path` | `string` | `"data/hippo.db"` | Path to SQLite database |

### Example

```bash
# Run migrations with defaults
hippo migrate

# Preview migrations without applying
hippo migrate --dry-run

# Use custom schema and database paths
hippo migrate --schema-dir custom/schemas --db-path custom/data/hippo.db
```

---

## validate

Validate schemas or configuration files against defined rules.

### Usage

```bash
hippo validate [OPTIONS]
```

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--schema`, `-s` | `string` | `None` | Path to schema file to validate |
| `--config`, `-c` | `string` | `None` | Path to config file to validate |
| `--verbose`, `-v` | `boolean` | `false` | Show detailed validation output |

### Example

```bash
# Validate default configuration
hippo validate

# Validate a specific schema file
hippo validate --schema schemas/entities.yaml

# Validate a specific config file
hippo validate --config config/production.yaml

# Validate with verbose output
hippo validate --schema schemas/entities.yaml --verbose
```

---

## ingest

Ingest data from configured external sources.

### Usage

```bash
hippo ingest [OPTIONS]
```

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--config`, `-c` | `string` | `None` | Path to data sources configuration file |
| `--dry-run` | `boolean` | `false` | Preview ingestion without applying changes |

### Example

```bash
# Ingest using default configuration
hippo ingest

# Ingest from specific configuration file
hippo ingest --config data-sources.yaml

# Preview ingestion without making changes
hippo ingest --dry-run
```

---

## reference

Manage reference data loader packages.

### Usage

```bash
hippo reference <subcommand> [OPTIONS]
```

### Subcommands

#### reference install

Install a reference loader package.

```bash
hippo reference install <PACKAGE> [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `package` | `string` | **required** | Package name to install |
| `--source`, `-s` | `string` | `None` | Package source (URL or local path) |

**Example:**

```bash
hippo reference install my-loader
hippo reference install my-loader --source https://example.com/loader.tar.gz
```

#### reference list

List installed reference loader packages.

```bash
hippo reference list
```

**Example:**

```bash
hippo reference list
```

---

## install-ref

Install reference data from a source.

### Usage

```bash
hippo install-ref <SOURCE> [OPTIONS]
```

### Arguments

| Argument | Type | Description |
|----------|------|-------------|
| `source` | `string` | **required** | Source path or URL |

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--name`, `-n` | `string` | `None` | Name for the reference |
| `--force`, `-f` | `boolean` | `false` | Force installation if already exists |

### Example

```bash
# Install from a local path
hippo install-ref /path/to/reference/data

# Install with a specific name
hippo install-ref /path/to/reference/data --name my_reference

# Force reinstall
hippo install-ref /path/to/reference/data --force
```

---

## update-ref

Update an existing reference.

### Usage

```bash
hippo update-ref <NAME> [OPTIONS]
```

### Arguments

| Argument | Type | Description |
|----------|------|-------------|
| `name` | `string` | **required** | Name of the reference to update |

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--source`, `-s` | `string` | `None` | New source path or URL |

### Example

```bash
# Update a reference
hippo update-ref my_reference

# Update with new source
hippo update-ref my_reference --source /new/path/to/data
```

---

## list-ref

List installed reference data.

### Usage

```bash
hippo list-ref [NAME] [OPTIONS]
```

### Arguments

| Argument | Type | Description |
|----------|------|-------------|
| `name` | `string` | `None` | Filter by reference name |

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--format`, `-f` | `string` | `"table"` | Output format: `table`, `json`, or `yaml` |

### Example

```bash
# List all references in table format
hippo list-ref

# List in JSON format
hippo list-ref --format json

# List in YAML format
hippo list-ref --format yaml

# Filter by name
hippo list-ref sample_ref
```

---

## validate-schema

Validate a LinkML schema file.

### Usage

```bash
hippo validate-schema <INPUT> [OPTIONS]
```

### Arguments

| Argument | Type | Description |
|----------|------|-------------|
| `input` | `string` | **required** | Input LinkML schema file path |

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--format`, `-f` | `string` | `"yaml"` | Input format: `yaml` or `json` |

### Example

```bash
# Validate a LinkML schema
hippo validate-schema schema.yaml

# Validate a JSON-format schema
hippo validate-schema schema.json --format json
```

---

## schema-diff

Compare two schema files and show differences.

### Usage

```bash
hippo schema-diff <FILE1> <FILE2>
```

### Arguments

| Argument | Type | Description |
|----------|------|-------------|
| `file1` | `string` | **required** | First schema file path |
| `file2` | `string` | **required** | Second schema file path |

### Example

```bash
# Compare two schema versions
hippo schema-diff schemas/v1.yaml schemas/v2.yaml
```
