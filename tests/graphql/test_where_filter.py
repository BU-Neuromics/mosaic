"""Generated `<Type>Filter` + `where:` argument (ADR-0006 increment 2).

The introspected filter inputs ARE the capability contract: each slot's
operator object carries exactly the operators its kind/range supports, so
operator applicability is enforced by GraphQL validation itself. Boolean
structure nests through and/or/not; `where` composes with the flat
`filters:` list by AND. Uses the shared conftest schema.
"""

from __future__ import annotations

import json


def _create_sample(gql, name, **fields) -> str:
    parts = [f'name: "{name}"'] + [f"{k}: {json.dumps(v)}" for k, v in fields.items()]
    body = gql("mutation { createSample(data: {%s}) { id } }" % ", ".join(parts))
    assert "errors" not in body, body
    return body["data"]["createSample"]["id"]


def _names(body, root="samples"):
    assert body.get("errors") is None, body
    return sorted(i["name"] for i in body["data"][root]["items"])


class TestWhereBasics:
    def test_single_operator(self, gql):
        _create_sample(gql, "small", volumeMl=1.0)
        _create_sample(gql, "large", volumeMl=9.0)

        body = gql(
            "{ samples(where: {volumeMl: {gt: 5.0}}) { total items { name } } }"
        )
        assert _names(body) == ["large"]

    def test_multiple_ops_on_one_field_and_together(self, gql):
        _create_sample(gql, "low", replicateCount=1)
        _create_sample(gql, "mid", replicateCount=5)
        _create_sample(gql, "high", replicateCount=9)

        body = gql(
            "{ samples(where: {replicateCount: {gt: 2, lt: 8}}) "
            "{ items { name } } }"
        )
        assert _names(body) == ["mid"]

    def test_multiple_fields_and_together(self, gql):
        _create_sample(gql, "yes", isTumor=True, replicateCount=3)
        _create_sample(gql, "no-count", isTumor=True, replicateCount=1)
        _create_sample(gql, "no-flag", isTumor=False, replicateCount=3)

        body = gql(
            "{ samples(where: {isTumor: {eq: true}, replicateCount: {gte: 2}}) "
            "{ items { name } } }"
        )
        assert _names(body) == ["yes"]

    def test_or_group(self, gql):
        _create_sample(gql, "alpha", replicateCount=1)
        _create_sample(gql, "beta", replicateCount=9)
        _create_sample(gql, "gamma", replicateCount=5)

        body = gql(
            "{ samples(where: {or: [{replicateCount: {lt: 2}}, "
            "{replicateCount: {gt: 8}}]}) { items { name } } }"
        )
        assert _names(body) == ["alpha", "beta"]

    def test_not_includes_entities_missing_the_field(self, gql):
        # Two-valued negation (mirror-consistent): an entity with no notes
        # satisfies not(notes contains ...) on the SQL path exactly as the
        # Python as-of mirror computes it.
        _create_sample(gql, "match", notes="alpha batch")
        _create_sample(gql, "other", notes="beta batch")
        _create_sample(gql, "bare")

        body = gql(
            '{ samples(where: {not: {notes: {contains: "alpha"}}}) '
            "{ items { name } } }"
        )
        assert _names(body) == ["bare", "other"]

    def test_nested_boolean_structure(self, gql):
        _create_sample(gql, "a", isTumor=True, replicateCount=1)
        _create_sample(gql, "b", isTumor=True, replicateCount=9)
        _create_sample(gql, "c", isTumor=False, replicateCount=9)

        body = gql(
            "{ samples(where: {and: [{isTumor: {eq: true}}, "
            "{or: [{replicateCount: {lt: 2}}, {replicateCount: {gt: 8}}]}]}) "
            "{ items { name } } }"
        )
        assert _names(body) == ["a", "b"]

    def test_enum_ops_typed(self, gql):
        for name, sex in (("Ada", "female"), ("Alan", "male"), ("Robin", "unknown")):
            body = gql(
                'mutation { createDonor(data: {name: "%s", sex: %s}) { id } }'
                % (name, sex)
            )
            assert "errors" not in body, body

        body = gql(
            "{ donors(where: {sex: {in: [female, unknown]}}) { items { name } } }"
        )
        assert _names(body, "donors") == ["Ada", "Robin"]

    def test_is_null_via_where(self, gql):
        _create_sample(gql, "annotated", notes="x")
        _create_sample(gql, "bare")

        body = gql(
            "{ samples(where: {notes: {isNull: true}}) { items { name } } }"
        )
        assert _names(body) == ["bare"]

    def test_where_composes_with_flat_filters_by_and(self, gql):
        _create_sample(gql, "both", isTumor=True, replicateCount=9)
        _create_sample(gql, "flag-only", isTumor=True, replicateCount=1)
        _create_sample(gql, "count-only", isTumor=False, replicateCount=9)

        body = gql(
            '{ samples(filters: [{field: "isTumor", value: true}], '
            "where: {replicateCount: {gt: 5}}) { items { name } } }"
        )
        assert _names(body) == ["both"]

    def test_where_under_as_of(self, gql):
        _create_sample(gql, "early", replicateCount=9)

        body = gql(
            '{ samples(asOf: "2999-01-01T00:00:00+00:00", '
            "where: {replicateCount: {gt: 5}}) { items { name } } }"
        )
        assert _names(body) == ["early"]

    def test_empty_where_is_a_noop(self, gql):
        _create_sample(gql, "one")
        body = gql("{ samples(where: {}) { total } }")
        assert body.get("errors") is None, body
        assert body["data"]["samples"]["total"] == 1


