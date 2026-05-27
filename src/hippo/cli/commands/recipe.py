"""``hippo recipe`` CLI subcommands (sec10 §10.2.2).

Phase 3 PR 5 (PTS-291) ships ``inspect`` only. ``import``, ``export``,
``extend``, ``diff``, ``export-lockfile``, and ``install-from-lockfile``
follow in PRs 6–8 and Phase 4.

CLI handlers stay thin: they construct a :class:`HippoClient` (or
:class:`RecipeService` directly for read-only verbs) and forward to
the SDK. Output formatting is the CLI's concern; SDK return shapes
are typed dataclasses.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from hippo.core.exceptions import RecipeManifestError
from hippo.core.recipe_service import RecipeService


recipe_app = typer.Typer(
    name="recipe",
    help="Manage Hippo recipes — declarative LinkML schema bundles.",
    no_args_is_help=True,
)


@recipe_app.command(name="inspect")
def recipe_inspect(
    source: str = typer.Argument(
        ...,
        help=(
            "Recipe source: a directory path, a tarball path, or a "
            "file:/https: URI. https: support lands in PR 6."
        ),
    ),
    show_elements: bool = typer.Option(
        False,
        "--show-elements",
        help="Also list every class and slot the embedded schema declares.",
    ),
) -> None:
    """Parse, validate, and digest a recipe without any state change.

    Reads ``recipe.yaml`` and ``schema.yaml`` from ``source``, validates
    the manifest against the bundled ``recipe_manifest.yaml`` LinkML
    schema, computes the recipe's canonical content-hash digest
    (sec10 §10.4.3), and prints a one-screen summary.

    No DB writes, no provenance, no cache writes. This is the
    authoring-and-pre-flight verb.
    """
    service = RecipeService()
    try:
        report = service.inspect(source)
    except RecipeManifestError as e:
        typer.echo(f"Error: invalid manifest at {e.source}: {e.message}", err=True)
        for msg in e.errors:
            typer.echo(f"  - {msg}", err=True)
        raise typer.Exit(1)
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    manifest = report.manifest
    typer.echo(f"id:           {manifest.id}")
    typer.echo(f"name:         {manifest.name}")
    typer.echo(f"version:      {manifest.version}")
    typer.echo(f"hippo:        {manifest.hippo_version}")
    typer.echo(f"created_at:   {manifest.created_at}")
    if manifest.description:
        typer.echo(f"description:  {manifest.description}")
    if manifest.license:
        typer.echo(f"license:      {manifest.license}")
    if manifest.parent is not None:
        typer.echo(
            f"parent:       {manifest.parent.id}@{manifest.parent.version} "
            f"({manifest.parent.source})"
        )
    if manifest.requires.recipes:
        typer.echo("requires.recipes:")
        for ref in manifest.requires.recipes:
            typer.echo(f"  - {ref.id}@{ref.version} ({ref.source})")
    if manifest.requires.reference_loaders:
        typer.echo("requires.reference_loaders:")
        for pin in manifest.requires.reference_loaders:
            typer.echo(f"  - {pin}")

    typer.echo(f"digest:       sha256:{report.digest}")
    typer.echo(f"classes:      {len(report.classes)}")
    typer.echo(f"slots:        {len(report.slots)}")

    if show_elements:
        if report.classes:
            typer.echo("\nclasses:")
            for name in report.classes:
                typer.echo(f"  - {name}")
        if report.slots:
            typer.echo("\nslots:")
            for name in report.slots:
                typer.echo(f"  - {name}")
