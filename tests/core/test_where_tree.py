"""Boolean filter trees on the SDK query surface (ADR-0006 increment 2).

``client.query(where=...)`` takes a leaf ``{"field", "op", "value"}`` or
nested ``{"and"|"or"|"not"}`` combinators, validated by ``normalize_where``
and compiled to SQL by the adapters' tree compilers. Every behavior is
asserted on the live SQL path AND the as-of path (``matches_tree``, the
shared mirror) — the two must never diverge, including the two-valued
``not`` semantics (an entity missing the field satisfies the negation).
"""

import os
import tempfile

import pytest

from mosaic.core.client import MosaicClient
from mosaic.core.exceptions import ValidationError
from mosaic.core.storage import (
    MAX_WHERE_DEPTH,
    matches_tree,
    normalize_where,
)
from mosaic.core.storage.adapters.sqlite_adapter import SQLiteAdapter
from mosaic.linkml_bridge import SchemaRegistry

from tests.core.test_comparison_filters import SCHEMA

FUTURE = "2999-01-01T00:00:00+00:00"


@pytest.fixture(scope="module")
def registry() -> SchemaRegistry:
    return SchemaRegistry.from_yaml(SCHEMA)


@pytest.fixture
def client(registry: SchemaRegistry):
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_where_tree.db")
        storage = SQLiteAdapter(db_path, schema_registry=registry)
        c = MosaicClient(storage=storage, bypass_validation=True)
        c.put(
            "Specimen",
            {"id": "s1", "name": "Alpha", "age": 45, "is_tumor": False,
             "notes": "First batch"},
        )
        c.put(
            "Specimen",
            {"id": "s2", "name": "Beta", "age": 60, "is_tumor": True},
        )
        c.put(
            "Specimen",
            {"id": "s3", "name": "Gamma", "age": 75, "is_tumor": False,
             "notes": "follow-up"},
        )
        yield c


def both_paths(client, where, filters=None) -> set[str]:
    live = {
        i["id"]
        for i in client.query("Specimen", filters=filters, where=where).items
    }
    asof = {
        i["id"]
        for i in client.query(
            "Specimen", filters=filters, where=where, as_of=FUTURE
        ).items
    }
    assert live == asof, f"live/as-of divergence for {where!r}: {live} != {asof}"
    return live


class TestWhereTreeQueries:
    def test_leaf(self, client) -> None:
        assert both_paths(
            client, {"field": "age", "op": "gt", "value": 50}
        ) == {"s2", "s3"}

    def test_and(self, client) -> None:
        assert both_paths(
            client,
            {"and": [
                {"field": "age", "op": "gt", "value": 50},
                {"field": "is_tumor", "value": False},
            ]},
        ) == {"s3"}

    def test_or(self, client) -> None:
        assert both_paths(
            client,
            {"or": [
                {"field": "age", "op": "lt", "value": 50},
                {"field": "notes", "op": "contains", "value": "follow"},
            ]},
        ) == {"s1", "s3"}

    def test_not_is_two_valued(self, client) -> None:
        # s2 has no notes; `not contains` must include it on BOTH paths
        # (the COALESCE wrap in the SQL compilers exists for exactly this).
        assert both_paths(
            client,
            {"not": {"field": "notes", "op": "contains", "value": "First"}},
        ) == {"s2", "s3"}

    def test_nested(self, client) -> None:
        assert both_paths(
            client,
            {"and": [
                {"not": {"field": "is_tumor", "value": True}},
                {"or": [
                    {"field": "age", "op": "lte", "value": 45},
                    {"field": "age", "op": "gte", "value": 75},
                ]},
            ]},
        ) == {"s1", "s3"}

    def test_composes_with_flat_filters_by_and(self, client) -> None:
        assert both_paths(
            client,
            {"field": "age", "op": "gt", "value": 50},
            filters=[{"field": "is_tumor", "value": False}],
        ) == {"s3"}

    def test_is_null_leaf(self, client) -> None:
        assert both_paths(
            client, {"field": "notes", "op": "is_null", "value": True}
        ) == {"s2"}


class TestWhereTreeValidation:
    def test_unknown_field_raises(self, client) -> None:
        with pytest.raises(ValidationError, match="Unknown filter field"):
            client.query(
                "Specimen", where={"field": "nope", "value": 1}
            )

    def test_bad_op_raises(self, client) -> None:
        with pytest.raises(ValidationError, match="Unsupported filter operator"):
            client.query(
                "Specimen",
                where={"field": "age", "op": "starts_with", "value": 1},
            )

    def test_empty_combinator_raises(self, client) -> None:
        with pytest.raises(ValidationError, match="non-empty"):
            client.query("Specimen", where={"and": []})

    def test_mixed_node_raises(self, client) -> None:
        with pytest.raises(ValidationError, match="exactly one key"):
            client.query(
                "Specimen",
                where={"and": [{"field": "age", "value": 1}], "or": []},
            )

    def test_non_dict_node_raises(self, client) -> None:
        with pytest.raises(ValidationError, match="must be a dict"):
            client.query("Specimen", where={"not": ["huh"]})

    def test_meaningless_node_raises(self, client) -> None:
        with pytest.raises(ValidationError, match="neither a leaf"):
            client.query("Specimen", where={"banana": 1})

    def test_depth_cap(self, client) -> None:
        node: dict = {"field": "age", "op": "gt", "value": 1}
        for _ in range(MAX_WHERE_DEPTH + 1):
            node = {"not": node}
        with pytest.raises(ValidationError, match="nesting depth"):
            client.query("Specimen", where=node)


class TestMatchesTreeUnit:
    def test_evaluator(self) -> None:
        tree = normalize_where(
            {"and": [
                {"field": "a", "op": "gt", "value": 1},
                {"not": {"field": "b", "value": "x"}},
            ]}
        )
        assert matches_tree({"a": 2}, "e1", tree)  # b absent → not(False)
        assert not matches_tree({"a": 2, "b": "x"}, "e1", tree)
        assert not matches_tree({"a": 0}, "e1", tree)

    def test_id_resolves_to_entity_id(self) -> None:
        tree = normalize_where({"field": "id", "value": "e9"})
        assert matches_tree({}, "e9", tree)
        assert not matches_tree({}, "e1", tree)
