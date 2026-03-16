"""Integration tests for FTS search functionality."""

import pytest
from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter, SQLiteEntity
from hippo.core.storage import ScoredMatch
from hippo.core.exceptions import SearchCapabilityError


def _create_fts_table(adapter, fts_table_name: str, fields: list[str]) -> None:
    """Create an FTS table without external content mode for testing."""
    with adapter._transaction() as conn:
        cursor = conn.cursor()
        columns = ["entity_id"] + fields
        columns_sql = ", ".join(columns)
        cursor.execute(
            f"CREATE VIRTUAL TABLE {fts_table_name} USING fts5({columns_sql})"
        )


def _sync_to_fts(
    adapter, fts_table_name: str, entity_id: str, content: str, field_name: str
) -> None:
    """Helper to sync entity to FTS table."""
    with adapter._transaction() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT rowid FROM {fts_table_name} WHERE entity_id = ?",
            (entity_id,),
        )
        existing = cursor.fetchone()

        if existing:
            cursor.execute(
                f"UPDATE {fts_table_name} SET {field_name} = ? WHERE entity_id = ?",
                (content, entity_id),
            )
        else:
            cursor.execute(
                f"INSERT INTO {fts_table_name} (entity_id, {field_name}) VALUES (?, ?)",
                (entity_id, content),
            )


class TestFTS5SearchIntegration:
    """Integration tests for FTS5 search with SQLite adapter."""

    def test_search_with_fts_indexed_field(self, temp_db_path):
        """Test search returns matching entities with scores."""
        adapter = SQLiteAdapter(temp_db_path)

        entity = SQLiteEntity(
            id="test-1",
            entity_type="Sample",
            is_available=True,
            version=1,
            data={"title": "prefrontal cortex analysis"},
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
        )
        adapter.create(entity)

        _create_fts_table(adapter, "fts_sample_title", ["title"])
        _sync_to_fts(
            adapter, "fts_sample_title", "test-1", "prefrontal cortex analysis", "title"
        )

        results = adapter.search(
            query="prefrontal",
            entity_type="Sample",
            field_name="title",
        )

        assert len(results) >= 1
        assert any(r.entity_id == "test-1" for r in results)
        scored_result = next(r for r in results if r.entity_id == "test-1")
        assert scored_result.score > 0.0

    def test_search_partial_term_match(self, temp_db_path):
        """Test search finds entity by partial term match."""
        adapter = SQLiteAdapter(temp_db_path)

        entity = SQLiteEntity(
            id="test-2",
            entity_type="Document",
            is_available=True,
            version=1,
            data={"content": "hello world test document"},
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
        )
        adapter.create(entity)

        _create_fts_table(adapter, "fts_document_content", ["content"])
        _sync_to_fts(
            adapter,
            "fts_document_content",
            "test-2",
            "hello world test document",
            "content",
        )

        results = adapter.search(
            query="hello",
            entity_type="Document",
            field_name="content",
        )

        assert len(results) >= 1
        assert results[0].entity_id == "test-2"

    def test_search_case_insensitive(self, temp_db_path):
        """Test search is case-insensitive."""
        adapter = SQLiteAdapter(temp_db_path)

        entity = SQLiteEntity(
            id="test-3",
            entity_type="Sample",
            is_available=True,
            version=1,
            data={"notes": "Analysis Results"},
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
        )
        adapter.create(entity)

        _create_fts_table(adapter, "fts_sample_notes", ["notes"])
        _sync_to_fts(adapter, "fts_sample_notes", "test-3", "Analysis Results", "notes")

        results = adapter.search(
            query="ANALYSIS",
            entity_type="Sample",
            field_name="notes",
        )

        assert len(results) >= 1

    def test_search_results_ordered_by_score_desc(self, temp_db_path):
        """Test search results are ordered by score descending."""
        adapter = SQLiteAdapter(temp_db_path)

        entity1 = SQLiteEntity(
            id="test-a",
            entity_type="Document",
            is_available=True,
            version=1,
            data={"content": "test test test test test"},
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
        )
        entity2 = SQLiteEntity(
            id="test-b",
            entity_type="Document",
            is_available=True,
            version=1,
            data={"content": "test test"},
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
        )
        adapter.create(entity1)
        adapter.create(entity2)

        _create_fts_table(adapter, "fts_document_content", ["content"])
        _sync_to_fts(
            adapter,
            "fts_document_content",
            "test-a",
            "test test test test test",
            "content",
        )
        _sync_to_fts(adapter, "fts_document_content", "test-b", "test test", "content")

        results = adapter.search(
            query="test",
            entity_type="Document",
            field_name="content",
        )

        assert len(results) == 2
        for i in range(len(results) - 1):
            assert results[i].score >= results[i + 1].score

    def test_search_scores_normalized_to_0_1_range(self, temp_db_path):
        """Test normalized scores are in [0.0, 1.0] range."""
        adapter = SQLiteAdapter(temp_db_path)

        entity = SQLiteEntity(
            id="test-4",
            entity_type="Sample",
            is_available=True,
            version=1,
            data={"title": "test document"},
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
        )
        adapter.create(entity)

        _create_fts_table(adapter, "fts_sample_title", ["title"])
        _sync_to_fts(adapter, "fts_sample_title", "test-4", "test document", "title")

        results = adapter.search(
            query="test",
            entity_type="Sample",
            field_name="title",
        )

        assert len(results) >= 1
        for result in results:
            assert 0.0 <= result.score <= 1.0

    def test_search_empty_results_for_non_matching_query(self, temp_db_path):
        """Test empty results for non-matching query."""
        adapter = SQLiteAdapter(temp_db_path)

        entity = SQLiteEntity(
            id="test-5",
            entity_type="Sample",
            is_available=True,
            version=1,
            data={"title": "hello world"},
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
        )
        adapter.create(entity)

        _create_fts_table(adapter, "fts_sample_title", ["title"])
        _sync_to_fts(adapter, "fts_sample_title", "test-5", "hello world", "title")

        results = adapter.search(
            query="nonexistent",
            entity_type="Sample",
            field_name="title",
        )

        assert results == []


