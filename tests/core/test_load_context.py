"""End-to-end tests for ``HippoClient.load_context()`` (sec2 §2.14.9 /
Decision 2.14.J).

The context manager is the only sanctioned way to enter reference write-log
mode. The acceptance criteria for PTS-254 spell out six behaviours; this
file mirrors them one-to-one. Coverage focuses on the SQLite path because
that's the unit-test substrate; Postgres parity is verified by
``tests/integration/test_load_context_postgres.py`` once gated infra wakes
up.

Spec interpretation note (PTS-254 thread): the design doc and AC bullet
"write-log insert shares the entity write's SQL transaction" plus "no
orphan log rows persist beyond committed entity writes" imply per-put
atomicity — each ``client.put()`` commits the entity row AND its log row
in one SQL transaction. The "exception rolls back" test below therefore
exercises a mid-put failure (where rollback is observable), not a
post-commit ``raise X`` (where the put has already committed by spec).
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from typing import Iterator
from unittest.mock import patch

import pytest

from hippo.core.client import HippoClient
from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter
from hippo.linkml_bridge import SchemaRegistry
from tests.support.linkml_schemas import build_registry


def _registry() -> SchemaRegistry:
    return build_registry(
        {
            "Sample": {
                "attributes": {
                    "id": {"identifier": True, "required": True},
                    "name": {"range": "string", "required": True},
                }
            },
            "Document": {
                "attributes": {
                    "id": {"identifier": True, "required": True},
                    "title": {"range": "string", "required": True},
                }
            },
        }
    )


@pytest.fixture
def db_path() -> Iterator[str]:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield os.path.join(tmpdir, "load_context.db")


@pytest.fixture
def client(db_path: str) -> Iterator[HippoClient]:
    storage = SQLiteAdapter(db_path, schema_registry=_registry())
    yield HippoClient(
        storage=storage,
        registry=storage.schema_registry,
        bypass_validation=True,
    )
    storage.close()


def _select_log(db_path: str) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            "SELECT loader_name, version, entity_id, entity_type "
            "FROM reference_write_log "
            "ORDER BY loader_name, version, entity_id"
        ).fetchall()
    finally:
        conn.close()


def test_load_context_outside_block_no_op(
    client: HippoClient, db_path: str
) -> None:
    """``client.put()`` outside any ``load_context`` does not write to
    the log — user data writes, REST handlers, and ingestion CLI calls
    must never appear in ``reference_write_log``.
    """
    client.put("Sample", {"id": "s1", "name": "S1"})
    client.put("Document", {"id": "d1", "title": "D1"})

    assert _select_log(db_path) == []


def test_load_context_inside_block_logs_row(
    client: HippoClient, db_path: str
) -> None:
    """A single put inside the block records exactly one row keyed by
    ``(loader_name, version, entity_id, entity_type)``.
    """
    with client.load_context("loader_a", "1.0.0"):
        client.put("Sample", {"id": "s1", "name": "S1"})

    rows = _select_log(db_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["loader_name"] == "loader_a"
    assert row["version"] == "1.0.0"
    assert row["entity_id"] == "s1"
    assert row["entity_type"] == "Sample"


def test_load_context_exception_rolls_back(
    client: HippoClient, db_path: str
) -> None:
    """A failure inside a ``put()`` rolls back BOTH the entity write and
    the would-be log row in the same SQL transaction (sec2 §2.14.9).

    Note on the AC wording: ``with load_context(): client.put(); raise X``
    technically lets ``put()`` commit first (the entity and log row land
    atomically per spec), so ``raise X`` afterwards cannot undo them.
    This test exercises the genuinely interesting rollback case — a
    failure DURING the per-put SQL transaction — and asserts that
    neither row leaks. That preserves the invariant
    "no orphan log rows persist beyond committed entity writes".
    """

    def boom(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("simulated mid-put failure")

    # First put commits cleanly so we can confirm the rollback is scoped
    # to the failing transaction, not a blanket revert of prior work.
    with client.load_context("loader_a", "1.0.0"):
        client.put("Sample", {"id": "s1", "name": "S1"})  # log row #1

        # Force the per-class insert to raise inside the second put's
        # transaction. Because create() also writes the log row inside
        # the same _transaction() block, the rollback covers both.
        with patch.object(SQLiteAdapter, "_insert_per_class", boom):
            with pytest.raises(RuntimeError, match="simulated mid-put failure"):
                client.put("Sample", {"id": "s2", "name": "S2"})

    rows = _select_log(db_path)
    # Exactly one log row: the committed put for s1. The failing put
    # for s2 rolled back together with its would-be log row.
    assert [r["entity_id"] for r in rows] == ["s1"]
    assert client._storage.read("s2") is None


def test_load_context_nested_raises(client: HippoClient) -> None:
    """Entering a ``load_context`` inside another raises — overlapping
    loads are intentionally unsupported in v2.
    """
    with client.load_context("loader_a", "1.0.0"):
        with pytest.raises(RuntimeError, match="nested"):
            with client.load_context("loader_b", "2.0.0"):
                pass  # never reached

    # The outer context is still cleared after the inner raise — the
    # client must not stay wedged in logging mode.
    assert client._loader_context is None


def test_load_context_multi_class(
    client: HippoClient, db_path: str
) -> None:
    """Heterogeneous puts in one block produce rows with the right
    ``entity_type`` per row — the log keys on entity class, not just id.
    """
    with client.load_context("loader_a", "1.0.0"):
        client.put("Sample", {"id": "s1", "name": "S1"})
        client.put("Document", {"id": "d1", "title": "D1"})
        client.put("Sample", {"id": "s2", "name": "S2"})

    triples = {
        (r["loader_name"], r["version"], r["entity_id"], r["entity_type"])
        for r in _select_log(db_path)
    }
    assert triples == {
        ("loader_a", "1.0.0", "s1", "Sample"),
        ("loader_a", "1.0.0", "d1", "Document"),
        ("loader_a", "1.0.0", "s2", "Sample"),
    }


def test_load_context_duplicate_put_collapsed(
    client: HippoClient, db_path: str
) -> None:
    """Re-writing the same ``(loader_name, version, entity_id)`` within
    a single load collapses to one row — the composite PK on
    ``reference_write_log`` makes upgrade() re-writes and per-batch
    retries idempotent (sec2 §2.14.9 / Decision 2.14.J).
    """
    with client.load_context("loader_a", "1.0.0"):
        client.put("Sample", {"id": "s1", "name": "S1"})
        client.put("Sample", {"id": "s1", "name": "S1-updated"})
        client.put("Sample", {"id": "s1", "name": "S1-updated-again"})

    rows = _select_log(db_path)
    assert len(rows) == 1
    assert rows[0]["entity_id"] == "s1"
    assert rows[0]["loader_name"] == "loader_a"
    assert rows[0]["version"] == "1.0.0"


def test_load_context_clears_state_after_normal_exit(
    client: HippoClient, db_path: str
) -> None:
    """The context manager clears ``_loader_context`` on normal exit so
    subsequent puts revert to the no-op log behavior.
    """
    with client.load_context("loader_a", "1.0.0"):
        client.put("Sample", {"id": "s1", "name": "S1"})

    client.put("Sample", {"id": "s2", "name": "S2"})

    rows = _select_log(db_path)
    assert [r["entity_id"] for r in rows] == ["s1"]


def test_load_context_clears_state_after_exception(
    client: HippoClient,
) -> None:
    """``_loader_context`` must reset even when the block raises so the
    client doesn't stay wedged in logging mode.
    """
    with pytest.raises(RuntimeError, match="boom"):
        with client.load_context("loader_a", "1.0.0"):
            raise RuntimeError("boom")

    assert client._loader_context is None
