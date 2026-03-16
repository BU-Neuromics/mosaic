"""Integration tests for the full expand workflow."""

import pytest
from unittest.mock import Mock, MagicMock, patch

from hippo.core.batch_fetcher import BatchFetcher
from hippo.core.cycle_detector import CycleDetector, validate_no_cycle
from hippo.core.expand_path_parser import (
    ExpandPathParser,
    MaxSizeExceededError,
    ParserConfig,
    ParsingError,
    PathNode,
    validate_path,
)
from hippo.core.client import HippoClient


class TestFullExpandWorkflow:
    """Integration tests for the complete expand workflow."""

    def test_parse_validate_cycle_detect_fetch(self):
        """Test full workflow: parse -> validate -> cycle detect -> fetch."""
        expand_path = "user.orders.items.product"

        parsed = validate_path(expand_path)
        assert parsed.field_count == 4

        validate_no_cycle(parsed)

        detector = CycleDetector()
        result = detector.detect(parsed)
        assert not result.has_cycle

    def test_expand_with_max_size_validation(self):
        """Test expand with max size validation."""
        long_path = "user.profile.settings.notifications.preferences.theme"

        config = ParserConfig(max_size=50)
        with pytest.raises(MaxSizeExceededError):
            validate_path(long_path, config)

    def test_expand_with_cycle_detection(self):
        """Test expand with cycle detection."""
        cyclic_path = "user.orders.items.user"

        root = ExpandPathParser().parse(cyclic_path).root
        orders = PathNode(name="orders")
        items = PathNode(name="items")
        user = PathNode(name="user")

        root.children = [orders]
        orders.parent = root
        orders.children = [items]
        items.parent = orders
        items.children = [user]
        user.parent = items

        from hippo.core.expand_path_parser import ParseResult

        parsed = ParseResult(
            root=root,
            raw_path=cyclic_path,
            field_count=4,
            max_depth=3,
        )

        detector = CycleDetector()
        result = detector.detect(parsed)
        assert result.has_cycle

        from hippo.core.cycle_detector import CycleDetectionError

        with pytest.raises(CycleDetectionError):
            detector.validate(parsed)


class TestHippoClientExpand:
    """Integration tests for HippoClient expand functionality."""

    def test_get_with_expand_parameter(self):
        """Test HippoClient.get with expand parameter."""
        mock_storage = Mock()
        mock_entity = Mock()
        mock_entity.id = "user-123"
        mock_entity.entity_type = "user"
        mock_entity.data = {"name": "Test User", "profile": {"id": "profile-1"}}
        mock_entity.version = 1
        mock_entity.created_at = "2024-01-01T00:00:00"
        mock_entity.updated_at = "2024-01-01T00:00:00"
        mock_storage.read.return_value = mock_entity

        client = HippoClient(storage=mock_storage)
        result = client.get("user", "user-123", expand="profile")

        assert result["id"] == "user-123"
        assert "data" in result

    def test_get_without_expand_parameter(self):
        """Test HippoClient.get without expand parameter."""
        mock_storage = Mock()
        mock_entity = Mock()
        mock_entity.id = "user-123"
        mock_entity.entity_type = "user"
        mock_entity.data = {"name": "Test User"}
        mock_entity.version = 1
        mock_entity.created_at = "2024-01-01T00:00:00"
        mock_entity.updated_at = "2024-01-01T00:00:00"
        mock_storage.read.return_value = mock_entity

        client = HippoClient(storage=mock_storage)
        result = client.get("user", "user-123")

        assert result["id"] == "user-123"
        assert "_expanded" not in result

    def test_get_with_expand_invalid_path(self):
        """Test HippoClient.get with invalid expand path."""
        mock_storage = Mock()
        mock_entity = Mock()
        mock_entity.id = "user-123"
        mock_entity.entity_type = "user"
        mock_entity.data = {"name": "Test User"}
        mock_entity.version = 1
        mock_entity.created_at = "2024-01-01T00:00:00"
        mock_entity.updated_at = "2024-01-01T00:00:00"
        mock_storage.read.return_value = mock_entity

        client = HippoClient(storage=mock_storage)

        with pytest.raises(ParsingError):
            client.get("user", "user-123", expand="user..profile")

    def test_get_with_expand_max_size_exceeded(self):
        """Test HippoClient.get with expand path exceeding max size."""
        mock_storage = Mock()
        mock_entity = Mock()
        mock_entity.id = "user-123"
        mock_entity.entity_type = "user"
        mock_entity.data = {"name": "Test User"}
        mock_entity.version = 1
        mock_entity.created_at = "2024-01-01T00:00:00"
        mock_entity.updated_at = "2024-01-01T00:00:00"
        mock_storage.read.return_value = mock_entity

        client = HippoClient(storage=mock_storage)

        with pytest.raises(MaxSizeExceededError):
            client.get("user", "user-123", expand="a" * 200)

    def test_get_with_expand_cyclic_path(self):
        """Test HippoClient.get with cyclic expand path."""
        mock_storage = Mock()
        mock_entity = Mock()
        mock_entity.id = "user-123"
        mock_entity.entity_type = "user"
        mock_entity.data = {"name": "Test User"}
        mock_entity.version = 1
        mock_entity.created_at = "2024-01-01T00:00:00"
        mock_entity.updated_at = "2024-01-01T00:00:00"
        mock_storage.read.return_value = mock_entity

        client = HippoClient(storage=mock_storage)

        from hippo.core.cycle_detector import CycleDetectionError

        with pytest.raises(CycleDetectionError):
            client.get("user", "user-123", expand="user.orders.user")


class TestEndToEndExpand:
    """End-to-end tests for expand functionality."""

    def test_expand_path_with_complex_nesting(self):
        """Test expand path with complex nesting."""
        path = "user.orders.items.product.category"

        parsed = validate_path(path)

        assert parsed.field_count == 5
        assert parsed.max_depth == 4

        validate_no_cycle(parsed)

    def test_expand_path_with_single_field(self):
        """Test expand path with single field."""
        path = "user"

        parsed = validate_path(path)

        assert parsed.field_count == 1
        assert parsed.max_depth == 0

    def test_expand_path_with_underscores_and_dashes(self):
        """Test expand path with underscores and dashes in field names."""
        path = "user_profile.settings-preferences.theme"

        parsed = validate_path(path)

        assert parsed.field_count == 3
