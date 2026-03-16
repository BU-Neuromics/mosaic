"""Unit tests for cycle detector."""

import pytest

from hippo.core.cycle_detector import (
    AdjacencyGraph,
    CycleDetectionError,
    CycleDetectionResult,
    CycleDetector,
    detect_cycle,
    validate_no_cycle,
)
from hippo.core.expand_path_parser import ExpandPathParser, ParseResult, PathNode


class TestAdjacencyGraph:
    """Tests for the AdjacencyGraph class."""

    def test_build_simple_graph(self):
        """Test building an adjacency graph from a simple path."""
        root = PathNode(name="user")
        profile = PathNode(name="profile")
        root.add_child(profile)

        graph = AdjacencyGraph(root)

        assert "user" in graph.nodes
        assert "user.profile" in graph.nodes
        assert graph.get_neighbors("user") == ["user.profile"]
        assert graph.get_neighbors("user.profile") == []

    def test_build_complex_graph(self):
        """Test building an adjacency graph from a complex path."""
        parser = ExpandPathParser()
        result = parser.parse("user.orders.items.product")

        graph = AdjacencyGraph(result.root)

        nodes = graph.get_all_nodes()
        assert "user" in nodes
        assert "user.orders" in nodes
        assert "user.orders.items" in nodes
        assert "user.orders.items.product" in nodes

    def test_get_neighbors(self):
        """Test getting neighbors of a node."""
        root = PathNode(name="a")
        b = PathNode(name="b")
        c = PathNode(name="c")
        root.add_child(b)
        root.add_child(c)

        graph = AdjacencyGraph(root)

        neighbors = graph.get_neighbors("a")
        assert "a.b" in neighbors
        assert "a.c" in neighbors


class TestCycleDetector:
    """Tests for the CycleDetector class."""

    def test_detect_no_cycle_simple_path(self):
        """Test detecting no cycle in a simple path."""
        parser = ExpandPathParser()
        result = parser.parse("user.profile.settings")

        detector = CycleDetector()
        detection_result = detector.detect(result)

        assert not detection_result.has_cycle
        assert detection_result.cycle_path == []
        assert "No cycles detected" in detection_result.message

    def test_detect_no_cycle_complex_path(self):
        """Test detecting no cycle in a complex nested path."""
        parser = ExpandPathParser()
        result = parser.parse("user.orders.items.product.category")

        detector = CycleDetector()
        detection_result = detector.detect(result)

        assert not detection_result.has_cycle

    def test_validate_no_cycle_raises_error(self):
        """Test that validate_no_cycle raises error for paths with cycles."""
        root = PathNode(name="user")
        orders = PathNode(name="orders")
        items = PathNode(name="items")
        user = PathNode(name="user")

        root.add_child(orders)
        orders.add_child(items)
        items.add_child(user)

        result = ParseResult(
            root=root,
            raw_path="user.orders.items.user",
            field_count=4,
            max_depth=3,
        )

        detector = CycleDetector()
        with pytest.raises(CycleDetectionError) as exc_info:
            detector.validate(result)

        assert "Circular reference" in str(exc_info.value)


class TestDetectCycle:
    """Tests for the detect_cycle convenience function."""

    def test_detect_cycle_function(self):
        """Test the detect_cycle convenience function."""
        parser = ExpandPathParser()
        result = parser.parse("user.profile")

        detection_result = detect_cycle(result)

        assert isinstance(detection_result, CycleDetectionResult)
        assert not detection_result.has_cycle


class TestValidateNoCycle:
    """Tests for the validate_no_cycle convenience function."""

    def test_validate_no_cycle_function(self):
        """Test the validate_no_cycle convenience function."""
        parser = ExpandPathParser()
        result = parser.parse("user.profile")

        validate_no_cycle(result)


class TestCycleDetectionResult:
    """Tests for the CycleDetectionResult class."""

    def test_to_dict(self):
        """Test converting cycle detection result to dictionary."""
        result = CycleDetectionResult(
            has_cycle=True,
            cycle_path=["a", "b", "c"],
            message="Cycle detected: a -> b -> c",
        )

        result_dict = result.to_dict()

        assert result_dict["has_cycle"] is True
        assert result_dict["cycle_path"] == ["a", "b", "c"]
        assert result_dict["message"] == "Cycle detected: a -> b -> c"


class TestCycleDetectionError:
    """Tests for the CycleDetectionError exception."""

    def test_error_without_cycle_path(self):
        """Test creating error without cycle path."""
        error = CycleDetectionError(message="Cycle detected")
        assert "Cycle detected" in str(error)
        assert error.cycle_path == []

    def test_error_with_cycle_path(self):
        """Test creating error with cycle path."""
        error = CycleDetectionError(
            message="Cycle detected",
            cycle_path=["user", "orders", "items", "user"],
        )
        assert "Cycle detected" in str(error)
        assert "user -> orders -> items -> user" in str(error)
