"""As-of reconstruction — sec6 §6.8 / ADR-0001, increment 1.

Covers the storage-layer reconstruction contract:
- ``state_at()`` returns the entity's data state (the latest ``create``/``update``
  full post-image at-or-before ``T``), never a non-state delta;
- ``get_temporal(as_of=...)`` bounds derivation to ``timestamp <= as_of``;
- ``find(as_of=...)`` is the increment-2 contract and raises ``NotImplementedError``.
"""

import os
import tempfile
import time

import pytest

from tests.conftest import _build_minimal_schema_registry
from hippo.core.storage import Query
from hippo.core.storage.adapters import SQLiteAdapter
from hippo.core.storage.adapters.sqlite_adapter import SQLiteEntity

# Far-future timestamp: at-or-after every record, so state_at sees the whole log.
FUTURE = "2999-01-01T00:00:00+00:00"


@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield os.path.join(tmpdir, "test_asof.db")


@pytest.fixture
def adapter(db_path):
    a = SQLiteAdapter(
        db_path, wal_mode=True, schema_registry=_build_minimal_schema_registry()
    )
    yield a
    a.close()


def _timestamps(adapter, entity_id):
    """Chronological provenance timestamps for an entity."""
    return [rec["timestamp"] for rec in adapter.history(entity_id)]


def test_state_at_returns_data_state_after_non_deletion_availability_change(adapter):
    """The reconstruction-contract bug fix: when the newest record <= T is a
    non-deletion ``availability_change`` (a delta), ``state_at`` must still return
    the entity's data state — not the availability patch."""
    adapter.create(
        SQLiteEntity(id="e1", entity_type="TestEntity", is_available=True,
                     version=1, data={"name": "v1"})
    )
    time.sleep(0.005)
    adapter.update_data(entity_id="e1", entity_type="TestEntity",
                        data={"name": "v2"}, new_version=2)
    time.sleep(0.005)
    # A non-deletion availability_change records a delta patch {is_available, reason}.
    adapter.set_availability("e1", "TestEntity", is_available=True, reason="re-check")

    result = adapter.state_at("e1", FUTURE)
    assert result is not None
    # Returns the data post-image, NOT {"is_available": True, "reason": "re-check"}.
    assert result["state"] == {"name": "v2"}


def test_state_at_none_after_delete(adapter):
    """A deleted entity is absent at any T after deletion (regression guard)."""
    adapter.create(
        SQLiteEntity(id="e2", entity_type="TestEntity", is_available=True,
                     version=1, data={"name": "x"})
    )
    time.sleep(0.005)
    adapter.delete("e2")
    assert adapter.state_at("e2", FUTURE) is None


def test_get_temporal_as_of_bounds_updated_at(adapter):
    adapter.create(
        SQLiteEntity(id="e3", entity_type="TestEntity", is_available=True,
                     version=1, data={"name": "v1"})
    )
    time.sleep(0.005)
    adapter.update_data(entity_id="e3", entity_type="TestEntity",
                        data={"name": "v2"}, new_version=2)
    time.sleep(0.005)
    adapter.update_data(entity_id="e3", entity_type="TestEntity",
                        data={"name": "v3"}, new_version=3)

    ts = _timestamps(adapter, "e3")  # [create, update2, update3]
    assert len(ts) == 3
    t_create, t2, t3 = ts

    current = adapter.get_temporal(["e3"])["e3"]
    assert current.created_at == t_create
    assert current.updated_at == t3

    asof = adapter.get_temporal(["e3"], as_of=t2)["e3"]
    assert asof.created_at == t_create
    assert asof.updated_at == t2  # the 3rd write is after as_of, excluded


def test_get_temporal_as_of_at_create_excludes_later_update(adapter):
    """as_of pinned to creation sees only the create event."""
    adapter.create(
        SQLiteEntity(id="e4", entity_type="TestEntity", is_available=True,
                     version=1, data={"name": "v1"})
    )
    t_create = _timestamps(adapter, "e4")[0]
    time.sleep(0.005)
    adapter.update_data(entity_id="e4", entity_type="TestEntity",
                        data={"name": "v2"}, new_version=2)

    asof = adapter.get_temporal(["e4"], as_of=t_create)["e4"]
    assert asof.created_at == t_create
    assert asof.updated_at == t_create


