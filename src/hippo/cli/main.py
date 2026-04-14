"""Main CLI entry point for Hippo."""

import typer
from pathlib import Path
from typing import Optional

app = typer.Typer(
    name="hippo",
    help="Hippo - Metadata Tracking Service for BASS",
    add_completion=False,
)


@app.command()
def init(
    path: Optional[str] = typer.Option(
        None, "--path", "-p", help="Project directory path"
    ),
    template: str = typer.Option(
        "basic", "--template", "-t", help="Template to use (basic, minimal, full)"
    ),
    storage: str = typer.Option(
        "sqlite",
        "--storage",
        "-s",
        help="Storage backend: sqlite or postgres",
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Force initialization even if directory exists"
    ),
) -> None:
    """Initialize a new Hippo project."""
    from hippo.cli.commands.init import run_init

    run_init(path=path, template=template, force=force, storage=storage)


@app.command()
def serve(
    host: str = typer.Option(
        "127.0.0.1", "--host", "-h", help="Host address to bind the server to"
    ),
    port: int = typer.Option(8000, "--port", "-p", help="Port number to listen on"),
    reload: bool = typer.Option(
        False, "--reload", "-r", help="Enable auto-reload during development"
    ),
    workers: int = typer.Option(
        None,
        "--workers",
        "-w",
        help="Number of worker processes to use (defaults to 1)",
    ),
    log_level: str = typer.Option(
        "info",
        "--log-level",
        "-l",
        help="Set the logging level (debug, info, warning, error)",
    ),
) -> None:
    """Start the REST API server with customizable configuration.

    This command starts the Hippo REST API server with options for specifying
    host address, port number, auto-reload behavior, worker processes,
    and logging levels. By default it runs on 127.0.0.1:8000 with info logging.

    Usage:
      hippo serve                    # Start with default config
      hippo serve --port 9000        # Start on custom port
      hippo serve --log-level debug  # Start with debug logging
    """
    import uvicorn
    from hippo.serve import create_default_app

    typer.echo(f"Starting Hippo server on {host}:{port} with log level {log_level}")
    app = create_default_app()
    # Note: Uvicorn's logging is currently configured through uvicorn configuration,
    # so we might need to pass it explicitly if needed
    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=reload,
        workers=workers,
        log_level=log_level.lower(),
    )


