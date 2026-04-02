"""Init command implementation for Hippo CLI."""

from pathlib import Path
from typing import Optional

import typer

from hippo.cli.templates import (
    get_template,
    get_template_file_content,
    list_templates,
)


class InitCommand:
    """Handles project initialization for Hippo."""

    DEFAULT_TEMPLATE = "basic"
    VALID_STORAGE_BACKENDS = {"sqlite", "postgres"}

    def __init__(
        self, path: Optional[str], template: str, force: bool, storage: str = "sqlite"
    ):
        self.target_path = Path(path) if path else Path.cwd()
        self.template_name = template if template else self.DEFAULT_TEMPLATE
        self.force = force
        self.storage = storage

    def run(self) -> None:
        """Execute the init command."""
        self._validate_storage()
        self._validate_template()
        self._validate_path()
        self._create_directories()
        self._generate_files()
        self._generate_config()

    def _validate_template(self) -> None:
        """Validate template name and show available templates if invalid."""
        template = get_template(self.template_name)
        if template is None:
            available = list_templates()
            typer.echo(f"Error: Unknown template '{self.template_name}'")
            typer.echo("\nAvailable templates:")
            for t in available:
                typer.echo(f"  {t['name']:<12} - {t['description']}")
            raise typer.Exit(1)

    def _validate_path(self) -> None:
        """Validate the target path."""
        if not self.force and self.target_path.exists():
            if list(self.target_path.iterdir()):
                typer.echo(
                    f"Error: Directory {self.target_path} is not empty. "
                    "Use --force to override.",
                    err=True,
                )
                raise typer.Exit(1)

        config_files = ["config.json", "config.toml", "config.yaml"]
        for config_file in config_files:
            config_path = self.target_path / config_file
            if config_path.exists() and not self.force:
                typer.echo(
                    f"Error: {config_path} already exists. "
                    "Use --force to override or remove the existing config file.",
                    err=True,
                )
                raise typer.Exit(1)

    def _create_directories(self) -> None:
        """Create necessary directories."""
        try:
            self.target_path.mkdir(parents=True, exist_ok=True)
            typer.echo(f"Created {self.target_path}/")
        except PermissionError as e:
            typer.echo(
                f"Error: Permission denied when creating {self.target_path}. "
                "Please check your permissions or choose a different location.",
                err=True,
            )
            raise typer.Exit(1)
        except OSError as e:
            typer.echo(
                f"Error: Could not create directory {self.target_path}: {e}",
                err=True,
            )
            raise typer.Exit(1)

        data_dir = self.target_path / "data"
        try:
            data_dir.mkdir(exist_ok=True)
            typer.echo(f"Created {data_dir}/")
        except PermissionError:
            typer.echo(
                f"Error: Permission denied when creating {data_dir}. "
                "Please check your permissions.",
                err=True,
            )
            raise typer.Exit(1)

    def _generate_files(self) -> None:
        """Generate files from template."""
        template = get_template(self.template_name)

        for filename, file_key in template.files.items():
            filepath = self.target_path / filename
            content = get_template_file_content(file_key)

            if content is None:
                typer.echo(
                    f"Warning: Template file '{filename}' not found, skipping",
                    err=True,
                )
                continue

            try:
                filepath.parent.mkdir(parents=True, exist_ok=True)
                filepath.write_text(content)
                typer.echo(f"Created {filepath}")
            except PermissionError:
                typer.echo(
                    f"Error: Permission denied when writing to {filepath}. "
                    "Please check your permissions.",
                    err=True,
                )
                raise typer.Exit(1)
            except OSError as e:
                typer.echo(
                    f"Error: Could not write to {filepath}: {e}",
                    err=True,
                )
                raise typer.Exit(1)

        typer.echo(f"\nHippo project initialized at {self.target_path}")
        typer.echo(f"Template: {template.name}")
        typer.echo(f"Storage: {self.storage}")
        typer.echo("Run 'hippo serve' to start the server")

    def _validate_storage(self) -> None:
        """Validate the storage backend option."""
        if self.storage not in self.VALID_STORAGE_BACKENDS:
            typer.echo(
                f"Error: Unknown storage backend '{self.storage}'. "
                f"Must be one of: {', '.join(sorted(self.VALID_STORAGE_BACKENDS))}",
                err=True,
            )
            raise typer.Exit(1)

    def _generate_config(self) -> None:
        """Generate hippo.yaml config file with storage backend settings."""
        config_path = self.target_path / "hippo.yaml"
        if config_path.exists() and not self.force:
            return

        if self.storage == "postgres":
            config_content = (
                "# Hippo configuration\n"
                "schema_path: schema.yaml\n"
                "storage_backend: postgres\n"
                "database_url: ${HIPPO_DATABASE_URL:-postgresql://localhost:5432/hippo}\n"
            )
        else:
            config_content = (
                "# Hippo configuration\n"
                "schema_path: schema.yaml\n"
                "storage_backend: sqlite\n"
                "# database_url: data/hippo.db\n"
            )

        try:
            config_path.write_text(config_content)
            typer.echo(f"Created {config_path}")
        except OSError as e:
            typer.echo(f"Error: Could not write to {config_path}: {e}", err=True)
            raise typer.Exit(1)


def run_init(
    path: Optional[str],
    template: str,
    force: bool,
    storage: str = "sqlite",
) -> None:
    """Entry point for hippo init command."""
    cmd = InitCommand(path=path, template=template, force=force, storage=storage)
    cmd.run()