def test_find_as_of_reconstructs_entity_set(adapter):
    """find(as_of=...) reconstructs the entity set as the graph stood at T
    (increment 2): an entity created after T is absent."""
    adapter.create(SQLiteEntity(id="f1", entity_type="TestEntity", is_available=True,
                                version=1, data={"name": "f1"}))
    t1 = adapter.history("f1")[0]["timestamp"]
    time.sleep(0.01)
    adapter.create(SQLiteEntity(id="f2", entity_type="TestEntity", is_available=True,
                                version=1, data={"name": "f2"}))

    at_t1 = {e.id for e in adapter.find(Query(entity_type="TestEntity"), as_of=t1)}
    assert at_t1 == {"f1"}  # f2 was created after t1

    current = {e.id for e in adapter.find(Query(entity_type="TestEntity"))}
    assert current == {"f1", "f2"}


# --------------------------------------------------------------------------
# End-to-end client.query(as_of=...) — sec6 §6.8 increment 2.
# --------------------------------------------------------------------------


@pytest.fixture
def client_and_adapter(db_path):
    from hippo.core.client import HippoClient
    adapter = SQLiteAdapter(
        db_path, wal_mode=True, schema_registry=_build_minimal_schema_registry()
    )
    client = HippoClient(storage=adapter)
    yield client, adapter
    adapter.close()


def _ids(result):
    return {item["id"] for item in result.items}


def test_query_as_of_excludes_entities_created_after_t(client_and_adapter):
    client, adapter = client_and_adapter
    adapter.create(SQLiteEntity(id="a", entity_type="TestEntity", is_available=True,
                                version=1, data={"name": "A"}))
    t_after_a = adapter.history("a")[0]["timestamp"]
    time.sleep(0.01)
    adapter.create(SQLiteEntity(id="b", entity_type="TestEntity", is_available=True,
                                version=1, data={"name": "B"}))

    assert {"a", "b"} <= _ids(client.query(entity_type="TestEntity"))
    assert _ids(client.query(entity_type="TestEntity", as_of=t_after_a)) == {"a"}


def test_query_as_of_reflects_historical_state(client_and_adapter):
    client, adapter = client_and_adapter
    adapter.create(SQLiteEntity(id="a", entity_type="TestEntity", is_available=True,
                                version=1, data={"name": "v1"}))
    t1 = adapter.history("a")[0]["timestamp"]
    time.sleep(0.01)
    adapter.update_data(entity_id="a", entity_type="TestEntity",
                        data={"name": "v2"}, new_version=2)

    asof = client.query(entity_type="TestEntity", as_of=t1)
    assert next(i for i in asof.items if i["id"] == "a")["data"]["name"] == "v1"

    current = client.query(entity_type="TestEntity")
    assert next(i for i in current.items if i["id"] == "a")["data"]["name"] == "v2"


def test_query_as_of_respects_availability_over_time(client_and_adapter):
    client, adapter = client_and_adapter
    adapter.create(SQLiteEntity(id="c", entity_type="TestEntity", is_available=True,
                                version=1, data={"name": "C"}))
    t_present = adapter.history("c")[0]["timestamp"]
    time.sleep(0.01)
    adapter.delete("c")

    # present at t_present; gone from the current view after delete
    assert "c" in _ids(client.query(entity_type="TestEntity", as_of=t_present))
    assert "c" not in _ids(client.query(entity_type="TestEntity"))


def test_query_as_of_applies_filters(client_and_adapter):
    client, adapter = client_and_adapter
    adapter.create(SQLiteEntity(id="x", entity_type="TestEntity", is_available=True,
                                version=1, data={"name": "keep"}))
    adapter.create(SQLiteEntity(id="y", entity_type="TestEntity", is_available=True,
                                version=1, data={"name": "drop"}))

    res = client.query(entity_type="TestEntity",
                       filters=[{"field": "name", "value": "keep"}], as_of=FUTURE)
    assert _ids(res) == {"x"}
