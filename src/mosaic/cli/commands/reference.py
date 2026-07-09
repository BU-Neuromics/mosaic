"""Reference-loader install/upgrade lifecycle (Mosaic design §2.14).

Implements the loader-driven ``mosaic reference install`` and
``mosaic reference upgrade`` verbs. The flow is:

1. Resolve a registered :class:`ReferenceLoader` from the
   ``mosaic.reference_loaders`` entry-point group (PTS-224).
2. Merge the loader's :meth:`schema_fragment` into the deployed schema
   via :func:`mosaic.linkml_bridge.merge_loader_fragment` (PTS-226).
3. Apply the resulting schema additively against the DB (the same
   migration pipeline ``mosaic schema migrate`` drives).
4. Hand a :class:`MosaicClient` to ``loader.load()`` / ``loader.upgrade()``
   inside a :meth:`MosaicClient.load_context` so every ``client.put()``
   appends a row to ``reference_write_log`` (sec2 §2.14.9, D2.14.J).
5. Record ``{loader_name: version}`` in ``hippo_meta.reference_versions``
   so ``requires:`` and "already installed" checks have a fixed source
   of truth. The v1 ``hippo_meta.reference_entity_ids`` JSON blob is
   gone — ``--prune-old`` queries the write log instead.

Decisions D2.14.F (additive upgrade, opt-in ``--prune-old``),
D2.14.I (``"test"`` reserved slug), and D2.14.J (write-log-driven
prune) are enforced here.

Also exposes :func:`reference_cache_root` and
:func:`clean_reference_cache` (PTS-225) so the ``mosaic reference
clean-cache`` verb can scrub per-loader cache subtrees without
instantiating a full client.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from collections import Counter
from collections.abc import Sequence
import argparse
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ValidationError
from pydantic_core import PydanticUndefined

from mosaic.core.exceptions import DeprovisionRefusedError
from mosaic.core.loaders.reference import (
    EntityRef,
    ExternalData,
    LoadResult,
    SchemaPackage,
)

# Discovery + `requires:` resolution moved to the core SDK layer
# (mosaic.core.loaders.discovery) so the config-driven client factory can
# build a spanning registry without importing the CLI (issue #67). Re-exported
# here so existing `mosaic.cli.commands.reference.<name>` imports keep working.
from mosaic.core.loaders.discovery import (  # noqa: F401  (re-export)
    _CLI_FLAG_SUPPORTED_HELP,
    REFERENCE_LOADERS_GROUP,
    SCHEMA_PACKAGES_GROUP,
    ReferenceLoaderNotFoundError,
    ReferenceLoaderRegistrationError,
    SchemaPackageRegistrationError,
    _build_fragment_spec,
    _build_package_info,
    _classify_load_params_field,
    _normalize_dist_name,
    _resolve_distribution,
    _resolve_group_eps,
    _validate_load_params_schema,
    discover_reference_loaders,
    discover_schema_packages,
    find_loader,
    fragment_specs_for_requires,
)

if TYPE_CHECKING:
    import typer

    from mosaic.core.client import MosaicClient
    from mosaic.linkml_bridge import SchemaRegistry


# Reserved slug per D2.14.I. The constant lives here so internal
# tooling that synthesises version strings can refuse to emit it.
RESERVED_TEST_SLUG = "test"

# hippo_meta key owned by the reference-loader lifecycle. The v1
# ``reference_entity_ids`` JSON blob was retired in v2 (D2.14.J); the
# substrate for ``--prune-old`` is the ``reference_write_log`` table.
META_KEY_VERSIONS = "reference_versions"


def reference_cache_root() -> Path:
    """Resolve the directory holding per-loader reference caches.

    Mirrors :meth:`MosaicClient._reference_cache_root` so the CLI can
    operate without instantiating a full client (sec2 §2.14.3,
    decision D2.14.E). ``$MOSAIC_CACHE_DIR`` wins when set (legacy
    ``$HIPPO_CACHE_DIR`` honored with a ``DeprecationWarning`` —
    ADR-0004); otherwise ``~/.cache/hippo/references/`` (the pre-rename
    on-disk location, kept so installed references stay found).
    """
    from mosaic.config.env import get_env

    env = get_env("CACHE_DIR")
    if env:
        return Path(env)
    return Path.home() / ".cache" / "hippo" / "references"


def clean_reference_cache(name: str | None = None) -> dict[str, Any]:
    """Remove cached reference-loader data.

    With ``name``, removes only that loader's cache subtree; other
    loaders are untouched. Without ``name``, removes the entire cache
    root. Missing targets are a silent no-op (idempotent) so the verb
    is safe to run on a fresh machine.
    """
    root = reference_cache_root()
    if name is not None:
        target = root / name
        existed = target.exists()
        if existed:
            shutil.rmtree(target)
        return {"removed": existed, "path": str(target), "scope": name}
    existed = root.exists()
    if existed:
        shutil.rmtree(root)
    return {"removed": existed, "path": str(root), "scope": None}


def get_references_dir() -> Path:
    """Return the on-disk references directory, creating it if needed.

    Kept for backwards-compatibility with the legacy installed.json
    bookkeeping. The lifecycle implemented here tracks installs in
    ``hippo_meta`` instead.
    """
    data_dir = Path.home() / ".hippo" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    refs_dir = data_dir / "references"
    refs_dir.mkdir(parents=True, exist_ok=True)
    return refs_dir


# ``mosaic.reference_loader_cli`` is canonical; the legacy ``hippo.*``
# spelling stays resolved for the ADR-0004 deprecation window (dedup by
# entry-point name, mosaic wins on collision).
REFERENCE_LOADER_CLI_GROUPS = (
    "mosaic.reference_loader_cli",
    "hippo.reference_loader_cli",  # legacy spelling (ADR-0004)
)


def discover_reference_loader_subapps() -> list[tuple[str, "typer.Typer"]]:
    """Discover loader-provided Typer sub-apps via the
    ``mosaic.reference_loader_cli`` entry-point group (D2.14.A) — or its
    legacy ``hippo.reference_loader_cli`` spelling (ADR-0004).

    Each entry point must resolve to a :class:`typer.Typer` instance.
    Anything else raises :class:`ReferenceLoaderRegistrationError` —
    consistent with the strict reference-loader registration on the
    sibling group (PTS-224). Sub-app registration is *optional*: a
    loader registered only under ``mosaic.reference_loaders`` simply
    won't surface here, leaving ``mosaic reference <name>`` to be served
    by the parent group's install/upgrade/list verbs. Entries are
    deduplicated by name, so a dual-registered sub-app mounts once.
    """
    import typer
    from importlib.metadata import entry_points

    eps_list = []
    seen: set[str] = set()
    for group in REFERENCE_LOADER_CLI_GROUPS:
        try:
            eps = entry_points()
            group_eps = list(eps.select(group=group))
        except (TypeError, AttributeError):
            try:
                eps = entry_points()
                group_eps = list(eps[group])
            except (KeyError, TypeError):
                group_eps = []
        for ep in group_eps:
            if ep.name in seen:
                continue
            seen.add(ep.name)
            eps_list.append(ep)

    subapps: list[tuple[str, typer.Typer]] = []
    for ep in eps_list:
        loaded = ep.load()
        if not isinstance(loaded, typer.Typer):
            raise ReferenceLoaderRegistrationError(
                f"Entry point 'mosaic.reference_loader_cli:{ep.name}' "
                f"({ep.value}) is not a typer.Typer instance"
            )
        subapps.append((ep.name, loaded))
    return subapps


def mount_reference_loader_subapps(reference_app: "typer.Typer") -> None:
    """Mount discovered loader sub-apps under ``reference_app`` (D2.14.A).

    Called at CLI startup so ``mosaic reference <loader> --help`` and
    ``mosaic reference <loader> <subcmd> ...`` reflect the loader's own
    Typer surface. Loaders without a ``mosaic.reference_loader_cli``
    entry are silently skipped — the install/upgrade/list verbs remain
    available on the parent group regardless.
    """
    for loader_name, sub in discover_reference_loader_subapps():
        reference_app.add_typer(sub, name=loader_name)


# ---------------------------------------------------------------------------
# load_params_schema → --flag rendering (D2.14.D). Field classification lives
# in mosaic.core.loaders.discovery (`_classify_load_params_field`); the argparse
# rendering below is the CLI half that consumes it.
# ---------------------------------------------------------------------------


def _field_default(field_info: Any) -> Any:
    """Resolve a Pydantic FieldInfo's default, handling default_factory.

    Returns :data:`pydantic_core.PydanticUndefined` when the field is
    truly required.
    """
    if field_info.default is not PydanticUndefined:
        return field_info.default
    if field_info.default_factory is not None:
        return field_info.default_factory()
    return PydanticUndefined


class _ListStrReplacingAppend(argparse.Action):
    """Append action that *replaces* the model default on first use.

    argparse's stock ``append`` extends whatever default was set, so a
    field declared as ``tags: list[str] = ["primary"]`` plus a user
    passing ``--tags secondary`` would yield ``["primary", "secondary"]``
    — surprising and wrong for our semantics. We want user-provided
    values to fully replace the default, while an omitted flag still
    produces the model default.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._user_seen = False

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: str | None = None,
    ) -> None:
        if not self._user_seen:
            self._user_seen = True
            current: list[str] = []
        else:
            current = list(getattr(namespace, self.dest, None) or [])
        current.append(values)
        setattr(namespace, self.dest, current)


