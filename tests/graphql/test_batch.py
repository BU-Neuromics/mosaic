"""GraphQL tests for the batch unit-of-work (issue #84 increment 3).

Exercises the root mutations `ingestBatch` and `validateBatch` over the
shared storage-backed schema from conftest (Donor/Sample/Study, name/title
required). The `gql` fixture posts to /graphql with bearer auth.

Note on validation paths: the conftest client registers no extra pre-write
validators, so LinkML `required` slots are enforced by the storage layer at
*write* time (NOT NULL), not by the pre-write pipeline. So a missing required
field is not caught by `validateBatch` (dry-run) here — it surfaces when
`ingestBatch` writes, which then rolls the whole set back and raises a coded
error. The pre-write-validation path (clean `committed: false`) is covered by
the REST tests, which register a validator.
"""

from __future__ import annotations

INGEST = """
mutation($entities: [BatchEntityInput!]!, $relationships: [BatchRelationshipInput!], $dryRun: Boolean) {
  ingestBatch(entities: $entities, relationships: $relationships, dryRun: $dryRun) {
    committed
    dryRun
    validation { passed results { entityId passed failures { tier message } } }
    entities
    relationships
  }
}
"""

VALIDATE = """
mutation($entities: [BatchEntityInput!]!) {
  validateBatch(entities: $entities) {
    passed
    results { entityId passed failures { tier message } }
  }
}
"""

DONOR_BY_ID = 'query($id: ID!) { donor(id: $id) { id name } }'


def test_validate_batch_valid_set_passes_without_writing(gql):
    body = gql(
        VALIDATE,
        {"entities": [
            {"entityType": "Donor", "data": {"id": "g-val-1", "name": "D"}},
            {"entityType": "Sample", "data": {"id": "g-val-2", "name": "S"}},
        ]},
    )
    result = body["data"]["validateBatch"]
    assert result["passed"] is True
    assert len(result["results"]) == 2
    # Pure report — nothing written.
    got = gql(DONOR_BY_ID, {"id": "g-val-1"})
    assert got["data"]["donor"] is None


def test_ingest_batch_commits_valid_set(gql):
    body = gql(
        INGEST,
        {"entities": [
            {"entityType": "Donor", "data": {"id": "g-donor-1", "name": "D"}},
            {"entityType": "Sample", "data": {"id": "g-sample-1", "name": "S"}},
        ]},
    )
    result = body["data"]["ingestBatch"]
    assert result["committed"] is True
    assert result["dryRun"] is False
    assert len(result["entities"]) == 2
    got = gql(DONOR_BY_ID, {"id": "g-donor-1"})
    assert got["data"]["donor"]["name"] == "D"


def test_ingest_batch_dry_run_writes_nothing(gql):
    body = gql(
        INGEST,
        {"dryRun": True, "entities": [
            {"entityType": "Donor", "data": {"id": "g-dry-1", "name": "D"}},
        ]},
    )
    result = body["data"]["ingestBatch"]
    assert result["committed"] is False
    assert result["dryRun"] is True
    got = gql(DONOR_BY_ID, {"id": "g-dry-1"})
    assert got["data"]["donor"] is None


def test_ingest_batch_rolls_back_on_write_failure(gql):
    # The second Donor violates the required `name` (NOT NULL) at write time;
    # the whole set must roll back and surface a coded error.
    body = gql(
        INGEST,
        {"entities": [
            {"entityType": "Donor", "data": {"id": "g-rb-ok", "name": "D"}},
            {"entityType": "Donor", "data": {"id": "g-rb-bad"}},  # missing required name
        ]},
    )
    assert body.get("errors"), "expected a coded GraphQL error"
    # All-or-nothing: the valid sibling written earlier in the batch is gone.
    got = gql(DONOR_BY_ID, {"id": "g-rb-ok"})
    assert got["data"]["donor"] is None


def test_ingest_batch_intra_batch_relationship(gql):
    body = gql(
        INGEST,
        {
            "entities": [
                {"entityType": "Donor", "data": {"id": "g-d2", "name": "D"}},
                {"entityType": "Sample", "data": {"id": "g-s2", "name": "S"}},
            ],
            "relationships": [
                {"sourceId": "g-d2", "targetId": "g-s2", "relationshipType": "donated"}
            ],
        },
    )
    result = body["data"]["ingestBatch"]
    assert result["committed"] is True
    assert len(result["relationships"]) == 1
