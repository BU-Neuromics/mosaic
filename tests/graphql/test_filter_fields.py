"""Filter-field vocabulary on the GraphQL list surface (issue #149).

``filters.field`` reaches storage, which is keyed by LinkML slot name
(snake_case), while the generated type exposes the same slots under
camelCase. Before this, the camelCase spelling matched no column and the
adapter answered with zero rows — a valid-shaped result indistinguishable
from "nothing matched". Both spellings now resolve, and a name that
addresses no column is an error instead of a silent empty page.

Uses the shared ``tests/graphql/conftest.py`` schema: ``Sample`` carries
multi-word slots (``is_tumor``, ``volume_ml``, ``replicate_count``), a
single-valued reference (``donor_id`` → resolved edge ``donor``), and
``Study.sample_ids`` is a multivalued (relationships-backed) reference.
"""

from __future__ import annotations

import json


def _create_sample(gql, name, **fields) -> str:
    parts = [f'name: "{name}"'] + [f"{k}: {json.dumps(v)}" for k, v in fields.items()]
    body = gql("mutation { createSample(data: {%s}) { id } }" % ", ".join(parts))
    assert "errors" not in body, body
    return body["data"]["createSample"]["id"]


class TestCamelCaseFilterFields:
    def test_camel_case_matches_same_rows_as_slot_name(self, gql):
        _create_sample(gql, "tumor-1", isTumor=True)
        _create_sample(gql, "normal-1", isTumor=False)

        snake = gql(
            '{ samples(filters: [{field: "is_tumor", value: true}]) '
            "{ total items { name } } }"
        )
        camel = gql(
            '{ samples(filters: [{field: "isTumor", value: true}]) '
            "{ total items { name } } }"
        )
        assert snake.get("errors") is None, snake
        assert camel.get("errors") is None, camel
        assert snake["data"]["samples"]["total"] == 1
        assert camel["data"]["samples"] == snake["data"]["samples"]

    def test_camel_case_on_numeric_slot(self, gql):
        _create_sample(gql, "three-reps", replicateCount=3)
        _create_sample(gql, "one-rep", replicateCount=1)

        body = gql(
            '{ samples(filters: [{field: "replicateCount", value: 3}]) '
            "{ total items { name } } }"
        )
        assert body.get("errors") is None, body
        assert body["data"]["samples"]["total"] == 1
        assert body["data"]["samples"]["items"][0]["name"] == "three-reps"

    def test_resolved_reference_edge_name_filters_on_the_foreign_key(self, gql):
        """Edge-only emission (ADR-0005) hides the raw ``donorId`` carrier, so
        the reference's only introspectable name is the resolved edge
        ``donor`` — it has to address the underlying ``donor_id`` column."""
        donor = gql('mutation { createDonor(data: {name: "Ada"}) { id } }')
        donor_id = donor["data"]["createDonor"]["id"]
        _create_sample(gql, "hers", donorId=donor_id)
        _create_sample(gql, "unrelated")

        for field in ("donor", "donor_id", "donorId"):
            body = gql(
                'query($id: JSON!) { samples(filters: [{field: "%s", value: $id}]) '
                "{ total items { name } } }" % field,
                {"id": donor_id},
            )
            assert body.get("errors") is None, (field, body)
            page = body["data"]["samples"]
            assert page["total"] == 1, (field, page)
            assert page["items"][0]["name"] == "hers"

    def test_single_word_slot_unaffected(self, gql):
        """snake_case == camelCase for one word; the aliasing must not
        disturb the spelling that already worked."""
        _create_sample(gql, "named")
        body = gql('{ samples(filters: [{field: "name", value: "named"}]) { total } }')
        assert body.get("errors") is None, body
        assert body["data"]["samples"]["total"] == 1


class TestUnrecognizedFilterFields:
    def test_unknown_field_errors_instead_of_returning_empty(self, gql):
        _create_sample(gql, "present")
        body = gql('{ samples(filters: [{field: "nonesuch", value: "x"}]) { total } }')

        assert body["data"] is None or body["data"].get("samples") is None
        assert body["errors"], body
        error = body["errors"][0]
        assert error["extensions"]["code"] == "UNKNOWN_FILTER_FIELD"
        assert error["extensions"]["field"] == "nonesuch"
        # The message names the vocabulary the caller should have used.
        assert "is_tumor" in error["message"]

    def test_read_time_computed_field_errors_under_either_spelling(self, gql):
        """``createdAt`` is a real field on the type but is computed at read
        time — no column to match. Introspection only ever shows the
        camelCase spelling, so that one has to be recognized too."""
        _create_sample(gql, "present")
        for field in ("created_at", "createdAt", "supersededBy"):
            body = gql(
                '{ samples(filters: [{field: "%s", value: "x"}]) { total } }' % field
            )
            assert body["errors"], (field, body)
            assert body["errors"][0]["extensions"]["code"] == "UNFILTERABLE_FIELD", (
                field,
                body["errors"][0],
            )

    def test_multivalued_reference_errors_and_points_at_related_to(self, gql):
        """``Study.sample_ids`` lives in the relationships table (ADR-0002),
        so no column predicate can match it."""
        body = gql(
            '{ studys(filters: [{field: "sample_ids", value: "x"}]) { total } }'
        )
        assert body["errors"], body
        error = body["errors"][0]
        assert error["extensions"]["code"] == "UNFILTERABLE_FIELD"
        assert "relatedTo" in error["message"]
