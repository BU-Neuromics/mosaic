"""Config-driven construction of storage adapters and ``HippoClient``.

Single source of truth for turning configuration into a configured
:class:`~hippo.core.client.HippoClient`. Shared by the CLI, the TUI SDK
backend, and ``hippo serve`` so every transport opens the *same* deployment
the *same* way — there is no longer one construction path for the SDK and
another (or none) for REST.

The storage backend is resolved through the ``hippo.storage_adapters``
entry-point group (``storage_backend`` in config, default ``"sqlite"``), so a
deployment can swap adapters by configuration without code changes. Every
registered adapter shares the construction contract
``Adapter(database_url, schema_registry=registry)``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Union

from hippo.core.exceptions import AdapterError
from hippo.core.storage import EntityStore

#: Backend assumed when config does not specify ``storage_backend``.
DEFAULT_BACKEND = "sqlite"
#: Entry-point group registering storage adapters (see ``pyproject.toml``).
STORAGE_ADAPTERS_GROUP = "hippo.storage_adapters"
#: Where a SQLite deployment lands when config gives no ``database_url``.
DEFAULT_SQLITE_PATH = "data/hippo.db"
#: Config filenames auto-detected in the cwd, in priority order.
CONFIG_CANDIDATES = ("config.json", "hippo.yaml", "hippo.yml")
#: Backends whose import failure should hint at an optional extra.
_BACKEND_EXTRA = {"postgres": "postgres"}

PathLike = Union[str, Path]


def build_schema_registry(schema_path: Optional[PathLike] = None) -> Any:
    """Build a ``SchemaRegistry`` from *schema_path* or the bundled hippo_core.

    The bundled schema declares only Hippo's framework classes (``Entity``,
    ``ProvenanceRecord``, ``ExternalID``, ...). Callers needing user-domain
    classes (``Sample``, ``Project``, ...) must pass an explicit
    *schema_path*.
    """
    from hippo.linkml_bridge import SchemaRegistry

    if schema_path:
        return SchemaRegistry.from_path(schema_path)

    import importlib.resources

    from linkml_runtime.utils.schemaview import SchemaView

    hippo_core_path = importlib.resources.files("hippo.schemas").joinpath(
        "hippo_core.yaml"
    )
    return SchemaRegistry(SchemaView(str(hippo_core_path)))


def resolve_storage_adapter_class(backend: str) -> type[EntityStore]:
    """Resolve a storage-adapter class from ``hippo.storage_adapters``.

    Raises:
        AdapterError: if *backend* is not registered, fails to import (e.g.
            an optional dependency is missing), or does not resolve to an
            :class:`EntityStore` subclass.
    """
    from importlib.metadata import entry_points

    try:
        eps = list(entry_points(group=STORAGE_ADAPTERS_GROUP))
    except TypeError:  # importlib.metadata < 3.10 dict-style API
        eps = list(entry_points().get(STORAGE_ADAPTERS_GROUP, []))  # type: ignore[attr-defined]

    match = next((ep for ep in eps if ep.name == backend), None)
    if match is None:
        available = ", ".join(sorted(ep.name for ep in eps)) or "(none)"
        raise AdapterError(
            f"Unknown storage backend {backend!r}. Registered backends: {available}.",
            adapter_type=backend,
        )

    try:
        cls = match.load()
    except ImportError as exc:
        extra = _BACKEND_EXTRA.get(backend)
        hint = f" Install it with `pip install 'hippo[{extra}]'`." if extra else ""
        raise AdapterError(
            f"Storage backend {backend!r} could not be loaded: {exc}.{hint}",
            adapter_type=backend,
        ) from exc

    if not (isinstance(cls, type) and issubclass(cls, EntityStore)):
        raise AdapterError(
            f"Storage backend {backend!r} does not resolve to an EntityStore "
            f"subclass (got {cls!r}).",
            adapter_type=backend,
        )
    return cls


def create_storage_adapter(
    *,
    storage_backend: Optional[str] = None,
    database_url: Optional[str] = None,
    registry: Any,
) -> EntityStore:
    """Construct a storage adapter for *storage_backend*.

    Resolves the adapter class via the entry-point registry and constructs
    it with the shared ``Adapter(database_url, schema_registry=registry)``
    contract. SQLite defaults to :data:`DEFAULT_SQLITE_PATH` when no
    *database_url* is given; other backends require one.
    """
    backend = storage_backend or DEFAULT_BACKEND
    if not database_url:
        if backend == "sqlite":
            database_url = DEFAULT_SQLITE_PATH
        else:
            raise AdapterError(
                f"Storage backend {backend!r} requires a database_url.",
                adapter_type=backend,
            )
    adapter_cls = resolve_storage_adapter_class(backend)
    return adapter_cls(database_url, schema_registry=registry)


def create_client(
    *,
    storage_backend: Optional[str] = None,
    database_url: Optional[str] = None,
    schema_path: Optional[PathLike] = None,
    validators_path: Optional[PathLike] = None,
    validation_enabled: bool = True,
) -> Any:
    """Assemble a configured ``HippoClient``.

    The single construction path shared by every transport: builds the
    schema registry, resolves and constructs the storage adapter, wires the
    CEL write-validation pipeline, and returns the client.
    """
    from hippo.core.client import HippoClient

    registry = build_schema_registry(schema_path)
    storage = create_storage_adapter(
        storage_backend=storage_backend,
        database_url=database_url,
        registry=registry,
    )
    pipeline = _build_pipeline(validators_path, validation_enabled)
    return HippoClient(storage=storage, registry=registry, pipeline=pipeline)


def create_client_from_config(config: Any) -> Any:
    """Assemble a ``HippoClient`` from a :class:`~hippo.config.HippoConfig`."""
    return create_client(
        storage_backend=config.storage_backend,
        database_url=config.database_url,
        schema_path=config.schema_path,
        validators_path=config.validators_path,
        validation_enabled=config.validation_enabled,
    )


def load_config_autodetect(config_path: Optional[PathLike] = None) -> Any:
    """Load a ``HippoConfig`` from *config_path*, or auto-detect one in the cwd.

    When *config_path* is given it is loaded directly (errors propagate).
    Otherwise the cwd is scanned for :data:`CONFIG_CANDIDATES`; the first
    match is loaded. Returns ``None`` when nothing is given and nothing is
    found, so callers can fall back to built-in defaults.
    """
    from hippo.config import load_hippo_config

    if config_path is not None:
        return load_hippo_config(config_path)
    for candidate in CONFIG_CANDIDATES:
        if Path(candidate).exists():
            return load_hippo_config(candidate)
    return None


def _build_pipeline(
    validators_path: Optional[PathLike], validation_enabled: bool = True
) -> Any:
    """Build a CEL write-validation pipeline, or ``None`` when not configured."""
    if not validation_enabled or not validators_path:
        return None

    from hippo.core.pipeline import ValidationPipeline
    from hippo.core.validators.write_validator import CELWriteValidator

    pipeline = ValidationPipeline()
    pipeline.add_validator(CELWriteValidator(validators_path=str(validators_path)))
    return pipeline
