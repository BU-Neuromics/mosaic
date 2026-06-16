"""Entity inspection verbs — ``hippo entity`` and ``hippo status``.

Read-only CLI affordances over the SDK query surface (sec4):

- ``hippo entity get`` — fetch one entity by type and id.
- ``hippo entity query`` — list entities with field filters.
- ``hippo entity search`` — full-text search over ``hippo_search``
  fields.
- ``hippo entity history`` — the entity's provenance trail.
- ``hippo status`` — adapter, schema version, entity counts, and
  capability summary (mirrors ``GET /status``).

All verbs are thin wrappers over :class:`HippoClient` (SDK-first,
transports thin) and default to YAML output; pass ``--json`` for
machine-readable JSON.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import typer

entity_app = typer.Typer(
    name="entity", help="Inspect entities: get, query, search, history"
)

_DB_PATH_OPTION = typer.Option(
    None, "--db-path", help="Path to the SQLite database (default: data/hippo.db)"
)
_SCHEMA_OPTION = typer.Option(
    None,
    "--schema",
    help=(
        "Path to the LinkML schema file or directory. Without it only "
        "the bundled hippo_core classes are recognized."
    ),
)
_JSON_OPTION = typer.Option(
    False, "--json", help="Emit JSON instead of YAML"
)


def _emit(payload: Any, as_json: bool) -> None:
    """Print ``payload`` as JSON or YAML."""
    if as_json:
        typer.echo(json.dumps(payload, indent=2, default=str))
    else:
        import yaml

        typer.echo(
            yaml.safe_dump(payload, sort_keys=False, default_flow_style=False).rstrip()
        )


def _get_readonly_client(db_path: Optional[str], schema: Optional[str]):
    """Build a client for read-only verbs, refusing to create a new DB.

    ``SQLiteAdapter`` creates the database file on first connection; for
    inspection commands a missing database is a caller mistake, not a
    reason to materialize an empty ``data/hippo.db``.
    """
    from pathlib import Path

    from hippo.cli.main import _get_client

    path = Path(db_path) if db_path else Path("data/hippo.db")
    if not path.exists():
        typer.echo(
            f"Error: database not found: {path} (use --db-path to point at "
            f"an existing Hippo database)",
            err=True,
        )
        raise typer.Exit(1)
    return _get_client(db_path=str(path), schema_path=schema)


def _parse_filters(filters: list[str]) -> list[dict[str, Any]]:
    """Parse repeated ``--filter field=value`` options into SDK filters."""
    parsed: list[dict[str, Any]] = []
    for raw in filters:
        field, sep, value = raw.partition("=")
        if not sep or not field:
            typer.echo(
                f"Error: invalid --filter {raw!r}; expected field=value", err=True
            )
            raise typer.Exit(1)
        parsed.append({"field": field, "operator": "eq", "value": value})
    return parsed


@entity_app.command(name="get")
def entity_get(
    entity_type: str = typer.Argument(..., help="Entity type, e.g. Sample"),
    entity_id: str = typer.Argument(..., help="Entity UUID"),
    expand: Optional[str] = typer.Option(
        None, "--expand", help="Expand path for related entities, e.g. donor_id"
    ),
    db_path: Optional[str] = _DB_PATH_OPTION,
    schema: Optional[str] = _SCHEMA_OPTION,
    as_json: bool = _JSON_OPTION,
) -> None:
    """Fetch a single entity by type and id."""
    from hippo.core.exceptions import HippoError

    client = _get_readonly_client(db_path, schema)
    try:
        entity = client.get(entity_type, entity_id, expand=expand)
    except HippoError as e:
        typer.echo(f"Error: {e.message}", err=True)
        raise typer.Exit(1)

    _emit(entity, as_json)


@entity_app.command(name="query")
def entity_query(
    entity_type: str = typer.Argument(..., help="Entity type, e.g. Sample"),
    filters: list[str] = typer.Option(
        [],
        "--filter",
        "-f",
        help="Field filter as field=value; repeat for AND composition",
    ),
    limit: int = typer.Option(100, "--limit", help="Maximum number of results"),
    offset: int = typer.Option(0, "--offset", help="Number of results to skip"),
    db_path: Optional[str] = _DB_PATH_OPTION,
    schema: Optional[str] = _SCHEMA_OPTION,
    as_json: bool = _JSON_OPTION,
) -> None:
    """Query entities of a type with optional field filters."""
    from hippo.core.exceptions import HippoError

    parsed_filters = _parse_filters(filters)

    client = _get_readonly_client(db_path, schema)
    try:
        result = client.query(
            entity_type,
            filters=parsed_filters or None,
            limit=limit,
            offset=offset,
        )
    except HippoError as e:
        typer.echo(f"Error: {e.message}", err=True)
        raise typer.Exit(1)

    _emit(
        {
            "items": result.items,
            "total": result.total,
            "limit": result.limit,
            "offset": result.offset,
        },
        as_json,
    )


@entity_app.command(name="search")
def entity_search(
    entity_type: str = typer.Argument(..., help="Entity type, e.g. Sample"),
    query: str = typer.Argument(..., help="Full-text search query"),
    limit: int = typer.Option(100, "--limit", help="Maximum number of results"),
    db_path: Optional[str] = _DB_PATH_OPTION,
    schema: Optional[str] = _SCHEMA_OPTION,
    as_json: bool = _JSON_OPTION,
) -> None:
    """Full-text search over fields declared with hippo_search."""
    from hippo.core.exceptions import HippoError

    client = _get_readonly_client(db_path, schema)
    try:
        results = client.search(entity_type, query, limit=limit)
    except HippoError as e:
        typer.echo(f"Error: {e.message}", err=True)
        raise typer.Exit(1)

    _emit({"items": results, "total": len(results)}, as_json)


@entity_app.command(name="history")
def entity_history(
    entity_id: str = typer.Argument(..., help="Entity UUID"),
    db_path: Optional[str] = _DB_PATH_OPTION,
    schema: Optional[str] = _SCHEMA_OPTION,
    as_json: bool = _JSON_OPTION,
) -> None:
    """Show the provenance trail for an entity, oldest first."""
    from hippo.core.exceptions import HippoError

    client = _get_readonly_client(db_path, schema)
    try:
        history = client.history(entity_id)
    except HippoError as e:
        typer.echo(f"Error: {e.message}", err=True)
        raise typer.Exit(1)

    if not history:
        typer.echo(f"No provenance records for entity {entity_id!r}", err=True)
        raise typer.Exit(1)

    _emit(history, as_json)


def status(
    db_path: Optional[str] = _DB_PATH_OPTION,
    schema: Optional[str] = _SCHEMA_OPTION,
    as_json: bool = _JSON_OPTION,
) -> None:
    """Show deployment status: adapter, schema version, entity counts,
    and capability summary (mirrors ``GET /status``)."""
    from hippo.core.exceptions import HippoError

    client = _get_readonly_client(db_path, schema)
    try:
        _emit(client.status(), as_json)
    except HippoError as e:
        typer.echo(f"Error: {e.message}", err=True)
        raise typer.Exit(1)
