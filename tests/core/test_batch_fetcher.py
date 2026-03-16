"""Unit tests for batch fetcher."""

import pytest
from unittest.mock import Mock, MagicMock

from hippo.core.batch_fetcher import (
    BatchFetcher,
    EntityQuery,
    ExpandableField,
    FetchResult,
    fetch_expanded,
)
from hippo.core.expand_path_parser import ExpandPathParser, ParseResult, PathNode


class TestBatchFetcher:
    """Tests for the BatchFetcher class."""

    def test_fetch_simple_path(self):
        """Test fetching with a simple expand path."""
        parser = ExpandPathParser()
        result = parser.parse("user.profile")

        mock_storage = Mock()
        mock_entity = Mock()
        mock_entity.id = "user-123"
        mock_entity.entity_type = "user"
        mock_entity.data = {"name": "Test User"}
        mock_entity.version = 1
        mock_entity.created_at = "2024-01-01T00:00:00"
        mock_entity.updated_at = "2024-01-01T00:00:00"
        mock_storage.read.return_value = mock_entity

        fetcher = BatchFetcher(storage=mock_storage)
        fetch_result = fetcher.fetch(result, "user-123")

        assert isinstance(fetch_result, FetchResult)
        assert fetch_result.primary_entity["id"] == "user-123"
        assert fetch_result.query_count >= 0

    def test_fetch_no_storage(self):
        """Test fetching without storage adapter."""
        parser = ExpandPathParser()
        result = parser.parse("user")

        fetcher = BatchFetcher(storage=None)
        fetch_result = fetcher.fetch(result, "user-123")

        assert fetch_result.primary_entity["id"] == "user-123"
        assert fetch_result.query_count == 0

    def test_fetch_nonexistent_entity(self):
        """Test fetching a non-existent entity."""
        parser = ExpandPathParser()
        result = parser.parse("user.profile")

        mock_storage = Mock()
        mock_storage.read.return_value = None

        fetcher = BatchFetcher(storage=mock_storage)
        fetch_result = fetcher.fetch(result, "nonexistent-id")

        assert fetch_result.primary_entity == {}
        assert fetch_result.query_count == 0


class TestFetchResult:
    """Tests for the FetchResult class."""

    def test_to_dict(self):
        """Test converting fetch result to dictionary."""
        result = FetchResult(
            primary_entity={"id": "123", "data": {}},
            expanded_data={"profile": []},
            query_count=1,
        )

        result_dict = result.to_dict()

        assert result_dict["primary_entity"]["id"] == "123"
        assert result_dict["expanded_data"]["profile"] == []
        assert result_dict["query_count"] == 1


class TestEntityQuery:
    """Tests for the EntityQuery class."""

    def test_create_entity_query(self):
        """Test creating an EntityQuery."""
        query = EntityQuery(
            entity_type="user",
            entity_ids=["1", "2", "3"],
            path_segment="user",
        )

        assert query.entity_type == "user"
        assert len(query.entity_ids) == 3
        assert query.path_segment == "user"


class TestExpandableField:
    """Tests for the ExpandableField class."""

    def test_create_expandable_field(self):
        """Test creating an ExpandableField."""
        field = ExpandableField(
            name="profile",
            entity_type="profile",
            path="user.profile",
        )

        assert field.name == "profile"
        assert field.entity_type == "profile"
        assert field.path == "user.profile"


class TestFetchExpanded:
    """Tests for the fetch_expanded convenience function."""

    def test_fetch_expanded_function(self):
        """Test the fetch_expanded convenience function."""
        parser = ExpandPathParser()
        result = parser.parse("user")

        mock_storage = Mock()
        mock_entity = Mock()
        mock_entity.id = "user-123"
        mock_entity.entity_type = "user"
        mock_entity.data = {}
        mock_entity.version = 1
        mock_entity.created_at = "2024-01-01"
        mock_entity.updated_at = "2024-01-01"
        mock_storage.read.return_value = mock_entity

        fetch_result = fetch_expanded(mock_storage, result, "user-123")

        assert isinstance(fetch_result, FetchResult)


class TestBatchFetcherSimpleFetch:
    """Tests for the BatchFetcher.fetch_simple method."""

    def test_fetch_simple_with_storage(self):
        """Test fetch_simple with storage adapter."""
        mock_storage = Mock()
        mock_entity = Mock()
        mock_entity.id = "user-123"
        mock_entity.entity_type = "user"
        mock_entity.data = {"name": "Test"}
        mock_entity.version = 1
        mock_entity.created_at = "2024-01-01"
        mock_entity.updated_at = "2024-01-01"
        mock_storage.read.return_value = mock_entity

        fetcher = BatchFetcher(storage=mock_storage)
        result = fetcher.fetch_simple("user", "user-123")

        assert result is not None
        assert result["id"] == "user-123"
        assert result["entity_type"] == "user"

    def test_fetch_simple_without_storage(self):
        """Test fetch_simple without storage adapter."""
        fetcher = BatchFetcher(storage=None)
        result = fetcher.fetch_simple("user", "user-123")

        assert result is not None
        assert result["id"] == "user-123"
        assert result["entity_type"] == "user"

    def test_fetch_simple_nonexistent(self):
        """Test fetch_simple with non-existent entity."""
        mock_storage = Mock()
        mock_storage.read.return_value = None

        fetcher = BatchFetcher(storage=mock_storage)
        result = fetcher.fetch_simple("user", "nonexistent")

        assert result is None
