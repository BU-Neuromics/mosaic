"""Comparison / null-test FilterOps on the GraphQL surface (ADR-0006 inc. 1).

The operator vocabulary a slot supports is selected by its kind/range —
comparisons on numeric/temporal slots, CONTAINS on strings, IS_NULL
everywhere — and an operator outside a slot's set is a coded
UNSUPPORTED_FILTER_OP error, never a silently-wrong result (issue #129's
discipline extended to the typed set). Uses the shared conftest schema:
``Sample`` carries integer (``replicate_count``), float (``volume_ml``),
datetime (``collected_at``), boolean (``is_tumor``) and string slots, and
``Donor.sex`` is an enum.
"""

from __future__ import annotations

import json


def _create_sample(gql, name, **fields) -> str:
    parts = [f'name: "{name}"'] + [f"{k}: {json.dumps(v)}" for k, v in fields.items()]
    body = gql("mutation { createSample(data: {%s}) { id } }" % ", ".join(parts))
    assert "errors" not in body, body
    return body["data"]["createSample"]["id"]


class TestComparisonOps:
    def test_gt_on_integer_slot(self, gql):
        _create_sample(gql, "one-rep", replicateCount=1)
        _create_sample(gql, "three-reps", replicateCount=3)

        body = gql(
            '{ samples(filters: [{field: "replicateCount", op: GT, value: 2}]) '
            "{ total items { name } } }"
        )
        assert body.get("errors") is None, body
        assert body["data"]["samples"]["total"] == 1
        assert body["data"]["samples"]["items"][0]["name"] == "three-reps"

    def test_lte_on_float_slot(self, gql):
        _create_sample(gql, "small", volumeMl=1.5)
        _create_sample(gql, "large", volumeMl=9.5)

        body = gql(
            '{ samples(filters: [{field: "volumeMl", op: LTE, value: 2.0}]) '
            "{ total items { name } } }"
        )
        assert body.get("errors") is None, body
        assert [i["name"] for i in body["data"]["samples"]["items"]] == ["small"]

    def test_gt_on_datetime_slot(self, gql):
        _create_sample(gql, "old", collectedAt="2024-01-01T00:00:00+00:00")
        _create_sample(gql, "new", collectedAt="2026-01-01T00:00:00+00:00")

        body = gql(
            '{ samples(filters: [{field: "collectedAt", op: GT, '
            'value: "2025-01-01T00:00:00+00:00"}]) { total items { name } } }'
        )
        assert body.get("errors") is None, body
        assert [i["name"] for i in body["data"]["samples"]["items"]] == ["new"]

    def test_neq_excludes_value_and_absent(self, gql):
        _create_sample(gql, "with-notes", notes="alpha")
        _create_sample(gql, "other-notes", notes="beta")
        _create_sample(gql, "no-notes")

        body = gql(
            '{ samples(filters: [{field: "notes", op: NEQ, value: "alpha"}]) '
            "{ total items { name } } }"
        )
        assert body.get("errors") is None, body
        assert [i["name"] for i in body["data"]["samples"]["items"]] == [
            "other-notes"
        ]

    def test_contains_case_insensitive(self, gql):
        _create_sample(gql, "brain-tumor")
        _create_sample(gql, "liver-normal")

        body = gql(
            '{ samples(filters: [{field: "name", op: CONTAINS, value: "TUMO"}]) '
            "{ total items { name } } }"
        )
        assert body.get("errors") is None, body
        assert [i["name"] for i in body["data"]["samples"]["items"]] == [
            "brain-tumor"
        ]

    def test_is_null_both_ways(self, gql):
        _create_sample(gql, "annotated", notes="x")
        _create_sample(gql, "bare")

        absent = gql(
            '{ samples(filters: [{field: "notes", op: IS_NULL, value: true}]) '
            "{ items { name } } }"
        )
        present = gql(
            '{ samples(filters: [{field: "notes", op: IS_NULL, value: false}]) '
            "{ items { name } } }"
        )
        assert absent.get("errors") is None, absent
        assert present.get("errors") is None, present
        assert [i["name"] for i in absent["data"]["samples"]["items"]] == ["bare"]
        assert [i["name"] for i in present["data"]["samples"]["items"]] == [
            "annotated"
        ]

    def test_neq_on_enum_slot(self, gql):
        body = gql('mutation { createDonor(data: {name: "Ada", sex: male}) { id } }')
        assert "errors" not in body, body
        body = gql('mutation { createDonor(data: {name: "Grace", sex: female}) { id } }')
        assert "errors" not in body, body

        result = gql(
            '{ donors(filters: [{field: "sex", op: NEQ, value: "male"}]) '
            "{ items { name } } }"
        )
        assert result.get("errors") is None, result
        assert [i["name"] for i in result["data"]["donors"]["items"]] == ["Grace"]


class TestOperatorRestrictions:
    def test_contains_on_integer_slot_is_coded_error(self, gql):
        body = gql(
            '{ samples(filters: [{field: "replicateCount", op: CONTAINS, '
            'value: "3"}]) { total } }'
        )
        error = body["errors"][0]
        assert error["extensions"]["code"] == "UNSUPPORTED_FILTER_OP"
        assert error["extensions"]["op"] == "CONTAINS"
        assert "GT" in error["message"]  # names the supported set

    def test_gt_on_string_slot_is_coded_error(self, gql):
        body = gql(
            '{ samples(filters: [{field: "name", op: GT, value: "a"}]) '
            "{ total } }"
        )
        assert body["errors"][0]["extensions"]["code"] == "UNSUPPORTED_FILTER_OP"

    def test_gt_on_boolean_slot_is_coded_error(self, gql):
        body = gql(
            '{ samples(filters: [{field: "isTumor", op: GT, value: false}]) '
            "{ total } }"
        )
        assert body["errors"][0]["extensions"]["code"] == "UNSUPPORTED_FILTER_OP"

    def test_contains_on_reference_slot_is_coded_error(self, gql):
        body = gql(
            '{ samples(filters: [{field: "donor", op: CONTAINS, value: "x"}]) '
            "{ total } }"
        )
        assert body["errors"][0]["extensions"]["code"] == "UNSUPPORTED_FILTER_OP"

    def test_multivalued_reference_still_unfilterable(self, gql):
        body = gql(
            '{ studys(filters: [{field: "sampleIds", op: IS_NULL, value: true}]) '
            "{ total } }"
        )
        assert body["errors"][0]["extensions"]["code"] == "UNFILTERABLE_FIELD"


class TestValueShapeValidation:
    def test_eq_null_rejected_by_graphql_validation(self, gql):
        # FilterInput.value is JSON! (non-null), so `value: null` never
        # reaches execution — GraphQL validation itself rejects it (the
        # dry-run property ADR-0006 leans on). The resolver keeps a
        # defense-in-depth INVALID_FILTER_VALUE check for non-GraphQL
        # entry points.
        body = gql(
            '{ samples(filters: [{field: "notes", value: null}]) { total } }'
        )
        assert body["errors"], body
        assert body.get("data") in (None, {}), body

    def test_is_null_requires_boolean(self, gql):
        body = gql(
            '{ samples(filters: [{field: "notes", op: IS_NULL, value: "yes"}]) '
            "{ total } }"
        )
        assert body["errors"][0]["extensions"]["code"] == "INVALID_FILTER_VALUE"

    def test_in_requires_list(self, gql):
        body = gql(
            '{ samples(filters: [{field: "name", op: IN, value: "solo"}]) '
            "{ total } }"
        )
        assert body["errors"][0]["extensions"]["code"] == "INVALID_FILTER_VALUE"