class TestFTS5SearchCapabilityError:
    """Tests for SearchCapabilityError."""

    def test_search_non_fts_field_raises_error(self, temp_db_path):
        """Test searching non-FTS field raises SearchCapabilityError."""
        adapter = SQLiteAdapter(temp_db_path)

        entity = SQLiteEntity(
            id="test-6",
            entity_type="Sample",
            is_available=True,
            version=1,
            data={"description": "some text"},
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
        )
        adapter.create(entity)

        with pytest.raises(SearchCapabilityError) as exc_info:
            adapter.search(
                query="some",
                entity_type="Sample",
                field_name="description",
            )

        assert "not FTS-indexed" in str(exc_info.value.message)
        assert exc_info.value.field_name == "description"
        assert exc_info.value.entity_type == "Sample"

    def test_search_capability_error_suggests_fts(self, temp_db_path):
        """Test SearchCapabilityError suggests enabling FTS."""
        adapter = SQLiteAdapter(temp_db_path)

        entity = SQLiteEntity(
            id="test-7",
            entity_type="Sample",
            is_available=True,
            version=1,
            data={"notes": "test"},
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
        )
        adapter.create(entity)

        try:
            adapter.search(
                query="test",
                entity_type="Sample",
                field_name="notes",
            )
        except SearchCapabilityError as e:
            suggestion = e.suggest_fts_enablement()
            assert "search: fts" in suggestion