def _build_load_params_parser(
    schema_cls: type[BaseModel],
) -> argparse.ArgumentParser:
    """Build an argparse parser whose options mirror ``schema_cls`` fields.

    Field naming: ``my_field`` becomes ``--my-field``. Required fields
    stay required (argparse raises if omitted); optional fields carry the
    model's default so Pydantic doesn't need to recompute it.
    """
    parser = argparse.ArgumentParser(
        prog=f"<{schema_cls.__name__}>",
        add_help=False,
        exit_on_error=False,
    )
    for field_name, field_info in schema_cls.model_fields.items():
        flag = f"--{field_name.replace('_', '-')}"
        kind, base_type = _classify_load_params_field(field_info.annotation)
        default = _field_default(field_info)
        required = default is PydanticUndefined

        kwargs: dict[str, Any] = {"dest": field_name}
        if required:
            kwargs["required"] = True
        else:
            kwargs["default"] = default

        if kind == "bool":
            kwargs["action"] = argparse.BooleanOptionalAction
        elif kind == "list_str":
            kwargs["action"] = _ListStrReplacingAppend
            kwargs["type"] = str
        else:  # "str" / "int"
            assert base_type is not None
            kwargs["type"] = base_type

        parser.add_argument(flag, **kwargs)
    return parser


