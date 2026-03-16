"""Cycle detection for expand path validation.

This module provides cycle detection functionality to prevent infinite loops
when traversing related entities through expand paths. It uses a graph-based
approach to detect circular references in the path structure.

Example:
    >>> from hippo.core.cycle_detector import CycleDetector
    >>> from hippo.core.expand_path_parser import ExpandPathParser
    >>> parser = ExpandPathParser()
    >>> parsed = parser.parse("user.orders.items.product")
    >>> detector = CycleDetector()
    >>> result = detector.detect(parsed)
    >>> print(result.has_cycle)
    False
"""

from dataclasses import dataclass
from typing import Any, Optional

from hippo.core.expand_path_parser import ParseResult, PathNode


@dataclass
class CycleDetectionResult:
    """Result of cycle detection analysis.

    Attributes:
        has_cycle: Whether a cycle was detected.
        cycle_path: List of node names forming the cycle, if detected.
        message: Human-readable message describing the result.
    """

    has_cycle: bool
    cycle_path: list[str]
    message: str

    def to_dict(self) -> dict[str, Any]:
        """Convert the result to a dictionary.

        Returns:
            Dictionary representation of the cycle detection result.
        """
        return {
            "has_cycle": self.has_cycle,
            "cycle_path": self.cycle_path,
            "message": self.message,
        }


class CycleDetectionError(Exception):
    """Exception raised when a cycle is detected in an expand path.

    Provides the cycle path in the error message for debugging purposes.
    """

    def __init__(
        self,
        message: str,
        cycle_path: Optional[list[str]] = None,
    ):
        self.message = message
        self.cycle_path = cycle_path or []

        if cycle_path:
            cycle_str = " -> ".join(cycle_path)
            full_message = f"{message} (cycle: {cycle_str})"
        else:
            full_message = message

        super().__init__(full_message)


class AdjacencyGraph:
    """Adjacency graph representation of a parsed expand path.

    Builds a directed graph from the path tree where each node can reference
    its children, enabling cycle detection through graph traversal.
    """

    def __init__(self, root: PathNode):
        """Initialize the adjacency graph from a parsed path.

        Args:
            root: The root PathNode of the parsed expand path.
        """
        self.root = root
        self.nodes: dict[str, list[str]] = {}
        self._build_graph(root)

    def _build_graph(self, node: PathNode) -> None:
        """Recursively build the adjacency list representation.

        Args:
            node: The current node in the path tree.
        """
        path = node.get_full_path()
        self.nodes[path] = []

        for child in node.children:
            child_path = child.get_full_path()
            self.nodes[path].append(child_path)
            self._build_graph(child)

    def get_neighbors(self, node_path: str) -> list[str]:
        """Get all neighbors (children) of a node.

        Args:
            node_path: The full path of the node.

        Returns:
            List of neighbor paths.
        """
        return self.nodes.get(node_path, [])

    def get_all_nodes(self) -> list[str]:
        """Get all nodes in the graph.

        Returns:
            List of all node paths.
        """
        return list(self.nodes.keys())


class CycleDetector:
    """Detects cycles in expand paths using DFS-based graph traversal.

    This detector builds an adjacency graph from the parsed expand path
    and uses depth-first search to identify circular references.

    Example:
        >>> from hippo.core.expand_path_parser import ExpandPathParser
        >>> parser = ExpandPathParser()
        >>> parsed = parser.parse("user.orders.items.user")
        >>> detector = CycleDetector()
        >>> result = detector.detect(parsed)
        >>> print(result.has_cycle)
        True
    """

    def __init__(self):
        """Initialize the cycle detector."""
        self._visited: set[str] = set()
        self._recursion_stack: set[str] = set()
        self._cycle_path: list[str] = []

    def detect(self, parsed_result: ParseResult) -> CycleDetectionResult:
        """Detect cycles in the parsed expand path.

        A cycle is defined as the same field *name* appearing more than once
        anywhere along the root-to-leaf path — meaning the expansion would
        loop back to an entity type already being traversed.

        Args:
            parsed_result: The parsed expand path result.

        Returns:
            CycleDetectionResult indicating whether a cycle was found.
        """
        cycle_path = self._find_name_cycle(parsed_result.root, [])
        if cycle_path:
            cycle_str = " -> ".join(cycle_path)
            return CycleDetectionResult(
                has_cycle=True,
                cycle_path=cycle_path,
                message=f"Cycle detected: {cycle_str}",
            )

        return CycleDetectionResult(
            has_cycle=False,
            cycle_path=[],
            message="No cycles detected",
        )

    def _find_name_cycle(
        self, node: "PathNode", ancestors: list[str]
    ) -> list[str]:
        """Recursively walk the path tree looking for repeated names.

        Returns the cycle path (list of names) if one is found, else [].
        """
        current_path = ancestors + [node.name]
        if node.name in ancestors:
            return current_path
        for child in node.children:
            result = self._find_name_cycle(child, current_path)
            if result:
                return result
        return []

    def _dfs(self, node_path: str, graph: AdjacencyGraph) -> bool:
        """Perform DFS to detect cycles.

        Args:
            node_path: The current node path.
            graph: The adjacency graph.

        Returns:
            True if a cycle is detected, False otherwise.
        """
        self._visited.add(node_path)
        self._recursion_stack.add(node_path)
        self._cycle_path.append(node_path)

        for neighbor in graph.get_neighbors(node_path):
            if neighbor not in self._visited:
                if self._dfs(neighbor, graph):
                    return True
            elif neighbor in self._recursion_stack:
                self._cycle_path.append(neighbor)
                return True

        self._recursion_stack.remove(node_path)
        if len(self._cycle_path) > 0 and self._cycle_path[-1] == node_path:
            self._cycle_path.pop()

        return False

    def validate(self, parsed_result: ParseResult) -> None:
        """Validate the parsed path and raise an exception if a cycle is found.

        Args:
            parsed_result: The parsed expand path result.

        Raises:
            CycleDetectionError: If a cycle is detected in the path.
        """
        result = self.detect(parsed_result)

        if result.has_cycle:
            raise CycleDetectionError(
                message="Circular reference detected in expand path",
                cycle_path=result.cycle_path,
            )


def detect_cycle(parsed_result: ParseResult) -> CycleDetectionResult:
    """Convenience function to detect cycles in a parsed expand path.

    Args:
        parsed_result: The parsed expand path result.

    Returns:
        CycleDetectionResult indicating whether a cycle was found.
    """
    detector = CycleDetector()
    return detector.detect(parsed_result)


def validate_no_cycle(parsed_result: ParseResult) -> None:
    """Convenience function to validate no cycles exist in the parsed path.

    Args:
        parsed_result: The parsed expand path result.

    Raises:
        CycleDetectionError: If a cycle is detected in the path.
    """
    detector = CycleDetector()
    detector.validate(parsed_result)
