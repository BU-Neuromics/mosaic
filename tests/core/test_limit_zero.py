"""``limit=0`` returns zero rows, not all rows (issue #130).

Python treats ``0`` as falsy, so limiting code gated on ``if limit:`` skipped
the slice entirely and returned the full result set — identical to
``limit=None``. The fix uses ``if limit is not None:`` on every paginating
path: ``QueryService.query``, ``QueryService.query_updated_since``, and the
SQLite adapter's live and as-of ``find`` slices.
"""

import os
import tempfile

import pytest

from mosaic.core.client import MosaicClient
from mosaic.core.storage import Query
from mosaic.core.storage.adapters.sqlite_adapter import SQLiteAdapter
from tests.conftest import _build_minimal_schema_registry

FUTURE = "2999-01-01T00:00:00+00:00"


class TestLimitZeroThroughClient:
    @pytest.fixture
    def client(self) -> MosaicClient:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = SQLiteAdapter(
                os.path.join(tmpdir, "lim.db"),
                schema_registry=_build_minimal_schema_registry(),
            )
            c = MosaicClient(storage=storage, bypass_validation=True)
            for i in range(5):
                c.put("Sample", {"id": f"I-{i}", "name": f"n{i}"})
            yield c

    def test_limit_zero_returns_no_rows(self, client: MosaicClient) -> None:
        r = client.query("Sample", limit=0)
        assert len(r.items) == 0
        # ``total`` still reflects the full matching count — only the page is
        # empty (paging is applied after counting).
        assert r.total == 5

    def test_limit_none_returns_all_rows(self, client: MosaicClient) -> None:
        r = client.query("Sample", limit=None)
        assert len(r.items) == 5

    def test_positive_limit_still_truncates(self, client: MosaicClient) -> None:
        r = client.query("Sample", limit=2)
        assert len(r.items) == 2
        assert r.total == 5

    def test_limit_zero_with_offset(self, client: MosaicClient) -> None:
        r = client.query("Sample", limit=0, offset=2)
        assert len(r.items) == 0

    def test_limit_zero_on_as_of_path(self, client: MosaicClient) -> None:
        r = client.query("Sample", limit=0, as_of=FUTURE)
        assert len(r.items) == 0

    def test_limit_zero_on_updated_since(self, client: MosaicClient) -> None:
        r = client.query_updated_since("Sample", since="2000-01-01T00:00:00+00:00", limit=0)
        assert len(r.items) == 0
        assert r.total == 5


class TestLimitZeroLowLevelAdapter:
    """``SQLiteAdapter.find`` builds ``LIMIT 0`` (live path) / slices ``[:0]``
    (as-of path) directly — pin both without ``MosaicClient`` in the way."""

    @pytest.fixture
    def adapter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            a = SQLiteAdapter(
                os.path.join(tmpdir, "lim_adapter.db"),
                schema_registry=_build_minimal_schema_registry(),
            )
            from mosaic.core.storage.adapters.sqlite_adapter import SQLiteEntity

            for i in range(3):
                a.create(
                    SQLiteEntity(
                        id=f"I-{i}", entity_type="Sample", is_available=True,
                        version=1, data={"name": f"n{i}"},
                    )
                )
            yield a
            a.close()

    def test_find_limit_zero_live_path(self, adapter) -> None:
        assert list(adapter.find(Query(entity_type="Sample", limit=0))) == []

    def test_find_limit_none_returns_all(self, adapter) -> None:
        assert len(list(adapter.find(Query(entity_type="Sample", limit=None)))) == 3

    def test_find_limit_zero_as_of_path(self, adapter) -> None:
        assert list(adapter.find(Query(entity_type="Sample", limit=0), as_of=FUTURE)) == []
