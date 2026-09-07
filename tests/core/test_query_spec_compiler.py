"""Tests for compile_query_spec (ADR-0009 / issue #183's execute half).

Uses an inline schema carrying both a to-one and a to-many reference
(Sample.donor_id, Study.sample_ids) so both relationship-predicate
compile paths (nested edge vs. quantifier) are exercised — the shared
``sample_schema.yaml`` fixture used elsewhere in ``tests/core`` has only
a to-one reference.
"""

from __future__ import annotations

import pytest

from mosaic.core.query_spec import parse_query_spec, validate_query_spec
from mosaic.core.query_spec_compiler import compile_query_spec
from mosaic.core.schema_typing import build_capability_manifest
from mosaic.linkml_bridge import SchemaRegistry

_SCHEMA = """
id: https://example.org/hippo/test_compiler
name: test_compiler
prefixes:
  linkml: https://w3id.org/linkml/
imports:
  - linkml:types
  - hippo_core
default_range: string

classes:
  Donor:
    is_a: Entity
    attributes:
      name:
        required: true

  Sample:
    is_a: Entity
    attributes:
      name:
        required: true
      donor_id:
        range: Donor
      volume_ml:
        range: float
      status:
        range: SampleStatus

  Study:
    is_a: Entity
    attributes:
      title:
        required: true
      sample_ids:
        range: Sample
        multivalued: true

enums:
  SampleStatus:
    permissible_values:
      active: {}
      archived: {}
"""


def _manifest():
    registry = SchemaRegistry.from_yaml(_SCHEMA)
    return build_capability_manifest(registry)


def _compile(raw: dict):
    manifest = _manifest()
    spec = parse_query_spec(raw)
    result = validate_query_spec(spec, manifest)
    assert result.valid, result.errors
    return compile_query_spec(spec, manifest)


def test_no_criteria_compiles_to_no_where():
    compiled = _compile({"v": 1, "anchor": "Sample", "mode": "AND", "criteria": []})
    assert compiled.entity_type == "Sample"
    assert compiled.where is None


def test_single_field_condition_compiles_to_a_bare_leaf():
    compiled = _compile(
        {
            "v": 1,
            "anchor": "Sample",
            "mode": "AND",
            "criteria": [{"kind": "field", "slot": "volume_ml", "op": "gt", "value": 1.0}],
        }
    )
    assert compiled.where == {"field": "volume_ml", "op": "gt", "value": 1.0}


def test_multiple_conditions_compile_to_the_spec_mode_combinator():
    compiled = _compile(
        {
            "v": 1,
            "anchor": "Sample",
            "mode": "OR",
            "criteria": [
                {"kind": "field", "slot": "status", "op": "eq", "value": "active"},
                {"kind": "field", "slot": "status", "op": "eq", "value": "archived"},
            ],
        }
    )
    assert compiled.where == {
        "or": [
            {"field": "status", "op": "eq", "value": "active"},
            {"field": "status", "op": "eq", "value": "archived"},
        ]
    }


def test_nested_group_compiles_to_its_own_combinator():
    compiled = _compile(
        {
            "v": 1,
            "anchor": "Sample",
            "mode": "AND",
            "criteria": [
                {
                    "kind": "group",
                    "mode": "OR",
                    "criteria": [
                        {"kind": "field", "slot": "status", "op": "eq", "value": "active"},
                        {"kind": "field", "slot": "status", "op": "eq", "value": "archived"},
                    ],
                }
            ],
        }
    )
    assert compiled.where == {
        "or": [
            {"field": "status", "op": "eq", "value": "active"},
            {"field": "status", "op": "eq", "value": "archived"},
        ]
    }


