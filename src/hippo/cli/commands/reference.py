"""Reference-loader install/upgrade lifecycle (Hippo design §2.14).

Implements the loader-driven ``hippo reference install`` and
``hippo reference upgrade`` verbs. The flow is:

1. Resolve a registered :class:`ReferenceLoader` from the
   ``hippo.reference_loaders`` entry-point group (PTS-224).
2. Merge the loader's :meth:`schema_fragment` into the deployed schema
   via :func:`hippo.linkml_bridge.merge_loader_fragment` (PTS-226).
3. Apply the resulting schema additively against the DB (the same
   migration pipeline ``hippo schema migrate`` drives).
4. Hand a :class:`HippoClient` to ``loader.load()`` / ``loader.upgrade()``.
5. Record ``{loader_name: version}`` in ``hippo_meta.reference_versions``
   plus the per-version entity IDs in
   ``hippo_meta.reference_entity_ids`` (for ``--prune-old``).

Decisions D2.14.F (additive upgrade, opt-in ``--prune-old``) and
D2.14.I (``"test"`` reserved slug) are enforced here.

Also exposes :func:`reference_cache_root` and
:func:`clean_reference_cache` (PTS-225) so the ``hippo reference
clean-cache`` verb can scrub per-loader cache subtrees without
instantiating a full client.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from importlib.metadata import (
    PackageNotFoundError,
    distributions,
    version as _dist_version,
)
import argparse
import types as _types
from pathlib import Path
from typing import TYPE_CHECKING, Any, Union, get_args, get_origin

from pydantic import BaseModel, ValidationError
from pydantic_core import PydanticUndefined

from hippo.core.loaders.reference import LoadResult, ReferenceLoader

if TYPE_CHECKING:
    import typer

    from hippo.core.client import HippoClient
    from hippo.linkml_bridge import SchemaRegistry


# Reserved slug per D2.14.I. The constant lives here so internal
# tooling that synthesises version strings can refuse to emit it.
RESERVED_TEST_SLUG = "test"

# hippo_meta keys owned by the reference-loader lifecycle.
META_KEY_VERSIONS = "reference_versions"
META_KEY_ENTITY_IDS = "reference_entity_ids"


class ReferenceLoaderRegistrationError(TypeError):
    """Raised when a ``hippo.reference_loaders`` entry point does not
    resolve to a concrete :class:`ReferenceLoader` subclass."""


class ReferenceLoaderNotFoundError(KeyError):
    """Raised when no ``hippo.reference_loaders`` entry point matches a
    requested loader name."""


def reference_cache_root() -> Path:
    """Resolve the directory holding per-loader reference caches.

    Mirrors :meth:`HippoClient._reference_cache_root` so the CLI can
    operate without instantiating a full client (sec2 §2.14.3,
    decision D2.14.E). ``$HIPPO_CACHE_DIR`` wins when set; otherwise
    ``~/.cache/hippo/references/``.
    """
    env = os.environ.get("HIPPO_CACHE_DIR")
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


def discover_reference_loaders() -> list[dict[str, Any]]:
    """Discover and instantiate reference loaders via entry points.

    Each entry point in the ``hippo.reference_loaders`` group must point
    at a concrete :class:`ReferenceLoader` subclass. The class is
    instantiated eagerly so that callers receive a ready-to-use loader
    surface; an entry point pointing at anything else raises
    :class:`ReferenceLoaderRegistrationError` with a message identifying
    the offending entry point.
    """
    from importlib.metadata import entry_points

    loaders: list[dict[str, Any]] = []

    try:
        eps = entry_points()
        ref_eps = eps.select(group="hippo.reference_loaders")
        eps_list = list(ref_eps)
    except (TypeError, AttributeError):
        try:
            eps = entry_points()
            eps_list = list(eps["hippo.reference_loaders"])
        except (KeyError, TypeError):
            eps_list = []

    for ep in eps_list:
        loaded = ep.load()
        if not (isinstance(loaded, type) and issubclass(loaded, ReferenceLoader)):
            raise ReferenceLoaderRegistrationError(
                f"Entry point 'hippo.reference_loaders:{ep.name}' "
                f"({ep.value}) is not a subclass of "
                f"hippo.core.loaders.reference.ReferenceLoader"
            )
        instance = loaded()
        # D2.14.D — validate at registration that every field on the
        # declared `load_params_schema` (if any) can be rendered as a
        # `--flag` arg. Loaders that ship an unsupported field type
        # fail loud here, not at first CLI invocation.
        if loaded.load_params_schema is not None:
            _validate_load_params_schema(ep.name, loaded.load_params_schema)
        package_name, package_version = _resolve_distribution(loaded.__module__)
        loaders.append(
            {
                "name": ep.name,
                "entry_point": ep.name,
                "class": loaded.__name__,
                "module": loaded.__module__,
                "package_name": package_name,
                "package_version": package_version,
                "description": getattr(instance, "description", ""),
                "instance": instance,
            }
        )

    return loaders


def discover_reference_loader_subapps() -> list[tuple[str, "typer.Typer"]]:
    """Discover loader-provided Typer sub-apps via the
    ``hippo.reference_loader_cli`` entry-point group (D2.14.A).

    Each entry point must resolve to a :class:`typer.Typer` instance.
    Anything else raises :class:`ReferenceLoaderRegistrationError` —
    consistent with the strict reference-loader registration on the
    sibling group (PTS-224). Sub-app registration is *optional*: a
    loader registered only under ``hippo.reference_loaders`` simply
    won't surface here, leaving ``hippo reference <name>`` to be served
    by the parent group's install/upgrade/list verbs.
    """
    import typer
    from importlib.metadata import entry_points

    try:
        eps = entry_points()
        cli_eps = eps.select(group="hippo.reference_loader_cli")
        eps_list = list(cli_eps)
    except (TypeError, AttributeError):
        try:
            eps = entry_points()
            eps_list = list(eps["hippo.reference_loader_cli"])
        except (KeyError, TypeError):
            eps_list = []

    subapps: list[tuple[str, typer.Typer]] = []
    for ep in eps_list:
        loaded = ep.load()
        if not isinstance(loaded, typer.Typer):
            raise ReferenceLoaderRegistrationError(
                f"Entry point 'hippo.reference_loader_cli:{ep.name}' "
                f"({ep.value}) is not a typer.Typer instance"
            )
        subapps.append((ep.name, loaded))
    return subapps


def mount_reference_loader_subapps(reference_app: "typer.Typer") -> None:
    """Mount discovered loader sub-apps under ``reference_app`` (D2.14.A).

    Called at CLI startup so ``hippo reference <loader> --help`` and
    ``hippo reference <loader> <subcmd> ...`` reflect the loader's own
    Typer surface. Loaders without a ``hippo.reference_loader_cli``
    entry are silently skipped — the install/upgrade/list verbs remain
    available on the parent group regardless.
    """
    for loader_name, sub in discover_reference_loader_subapps():
        reference_app.add_typer(sub, name=loader_name)


def find_loader(name: str) -> dict[str, Any]:
    """Look up a single loader info dict by entry-point name.

    Raises :class:`ReferenceLoaderNotFoundError` with a clear message
    when no loader is registered under ``name``.
    """
    for info in discover_reference_loaders():
        if info["name"] == name:
            return info
    raise ReferenceLoaderNotFoundError(
        f"No reference loader registered under name {name!r}. "
        f"Install the corresponding hippo-reference-* package or check "
        f"the ``hippo.reference_loaders`` entry point in its pyproject.toml."
    )


def _resolve_distribution(module: str) -> tuple[str, str]:
    """Best-effort lookup of the package name + version that ships ``module``.

    Falls back to ``("<unknown>", "0")`` when the module isn't owned by
    a discoverable distribution (e.g., running from a source checkout).
    """
    # Walk the installed distributions and find the one that owns the
    # top-level package of ``module``. The mapping API isn't always
    # reliable across Python versions; this loop is small and explicit.
    top_pkg = module.split(".", 1)[0]
    for dist in distributions():
        try:
            top_level = dist.read_text("top_level.txt") or ""
        except FileNotFoundError:
            top_level = ""
        top_names = {line.strip() for line in top_level.splitlines() if line.strip()}
        if top_pkg in top_names or dist.metadata["Name"].replace("-", "_") == top_pkg:
            return dist.metadata["Name"], dist.version
    try:
        return top_pkg, _dist_version(top_pkg)
    except PackageNotFoundError:
        return top_pkg, "0"


# ---------------------------------------------------------------------------
# load_params_schema → --flag rendering (D2.14.D).
# ---------------------------------------------------------------------------


_CLI_FLAG_SUPPORTED_HELP = "str, int, bool, list[str], or Optional thereof"


def _classify_load_params_field(
    annotation: Any,
) -> tuple[str, type | None]:
    """Classify a Pydantic field annotation for CLI rendering.

    Returns a ``(kind, base_type)`` pair. ``kind`` is one of:

    - ``"str"`` / ``"int"`` — scalar arg; ``base_type`` is the converter.
    - ``"bool"`` — rendered as ``--<name>`` / ``--no-<name>``.
    - ``"list_str"`` — rendered as repeated ``--<name>`` args.
    - ``"unsupported"`` — out of scope for v1.

    Optional[T] unwraps to T; Optional[list[str]] is treated as list[str]
    (argparse can carry ``default=None`` for that case).
    """
    inner = annotation
    if get_origin(inner) in (Union, _types.UnionType):
        non_none = [arg for arg in get_args(inner) if arg is not type(None)]
        if len(non_none) == 1:
            inner = non_none[0]
        else:
            return ("unsupported", None)

    if inner is str:
        return ("str", str)
    if inner is int:
        return ("int", int)
    if inner is bool:
        return ("bool", bool)
    if get_origin(inner) is list:
        list_args = get_args(inner)
        if len(list_args) == 1 and list_args[0] is str:
            return ("list_str", str)
    return ("unsupported", None)


def _validate_load_params_schema(
    loader_name: str, schema_cls: type[BaseModel]
) -> None:
    """Raise if any field of ``schema_cls`` can't be rendered as a CLI flag.

    The error message names both the offending field and the type so the
    loader author can fix it at registration time rather than discovering
    the problem when an end user runs ``hippo reference install``.
    """
    for field_name, field_info in schema_cls.model_fields.items():
        kind, _ = _classify_load_params_field(field_info.annotation)
        if kind == "unsupported":
            raise ReferenceLoaderRegistrationError(
                f"Reference loader {loader_name!r}: field {field_name!r} on "
                f"{schema_cls.__name__} has type {field_info.annotation!r}, "
                f"which is not supported for CLI rendering. "
                f"Supported: {_CLI_FLAG_SUPPORTED_HELP}."
            )


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
    field declared as ``gene_biotypes: list[str] = ["protein_coding"]``
    plus a user passing ``--gene-biotypes miRNA`` would yield
    ``["protein_coding", "miRNA"]`` — surprising and wrong for our
    semantics. We want user-provided values to fully replace the
    default, while an omitted flag still produces the model default.
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

    Field naming: ``gene_biotypes`` becomes ``--gene-biotypes``. Required
    fields stay required (argparse raises if omitted); optional fields
    carry the model's default so Pydantic doesn't need to recompute it.
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
    loader: ReferenceLoader, extra_args: list[str]
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
    loader: ReferenceLoader = info["instance"]
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
    # This mirrors the non-interactive half of `hippo schema migrate`
    # (spec §2.14 install step 3) without the prompt branch.
    client = _build_client(merged_registry, db)
    load_result = loader.load(client, resolved_version, params)
    _abort_on_load_errors(name, resolved_version, load_result)

    _write_versions(db, name, resolved_version, load_result.entity_ids)

    return {
        "name": name,
        "version": resolved_version,
        "status": "installed",
        "created": load_result.created,
        "entity_type": load_result.entity_type,
        "entity_ids": list(load_result.entity_ids),
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
    loader: ReferenceLoader = info["instance"]
    resolved_to = _resolve_version(loader, to_version)

    db = Path(db_path)
    existing = _read_versions(db)
    from_version = existing.get(name)
    if from_version is None:
        raise ValueError(
            f"Loader {name!r} is not installed; run "
            f"`hippo reference install {name} --version {resolved_to}` first."
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
    load_result = loader.upgrade(client, from_version, resolved_to, params)
    _abort_on_load_errors(name, resolved_to, load_result)

    pruned_ids: list[str] = []
    if prune_old:
        prior_ids = _read_entity_ids(db).get(name, {}).get(from_version, [])
        if not prior_ids:
            raise ValueError(
                f"--prune-old requested but no entity IDs were recorded for "
                f"{name}@{from_version} (loader did not populate "
                f"LoadResult.entity_ids at install time)."
            )
        pruned_ids = _delete_entities(client, load_result.entity_type, prior_ids)

    _write_versions(db, name, resolved_to, load_result.entity_ids)
    if prune_old:
        _forget_entity_ids(db, name, from_version)

    return {
        "name": name,
        "from_version": from_version,
        "to_version": resolved_to,
        "status": "upgraded",
        "created": load_result.created,
        "entity_type": load_result.entity_type,
        "entity_ids": list(load_result.entity_ids),
        "pruned": pruned_ids,
    }


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


def _resolve_version(loader: ReferenceLoader, requested: str | None) -> str:
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
    from hippo.linkml_bridge import SchemaRegistry
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
    hippo_core_path = importlib.resources.files("hippo.schemas").joinpath(
        "hippo_core.yaml"
    )
    schema_view = SchemaView(str(hippo_core_path))
    return SchemaRegistry(schema_view)


def _build_fragment_spec(info: dict[str, Any], loader: ReferenceLoader):
    from hippo.linkml_bridge import LoaderFragmentSpec

    return LoaderFragmentSpec(
        loader_name=loader.name,
        package_name=info["package_name"],
        package_version=info["package_version"],
        fragment=loader.schema_fragment(),
    )


def _merge_fragment_into(
    deployed_registry: "SchemaRegistry", spec
) -> "SchemaRegistry":
    from hippo.linkml_bridge import SchemaRegistry, merge_loader_fragment

    merged_sv = merge_loader_fragment(deployed_registry._sv, spec)
    return SchemaRegistry(merged_sv)


def _build_client(
    registry: "SchemaRegistry", db_path: Path
) -> "HippoClient":
    from hippo.core.client import HippoClient
    from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter

    db_path.parent.mkdir(parents=True, exist_ok=True)
    storage = SQLiteAdapter(str(db_path), schema_registry=registry)
    return HippoClient(storage=storage, registry=registry)


def _abort_on_load_errors(
    name: str, version: str, load_result: LoadResult
) -> None:
    if load_result.errors:
        messages = "; ".join(load_result.error_messages) or "no detail"
        raise ValueError(
            f"Loader {name!r} reported {load_result.errors} error(s) while "
            f"loading version {version!r}: {messages}"
        )


def _read_versions(db_path: Path) -> dict[str, str]:
    from hippo.core.meta import get_meta

    if not db_path.exists():
        return {}
    conn = sqlite3.connect(str(db_path))
    try:
        if not _has_meta_table(conn):
            return {}
        return get_meta(conn, META_KEY_VERSIONS) or {}
    finally:
        conn.close()


def _read_entity_ids(db_path: Path) -> dict[str, dict[str, list[str]]]:
    from hippo.core.meta import get_meta

    if not db_path.exists():
        return {}
    conn = sqlite3.connect(str(db_path))
    try:
        if not _has_meta_table(conn):
            return {}
        return get_meta(conn, META_KEY_ENTITY_IDS) or {}
    finally:
        conn.close()


def _write_versions(
    db_path: Path,
    name: str,
    version: str,
    entity_ids: list[str],
) -> None:
    from hippo.core.meta import get_meta, set_meta

    conn = sqlite3.connect(str(db_path))
    try:
        versions = get_meta(conn, META_KEY_VERSIONS) or {}
        versions[name] = version
        set_meta(conn, META_KEY_VERSIONS, versions)

        ids_map = get_meta(conn, META_KEY_ENTITY_IDS) or {}
        ids_map.setdefault(name, {})[version] = list(entity_ids)
        set_meta(conn, META_KEY_ENTITY_IDS, ids_map)
        conn.commit()
    finally:
        conn.close()


def _forget_entity_ids(db_path: Path, name: str, version: str) -> None:
    from hippo.core.meta import get_meta, set_meta

    conn = sqlite3.connect(str(db_path))
    try:
        ids_map = get_meta(conn, META_KEY_ENTITY_IDS) or {}
        per_loader = ids_map.get(name) or {}
        per_loader.pop(version, None)
        if per_loader:
            ids_map[name] = per_loader
        else:
            ids_map.pop(name, None)
        set_meta(conn, META_KEY_ENTITY_IDS, ids_map)
        conn.commit()
    finally:
        conn.close()


def _delete_entities(
    client: "HippoClient", entity_type: str | None, entity_ids: list[str]
) -> list[str]:
    if entity_type is None or not entity_ids:
        return []
    deleted: list[str] = []
    for entity_id in entity_ids:
        client.delete(entity_type, entity_id, bypass_validation=True)
        deleted.append(entity_id)
    return deleted


def _has_meta_table(conn: sqlite3.Connection) -> bool:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='hippo_meta'"
    )
    return cursor.fetchone() is not None