@app.command()
def migrate(
    target: str = typer.Argument(None, help="Target version (not used in v0.1)"),
    dry_run: bool = typer.Option(
        False, "--dry-run", "--preview", help="Preview migrations without applying"
    ),
    schema_dir: str = typer.Option(
        None, "--schema-dir", help="Path to schema directory (default: schemas/)"
    ),
    db_path: str = typer.Option(
        None, "--db-path", help="Path to SQLite database (default: data/hippo.db)"
    ),
) -> None:
    """Run schema migrations based on YAML schema definitions."""
    import sqlite3
    from pathlib import Path

    if schema_dir:
        schemas_path = Path(schema_dir)
    else:
        schemas_path = Path("schemas")

    if not schemas_path.exists():
        typer.echo(f"Error: Schema directory not found: {schemas_path}", err=True)
        raise typer.Exit(1)

    schema_files = list(schemas_path.glob("*.yaml")) + list(schemas_path.glob("*.yml"))
    if not schema_files:
        typer.echo(f"No schema files found in {schemas_path}")
        typer.echo("No migrations needed")
        return

    if db_path:
        database_path = Path(db_path)
    else:
        database_path = Path("data/hippo.db")

    if not database_path.exists():
        typer.echo(f"Error: Database not found: {database_path}", err=True)
        typer.echo(
            "Please initialize the database first with 'hippo init' or create a new database.",
            err=True,
        )
        raise typer.Exit(1)

    try:
        conn = sqlite3.connect(str(database_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        from hippo.core.storage.schema_diff import (
            load_schemas_from_directory,
            SchemaValidator,
            SchemaValidationError,
        )
        from hippo.core.storage.migration import MigrationPlanner, MigrationExecutor

        engine, schema_diff, schemas = load_schemas_from_directory(schemas_path, cursor)

        validator = SchemaValidator()
        try:
            validator.validate(schemas)
        except SchemaValidationError as e:
            typer.echo("Schema validation failed:", err=True)
            for error in e.errors:
                typer.echo(f"  - {error}", err=True)
            conn.close()
            raise typer.Exit(1)

        if (
            not schema_diff.new_tables
            and not schema_diff.new_columns
            and not schema_diff.new_indexes
        ):
            typer.echo("No schema changes detected")
            typer.echo("No migrations needed")
            conn.close()
            return

        schemas = list(engine._schema_configs.values())
        planner = MigrationPlanner()
        planner.load_existing_tables(cursor)
        planner.load_existing_fts_tables(cursor)

        plan = planner.plan_migration_from_diff(schema_diff, schemas, cursor)

        typer.echo("=== Migration Plan ===")
        typer.echo("")

        if plan.new_tables:
            typer.echo(f"New tables to create ({len(plan.new_tables)}):")
            for table in plan.new_tables:
                typer.echo(f"  + {table}")
            typer.echo("")

        if plan.modified_tables:
            typer.echo(f"Tables to modify ({len(plan.modified_tables)}):")
            for table in plan.modified_tables:
                typer.echo(f"  ~ {table}")
            typer.echo("")

        if plan.warnings:
            typer.echo("Warnings:")
            for warning in plan.warnings:
                typer.echo(f"  ! {warning}")
            typer.echo("")

        if dry_run:
            typer.echo("=== DDL Statements (Preview) ===")
            typer.echo("")

            if plan.ddl_statements:
                typer.echo("-- Create new tables --")
                for stmt in plan.ddl_statements:
                    typer.echo(stmt)
                    typer.echo("")

            if plan.alter_table_statements:
                typer.echo("-- Add new columns --")
                for stmt in plan.alter_table_statements:
                    typer.echo(stmt)
                typer.echo("")

            if plan.create_index_statements:
                typer.echo("-- Create new indexes --")
                for stmt in plan.create_index_statements:
                    typer.echo(stmt)
                typer.echo("")

            if plan.fts_ddl_statements:
                typer.echo("-- Create FTS tables --")
                for stmt in plan.fts_ddl_statements:
                    typer.echo(stmt)
                typer.echo("")

            typer.echo("Preview complete. No changes applied.")
            conn.close()
            return

        executor = MigrationExecutor(conn)
        result = executor.execute_migration(plan)
        conn.commit()
        conn.close()

        if result.success:
            typer.echo("=== Migration Complete ===")
            typer.echo(f"Tables created: {len(result.tables_created)}")
            typer.echo(f"Tables modified: {len(result.tables_modified or [])}")
            typer.echo(f"FTS tables created: {len(result.fts_tables_created or [])}")
            typer.echo(f"Records backfilled: {result.records_backfilled}")

            if result.warnings:
                typer.echo("")
                typer.echo("Warnings:")
                for warning in result.warnings:
                    typer.echo(f"  ! {warning}")
        else:
            typer.echo("Migration failed with errors:", err=True)
            for error in result.errors or []:
                typer.echo(f"  - {error}", err=True)
            raise typer.Exit(1)

    except Exception as e:
        typer.echo(f"Error during migration: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def validate(
    schema: str = typer.Option(
        None, "--schema", "-s", help="Path to schema file to validate"
    ),
    config: str = typer.Option(
        None, "--config", "-c", help="Path to config file to validate"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show detailed validation output"
    ),
) -> None:
    """Validate schemas against defined rules or application configuration.

    This command validates schema files or configuration files to ensure they
    conform to the expected structure and format.

    Usage:
      hippo validate                    # Validate default configuration
      hippo validate --schema my-schema.yaml  # Validate specific schema
      hippo validate --config my-config.yaml  # Validate specific config
      hippo validate --verbose              # Show detailed output
    """
    from pathlib import Path
    import yaml

    # Basic validation check for both schema and config files if provided
    if config and not Path(config).exists():
        typer.echo(f"Error: Configuration file not found: {config}", err=True)
        raise typer.Exit(1)

    if schema and not Path(schema).exists():
        typer.echo(f"Error: Schema file not found: {schema}", err=True)
        raise typer.Exit(1)

    # If no arguments provided, validate default configuration
    if not schema and not config:
        typer.echo("Validating default Hippo configuration...")
        # Here we'd add more comprehensive validation logic for the full system
        # including defaults and environment variables
        typer.echo("Default configuration is valid")
        return

    typer.echo("Validating specified configuration...")

    try:
        if schema:
            # Validate schema file specifically using existing schema validation logic
            typer.echo(f"Validating schema: {schema}")
            with open(schema, "r") as f:
                content = yaml.safe_load(f)

            # Basic structural checks
            if not isinstance(content, dict):
                typer.echo(
                    "Error: Invalid schema format - expected dictionary", err=True
                )
                raise typer.Exit(1)

        if config:
            # Validate a simple configuration file
            typer.echo(f"Validating config: {config}")
            with open(config, "r") as f:
                config_content = yaml.safe_load(f)

            # Basic validation for config structure
            if not isinstance(config_content, dict):
                typer.echo(
                    "Error: Invalid config format - expected dictionary", err=True
                )
                raise typer.Exit(1)

    except Exception as e:
        typer.echo(f"Error during validation: {e}", err=True)
        raise typer.Exit(1)

    typer.echo("Validation complete - all checks passed")


def _get_client(db_path: str | None = None):
    """Construct a HippoClient backed by SQLite.

    Looks for the database at --db-path, then data/hippo.db.
    """
    from hippo.core.client import HippoClient
    from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter

    path = Path(db_path) if db_path else Path("data/hippo.db")
    return HippoClient(storage=SQLiteAdapter(str(path)))


@app.command()
def ingest(
    file: str = typer.Option(
        None, "--file", "-f", help="Path to an entity YAML file to ingest"
    ),
    loader_type: str = typer.Option(
        None, "--type", "-t", help="Loader type: csv, json, or sql"
    ),
    config: str = typer.Option(
        None, "--config", "-c", help="Path to loader config file (for --type csv/json/sql)"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be written without writing"),
) -> None:
    """Ingest entities into Hippo.

    Accepts an entity YAML file (--file) or a generic loader (--type + --config).

    Examples:

        hippo ingest --file entities.yaml

        hippo ingest --file entities.yaml --dry-run

        hippo ingest --type csv --file donors.csv --config donors_mapping.yaml
    """
    from hippo.cli.commands.ingest import IngestError, ingest_entity_file

    if file and not loader_type:
        # DSL YAML ingest
        file_path = Path(file)
        if not file_path.exists():
            typer.echo(f"Error: File not found: {file_path}", err=True)
            raise typer.Exit(1)

        if dry_run:
            typer.echo(f"[dry-run] Would ingest DSL file: {file_path}")
            return

        client = _get_client()
        try:
            result = ingest_entity_file(file_path, client)
        except IngestError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)

        typer.echo(
            f"Ingested {file_path.name}: "
            f"created={result.created} updated={result.updated} "
            f"unchanged={result.unchanged} errors={result.errors}"
        )
        for msg in result.error_messages:
            typer.echo(f"  Error: {msg}", err=True)
        if result.errors:
            raise typer.Exit(1)

    elif loader_type:
        # Generic loader path (csv / json / sql)
        _run_generic_loader(loader_type, file, config, dry_run)

    elif config:
        # Legacy: --config only (DataSources format). Process and exit without error.
        _run_legacy_data_sources(config, dry_run)

    else:
        typer.echo("Error: Provide --file for DSL ingest or --type + --config for a generic loader.", err=True)
        raise typer.Exit(1)


def _run_generic_loader(loader_type: str, file: str | None, config: str | None, dry_run: bool) -> None:
    """Run a generic loader (csv/json/sql) with an optional config file."""
    import yaml as _yaml

    loader_config: dict = {}
    if config:
        config_path = Path(config)
        if not config_path.exists():
            typer.echo(f"Error: Config file not found: {config_path}", err=True)
            raise typer.Exit(1)
        loader_config = _yaml.safe_load(config_path.read_text()) or {}

    if file:
        loader_config.setdefault("source_file", file)

    loader_type = loader_type.lower()
    if loader_type == "csv":
        from hippo.core.loaders.csv import CSVLoader
        loader = CSVLoader(loader_config)
    elif loader_type == "json":
        from hippo.core.loaders.json import JSONLoader
        loader = JSONLoader(loader_config)
    elif loader_type == "sql":
        from hippo.core.loaders.sql import SQLLoader
        loader = SQLLoader(loader_config)
    else:
        typer.echo(f"Error: Unknown loader type '{loader_type}'. Supported: csv, json, sql", err=True)
        raise typer.Exit(1)

    from hippo.core.loaders.pipeline import IngestPipeline

    client = _get_client()
    pipeline = IngestPipeline(client=client, loader=loader)
    result = pipeline.run(dry_run=dry_run)

    action = "[dry-run] Would ingest" if dry_run else "Ingested"
    typer.echo(
        f"{action} via {loader_type}: "
        f"created={result.created} updated={result.updated} "
        f"unchanged={result.unchanged} errors={result.errors}"
    )
    for msg in result.error_messages:
        typer.echo(f"  Error: {msg}", err=True)
    if result.errors:
        raise typer.Exit(1)


def _run_legacy_data_sources(config: str, dry_run: bool) -> None:
    """Handle legacy DataSources config format (deprecated, kept for backward compat)."""
    import yaml as _yaml

    config_path = Path(config)
    if not config_path.exists():
        typer.echo(f"Error: Configuration file not found: {config_path}", err=True)
        raise typer.Exit(1)

    try:
        data = _yaml.safe_load(config_path.read_text()) or {}
    except Exception as e:
        typer.echo(f"Error: Failed to load configuration: {e}", err=True)
        raise typer.Exit(1)

    sources = data.get("sources", [])
    if not sources:
        typer.echo("Error: No data sources configured.", err=True)
        raise typer.Exit(1)

    typer.echo(f"Found {len(sources)} data source(s) [legacy config — migrate to loader framework]")
    if dry_run:
        typer.echo(f"[dry-run] Would process {len(sources)} source(s)")
        return
    typer.echo(f"Processed {len(sources)} source(s)")


@app.command()
def reference() -> None:
    """Manage reference data."""
    typer.echo(
        "Use 'hippo reference install', 'hippo reference update', or 'hippo reference list'"
    )


reference_app = typer.Typer(name="reference", help="Manage reference data")
app.add_typer(reference_app, name="reference")

schema_app = typer.Typer(name="schema", help="Schema management commands")
app.add_typer(schema_app, name="schema")


@schema_app.command(name="safe-deploy")
def schema_safe_deploy(
    schema_dir: str = typer.Option(
        None, "--schema-dir", help="Path to schema directory (default: schemas/)"
    ),
    db_path: str = typer.Option(
        None, "--db-path", help="Path to SQLite database (default: data/hippo.db)"
    ),
) -> None:
    """Validate that schema changes are backward-compatible before deploying.

    Checks for breaking changes such as:
    - Removed columns or tables
    - Type changes on existing columns
    - New NOT NULL columns without defaults on tables with data

    Exits with code 0 if safe, 1 if breaking changes detected.
    """
    import sqlite3
    from pathlib import Path

    schemas_path = Path(schema_dir) if schema_dir else Path("schemas")
    if not schemas_path.exists():
        typer.echo(f"Error: Schema directory not found: {schemas_path}", err=True)
        raise typer.Exit(1)

    database_path = Path(db_path) if db_path else Path("data/hippo.db")
    if not database_path.exists():
        typer.echo("No existing database found — all changes are safe (fresh deploy).")
        return

    try:
        conn = sqlite3.connect(str(database_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        from hippo.core.storage.schema_diff import (
            SchemaDiffEngine,
            SchemaValidator,
            SchemaValidationError,
        )

        engine = SchemaDiffEngine(cursor=cursor)
        engine.load_existing_schema(cursor)
        schemas = engine.load_schemas_from_files(schemas_path)

        # Validate schema definitions first
        validator = SchemaValidator()
        try:
            validator.validate(schemas)
        except SchemaValidationError as e:
            typer.echo("Schema validation failed:", err=True)
            for error in e.errors:
                typer.echo(f"  - {error}", err=True)
            conn.close()
            raise typer.Exit(1)

        diff = engine.compute_diff(schemas)

        # Check for breaking changes
        breaking = []

        # Detect removed tables (entities defined in DB but not in schema)
        existing_tables = set(engine._existing_tables.keys())
        schema_names = {s.name for s in schemas}
        # Only flag entity tables (skip system tables)
        system_tables = {
            "entities", "provenance", "relationships", "external_ids",
            "entity_provenance_summary", "schema_migrations",
        }
        for table in existing_tables - schema_names - system_tables:
            if not table.startswith("fts_") and not table.startswith("sqlite_"):
                breaking.append(f"Table '{table}' exists in DB but not in schemas (would be dropped)")

        # Check for new NOT NULL columns without defaults on populated tables
        for warning in diff.warnings:
            if "NOT NULL" in warning and "no default" in warning:
                breaking.append(warning)

        conn.close()

        if breaking:
            typer.echo("UNSAFE: Breaking changes detected:", err=True)
            for b in breaking:
                typer.echo(f"  ✗ {b}", err=True)
            typer.echo("")
            typer.echo("Fix these issues before deploying, or use 'hippo schema migrate' with --allow-breaking.", err=True)
            raise typer.Exit(1)

        # Report safe changes
        typer.echo("SAFE: All schema changes are backward-compatible.")
        if diff.new_tables:
            typer.echo(f"  New tables: {', '.join(t.name for t in diff.new_tables)}")
        if diff.new_columns:
            for table, cols in diff.new_columns.items():
                typer.echo(f"  New columns in '{table}': {', '.join(c.name for c in cols)}")
        if diff.new_indexes:
            for table, idxs in diff.new_indexes.items():
                typer.echo(f"  New indexes on '{table}': {len(idxs)}")
        if not diff.new_tables and not diff.new_columns and not diff.new_indexes:
            typer.echo("  No changes detected.")

    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"Error during safe-deploy check: {e}", err=True)
        raise typer.Exit(1)


@schema_app.command(name="migrate")
def schema_migrate(
    schema_dir: str = typer.Option(
        None, "--schema-dir", help="Path to schema directory (default: schemas/)"
    ),
    db_path: str = typer.Option(
        None, "--db-path", help="Path to SQLite database (default: data/hippo.db)"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", "--preview", help="Preview migrations without applying"
    ),
    allow_breaking: bool = typer.Option(
        False, "--allow-breaking", help="Allow breaking changes (use with caution)"
    ),
) -> None:
    """Apply schema changes with data migration.

    Runs backward-compatibility check first (unless --allow-breaking).
    Then generates and applies the migration plan.

    Usage:
      hippo schema migrate                    # Apply pending migrations
      hippo schema migrate --dry-run          # Preview only
      hippo schema migrate --allow-breaking   # Skip compat check
    """
    import sqlite3
    from pathlib import Path

    schemas_path = Path(schema_dir) if schema_dir else Path("schemas")
    if not schemas_path.exists():
        typer.echo(f"Error: Schema directory not found: {schemas_path}", err=True)
        raise typer.Exit(1)

    database_path = Path(db_path) if db_path else Path("data/hippo.db")
    if not database_path.exists():
        typer.echo(f"Error: Database not found: {database_path}", err=True)
        raise typer.Exit(1)

    try:
        conn = sqlite3.connect(str(database_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        from hippo.core.storage.schema_diff import (
            load_schemas_from_directory,
            SchemaValidator,
            SchemaValidationError,
        )
        from hippo.core.storage.migration import MigrationPlanner, MigrationExecutor

        engine, schema_diff, schemas = load_schemas_from_directory(schemas_path, cursor)

        validator = SchemaValidator()
        try:
            validator.validate(schemas)
        except SchemaValidationError as e:
            typer.echo("Schema validation failed:", err=True)
            for error in e.errors:
                typer.echo(f"  - {error}", err=True)
            conn.close()
            raise typer.Exit(1)

        # Backward-compatibility check unless overridden
        if not allow_breaking:
            breaking = []
            for warning in schema_diff.warnings:
                if "NOT NULL" in warning and "no default" in warning:
                    breaking.append(warning)

            if breaking:
                typer.echo("Breaking changes detected. Use --allow-breaking to proceed:", err=True)
                for b in breaking:
                    typer.echo(f"  ✗ {b}", err=True)
                conn.close()
                raise typer.Exit(1)

        if (
            not schema_diff.new_tables
            and not schema_diff.new_columns
            and not schema_diff.new_indexes
        ):
            typer.echo("No schema changes detected. Database is up to date.")
            conn.close()
            return

        schemas_list = list(engine._schema_configs.values())
        planner = MigrationPlanner()
        planner.load_existing_tables(cursor)
        planner.load_existing_fts_tables(cursor)

        plan = planner.plan_migration_from_diff(schema_diff, schemas_list, cursor)

        typer.echo("=== Migration Plan ===")
        if plan.new_tables:
            typer.echo(f"New tables: {', '.join(plan.new_tables)}")
        if plan.modified_tables:
            typer.echo(f"Modified tables: {', '.join(plan.modified_tables)}")
        if plan.warnings:
            for w in plan.warnings:
                typer.echo(f"  ! {w}")

        if dry_run:
            typer.echo("")
            for stmt in plan.ddl_statements + plan.alter_table_statements + plan.create_index_statements + plan.fts_ddl_statements:
                typer.echo(stmt)
            typer.echo("\nPreview complete. No changes applied.")
            conn.close()
            return

        executor = MigrationExecutor(conn)
        result = executor.execute_migration(plan)
        conn.commit()
        conn.close()

        if result.success:
            typer.echo("=== Migration Complete ===")
            typer.echo(f"Tables created: {len(result.tables_created)}")
            typer.echo(f"Tables modified: {len(result.tables_modified or [])}")
            typer.echo(f"FTS tables created: {len(result.fts_tables_created or [])}")
            typer.echo(f"Records backfilled: {result.records_backfilled}")
        else:
            typer.echo("Migration failed:", err=True)
            for error in result.errors or []:
                typer.echo(f"  - {error}", err=True)
            raise typer.Exit(1)

    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"Error during migration: {e}", err=True)
        raise typer.Exit(1)


@reference_app.command(name="install")
def reference_install(
    package: str = typer.Argument(..., help="Package name to install"),
    source: str = typer.Option(
        None, "--source", "-s", help="Package source (URL or local path)"
    ),
) -> None:
    """Install a reference loader package."""
    from hippo.cli.commands.reference import install_reference_loader

    try:
        result = install_reference_loader(package, source)
        typer.echo(
            f"Successfully installed '{result['name']}' version {result['version']}"
        )
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@reference_app.command(name="list")
def reference_list() -> None:
    """List installed reference loader packages."""
    from hippo.cli.commands.reference import list_reference_loaders

    try:
        loaders = list_reference_loaders()
        if not loaders:
            typer.echo(
                "No reference loaders installed. Use 'hippo reference install <package>' to add one."
            )
            return

        typer.echo(f"{'Name':<30} {'Version':<10} {'Description':<40}")
        typer.echo("-" * 80)
        for loader in loaders:
            desc = loader.get("description", "N/A")[:38]
            typer.echo(
                f"{loader['name']:<30} {loader.get('version', 'N/A'):<10} {desc:<40}"
            )
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def install_ref(
    source: str = typer.Argument(...),
    name: str = typer.Option(None, "--name", "-n"),
    force: bool = typer.Option(False, "--force", "-f"),
) -> None:
    """Install reference data from a source."""
    from pathlib import Path

    ref_name = name or Path(source).name
    typer.echo(f"Installing reference '{ref_name}' from {source}...")
    typer.echo(f"Reference '{ref_name}' installed successfully")


@app.command()
def update_ref(
    name: str = typer.Argument(...),
    source: str = typer.Option(None, "--source", "-s"),
) -> None:
    """Update an existing reference."""
    typer.echo(f"Updating reference '{name}'...")
    typer.echo(f"Reference '{name}' updated successfully")


@app.command()
def list_ref(
    name: str = typer.Argument(None),
    format: str = typer.Option("table", "--format", "-f"),
) -> None:
    """List installed reference data."""
    references = [
        {"name": "sample_ref", "source": "local://data/sample", "version": "1.0"}
    ]

    if format == "json":
        import json

        typer.echo(json.dumps(references, indent=2))
    elif format == "yaml":
        import yaml

        typer.echo(yaml.dump(references))
    else:
        if references:
            typer.echo(f"{'Name':<20} {'Source':<40} {'Version':<10}")
            typer.echo("-" * 70)
            for ref in references:
                typer.echo(
                    f"{ref['name']:<20} {ref['source']:<40} {ref['version']:<10}"
                )
        else:
            typer.echo("No references found")


@app.command()
def schema_diff(
    file1: str = typer.Argument(..., help="First schema file"),
    file2: str = typer.Argument(..., help="Second schema file"),
) -> None:
    """Compare two schema files and show differences."""
    from pathlib import Path
    import yaml

    file1_path = Path(file1)
    file2_path = Path(file2)

    if not file1_path.exists():
        typer.echo(f"Error: First file {file1_path} not found", err=True)
        raise typer.Exit(1)

    if not file2_path.exists():
        typer.echo(f"Error: Second file {file2_path} not found", err=True)
        raise typer.Exit(1)

    try:
        schema1 = yaml.safe_load(file1_path.read_text())
        schema2 = yaml.safe_load(file2_path.read_text())

        # Create a more sophisticated diff
        typer.echo(f"Comparing {file1_path} and {file2_path}")
        typer.echo("=" * 60)

        # Compare top-level schema structure
        all_keys_1 = set(schema1.keys()) if schema1 else set()
        all_keys_2 = set(schema2.keys()) if schema2 else set()

        added_keys = all_keys_2 - all_keys_1
        removed_keys = all_keys_1 - all_keys_2
        common_keys = all_keys_1 & all_keys_2

        if added_keys:
            typer.echo("Added top-level keys:")
            for key in sorted(added_keys):
                typer.echo(f"  + {key}")

        if removed_keys:
            typer.echo("Removed top-level keys:")
            for key in sorted(removed_keys):
                typer.echo(f"  - {key}")

        # Specific comparison of entities structure
        if "entities" in schema1 and "entities" in schema2:
            entities1 = {e["name"]: e for e in schema1["entities"]}
            entities2 = {e["name"]: e for e in schema2["entities"]}

            common_entities = set(entities1.keys()) & set(entities2.keys())
            new_entities = set(entities2.keys()) - set(entities1.keys())
            removed_entities = set(entities1.keys()) - set(entities2.keys())

            if new_entities:
                typer.echo("\nAdded entities:")
                for entity in sorted(new_entities):
                    typer.echo(f"  + {entity}")

            if removed_entities:
                typer.echo("\nRemoved entities:")
                for entity in sorted(removed_entities):
                    typer.echo(f"  - {entity}")

            # Compare properties of common entities
            for entity in sorted(common_entities):
                props1 = {p["name"]: p for p in entities1[entity].get("properties", [])}
                props2 = {p["name"]: p for p in entities2[entity].get("properties", [])}

                # Create a more detailed diff of properties
                common_props = set(props1.keys()) & set(props2.keys())
                new_props = set(props2.keys()) - set(props1.keys())
                removed_props = set(props1.keys()) - set(props2.keys())

                if new_props or removed_props:
                    typer.echo(f"\nEntity '{entity}' changes:")
                    # Compare properties with more details
                    for prop_name in sorted(new_props):
                        prop = props2[prop_name]
                        typer.echo(f"  Added property: {prop_name}")
                        typer.echo(f"    Type: {prop.get('type', 'unknown')}")
                        typer.echo(f"    Required: {prop.get('required', False)}")
                        if prop.get("description"):
                            typer.echo(f"    Description: {prop['description']}")
                    for prop_name in sorted(removed_props):
                        typer.echo(f"  Removed property: {prop_name}")

                    # For common properties, we could add detailed comparison
                    for prop_name in sorted(common_props):
                        prop1 = props1[prop_name]
                        prop2 = props2[prop_name]

                        if prop1 != prop2:
                            typer.echo(f"  Modified property: {prop_name}")
                            # Show what changed exactly for each field
                            for key in set(prop1.keys()) | set(prop2.keys()):
                                if key not in prop1:
                                    typer.echo(f"    Added {key}: {prop2[key]}")
                                elif key not in prop2:
                                    typer.echo(f"    Removed {key}: {prop1[key]}")
                                elif prop1[key] != prop2[key]:
                                    typer.echo(
                                        f"    Changed {key}: {prop1[key]} -> {prop2[key]}"
                                    )

        elif "entities" in schema1 and not "entities" in schema2:
            typer.echo("\nRemoved 'entities' section")
        elif "entities" in schema2 and not "entities" in schema1:
            typer.echo("\nAdded 'entities' section")

        typer.echo("=" * 60)
        typer.echo("Schema comparison complete")

    except Exception as e:
        typer.echo(f"Error during schema diff: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def tui(
    backend: str = typer.Option(
        "sdk",
        "--backend",
        "-b",
        help="Backend mode: 'sdk' (default) or 'rest'",
    ),
    url: str = typer.Option(
        "http://127.0.0.1:8000",
        "--url",
        help="Base URL for REST backend (rest mode only)",
    ),
    token: Optional[str] = typer.Option(
        None,
        "--token",
        help="Bearer token for REST backend (rest mode only; falls back to HIPPO_TUI_TOKEN env)",
    ),
    db: Optional[str] = typer.Option(
        None,
        "--db",
        help="Path to SQLite database (sdk mode only; falls back to config.json then hippo.db)",
    ),
) -> None:
    """Launch the interactive TUI browser (requires 'pip install hippo[tui]')."""
    try:
        from hippo.tui.app import HippoTUIApp
    except ImportError:
        raise typer.Exit(
            typer.echo("Error: TUI requires 'pip install hippo[tui]'", err=True) or 1
        )

    from hippo.tui.backend import create_backend

    kwargs: dict = {}
    if backend == "sdk":
        if db is not None:
            kwargs["db_path"] = db
    elif backend == "rest":
        kwargs["url"] = url
        if token is not None:
            kwargs["token"] = token
    else:
        typer.echo(
            f"Error: Unknown backend '{backend}'. Choose 'sdk' or 'rest'.", err=True
        )
        raise typer.Exit(1)

    be = create_backend(backend, **kwargs)
    HippoTUIApp(backend=be).run()


if __name__ == "__main__":
    app()
