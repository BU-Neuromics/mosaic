"""GraphQL `asOf` argument on generated list queries — sec6 §6.8 / ADR-0001
increment 4. Uses the package `gql` fixture (tests/graphql/conftest.py).

Timestamp-robust past/future boundaries: `asOf` far in the past yields the empty
set; far in the future yields the current set — proving the argument threads
through to the as-of reconstruction without fragile timing.
"""

PAST = "2000-01-01T00:00:00+00:00"
FUTURE = "2999-01-01T00:00:00+00:00"


def test_samples_as_of_past_is_empty(gql):
    created = gql('mutation { createSample(data: {name: "x"}) { id } }')
    assert created["data"]["createSample"]["id"]

    past = gql(f'query {{ samples(asOf: "{PAST}") {{ total }} }}')
    assert past.get("errors") is None, past
    assert past["data"]["samples"]["total"] == 0


def test_samples_as_of_future_includes_current(gql):
    gql('mutation { createSample(data: {name: "y"}) { id } }')

    fut = gql(f'query {{ samples(asOf: "{FUTURE}") {{ total items {{ name }} }} }}')
    assert fut.get("errors") is None, fut
    assert fut["data"]["samples"]["total"] >= 1
    assert "y" in {s["name"] for s in fut["data"]["samples"]["items"]}
