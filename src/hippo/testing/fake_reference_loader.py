"""Network-free ``ReferenceLoader`` for use in Hippo test suites.

Implements every abstract method against an in-memory dataset so tests
exercising loader discovery, the install/upgrade lifecycle, and CLI
plumbing have a concrete entry-point target without depending on a real
reference package.

The loader is deterministic: ``versions()`` lists ``"test"`` and ``"v1"``,
both of which write a small fixed set of ``FakeTerm`` rows through the
``HippoClient`` it is handed. Loader unit tests that need to simulate a
failure mid-load can pass ``params=FakeLoadParams(fail_after=N)`` to
abort the write after ``N`` entities; the rows written before the abort
remain in the database (matching how a real loader behaves if its HTTP
fetch dies mid-stream).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import typer
from pydantic import BaseModel, Field

from hippo.core.loaders.reference import LoadResult, ReferenceLoader

if TYPE_CHECKING:
    from hippo.core.client import HippoClient


class FakeLoadParams(BaseModel):
    """Parameter model rendered by the CLI when the fake loader is
    invoked with ``--flag`` args."""

    tag: str = "default"
    # Internal test knob — if set, ``load()`` raises after persisting
    # this many rows. Real loaders never expose this; it lives here so
    # CLI tests can simulate a partial-load failure without monkey-
    # patching the loader class.
    fail_after: int | None = None


class FakeReferenceLoader(ReferenceLoader):
    """Deterministic, in-memory ``ReferenceLoader`` for the test suite."""

    name = "fake"
    description = "In-memory fake reference loader (test fixture)"
    load_params_schema = FakeLoadParams

    # In-memory dataset keyed by version. Kept tiny on purpose.
    _DATASET: dict[str, list[dict[str, Any]]] = {
        "test": [
            {"label": "alpha"},
            {"label": "beta"},
        ],
        "v1": [
            {"label": "alpha"},
            {"label": "beta"},
            {"label": "gamma"},
        ],
        "v2": [
            {"label": "alpha"},
            {"label": "beta"},
            {"label": "gamma"},
            {"label": "delta"},
        ],
    }

    def versions(self) -> list[str]:
        return list(self._DATASET.keys())

    def entity_types(self) -> list[str]:
        return ["FakeTerm"]

    def schema_fragment(self) -> dict:
        return {
            "id": "https://example.org/hippo/fake",
            "name": "fake",
            "default_prefix": "fake",
            "prefixes": {"fake": "https://example.org/hippo/fake/"},
            "classes": {
                "FakeTerm": {
                    "is_a": "Entity",
                    "attributes": {
                        "label": {"range": "string", "required": True},
                    },
                },
            },
        }

    def load(
        self,
        client: "HippoClient",
        version: str,
        params: BaseModel | None = None,
    ) -> LoadResult:
        rows = self._DATASET.get(version)
        if rows is None:
            return LoadResult(
                errors=1,
                error_messages=[f"unknown version: {version}"],
                entity_type="FakeTerm",
            )

        fail_after: int | None = None
        if isinstance(params, FakeLoadParams):
            fail_after = params.fail_after

        entity_ids: list[str] = []
        for index, row in enumerate(rows):
            if fail_after is not None and index >= fail_after:
                raise RuntimeError(
                    f"FakeReferenceLoader simulated failure after "
                    f"{fail_after} rows"
                )
            result = client.put("FakeTerm", dict(row))
            entity_ids.append(result["id"])

        return LoadResult(
            created=len(entity_ids),
            entity_type="FakeTerm",
            entity_ids=entity_ids,
        )


# ---------------------------------------------------------------------------
# Fixture loaders exercising the load_params_schema → --flag pipeline
# (D2.14.D / PTS-230).
# ---------------------------------------------------------------------------


class RichParams(BaseModel):
    """All-supported-type Pydantic schema for CLI-rendering tests."""

    # required scalar
    organism: str
    # int with default + Pydantic constraint (drives the validation-error test)
    release: int = Field(default=110, ge=1, le=1000)
    # bool with default False — exercises ``--<name>`` / ``--no-<name>``
    cleanup: bool = False
    # list[str] with non-empty default — exercises append-replaces-default
    gene_biotypes: list[str] = Field(default_factory=lambda: ["protein_coding"])
    # Optional[str] with default None — omitted flag yields None
    optional_tag: str | None = None


class RichParamsLoader(ReferenceLoader):
    """Loader with one field per supported type.

    ``load()`` echoes the received params model into ``LoadResult`` so
    tests can round-trip flag → model → loader call. ``params`` MUST be a
    :class:`RichParams` instance (i.e. CLI parsing actually happened).
    """

    name = "rich"
    description = "Fixture loader covering all CLI-renderable parameter types"
    load_params_schema = RichParams

    _DATASET: dict[str, list[dict[str, Any]]] = {
        "test": [{"label": "rich-test"}],
        "v1": [{"label": "rich-v1"}],
    }

    # Most-recent params model received by .load(); inspected by tests.
    last_params: RichParams | None = None

    def versions(self) -> list[str]:
        return list(self._DATASET.keys())

    def entity_types(self) -> list[str]:
        return ["RichTerm"]

    def schema_fragment(self) -> dict:
        return {
            "id": "https://example.org/hippo/rich",
            "name": "rich",
            "default_prefix": "rich",
            "prefixes": {"rich": "https://example.org/hippo/rich/"},
            "classes": {
                "RichTerm": {
                    "is_a": "Entity",
                    "attributes": {
                        "label": {"range": "string", "required": True},
                    },
                },
            },
        }

    def load(
        self,
        client: "HippoClient",
        version: str,
        params: BaseModel | None = None,
    ) -> LoadResult:
        if not isinstance(params, RichParams):
            raise AssertionError(
                f"RichParamsLoader.load expected RichParams instance, "
                f"got {type(params).__name__}"
            )
        # Stash the parsed model on the *class* so test assertions can
        # read it after the CLI invocation returns. Tests reset this
        # between cases.
        type(self).last_params = params

        rows = self._DATASET.get(version, [])
        entity_ids: list[str] = []
        for row in rows:
            result = client.put("RichTerm", dict(row))
            entity_ids.append(result["id"])
        return LoadResult(
            created=len(entity_ids),
            entity_type="RichTerm",
            entity_ids=entity_ids,
        )


class BareReferenceLoader(ReferenceLoader):
    """Loader with ``load_params_schema = None``.

    Used by tests asserting that ``load()`` receives ``params=None`` when
    the loader declares no schema, and that any extra ``--flag`` args
    are rejected with a clear error.
    """

    name = "bare"
    description = "Fixture loader with no parameter schema"
    load_params_schema = None

    _DATASET: dict[str, list[dict[str, Any]]] = {
        "test": [{"label": "bare-test"}],
        "v1": [{"label": "bare-v1"}],
    }

    # Sentinel: distinguishes "load() never called" from "load(params=None)".
    last_params_was_none: bool | None = None

    def versions(self) -> list[str]:
        return list(self._DATASET.keys())

    def entity_types(self) -> list[str]:
        return ["BareTerm"]

    def schema_fragment(self) -> dict:
        return {
            "id": "https://example.org/hippo/bare",
            "name": "bare",
            "default_prefix": "bare",
            "prefixes": {"bare": "https://example.org/hippo/bare/"},
            "classes": {
                "BareTerm": {
                    "is_a": "Entity",
                    "attributes": {
                        "label": {"range": "string", "required": True},
                    },
                },
            },
        }

    def load(
        self,
        client: "HippoClient",
        version: str,
        params: BaseModel | None = None,
    ) -> LoadResult:
        type(self).last_params_was_none = params is None
        rows = self._DATASET.get(version, [])
        entity_ids: list[str] = []
        for row in rows:
            result = client.put("BareTerm", dict(row))
            entity_ids.append(result["id"])
        return LoadResult(
            created=len(entity_ids),
            entity_type="BareTerm",
            entity_ids=entity_ids,
        )


# ---------------------------------------------------------------------------
# Loader-provided Typer sub-app (D2.14.A / PTS-228). Registered via the
# ``hippo.reference_loader_cli`` entry point under the same key as the
# loader (`fake`), Hippo mounts it as ``hippo reference fake ...``.
# ---------------------------------------------------------------------------


fake_cli_app = typer.Typer(
    name="fake",
    help="Fake reference loader subcommands (test fixture).",
)


@fake_cli_app.command(name="echo")
def _fake_echo(
    message: str = typer.Argument("hello", help="Message to echo."),
) -> None:
    """Echo a message — exercises the mounted sub-app code path."""
    typer.echo(message)


@fake_cli_app.command(name="cache-path")
def _fake_cache_path() -> None:
    """Print the cache directory the loader would use.

    Resolved via the canonical :meth:`HippoClient.cache_dir_for` path so
    the sub-app and ``load()`` agree on the same per-loader cache root
    (PTS-228 acceptance: same ``cache_dir_for('fake')``). The subcommand
    instantiates an in-memory ``HippoClient`` because cache resolution
    is stateless and doesn't depend on the on-disk database.
    """
    from hippo.core.client import HippoClient
    from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter
    from hippo.linkml_bridge import SchemaRegistry
    from linkml_runtime.utils.schemaview import SchemaView
    import importlib.resources

    hippo_core_path = importlib.resources.files("hippo.schemas").joinpath(
        "hippo_core.yaml"
    )
    registry = SchemaRegistry(SchemaView(str(hippo_core_path)))
    storage = SQLiteAdapter(":memory:", schema_registry=registry)
    client = HippoClient(storage=storage, registry=registry)
    typer.echo(str(client.cache_dir_for("fake")))
