"""End-to-end tests for the reference loader install/upgrade lifecycle.

Exercises every acceptance criterion from PTS-229 and the v2 substrate
swap from PTS-256:

- ``install --version v1`` writes ``hippo_meta[reference_versions]``
  AND populates ``reference_write_log`` for every ``client.put()`` made
  inside the ``load_context`` block (sec2 §2.14.9, D2.14.J).
- Upgrade additive: both versions queryable, hippo_meta reflects target.
- Upgrade ``--prune-old`` success: prior rows removed (hard delete) and
  matching ``reference_write_log`` rows deleted in the same transaction.
- Upgrade ``--prune-old`` failure mid-load: prior rows intact.
- ``--prune-old`` works when the loader returns an empty
  ``LoadResult.entities`` list (write log is the authoritative substrate).
- ``--prune-old`` removes the entity row on stable-id upgrade overlap
  (documented v2 constraint, sec2 §2.14.9).
- ``--version test`` install works against the fake loader's bundled
  fixture with no network.
- Re-installing the same version is a clear, idempotent no-op.

All cases drive the public ``install_reference`` / ``upgrade_reference``
helpers against the real SQLite adapter and ``FakeReferenceLoader``.
The Typer surface is exercised in one smoke test via ``CliRunner``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from hippo.cli.commands.reference import (
    META_KEY_VERSIONS,
    install_reference,
    list_reference_loaders,
    upgrade_reference,
)
from hippo.cli.main import app
from hippo.core.loaders.reference import EntityRef
from hippo.core.meta import get_meta
from hippo.testing.fake_reference_loader import FakeLoadParams


@pytest.fixture
def hippo_workspace(tmp_path: Path) -> dict[str, Path]:
    """Return paths to an empty Hippo workspace (db + schemas dir).

    The schemas dir is intentionally left empty so the install lifecycle
    falls back to the bundled ``hippo_core`` schema as the base. The
    fake loader's fragment is then merged on top.
    """
    db_path = tmp_path / "hippo.db"
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    return {"db": db_path, "schemas": schema_dir, "root": tmp_path}


def _open(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _count_rows(db_path: Path, table: str) -> int:
    """Count *available* rows. Hippo uses soft-delete (sec3) for the
    standard user/REST path — every ``client.delete()`` flips
    ``is_available=0`` instead of removing the row. ``--prune-old``
    bypasses that path and hard-deletes from the entity tables, so a
    post-prune count is also the total row count for the loader.
    """
    conn = _open(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            f'SELECT COUNT(*) AS n FROM "{table}" WHERE is_available = 1'
        )
        return cursor.fetchone()["n"]
    finally:
        conn.close()


def _count_all_rows(db_path: Path, table: str) -> int:
    """Count every row, including soft-deleted. Used to assert that
    ``--prune-old`` actually drops rows from disk (D2.14.J hard delete).
    """
    conn = _open(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(f'SELECT COUNT(*) AS n FROM "{table}"')
        return cursor.fetchone()["n"]
    finally:
        conn.close()


def _select_write_log(
    db_path: Path, loader: str, version: str
) -> list[tuple[str, str]]:
    """Return ``(entity_id, entity_type)`` rows from the write log."""
    conn = _open(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT entity_id, entity_type FROM reference_write_log "
            "WHERE loader_name = ? AND version = ? "
            "ORDER BY entity_id",
            (loader, version),
        )
        return [(row["entity_id"], row["entity_type"]) for row in cursor.fetchall()]
    finally:
        conn.close()


class TestInstall:
    def test_install_records_version_in_hippo_meta(self, hippo_workspace):
        result = install_reference(
            "fake",
            "v1",
            db_path=hippo_workspace["db"],
            schema_dir=hippo_workspace["schemas"],
        )

        assert result["status"] == "installed"
        assert result["version"] == "v1"
        assert result["created"] == 3
        # v2 LoadResult shape: result["entities"] is the advisory list of
        # EntityRef handles populated by the loader.
        assert len(result["entities"]) == 3
        assert all(isinstance(e, EntityRef) for e in result["entities"])
        assert all(e.type == "FakeTerm" for e in result["entities"])

        conn = _open(hippo_workspace["db"])
        try:
            versions = get_meta(conn, META_KEY_VERSIONS)
        finally:
            conn.close()
        assert versions == {"fake": "v1"}
        assert _count_rows(hippo_workspace["db"], "FakeTerm") == 3

        # Every put() inside ``load_context`` recorded a write-log row.
        log = _select_write_log(hippo_workspace["db"], "fake", "v1")
        assert len(log) == 3
        assert {entity_type for _, entity_type in log} == {"FakeTerm"}
        assert {entity_id for entity_id, _ in log} == {
            e.id for e in result["entities"]
        }

    def test_reinstall_same_version_is_noop(self, hippo_workspace):
        install_reference(
            "fake",
            "v1",
            db_path=hippo_workspace["db"],
            schema_dir=hippo_workspace["schemas"],
        )
        again = install_reference(
            "fake",
            "v1",
            db_path=hippo_workspace["db"],
            schema_dir=hippo_workspace["schemas"],
        )
        assert again["status"] == "already_installed"
        # No duplicate rows were written on the second invocation.
        assert _count_rows(hippo_workspace["db"], "FakeTerm") == 3

    def test_install_test_slug_works_without_network(self, hippo_workspace):
        # No HTTP traffic is mocked here — the fake loader is in-memory.
        # If the test_slug code path ever introduces a network call, this
        # test will hang or fail outright.
        result = install_reference(
            "fake",
            "test",
            db_path=hippo_workspace["db"],
            schema_dir=hippo_workspace["schemas"],
        )
        assert result["version"] == "test"
        assert result["created"] == 2
        assert _count_rows(hippo_workspace["db"], "FakeTerm") == 2

    def test_install_unknown_loader_raises(self, hippo_workspace):
        with pytest.raises(KeyError):
            install_reference(
                "no-such-loader",
                "v1",
                db_path=hippo_workspace["db"],
                schema_dir=hippo_workspace["schemas"],
            )

    def test_install_default_version_skips_reserved_test_slug(
        self, hippo_workspace
    ):
        # Confirm D2.14.I — internal default-version resolution never
        # picks "test" even when the loader exposes it.
        result = install_reference(
            "fake",
            None,
            db_path=hippo_workspace["db"],
            schema_dir=hippo_workspace["schemas"],
        )
        assert result["version"] != "test"


class TestUpgradeAdditive:
    def test_upgrade_keeps_old_rows_and_adds_new(self, hippo_workspace):
        install_reference(
            "fake",
            "v1",
            db_path=hippo_workspace["db"],
            schema_dir=hippo_workspace["schemas"],
        )
        before = _count_rows(hippo_workspace["db"], "FakeTerm")
        assert before == 3

        upgrade = upgrade_reference(
            "fake",
            "v2",
            db_path=hippo_workspace["db"],
            schema_dir=hippo_workspace["schemas"],
        )
        assert upgrade["status"] == "upgraded"
        assert upgrade["from_version"] == "v1"
        assert upgrade["to_version"] == "v2"
        assert upgrade["created"] == 4
        assert upgrade["pruned"] == []

        # v1 (3) + v2 (4) ingested side-by-side per D2.14.F.
        assert _count_rows(hippo_workspace["db"], "FakeTerm") == before + 4

        conn = _open(hippo_workspace["db"])
        try:
            versions = get_meta(conn, META_KEY_VERSIONS)
        finally:
            conn.close()
        assert versions == {"fake": "v2"}

        # Both versions appear in the write log (additive — no prune).
        assert len(_select_write_log(hippo_workspace["db"], "fake", "v1")) == 3
        assert len(_select_write_log(hippo_workspace["db"], "fake", "v2")) == 4


class TestUpgradePruneOld:
    def test_prune_old_success_removes_prior_rows(self, hippo_workspace):
        install_reference(
            "fake",
            "v1",
            db_path=hippo_workspace["db"],
            schema_dir=hippo_workspace["schemas"],
        )
        assert _count_rows(hippo_workspace["db"], "FakeTerm") == 3

        upgrade = upgrade_reference(
            "fake",
            "v2",
            db_path=hippo_workspace["db"],
            schema_dir=hippo_workspace["schemas"],
            prune_old=True,
        )
        assert upgrade["status"] == "upgraded"
        assert len(upgrade["pruned"]) == 3
        assert all(isinstance(p, EntityRef) for p in upgrade["pruned"])
        assert all(p.type == "FakeTerm" for p in upgrade["pruned"])
        # Hard delete — only v2 rows survive in the entity table.
        assert _count_rows(hippo_workspace["db"], "FakeTerm") == 4
        assert _count_all_rows(hippo_workspace["db"], "FakeTerm") == 4

        # The matching write-log rows for the pruned version went with
        # the entity rows; the new version's log rows are intact.
        assert _select_write_log(hippo_workspace["db"], "fake", "v1") == []
        assert len(_select_write_log(hippo_workspace["db"], "fake", "v2")) == 4

    def test_prune_old_uses_write_log_when_entities_empty(
        self, hippo_workspace
    ):
        # Simulates a large-scale loader that leaves
        # ``LoadResult.entities`` empty and relies on the write log
        # (sec2 §2.14.8 advisory contract).
        install_reference(
            "fake",
            "v1",
            db_path=hippo_workspace["db"],
            schema_dir=hippo_workspace["schemas"],
            params=FakeLoadParams(omit_entity_refs=True),
        )
        # Loader returned an empty advisory list, but writes still
        # happened — assert the substrate is decoupled.
        installed_log = _select_write_log(hippo_workspace["db"], "fake", "v1")
        assert len(installed_log) == 3

        upgrade = upgrade_reference(
            "fake",
            "v2",
            db_path=hippo_workspace["db"],
            schema_dir=hippo_workspace["schemas"],
            prune_old=True,
            params=FakeLoadParams(omit_entity_refs=True),
        )
        assert upgrade["entities"] == []
        # Prune still removed all 3 v1 rows — the write log was the
        # source of truth, not ``LoadResult.entities``.
        assert len(upgrade["pruned"]) == 3
        assert _count_rows(hippo_workspace["db"], "FakeTerm") == 4
        assert _select_write_log(hippo_workspace["db"], "fake", "v1") == []

    def test_prune_old_removes_overlapping_stable_ids(self, hippo_workspace):
        # Stable-id overlap (sec2 §2.14.9): v1 and v2 share IDs for
        # "alpha"/"beta"/"gamma". The default ``upgrade()`` re-writes
        # those rows under v2 so the entity table holds 4 rows
        # (alpha/beta/gamma updated + delta new). Prune of v1 then
        # removes the overlapping entity rows even though v2 still
        # references the same IDs — documented v2 behavior; loaders
        # that need overlap survival must override ``upgrade()``.
        install_reference(
            "fake",
            "v1",
            db_path=hippo_workspace["db"],
            schema_dir=hippo_workspace["schemas"],
            params=FakeLoadParams(stable_ids=True),
        )
        assert _count_rows(hippo_workspace["db"], "FakeTerm") == 3
        v1_log = _select_write_log(hippo_workspace["db"], "fake", "v1")
        v1_ids = {entity_id for entity_id, _ in v1_log}
        assert v1_ids == {"fake-alpha", "fake-beta", "fake-gamma"}

        upgrade = upgrade_reference(
            "fake",
            "v2",
            db_path=hippo_workspace["db"],
            schema_dir=hippo_workspace["schemas"],
            prune_old=True,
            params=FakeLoadParams(stable_ids=True),
        )
        assert upgrade["status"] == "upgraded"
        assert len(upgrade["pruned"]) == 3

        # All three overlapping entity rows are gone — the v2 "delta"
        # row is the only thing left.
        assert _count_all_rows(hippo_workspace["db"], "FakeTerm") == 1
        conn = _open(hippo_workspace["db"])
        try:
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM "FakeTerm"')
            remaining = {row["id"] for row in cursor.fetchall()}
        finally:
            conn.close()
        assert remaining == {"fake-delta"}

        # v1 log rows are gone; v2 still has its 4 rows (3 overlapping
        # ids + delta).
        assert _select_write_log(hippo_workspace["db"], "fake", "v1") == []
        v2_log = _select_write_log(hippo_workspace["db"], "fake", "v2")
        assert len(v2_log) == 4

    def test_prune_old_failure_mid_load_keeps_prior_rows(self, hippo_workspace):
        install_reference(
            "fake",
            "v1",
            db_path=hippo_workspace["db"],
            schema_dir=hippo_workspace["schemas"],
        )
        baseline = _count_rows(hippo_workspace["db"], "FakeTerm")
        assert baseline == 3

        # Force loader.load() (called via .upgrade default) to raise
        # after persisting 2 rows of the v2 dataset.
        with pytest.raises(RuntimeError, match="simulated failure"):
            upgrade_reference(
                "fake",
                "v2",
                db_path=hippo_workspace["db"],
                schema_dir=hippo_workspace["schemas"],
                prune_old=True,
                params=FakeLoadParams(fail_after=2),
            )

        # The prior v1 rows MUST still be intact — prune runs only after
        # a clean LoadResult. The partial v2 writes are not rolled back
        # (the loader contract isn't transactional). The test asserts on
        # the v1 invariant, which is the load-bearing one here.
        conn = _open(hippo_workspace["db"])
        try:
            versions = get_meta(conn, META_KEY_VERSIONS) or {}
        finally:
            conn.close()
        # hippo_meta still points at v1 — upgrade was aborted before
        # the version pointer rotated.
        assert versions == {"fake": "v1"}

        # The write log still has all 3 v1 rows (the prune path never
        # ran). The 2 committed v2 puts also appear — that mirrors the
        # "log rows correspond exactly to committed entity writes"
        # invariant from sec2 §2.14.9.
        v1_log = _select_write_log(hippo_workspace["db"], "fake", "v1")
        assert len(v1_log) == 3
        v2_log = _select_write_log(hippo_workspace["db"], "fake", "v2")
        assert len(v2_log) == 2

        # All three prior IDs still queryable in FakeTerm with
        # is_available=1.
        prior_ids = [entity_id for entity_id, _ in v1_log]
        conn = _open(hippo_workspace["db"])
        try:
            cursor = conn.cursor()
            placeholders = ",".join("?" * len(prior_ids))
            cursor.execute(
                f'SELECT id, is_available FROM "FakeTerm" '
                f'WHERE id IN ({placeholders})',
                prior_ids,
            )
            rows = cursor.fetchall()
        finally:
            conn.close()
        ids_still_there = {row["id"] for row in rows}
        assert ids_still_there == set(prior_ids)
        assert all(row["is_available"] == 1 for row in rows)


class TestUpgradeGuards:
    def test_upgrade_without_prior_install_errors(self, hippo_workspace):
        with pytest.raises(ValueError, match="not installed"):
            upgrade_reference(
                "fake",
                "v2",
                db_path=hippo_workspace["db"],
                schema_dir=hippo_workspace["schemas"],
            )

    def test_upgrade_to_same_version_is_noop(self, hippo_workspace):
        install_reference(
            "fake",
            "v1",
            db_path=hippo_workspace["db"],
            schema_dir=hippo_workspace["schemas"],
        )
        result = upgrade_reference(
            "fake",
            "v1",
            db_path=hippo_workspace["db"],
            schema_dir=hippo_workspace["schemas"],
        )
        assert result["status"] == "already_at_version"


class TestListing:
    def test_list_reports_installed_version(self, hippo_workspace):
        install_reference(
            "fake",
            "v1",
            db_path=hippo_workspace["db"],
            schema_dir=hippo_workspace["schemas"],
        )
        loaders = list_reference_loaders(db_path=hippo_workspace["db"])
        fake = next(loader for loader in loaders if loader["name"] == "fake")
        assert fake["installed"] is True
        assert fake["installed_version"] == "v1"

    def test_list_reports_not_installed(self, hippo_workspace):
        loaders = list_reference_loaders(db_path=hippo_workspace["db"])
        fake = next(loader for loader in loaders if loader["name"] == "fake")
        assert fake["installed"] is False
        assert fake["installed_version"] is None


class TestCliSmoke:
    """Drive one happy path through the Typer surface for coverage."""

    def test_install_then_upgrade_via_typer(self, hippo_workspace):
        runner = CliRunner()
        db = str(hippo_workspace["db"])
        sd = str(hippo_workspace["schemas"])

        install = runner.invoke(
            app,
            ["reference", "install", "fake", "--version", "v1",
             "--db-path", db, "--schema-dir", sd],
        )
        assert install.exit_code == 0, install.output
        assert "Installed fake@v1" in install.output

        upgrade = runner.invoke(
            app,
            ["reference", "upgrade", "fake", "--version", "v2",
             "--db-path", db, "--schema-dir", sd, "--prune-old"],
        )
        assert upgrade.exit_code == 0, upgrade.output
        assert "Upgraded fake v1 → v2" in upgrade.output
        assert "3 prior row(s) pruned" in upgrade.output

        ls = runner.invoke(app, ["reference", "list", "--db-path", db])
        assert ls.exit_code == 0, ls.output
        assert "fake" in ls.output
        assert "v2" in ls.output
