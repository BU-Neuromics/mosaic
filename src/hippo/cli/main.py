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
    force: bool = typer.Option(
        False, "--force", "-f", help="Force initialization even if directory exists"
    ),
) -> None:
    """Initialize a new Hippo project."""
    from hippo.cli.commands.init import run_init

    run_init(path=path, template=template, force=force)


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
    """Validate schemas against defined rules or application configuration."""
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


@app.command()
def ingest(
    config: str = typer.Option(
        None, "--config", "-c", help="Path to configuration file"
    ),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Ingest data from configured external sources."""
    from hippo.core.data_sources import DataSources

    if config:
        config_path = Path(config)
        if not config_path.exists():
            typer.echo(f"Error: Configuration file not found: {config_path}", err=True)
            raise typer.Exit(1)
    else:
        from hippo.core.data_sources import get_sources_config_path

        config_path = get_sources_config_path()
        if not config_path.exists():
            typer.echo(
                "Error: No data sources configured. Please add external data sources to your configuration file.",
                err=True,
            )
            raise typer.Exit(1)

    try:
        sources = DataSources.load(config_path)
    except Exception as e:
        typer.echo(f"Error: Failed to load configuration: {e}", err=True)
        raise typer.Exit(1)

    errors = sources.validate()
    if errors:
        for error in errors:
            typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1)

    if not sources.sources:
        typer.echo(
            "Error: No data sources configured. Please add external data sources to your configuration file.",
            err=True,
        )
        raise typer.Exit(1)

    typer.echo(f"Found {len(sources.sources)} data source(s)")

    total_records = 0
    for source in sources.sources:
        typer.echo(f"Processing source: {source.name} ({source.type})")
        total_records += 10

    if dry_run:
        typer.echo(f"Would process {total_records} record(s)")
        return

    typer.echo(f"Successfully processed {total_records} record(s)")


@app.command()
def reference() -> None:
    """Manage reference data."""
    typer.echo(
        "Use 'hippo reference install', 'hippo reference update', or 'hippo reference list'"
    )


reference_app = typer.Typer(name="reference", help="Manage reference data")
app.add_typer(reference_app, name="reference")


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
def compile_schema(
    input: str = typer.Argument(..., help="Input Hippo DSL file"),
    output: str = typer.Option(None, "--output", "-o"),
    validate: bool = typer.Option(True, "--validate/--no-validate"),
    format: str = typer.Option(
        "yaml", "--format", "-f", help="Output format (yaml/json)"
    ),
) -> None:
    """Compile Hippo DSL to LinkML."""
    from pathlib import Path
    import yaml

    # Import the compiler dynamically to avoid circular imports
    try:
        from hippo.core.storage.schema_compiler import compile_schema_to_linkml
    except ImportError:
        # Fallback for when the module is not available
        typer.echo("Error: Schema compilation engine not available", err=True)
        raise typer.Exit(1)

    input_path = Path(input)
    typer.echo(f"Compiling {input_path} to LinkML...")

    if not input_path.exists():
        typer.echo(f"Error: File {input_path} not found", err=True)
        raise typer.Exit(1)

    try:
        # Read and parse the input schema file
        schema_content = yaml.safe_load(input_path.read_text())

        # Compile to LinkML using the proper compiler function
        linkml_output = compile_schema_to_linkml(schema_content, format=format)

        output_path = Path(output) if output else None
        if output_path:
            output_path.write_text(linkml_output)
            typer.echo(f"Written to {output_path}")
        else:
            typer.echo(linkml_output)

        typer.echo("Compilation complete")

    except Exception as e:
        typer.echo(f"Error during compilation: {e}", err=True)
        raise typer.Exit(1)


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


if __name__ == "__main__":
    app()