class TestToOneRelatedCondition:
    def test_some_compiles_to_the_bare_edge_node(self):
        compiled = _compile(
            {
                "v": 1,
                "anchor": "Sample",
                "mode": "AND",
                "criteria": [
                    {
                        "kind": "related",
                        "edge": "donor_id",
                        "quantifier": "some",
                        "criteria": [{"kind": "field", "slot": "name", "op": "eq", "value": "D1"}],
                    }
                ],
            }
        )
        assert compiled.where == {
            "edge": "donor_id",
            "where": {"field": "name", "op": "eq", "value": "D1"},
        }

    def test_none_compiles_to_a_negated_edge_node(self):
        # normalize_where has no quantifier for a to-one edge — bare
        # {"edge","where"} already means "some" (target exists and
        # matches), so "none" is exactly its negation.
        compiled = _compile(
            {
                "v": 1,
                "anchor": "Sample",
                "mode": "AND",
                "criteria": [
                    {
                        "kind": "related",
                        "edge": "donor_id",
                        "quantifier": "none",
                        "criteria": [{"kind": "field", "slot": "name", "op": "eq", "value": "D1"}],
                    }
                ],
            }
        )
        assert compiled.where == {
            "not": {"edge": "donor_id", "where": {"field": "name", "op": "eq", "value": "D1"}}
        }

    def test_empty_criteria_fills_with_an_identifier_existence_check(self):
        compiled = _compile(
            {
                "v": 1,
                "anchor": "Sample",
                "mode": "AND",
                "criteria": [
                    {"kind": "related", "edge": "donor_id", "quantifier": "some", "criteria": []}
                ],
            }
        )
        assert compiled.where == {
            "edge": "donor_id",
            "where": {"field": "id", "op": "is_null", "value": False},
        }


class TestToManyRelatedCondition:
    def test_some_carries_the_quantifier_explicitly(self):
        compiled = _compile(
            {
                "v": 1,
                "anchor": "Study",
                "mode": "AND",
                "criteria": [
                    {
                        "kind": "related",
                        "edge": "sample_ids",
                        "quantifier": "some",
                        "criteria": [{"kind": "field", "slot": "volume_ml", "op": "gt", "value": 1.0}],
                    }
                ],
            }
        )
        assert compiled.where == {
            "edge": "sample_ids",
            "quantifier": "some",
            "where": {"field": "volume_ml", "op": "gt", "value": 1.0},
        }

    def test_none_carries_the_quantifier_explicitly_not_negated(self):
        compiled = _compile(
            {
                "v": 1,
                "anchor": "Study",
                "mode": "AND",
                "criteria": [
                    {
                        "kind": "related",
                        "edge": "sample_ids",
                        "quantifier": "none",
                        "criteria": [{"kind": "field", "slot": "volume_ml", "op": "gt", "value": 1.0}],
                    }
                ],
            }
        )
        assert compiled.where == {
            "edge": "sample_ids",
            "quantifier": "none",
            "where": {"field": "volume_ml", "op": "gt", "value": 1.0},
        }


def test_as_of_and_order_by_pass_through():
    compiled = _compile(
        {
            "v": 1,
            "anchor": "Sample",
            "mode": "AND",
            "criteria": [],
            "asOf": "2026-01-01T00:00:00Z",
            "sort": [{"slot": "volume_ml", "direction": "desc"}],
        }
    )
    assert compiled.as_of == "2026-01-01T00:00:00Z"
    assert compiled.order_by == "volume_ml"
    assert compiled.order_dir == "desc"


def test_no_sort_defaults_to_none_asc():
    compiled = _compile({"v": 1, "anchor": "Sample", "mode": "AND", "criteria": []})
    assert compiled.order_by is None
    assert compiled.order_dir == "asc"


def test_compiled_where_is_actually_accepted_by_the_real_storage_layer():
    """The one test that proves this against ground truth rather than
    self-consistency with the compiler's own assumptions: feed a compiled
    tree covering every shape (nested group, to-one some/none, to-many
    some/none) into the real `normalize_where` and confirm it round-trips
    with no ValidationError."""
    from mosaic.core.storage import normalize_where

    compiled = _compile(
        {
            "v": 1,
            "anchor": "Sample",
            "mode": "AND",
            "criteria": [
                {
                    "kind": "group",
                    "mode": "OR",
                    "criteria": [
                        {"kind": "field", "slot": "status", "op": "eq", "value": "active"},
                        {"kind": "field", "slot": "status", "op": "eq", "value": "archived"},
                    ],
                },
                {
                    "kind": "related",
                    "edge": "donor_id",
                    "quantifier": "none",
                    "criteria": [{"kind": "field", "slot": "name", "op": "eq", "value": "D1"}],
                },
            ],
        }
    )
    assert normalize_where(compiled.where) == compiled.where

    study_compiled = _compile(
        {
            "v": 1,
            "anchor": "Study",
            "mode": "AND",
            "criteria": [
                {
                    "kind": "related",
                    "edge": "sample_ids",
                    "quantifier": "some",
                    "criteria": [{"kind": "field", "slot": "volume_ml", "op": "gt", "value": 1.0}],
                }
            ],
        }
    )
    assert normalize_where(study_compiled.where) == study_compiled.where
