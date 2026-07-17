"""Filter-operator validation (issue #129).

Only ``eq`` and ``in`` are implemented (:data:`VALID_FILTER_OPS`). Before this
fix, any other ``op`` (``gt``/``lt``/``ne``/``contains``/...) silently fell
through to exact equality — the worst failure mode for a query API, because it
returns a *wrong* result set rather than erroring, and ``ne`` returns the exact
inverse of what was asked. A canonical filter dict carrying the key
``operator`` (the ``FilterCondition`` model field name) instead of ``op`` was
likewise silently ignored and defaulted to ``eq``.

These tests pin the new loud behavior: unsupported ops and the ``operator``
slip raise ``ValidationError`` on every read path (live SQL, as-of, and the
low-level adapter), while ``eq``/``in``/bare-shorthand keep working.
"""

import os
import tempfile

import pytest

from mosaic.core.client import MosaicClient
from mosaic.core.exceptions import ValidationError
from mosaic.core.storage import Query, normalize_filter
from mosaic.core.storage.adapters.sqlite_adapter import SQLiteAdapter
from tests.conftest import _build_minimal_schema_registry

FUTURE = "2999-01-01T00:00:00+00:00"


class TestNormalizeFilterUnit:
    """``normalize_filter`` is the single chokepoint both adapters route
    through, so validating there covers every backend and both the live and
    as-of read paths at once."""

    def test_eq_default_and_explicit_pass(self) -> None:
        assert normalize_filter({"field": "name", "value": "A"}) == [("name", "eq", "A")]
        assert normalize_filter({"field": "name", "op": "eq", "value": "A"}) == [
            ("name", "eq", "A")
        ]

    def test_in_op_passes(self) -> None:
        assert normalize_filter({"field": "name", "op": "in", "value": ["A", "B"]}) == [
            ("name", "in", ["A", "B"])
        ]

    def test_bare_shorthand_passes(self) -> None:
        assert normalize_filter({"name": "A", "tissue": "brain"}) == [
            ("name", "eq", "A"),
            ("tissue", "eq", "brain"),
        ]

    @pytest.mark.parametrize(
        "op", ["gt", "lt", "gte", "lte", "ne", "not_in", "contains", "starts_with", "is_null"]
    )
    def test_unsupported_op_raises(self, op: str) -> None:
        with pytest.raises(ValidationError, match="Unsupported filter operator"):
            normalize_filter({"field": "score", "op": op, "value": 1})

    def test_operator_key_without_op_raises(self) -> None:
        with pytest.raises(ValidationError, match="operator"):
            normalize_filter({"field": "name", "operator": "eq", "value": "A"})

    def test_op_takes_precedence_over_stray_operator_key(self) -> None:
        # A well-formed dict that also carries a stray ``operator`` is honored
        # by ``op`` and the extra key ignored (no false positive).
        assert normalize_filter(
            {"field": "name", "op": "eq", "operator": "ne", "value": "A"}
        ) == [("name", "eq", "A")]


class TestFilterOpValidationThroughClient:
    """End-to-end through ``MosaicClient.query`` — the caller-facing surface
    described in the issue's repro."""

    @pytest.fixture
    def client(self) -> MosaicClient:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = SQLiteAdapter(
                os.path.join(tmpdir, "ops.db"),
                schema_registry=_build_minimal_schema_registry(),
            )
            c = MosaicClient(storage=storage, bypass_validation=True)
            c.put("Sample", {"id": "s1", "name": "Alpha", "tissue": "brain"})
            c.put("Sample", {"id": "s2", "name": "Beta", "tissue": "liver"})
            yield c

    def test_gt_raises_rather_than_matching_equality(self, client: MosaicClient) -> None:
        with pytest.raises(ValidationError, match="Unsupported filter operator"):
            client.query("Sample", filters=[{"field": "name", "op": "gt", "value": "Alpha"}])

    def test_ne_raises_rather_than_returning_inverse(self, client: MosaicClient) -> None:
        # The dangerous case: silently, ``ne`` used to return the entities that
        # DID equal the value — the logical opposite of "not equal".
        with pytest.raises(ValidationError, match="Unsupported filter operator"):
            client.query("Sample", filters=[{"field": "name", "op": "ne", "value": "Alpha"}])

    def test_operator_key_raises(self, client: MosaicClient) -> None:
        with pytest.raises(ValidationError, match="operator"):
            client.query("Sample", filters=[{"field": "name", "operator": "eq", "value": "Alpha"}])

    def test_unsupported_op_raises_on_as_of_path_too(self, client: MosaicClient) -> None:
        with pytest.raises(ValidationError, match="Unsupported filter operator"):
            client.query(
                "Sample",
                filters=[{"field": "name", "op": "contains", "value": "lph"}],
                as_of=FUTURE,
            )

    def test_supported_ops_still_work(self, client: MosaicClient) -> None:
        eq = client.query("Sample", filters=[{"field": "name", "value": "Alpha"}])
        assert {i["id"] for i in eq.items} == {"s1"}
        in_ = client.query(
            "Sample", filters=[{"field": "tissue", "op": "in", "value": ["brain", "liver"]}]
        )
        assert {i["id"] for i in in_.items} == {"s1", "s2"}


class TestFilterOpValidationLowLevelAdapter:
    """Directly exercises ``SQLiteAdapter.find`` (bypassing ``MosaicClient``)
    so the guard is pinned at the adapter boundary too."""

    @pytest.fixture
    def adapter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            a = SQLiteAdapter(
                os.path.join(tmpdir, "ops_adapter.db"),
                schema_registry=_build_minimal_schema_registry(),
            )
            yield a
            a.close()

    def test_find_with_unsupported_op_raises(self, adapter) -> None:
        query = Query(entity_type="Sample", filters=[{"field": "name", "op": "gt", "value": "A"}])
        with pytest.raises(ValidationError, match="Unsupported filter operator"):
            list(adapter.find(query))