class TestWhereValidation:
    def test_wrong_typed_value_fails_graphql_validation(self, gql):
        # The dry-run property: IntFilterOps.gt is Int, so a string fails
        # validation before execution.
        body = gql(
            '{ samples(where: {replicateCount: {gt: "three"}}) { total } }'
        )
        assert body["errors"], body

    def test_contains_not_available_on_int_slot(self, gql):
        # The schema itself is the capability contract: IntFilterOps has no
        # `contains` field, so this is a validation error, not a runtime one.
        body = gql(
            '{ samples(where: {replicateCount: {contains: "3"}}) { total } }'
        )
        assert body["errors"], body

    def test_reference_slots_absent_from_filter_input(self, gql):
        body = gql('{ samples(where: {donor: {eq: "x"}}) { total } }')
        assert body["errors"], body

    def test_empty_operator_object_is_coded_error(self, gql):
        body = gql("{ samples(where: {notes: {}}) { total } }")
        assert (
            body["errors"][0]["extensions"]["code"] == "INVALID_FILTER_VALUE"
        )

    def test_empty_subfilter_in_or_is_coded_error(self, gql):
        body = gql(
            "{ samples(where: {or: [{notes: {isNull: true}}, {}]}) { total } }"
        )
        assert (
            body["errors"][0]["extensions"]["code"] == "INVALID_FILTER_VALUE"
        )

    def test_explicit_null_value_is_coded_error(self, gql):
        body = gql("{ samples(where: {notes: {eq: null}}) { total } }")
        assert (
            body["errors"][0]["extensions"]["code"] == "INVALID_FILTER_VALUE"
        )
        assert "isNull" in body["errors"][0]["message"]

    def test_depth_cap(self, gql):
        deep = "{notes: {isNull: false}}"
        for _ in range(11):
            deep = "{not: %s}" % deep
        body = gql("{ samples(where: %s) { total } }" % deep)
        assert body["errors"][0]["extensions"]["code"] == "FILTER_TOO_DEEP"


class TestFilterInputIntrospection:
    def test_per_slot_operator_contract(self, gql):
        body = gql(
            '{ __type(name: "SampleFilter") { inputFields { name type { name } } } }'
        )
        fields = {
            f["name"]: (f["type"]["name"] or "")
            for f in body["data"]["__type"]["inputFields"]
        }
        assert fields["volumeMl"] == "FloatFilterOps"
        assert fields["replicateCount"] == "IntFilterOps"
        assert fields["collectedAt"] == "DateTimeFilterOps"
        assert fields["isTumor"] == "BooleanFilterOps"
        assert fields["notes"] == "StringFilterOps"
        assert "and" in fields and "or" in fields and "not" in fields
        # To-one reference edges nest the TARGET's filter (M5a); the raw
        # id column is not separately filterable through `where`.
        assert fields["donor"] == "DonorFilter"
        assert fields["parent"] == "SampleFilter"  # self-reference works
        assert "donorId" not in fields

    def test_operator_sets_by_kind(self, gql):
        def ops(name):
            body = gql(
                '{ __type(name: "%s") { inputFields { name } } }' % name
            )
            return {f["name"] for f in body["data"]["__type"]["inputFields"]}

        assert ops("StringFilterOps") == {"eq", "neq", "in", "contains", "isNull"}
        assert ops("IntFilterOps") == {
            "eq", "neq", "in", "gt", "gte", "lt", "lte", "isNull",
        }
        assert ops("BooleanFilterOps") == {"eq", "neq", "isNull"}
        assert ops("SexEnumFilterOps") == {"eq", "neq", "in", "isNull"}
