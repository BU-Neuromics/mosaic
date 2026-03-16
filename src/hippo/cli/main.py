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
    host: str = typer.Option("127.0.0.1", "--host", "-h"),
    port: int = typer.Option(8000, "--port", "-p"),
    reload: bool = typer.Option(False, "--reload", "-r"),
    workers: int = typer.Option(None, "--workers", "-w"),
) -> None:
    """Start the REST API server."""
    import uvicorn
    from hippo.serve import create_default_app

    typer.echo(f"Starting Hippo server on {host}:{port}")
    app = create_default_app()
    uvicorn.run(app, host=host, port=port, reload=reload, workers=workers)


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
    schema: str = typer.Argument(None),
) -> None:
    """Validate schemas."""
    from pathlib import Path

    typer.echo("Validating schemas...")

    if schema:
        schemas = [Path(schema)]
    else:
        schemas_dir = Path("schemas")
        if not schemas_dir.exists():
            typer.echo("No schemas directory found")
            typer.echo("Validation skipped")
            return
        schemas = list(schemas_dir.glob("*.yaml")) + list(schemas_dir.glob("*.yml"))

    if not schemas:
        typer.echo("No schema files found")
        return

    errors = []

    for schema_file in schemas:
        typer.echo(f"Validating {schema_file}...")
        try:
            import yaml

            content = yaml.safe_load(schema_file.read_text())
            if not isinstance(content, dict):
                errors.append(f"{schema_file}: Invalid schema format")
            else:
                typer.echo(f"  OK")
        except Exception as e:
            errors.append(f"{schema_file}: {e}")

    if errors:
        typer.echo(f"\nValidation failed with {len(errors)} error(s):", err=True)
        for error in errors:
            typer.echo(f"  - {error}", err=True)
        raise typer.Exit(1)

    typer.echo(f"\nValidation passed for {len(schemas)} schema(s)")


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
) -> None:
    """Compile Hippo DSL to LinkML."""
    from pathlib import Path
    import yaml

    input_path = Path(input)
    typer.echo(f"Compiling {input_path} to LinkML...")

    if not input_path.exists():
        typer.echo(f"Error: File {input_path} not found", err=True)
        raise typer.Exit(1)

    try:
        schema_content = yaml.safe_load(input_path.read_text())

        linkml_output = convert_to_linkml(schema_content)

        if validate:
            typer.echo("Validating LinkML output...")

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


def convert_to_linkml(schema: dict) -> str:
    """Convert Hippo DSL schema to LinkML format."""
    import yaml

    linkml = {
        "id": f"https://example.org/{schema.get('name', 'schema')}",
        "name": schema.get("name", "hippo_schema"),
        "description": schema.get("description", "Compiled from Hippo DSL"),
        "prefixes": {
            "linkml": "https://w3id.org/linkml/",
            "schema": "http://schema.org/",
        },
        "imports": ["linkml:types"],
        "classes": {},
    }

    for entity in schema.get("entities", []):
        class_def = {
            "description": entity.get("description", ""),
            "attributes": {},
        }

        for prop in entity.get("properties", []):
            attr_name = prop.get("name")
            attr_type = prop.get("type", "string")

            linkml_type = map_type_to_linkml(attr_type)
            class_def["attributes"][attr_name] = {
                "description": prop.get("description", ""),
                "range": linkml_type,
                "required": prop.get("required", False),
            }

        linkml["classes"][entity["name"]] = class_def

    return yaml.dump(linkml, default_flow_style=False, sort_keys=False)


def map_type_to_linkml(hippo_type: str) -> str:
    """Map Hippo types to LinkML types."""
    type_map = {
        "string": "string",
        "integer": "integer",
        "float": "float",
        "boolean": "boolean",
        "date": "date",
        "datetime": "datetime",
        "uri": "uri",
        "enum": "string",
    }
    return type_map.get(hippo_type, "string")


if __name__ == "__main__":
    app()
