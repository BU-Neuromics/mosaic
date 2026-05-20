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

from pydantic import BaseModel

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