def parse_load_params(
    loader: SchemaPackage, extra_args: list[str]
) -> BaseModel | None:
    """Parse ``--<field>`` args against ``loader.load_params_schema``.

    Returns a validated model instance, or ``None`` when the loader
    declares no schema. Surfaces argparse and Pydantic errors as
    :class:`ValueError` so the Typer surface can convert them to a clean
    CLI exit code.
    """
    schema_cls = loader.load_params_schema
    if schema_cls is None:
        if extra_args:
            raise ValueError(
                f"Loader {loader.name!r} accepts no --flag arguments "
                f"(load_params_schema is None); got {extra_args!r}."
            )
        return None

    parser = _build_load_params_parser(schema_cls)
    try:
        namespace = parser.parse_args(extra_args)
    except argparse.ArgumentError as exc:
        raise ValueError(
            f"Invalid --flag arguments for loader {loader.name!r}: {exc}"
        ) from exc
    except SystemExit as exc:
        # Older argparse paths (notably required-arg errors before
        # exit_on_error landed across all code paths) raise SystemExit.
        # Convert so the CLI layer can render a single clean message.
        raise ValueError(
            f"Invalid --flag arguments for loader {loader.name!r} "
            f"(argparse exit {exc.code})."
        ) from exc

    try:
        return schema_cls(**vars(namespace))
    except ValidationError as exc:
        raise ValueError(
            f"Invalid --flag values for loader {loader.name!r}:\n{exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Install / upgrade lifecycle.
# ---------------------------------------------------------------------------


def install_reference(
    name: str,
    version: str | None,
    *,
    db_path: str | Path,
    schema_dir: str | Path | None = None,
    params: "BaseModel | None" = None,
) -> dict[str, Any]:
    """Run the install lifecycle for ``name`` at ``version``.

    Mirrors §2.14 *Install lifecycle*. ``schema_dir`` is the deployed
    user-schema directory (defaults to ``schemas/``); when absent the
    bundled ``hippo_core`` schema is used as the base. ``params`` is
    forwarded verbatim to :meth:`ReferenceLoader.load`.

    Re-installing the same version under the same loader is a no-op —
    the return dict reports ``status='already_installed'`` and exits
    without re-running the loader.
    """
    info = find_loader(name)
    loader: SchemaPackage = info["instance"]
    resolved_version = _resolve_version(loader, version)

    if resolved_version == RESERVED_TEST_SLUG:
        # ``"test"`` is supported when the loader exposes it; otherwise
        # we surface a clear "loader does not implement test fixture"
        # error rather than a confusing "unknown version" from load().
        if RESERVED_TEST_SLUG not in loader.versions():
            raise ValueError(
                f"Loader {name!r} does not expose a {RESERVED_TEST_SLUG!r} "
                f"fixture; pass an explicit --version."
            )

    db = Path(db_path)
    existing = _read_versions(db)
    if existing.get(name) == resolved_version:
        return {
            "name": name,
            "version": resolved_version,
            "status": "already_installed",
        }

    deployed_registry = _load_deployed_registry(schema_dir)
    spec = _build_fragment_spec(info, loader)
    merged_registry = _merge_fragment_into(deployed_registry, spec)

    # SQLiteAdapter.__init__ runs `_init_per_class_tables` and skips
    # already-present tables, so wiring the adapter with the merged
    # registry is sufficient to create the loader's new tables additively.
    # This mirrors the non-interactive half of `mosaic schema migrate`
    # (spec §2.14 install step 3) without the prompt branch.
    client = _build_client(merged_registry, db)
    with client.load_context(loader_name=name, version=resolved_version):
        # Genus lifecycle hook (Doc 2 §2A): ReferenceLoader.provision maps
        # to load(); a pure-schema SchemaPackage inherits the no-op (the
        # fragment is already merged above) and returns None.
        load_result = loader.provision(client, resolved_version, params)
    if load_result is None:
        load_result = LoadResult()
    _abort_on_load_errors(name, resolved_version, load_result)

    _write_versions(db, name, resolved_version)

    return {
        "name": name,
        "version": resolved_version,
        "status": "installed",
        "created": load_result.created,
        "entities": list(load_result.entities),
    }


def upgrade_reference(
    name: str,
    to_version: str | None,
    *,
    db_path: str | Path,
    schema_dir: str | Path | None = None,
    params: "BaseModel | None" = None,
    prune_old: bool = False,
) -> dict[str, Any]:
    """Run the upgrade lifecycle for ``name`` from the recorded version
    to ``to_version``.

    Additive by default (D2.14.F): old-version entities remain in place.
    Pass ``prune_old=True`` to delete the prior version's rows *after*
    the new install succeeds. If the loader raises during ``upgrade``,
    the prior rows are guaranteed to stay intact (the new-version row
    deletion is gated behind a clean LoadResult).
    """
    info = find_loader(name)
    loader: SchemaPackage = info["instance"]
    resolved_to = _resolve_version(loader, to_version)

    db = Path(db_path)
    existing = _read_versions(db)
    from_version = existing.get(name)
    if from_version is None:
        raise ValueError(
            f"Loader {name!r} is not installed; run "
            f"`mosaic reference install {name} --version {resolved_to}` first."
        )
    if from_version == resolved_to:
        return {
            "name": name,
            "from_version": from_version,
            "to_version": resolved_to,
            "status": "already_at_version",
        }

    deployed_registry = _load_deployed_registry(schema_dir)
    spec = _build_fragment_spec(info, loader)
    merged_registry = _merge_fragment_into(deployed_registry, spec)

    client = _build_client(merged_registry, db)
    with client.load_context(loader_name=name, version=resolved_to):
        # Genus lifecycle hook (Doc 2 §2A): ReferenceLoader.evolve maps to
        # upgrade() (re-ingest / diff); a pure-schema SchemaPackage
        # inherits the no-op and returns None.
        load_result = loader.evolve(client, from_version, resolved_to, params)
    if load_result is None:
        load_result = LoadResult()
    _abort_on_load_errors(name, resolved_to, load_result)

    pruned: list[EntityRef] = []
    if prune_old:
        pruned = _prune_via_write_log(db, name, from_version)

    _write_versions(db, name, resolved_to)

    return {
        "name": name,
        "from_version": from_version,
        "to_version": resolved_to,
        "status": "upgraded",
        "created": load_result.created,
        "entities": list(load_result.entities),
        "pruned": pruned,
    }


def _build_merged_registry(schema_dir, installed_infos: list[dict[str, Any]]):
    """Fold every installed package's fragment into the deployed registry.

    The S4 orchestrator validates the post-migration state against the
    *fully merged* schema — user schema + every installed package's
    fragment, **including lab extensions** (sec11 §11.5.2 / §6.3). Unlike
    install/upgrade (which merge one fragment for one operation), the
    orchestrator needs the whole merged closure, so this folds all of them.
    """
    registry = _load_deployed_registry(schema_dir)
    for info in installed_infos:
        spec = _build_fragment_spec(info, info["instance"])
        registry = _merge_fragment_into(registry, spec)
    return registry


def migrate_bundle(
    bundle_source: str | Path | dict[str, Any],
    *,
    db_path: str | Path,
    schema_dir: str | Path | None = None,
    params_by_pkg: dict[str, "BaseModel"] | None = None,
) -> dict[str, Any]:
    """Migrate a multi-package deployment to a target bundle (sec11 §11.5).

    The *one command* of the S4 acceptance criterion: resolves the
    ``depends_on`` graph across all installed packages, drives every pinned
    package through the bundle's coordinate sequence in base→dependent order
    inside a single staged commit-or-rollback scope, and validates the full
    post-migration state (incl. lab extensions) before the one commit. On a
    gate failure the whole chain rolls back and version pointers are left
    untouched.

    ``bundle_source`` is a manifest path (or parsed dict). Returns a result
    dict with the per-package transitions and the committed target versions.
    """
    from mosaic.core.loaders.bundle import Bundle
    from mosaic.core.loaders.orchestrator import migrate_to_bundle

    db = Path(db_path)
    bundle = Bundle.from_manifest(bundle_source)

    # Current installed versions (read on a separate connection BEFORE the
    # staged write-lock opens — must not run inside the scope).
    current = _read_versions(db)

    discovered = {info["name"]: info for info in discover_schema_packages()}
    installed_infos = [discovered[n] for n in current if n in discovered]
    packages = [info["instance"] for info in installed_infos]

    # A pinned target must be a discoverable, installed package — otherwise
    # its evolve would be silently skipped. Fail loud instead.
    unknown = [
        n for n in bundle.packages if n not in {info["name"] for info in installed_infos}
    ]
    if unknown:
        raise ValueError(
            f"bundle {bundle.name!r} pins package(s) {unknown!r} that are not "
            f"installed/discoverable; install them before migrating."
        )

    registry = _build_merged_registry(schema_dir, installed_infos)
    client = _build_client(registry, db)

    result = migrate_to_bundle(
        client, packages, bundle, current, params_by_pkg=params_by_pkg
    )

    # Persist version pointers only after the staged data commit returned
    # clean (the data migration is the atomic unit; mirrors the existing
    # evolve-then-record pattern). On a gate failure migrate_to_bundle
    # raised and we never reach here, so pointers stay at the old versions.
    for pkg_name, version in result.target_versions.items():
        _write_versions(db, pkg_name, version)

    return {
        "bundle": result.bundle,
        "committed": result.committed,
        "migrations": [
            {
                "package": m.package,
                "from_version": m.from_version,
                "to_version": m.to_version,
                "created": m.created,
            }
            for m in result.migrations
        ],
        "target_versions": result.target_versions,
    }


def compute_exposure(
    old_schema: str | Path,
    new_schema: str | Path,
    extension_name: str,
    *,
    extension_fragment: dict[str, Any] | None = None,
):
    """Exposure report for a proposed base migration vs. an installed extension.

    The *pre-migration warning* half of S4 (sec11 §11.6.1): intersect the
    structural write-set of a base migration (``old_schema`` → ``new_schema``,
    two merged-schema YAML files) with the elements an installed extension
    references. Empty ⇒ the base migration is safe to apply without an
    extension step; non-empty ⇒ the lab must supply a complementary step (or
    the end-to-end gate will block it at migration time).

    The extension's fragment defaults to the installed package's
    :meth:`SchemaPackage.schema_fragment`; pass ``extension_fragment`` to
    report against a fragment that is not (yet) installed.
    """
    import yaml as _yaml

    from mosaic.core.loaders.exposure import compute_write_set, exposure_report

    old = _yaml.safe_load(Path(old_schema).read_text(encoding="utf-8")) or {}
    new = _yaml.safe_load(Path(new_schema).read_text(encoding="utf-8")) or {}
    if extension_fragment is None:
        info = find_loader(extension_name)
        extension_fragment = info["instance"].schema_fragment()
    write_set = compute_write_set(old, new)
    return exposure_report(
        write_set, extension_fragment, extension_name=extension_name
    )


def deprovision_reference(
    name: str,
    *,
    db_path: str | Path,
    schema_dir: str | Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Tear down an installed schema package (sec11 §11.4).

    The dependency-ordered teardown:

    1. **Dependents guard (§11.4.4, all species).** Refuse if any *other
       installed* package declares ``name`` in its ``depends_on()`` — the
       error names them. This precedes everything else so a guarded
       package is never partially torn down.
    2. **Species data-retirement hook.** Call
       ``loader.deprovision(client, version, force=force)``:

       * ``DomainModule`` refuses by default when it owns live domain data
         (raises :class:`DeprovisionRefusedError` unless ``force=True``,
         then soft-deletes — §11.4.3);
       * ``ReferenceLoader`` and pure-schema packages inherit the genus
         no-op (a ``ReferenceLoader`` has no write-log handle, so the
         orchestrator prunes its rows — step 3).
    3. **Prune (``ExternalData`` only).** Hard-delete every
       ``reference_write_log``-tracked row for ``name`` across all
       versions. Safe because the source is external and reconstructible
       (D2.14.J substrate; see the wording note below).
    4. **Remove the version record** from ``hippo_meta.reference_versions``
       so the package reads as uninstalled.

    Note on §11.4.2 wording: the spec says ``ReferenceLoader`` deprovision
    *soft-deletes*, but the authoritative ``--prune-old`` / write-log
    substrate (D2.14.J) **hard-deletes**. This orchestrator follows the
    implemented hard-delete for consistency, mirroring ``--prune-old``;
    the ``DomainModule`` path soft-deletes (its data is authoritative, not
    reconstructible). DDL table teardown is out of scope (no destructive
    schema ops in v1; that is the S4 orchestrator's concern).

    Raises ``ValueError`` when ``name`` is not installed.
    """
    info = find_loader(name)
    loader: SchemaPackage = info["instance"]

    db = Path(db_path)
    existing = _read_versions(db)
    version = existing.get(name)
    if version is None:
        raise ValueError(
            f"Loader {name!r} is not installed; nothing to deprovision."
        )

    # 1) Dependents guard — refuse if any installed package depends on this.
    dependents = _find_installed_dependents(name, db)
    if dependents:
        raise DeprovisionRefusedError(
            message=(
                f"Cannot deprovision {name!r}: installed package(s) "
                f"{dependents} depend on it. Deprovision the dependent(s) "
                f"first."
            ),
            package=name,
            reason="has_dependents",
            dependents=dependents,
        )

    deployed_registry = _load_deployed_registry(schema_dir)
    spec = _build_fragment_spec(info, loader)
    merged_registry = _merge_fragment_into(deployed_registry, spec)
    client = _build_client(merged_registry, db)

    # 2) Species hook retires its own data. DomainModule raises
    # DeprovisionRefusedError on live data unless force=True; the genus /
    # ReferenceLoader no-op leaves the prune (step 3) to the orchestrator.
    loader.deprovision(client, version, force=force)

    # 3) Prune external-data rows off the write log (the loader has no
    # write-log handle, so this can't live on the species hook).
    pruned: list[EntityRef] = []
    if isinstance(loader, ExternalData):
        pruned = _prune_all_via_write_log(db, name)

    # 4) Drop the installed-version record so the package reads as gone.
    _remove_version(db, name)

    return {
        "name": name,
        "version": version,
        "status": "deprovisioned",
        "pruned": pruned,
        "forced": force,
    }


def _find_installed_dependents(name: str, db_path: Path) -> list[str]:
    """Return the names of *installed* packages that ``depends_on`` ``name``.

    Cross-references ``hippo_meta.reference_versions`` (the installed set,
    §11.4.4) against each installed package's declared ``depends_on()``
    (a ``list[str]`` of package names — schema_package.py is authoritative
    over the §11.2.2 table). Installed-but-no-longer-discoverable packages
    are skipped rather than crashing the guard.
    """
    installed = _read_versions(db_path)
    dependents: list[str] = []
    for other in installed:
        if other == name:
            continue
        try:
            instance = find_loader(other)["instance"]
        except ReferenceLoaderNotFoundError:
            continue
        if name in instance.depends_on():
            dependents.append(other)
    return sorted(dependents)


def _prune_all_via_write_log(db_path: Path, name: str) -> list[EntityRef]:
    """Hard-delete every ``reference_write_log`` row for ``name`` (all versions).

    The teardown counterpart of :func:`_prune_via_write_log`, which is
    scoped to a single ``from_version`` for ``--prune-old``. Deprovision
    removes the whole package, so it prunes across every version the
    loader ever wrote. Entity rows are deleted per ``entity_type`` group
    and the matching log rows are removed in the same transaction.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        if not _has_write_log_table(cursor):
            return []
        cursor.execute(
            "SELECT entity_id, entity_type FROM reference_write_log "
            "WHERE loader_name = ?",
            (name,),
        )
        rows = cursor.fetchall()
        if not rows:
            return []

        deleted: list[EntityRef] = []
        by_type: dict[str, list[str]] = {}
        for entity_id, entity_type in rows:
            by_type.setdefault(entity_type, []).append(entity_id)
            deleted.append(EntityRef(id=entity_id, type=entity_type))

        try:
            cursor.execute("BEGIN")
            for entity_type, ids in by_type.items():
                placeholders = ",".join("?" * len(ids))
                cursor.execute(
                    f'DELETE FROM "{entity_type}" WHERE id IN ({placeholders})',
                    ids,
                )
            cursor.execute(
                "DELETE FROM reference_write_log WHERE loader_name = ?",
                (name,),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return deleted
    finally:
        conn.close()


def _remove_version(db_path: Path, name: str) -> None:
    """Drop ``name`` from ``hippo_meta.reference_versions`` (uninstall mark).

    The inverse of :func:`_write_versions`. A no-op when the key is
    already absent so the teardown stays idempotent.
    """
    from mosaic.core.meta import get_meta, set_meta

    if not db_path.exists():
        return
    conn = sqlite3.connect(str(db_path))
    try:
        if not _has_meta_table(conn):
            return
        versions = get_meta(conn, META_KEY_VERSIONS) or {}
        if name in versions:
            del versions[name]
            set_meta(conn, META_KEY_VERSIONS, versions)
            conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Listing (read-only).
# ---------------------------------------------------------------------------


def list_reference_loaders(
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """List every discoverable reference loader, annotated with the
    installed version recorded in ``hippo_meta`` (if any).
    """
    discovered = discover_reference_loaders()
    installed_versions: dict[str, str] = {}
    if db_path is not None and Path(db_path).exists():
        installed_versions = _read_versions(Path(db_path))

    result: list[dict[str, Any]] = []
    for loader in discovered:
        installed_version = installed_versions.get(loader["name"])
        result.append(
            {
                "name": loader["name"],
                "description": loader["description"],
                "package": loader["package_name"],
                "package_version": loader["package_version"],
                "installed_version": installed_version,
                "installed": installed_version is not None,
            }
        )
    return result


# ---------------------------------------------------------------------------
# Internals.
# ---------------------------------------------------------------------------


def _resolve_version(loader: SchemaPackage, requested: str | None) -> str:
    if requested is not None:
        return requested
    available = loader.versions()
    if not available:
        raise ValueError(
            f"Loader {loader.name!r} reports no versions; cannot pick a default."
        )
    # Pick the last non-reserved slug so callers without --version don't
    # accidentally install the test fixture.
    for slug in reversed(available):
        if slug != RESERVED_TEST_SLUG:
            return slug
    return available[-1]


def _load_deployed_registry(
    schema_dir: str | Path | None,
) -> "SchemaRegistry":
    from mosaic.linkml_bridge import SchemaRegistry
    from linkml_runtime.utils.schemaview import SchemaView
    import importlib.resources

    if schema_dir is not None:
        path = Path(schema_dir)
        if path.is_dir():
            yamls = list(path.glob("*.yaml")) + list(path.glob("*.yml"))
            if yamls:
                return SchemaRegistry.from_path(path)
        elif path.exists():
            return SchemaRegistry.from_path(path)
    hippo_core_path = importlib.resources.files("mosaic.schemas").joinpath(
        "hippo_core.yaml"
    )
    schema_view = SchemaView(str(hippo_core_path))
    return SchemaRegistry(schema_view)


def _merge_fragment_into(
    deployed_registry: "SchemaRegistry", spec
) -> "SchemaRegistry":
    from mosaic.linkml_bridge import SchemaRegistry, merge_loader_fragment

    merged_sv = merge_loader_fragment(deployed_registry._sv, spec)
    return SchemaRegistry(merged_sv)


def _build_client(
    registry: "SchemaRegistry", db_path: Path
) -> "MosaicClient":
    from mosaic.core.client import MosaicClient
    from mosaic.core.storage.adapters.sqlite_adapter import SQLiteAdapter

    db_path.parent.mkdir(parents=True, exist_ok=True)
    storage = SQLiteAdapter(str(db_path), schema_registry=registry)
    return MosaicClient(storage=storage, registry=registry)


def _abort_on_load_errors(
    name: str, version: str, load_result: LoadResult
) -> None:
    if load_result.errors:
        messages = "; ".join(load_result.error_messages) or "no detail"
        raise ValueError(
            f"Loader {name!r} reported {load_result.errors} error(s) while "
            f"loading version {version!r}: {messages}"
        )


# ---------------------------------------------------------------------------
# Per-entity_type breakdown rendering for the install/upgrade CLI surface
# (sec2 §2.14.8 advisory contract, decisions D2.14.J / D2.14.K).
# ---------------------------------------------------------------------------


def _resolve_breakdown_counts(
    entities: Sequence[EntityRef],
    db_path: Path,
    loader_name: str,
    version: str,
) -> Counter:
    """Choose the source for the per-``entity_type`` count breakdown.

    Honours the advisory contract: when the loader populated
    ``LoadResult.entities`` we count those directly; when it left the
    list empty (large-loader pattern) we fall back to a ``GROUP BY``
    over ``reference_write_log`` scoped to ``(loader_name, version)``.
    Both branches return a :class:`Counter` so the renderer is source-
    agnostic.
    """
    if entities:
        return Counter(e.type for e in entities)
    return _query_write_log_counts(db_path, loader_name, version)


def _query_write_log_counts(
    db_path: Path, loader_name: str, version: str
) -> Counter:
    """Return ``Counter({entity_type: count})`` from ``reference_write_log``.

    Used by the install/upgrade printers when ``LoadResult.entities``
    came back empty — the write log is the authoritative substrate for
    "what got written under ``(loader, version)``" per sec2 §2.14.9.
    A missing db (e.g., a dry-run that never opened it) yields an empty
    Counter so callers can render a stand-alone ``total`` line.
    """
    if not db_path.exists():
        return Counter()
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        if not _has_write_log_table(cursor):
            return Counter()
        cursor.execute(
            "SELECT entity_type, COUNT(*) FROM reference_write_log "
            "WHERE loader_name = ? AND version = ? "
            "GROUP BY entity_type",
            (loader_name, version),
        )
        return Counter({row[0]: row[1] for row in cursor.fetchall()})
    finally:
        conn.close()


def _has_write_log_table(cursor: sqlite3.Cursor) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name='reference_write_log'"
    )
    return cursor.fetchone() is not None


def render_breakdown(header: str, counts: Counter, total: int) -> str:
    """Format a multi-line install/upgrade summary with per-type counts.

    ``header`` is the leading status line (without trailing colon, e.g.
    ``"Installed fake@v1"``); ``counts`` is a :class:`Counter` of
    ``entity_type → row_count``; ``total`` is the scalar preserved from
    ``LoadResult.created`` so the bottom line matches v1 output even
    when the breakdown source disagrees (advisory drift).

    Rows sort by ``(count desc, type asc)`` so the entities-path and the
    write-log-path render byte-identically for the same dataset — the
    acceptance criterion calls that parity out explicitly.
    """
    label_width = max(
        (len(name) for name in counts),
        default=0,
    )
    label_width = max(label_width, len("total"))
    count_width = max(
        (len(f"{count:,}") for count in counts.values()),
        default=0,
    )
    count_width = max(count_width, len(f"{total:,}"))

    lines = [f"{header}:"]
    for entity_type, count in sorted(
        counts.items(), key=lambda kv: (-kv[1], kv[0])
    ):
        lines.append(
            f"  {entity_type:<{label_width}}  {count:>{count_width},}"
        )
    lines.append(f"  {'total':<{label_width}}  {total:>{count_width},}")
    return "\n".join(lines)


def _read_versions(db_path: Path) -> dict[str, str]:
    from mosaic.core.meta import get_meta

    if not db_path.exists():
        return {}
    conn = sqlite3.connect(str(db_path))
    try:
        if not _has_meta_table(conn):
            return {}
        return get_meta(conn, META_KEY_VERSIONS) or {}
    finally:
        conn.close()


def _write_versions(db_path: Path, name: str, version: str) -> None:
    """Record ``{loader_name → current_version}`` in
    ``hippo_meta.reference_versions``.

    Drives ``requires:`` resolution and "already installed" checks.
    The per-version entity-ID JSON blob (``reference_entity_ids``) is no
    longer written — ``--prune-old`` reads ``reference_write_log``
    instead (D2.14.J).
    """
    from mosaic.core.meta import get_meta, set_meta

    conn = sqlite3.connect(str(db_path))
    try:
        versions = get_meta(conn, META_KEY_VERSIONS) or {}
        versions[name] = version
        set_meta(conn, META_KEY_VERSIONS, versions)
        conn.commit()
    finally:
        conn.close()


def _prune_via_write_log(
    db_path: Path, name: str, from_version: str
) -> list[EntityRef]:
    """Hard-delete the prior version's entity rows and write-log rows.

    Driven by the ``reference_write_log`` substrate (sec2 §2.14.9 /
    D2.14.J). Entity tables are deleted by ``id`` per ``entity_type``
    group; the matching log rows for ``(name, from_version)`` are
    removed in the same transaction. The returned list mirrors the
    deleted log rows so callers can surface a per-type breakdown.

    Stable-id upgrade overlap (sec2 §2.14.9): when the new version
    re-wrote the same ``entity_id`` under ``to_version``, prune of
    ``from_version`` removes the entity row even though the new version
    still references it. Loaders that need overlap survival must
    override ``upgrade()`` to skip unchanged writes; this code path
    makes no attempt to spare them.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT entity_id, entity_type FROM reference_write_log "
            "WHERE loader_name = ? AND version = ?",
            (name, from_version),
        )
        rows = cursor.fetchall()
        if not rows:
            return []

        deleted: list[EntityRef] = []
        by_type: dict[str, list[str]] = {}
        for entity_id, entity_type in rows:
            by_type.setdefault(entity_type, []).append(entity_id)
            deleted.append(EntityRef(id=entity_id, type=entity_type))

        try:
            cursor.execute("BEGIN")
            for entity_type, ids in by_type.items():
                placeholders = ",".join("?" * len(ids))
                cursor.execute(
                    f'DELETE FROM "{entity_type}" WHERE id IN ({placeholders})',
                    ids,
                )
            cursor.execute(
                "DELETE FROM reference_write_log "
                "WHERE loader_name = ? AND version = ?",
                (name, from_version),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return deleted
    finally:
        conn.close()


def _has_meta_table(conn: sqlite3.Connection) -> bool:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='hippo_meta'"
    )
    return cursor.fetchone() is not None