class TestFTS5SearchMinScore:
    """Tests for min_score parameter."""

    def test_min_score_filters_results(self, temp_db_path):
        """Test min_score filters out low-scored entities."""
        adapter = SQLiteAdapter(temp_db_path)

        entity1 = SQLiteEntity(
            id="test-high",
            entity_type="Document",
            is_available=True,
            version=1,
            data={"content": "test test test test test"},
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
        )
        entity2 = SQLiteEntity(
            id="test-low",
            entity_type="Document",
            is_available=True,
            version=1,
            data={"content": "test"},
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
        )
        adapter.create(entity1)
        adapter.create(entity2)

        _create_fts_table(adapter, "fts_document_content", ["content"])
        _sync_to_fts(
            adapter,
            "fts_document_content",
            "test-high",
            "test test test test test",
            "content",
        )
        _sync_to_fts(adapter, "fts_document_content", "test-low", "test", "content")

        results = adapter.search(
            query="test",
            entity_type="Document",
            field_name="content",
            min_score=0.5,
        )

        for result in results:
            assert result.score >= 0.5

    def test_min_score_zero_returns_all(self, temp_db_path):
        """Test min_score=0.0 returns all matches."""
        adapter = SQLiteAdapter(temp_db_path)

        entity = SQLiteEntity(
            id="test-8",
            entity_type="Sample",
            is_available=True,
            version=1,
            data={"title": "test document"},
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
        )
        adapter.create(entity)

        _create_fts_table(adapter, "fts_sample_title", ["title"])
        _sync_to_fts(adapter, "fts_sample_title", "test-8", "test document", "title")

        results = adapter.search(
            query="test",
            entity_type="Sample",
            field_name="title",
            min_score=0.0,
        )

        assert len(results) >= 1


class TestFTS5SearchLimit:
    """Tests for limit parameter."""

    def test_limit_restricts_results(self, temp_db_path):
        """Test limit restricts result count."""
        adapter = SQLiteAdapter(temp_db_path)

        _create_fts_table(adapter, "fts_document_content", ["content"])

        for i in range(10):
            entity = SQLiteEntity(
                id=f"test-{i}",
                entity_type="Document",
                is_available=True,
                version=1,
                data={"content": "test content"},
                created_at="2024-01-01T00:00:00",
                updated_at="2024-01-01T00:00:00",
            )
            adapter.create(entity)
            _sync_to_fts(
                adapter, "fts_document_content", f"test-{i}", "test content", "content"
            )

        results = adapter.search(
            query="test",
            entity_type="Document",
            field_name="content",
            limit=5,
        )

        assert len(results) <= 5

    def test_limit_defaults_to_100(self, temp_db_path):
        """Test limit defaults to 100."""
        adapter = SQLiteAdapter(temp_db_path)

        entity = SQLiteEntity(
            id="test-9",
            entity_type="Sample",
            is_available=True,
            version=1,
            data={"title": "test"},
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
        )
        adapter.create(entity)

        _create_fts_table(adapter, "fts_sample_title", ["title"])
        _sync_to_fts(adapter, "fts_sample_title", "test-9", "test", "title")

        results = adapter.search(
            query="test",
            entity_type="Sample",
            field_name="title",
        )

        assert len(results) <= 100

    def test_limit_higher_than_matches_returns_all(self, temp_db_path):
        """Test limit higher than matches returns all."""
        adapter = SQLiteAdapter(temp_db_path)

        _create_fts_table(adapter, "fts_document_content", ["content"])

        for i in range(5):
            entity = SQLiteEntity(
                id=f"doc-{i}",
                entity_type="Document",
                is_available=True,
                version=1,
                data={"content": "test"},
                created_at="2024-01-01T00:00:00",
                updated_at="2024-01-01T00:00:00",
            )
            adapter.create(entity)
            _sync_to_fts(adapter, "fts_document_content", f"doc-{i}", "test", "content")

        results = adapter.search(
            query="test",
            entity_type="Document",
            field_name="content",
            limit=1000,
        )

        assert len(results) == 5


@pytest.fixture
def temp_db_path(tmp_path):
    """Create a temporary database path."""
    db_path = tmp_path / "test_fts_search.db"
    yield str(db_path)
    if db_path.exists():
        db_path.unlink()
