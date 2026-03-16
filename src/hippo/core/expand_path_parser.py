"""Expand path parser for parsing dot-notation field expansion paths.

This module provides parsing and validation for expand paths used in the Hippo SDK
to efficiently fetch related entities. Expand paths use dot notation (e.g., "user.profile.settings")
to specify which related entities should be fetched alongside the primary entity.

Example:
    >>> from hippo.core.expand_path_parser import ExpandPathParser
    >>> parser = ExpandPathParser()
    >>> result = parser.parse("user.profile.settings")
    >>> print(result.root.field_names)
    ['user', 'profile', 'settings']
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class PathNode:
    """Represents a node in the parsed expand path AST.

    Each node corresponds to a field in the expansion path, with parent-child
    relationships tracked to represent the nested structure.
    """

    name: str
    parent: Optional["PathNode"] = None
    children: list["PathNode"] = field(default_factory=list)
    depth: int = 0
    field_names: list[str] = field(default_factory=list)

    def add_child(self, child: "PathNode") -> None:
        """Add a child node to this node.

        Args:
            child: The child PathNode to add.
        """
        child.parent = self
        child.depth = self.depth + 1
        self.children.append(child)

    def get_full_path(self) -> str:
        """Get the full path from root to this node.

        Returns:
            Dot-notation path string (e.g., "user.profile.settings").
        """
        if self.parent is None:
            return self.name
        return f"{self.parent.get_full_path()}.{self.name}"

    def get_all_field_names(self) -> list[str]:
        """Get all unique field names in the path tree.

        Returns:
            List of all field names in the expansion path.
        """
        names = [self.name]
        for child in self.children:
            names.extend(child.get_all_field_names())
        return names

    def to_dict(self) -> dict[str, Any]:
        """Convert the node to a dictionary representation.

        Returns:
            Dictionary representation of the path node.
        """
        return {
            "name": self.name,
            "depth": self.depth,
            "children": [child.to_dict() for child in self.children],
        }


@dataclass
class ParseResult:
    """Result of parsing an expand path.

    Contains the parsed AST and any metadata about the parse operation.
    """

    root: PathNode
    raw_path: str
    field_count: int
    max_depth: int

    def to_dict(self) -> dict[str, Any]:
        """Convert the result to a dictionary.

        Returns:
            Dictionary representation of the parse result.
        """
        return {
            "root": self.root.to_dict(),
            "raw_path": self.raw_path,
            "field_count": self.field_count,
            "max_depth": self.max_depth,
        }


class ParsingError(Exception):
    """Exception raised when expand path parsing fails.

    Provides descriptive error messages indicating the location and nature
    of parsing errors.
    """

    def __init__(
        self,
        message: str,
        path: Optional[str] = None,
        position: Optional[int] = None,
    ):
        self.message = message
        self.path = path
        self.position = position

        if path and position is not None:
            full_message = f"{message} at position {position} in path '{path}'"
        elif path:
            full_message = f"{message} in path '{path}'"
        else:
            full_message = message

        super().__init__(full_message)


class MaxSizeExceededError(Exception):
    """Exception raised when expand path exceeds maximum allowed size.

    Provides information about the size limit and actual size.
    """

    def __init__(
        self,
        message: str,
        limit: int,
        actual_size: int,
    ):
        self.message = message
        self.limit = limit
        self.actual_size = actual_size

        full_message = f"{message} (limit: {limit}, actual: {actual_size})"
        super().__init__(full_message)


class CycleDetectionError(Exception):
    """Exception raised when a circular reference is detected in the expand path.

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


@dataclass
class ParserConfig:
    """Configuration for the expand path parser.

    Attributes:
        max_size: Maximum allowed length of the expand path string (default: 100).
        max_depth: Maximum allowed depth of nested fields (default: 5).
    """

    max_size: int = 100
    max_depth: int = 5


class Token:
    """Represents a token in the expand path."""

    DOT = "DOT"
    IDENTIFIER = "IDENTIFIER"
    EOF = "EOF"

    def __init__(self, type: str, value: str, position: int):
        self.type = type
        self.value = value
        self.position = position

    def __repr__(self) -> str:
        return f"Token({self.type}, '{self.value}', {self.position})"


class Tokenizer:
    """Tokenizes an expand path string into tokens for parsing."""

    def __init__(self, path: str):
        self.path = path
        self.position = 0
        self.tokens: list[Token] = []

    def tokenize(self) -> list[Token]:
        """Tokenize the expand path string.

        Returns:
            List of tokens.

        Raises:
            ParsingError: If invalid characters are found.
        """
        while self.position < len(self.path):
            char = self.path[self.position]

            if char == ".":
                self.tokens.append(Token(Token.DOT, ".", self.position))
                self.position += 1
            elif char.isalnum() or char in ("_", "-"):
                identifier = self._read_identifier()
                self.tokens.append(Token(Token.IDENTIFIER, identifier, self.position))
            elif char.isspace():
                self.position += 1
            else:
                raise ParsingError(
                    message=f"Invalid character: '{char}'",
                    path=self.path,
                    position=self.position,
                )

        self.tokens.append(Token(Token.EOF, "", self.position))
        return self.tokens

    def _read_identifier(self) -> str:
        """Read an identifier token.

        Returns:
            The identifier string.
        """
        start = self.position
        while self.position < len(self.path):
            char = self.path[self.position]
            if char.isalnum() or char in ("_", "-"):
                self.position += 1
            else:
                break
        return self.path[start : self.position]


class ExpandPathParser:
    """Recursive descent parser for expand path strings.

    Parses dot-notation expand paths (e.g., "user.profile.settings") into
    a tree structure for efficient fetching of related entities.

    Example:
        >>> parser = ExpandPathParser()
        >>> result = parser.parse("user.orders.items.product")
        >>> print(result.root.get_full_path())
        user.orders.items.product
    """

    def __init__(self, config: Optional[ParserConfig] = None):
        """Initialize the parser with optional configuration.

        Args:
            config: Parser configuration. Uses defaults if not provided.
        """
        self.config = config or ParserConfig()

    def parse(self, path: str) -> ParseResult:
        """Parse an expand path string.

        Args:
            path: The expand path to parse (e.g., "user.profile.settings").

        Returns:
            ParseResult containing the parsed path tree.

        Raises:
            ParsingError: If the path is malformed.
            MaxSizeExceededError: If the path exceeds maximum size.
        """
        if not path:
            raise ParsingError(message="Expand path cannot be empty", path=path)

        actual_size = len(path)
        if actual_size > self.config.max_size:
            raise MaxSizeExceededError(
                message="Expand path exceeds maximum allowed size",
                limit=self.config.max_size,
                actual_size=actual_size,
            )

        tokens = Tokenizer(path).tokenize()
        self._tokens = tokens
        self._current = 0

        root = self._parse_path()

        field_names = root.get_all_field_names()
        max_depth = self._calculate_max_depth(root)

        if max_depth > self.config.max_depth:
            raise ParsingError(
                message=f"Path depth exceeds maximum allowed depth of {self.config.max_depth}",
                path=path,
            )

        return ParseResult(
            root=root,
            raw_path=path,
            field_count=len(field_names),
            max_depth=max_depth,
        )

    def _parse_path(self) -> PathNode:
        """Parse the path starting from current token.

        Returns:
            Root PathNode of the parsed path.

        Raises:
            ParsingError: If the path syntax is invalid.
        """
        root = PathNode(name=self._current_token().value)
        root.field_names.append(self._current_token().value)
        self._advance()

        current = root  # track deepest node so we build a chain, not a flat list
        while self._current_token().type != Token.EOF:
            self._expect(Token.DOT)
            self._advance()

            if self._current_token().type == Token.DOT:
                raise ParsingError(
                    message="Empty segment in path (consecutive dots)",
                    path=self._tokens[0].value if self._tokens else "",
                )

            if self._current_token().type == Token.EOF:
                raise ParsingError(
                    message="Path cannot end with a dot",
                    path=self._tokens[0].value if self._tokens else "",
                )

            child_name = self._current_token().value
            child = PathNode(name=child_name)
            current.add_child(child)
            root.field_names.append(child_name)
            current = child  # advance pointer so next segment becomes child of this one
            self._advance()

        return root

    def _calculate_max_depth(self, node: PathNode) -> int:
        """Calculate the maximum depth of the path tree.

        Args:
            node: The root node of the path tree.

        Returns:
            Maximum depth value.
        """
        if not node.children:
            return node.depth

        return max(self._calculate_max_depth(child) for child in node.children)

    def _current_token(self) -> Token:
        """Get the current token.

        Returns:
            The current token.
        """
        if self._current >= len(self._tokens):
            return self._tokens[-1]
        return self._tokens[self._current]

    def _advance(self) -> Token:
        """Advance to the next token.

        Returns:
            The token that was passed.
        """
        if self._current < len(self._tokens) - 1:
            self._current += 1
        return self._tokens[self._current]

    def _expect(self, token_type: str) -> None:
        """Expect a specific token type.

        Args:
            token_type: The expected token type.

        Raises:
            ParsingError: If the token type doesn't match.
        """
        token = self._current_token()
        if token.type != token_type:
            raise ParsingError(
                message=f"Expected {token_type}, got {token.type}",
                path=self._tokens[0].value if self._tokens else "",
                position=token.position,
            )


def validate_path(path: str, config: Optional[ParserConfig] = None) -> ParseResult:
    """Validate and parse an expand path.

    This is a convenience function that creates a parser and validates the path.

    Args:
        path: The expand path to validate.
        config: Optional parser configuration.

    Returns:
        ParseResult containing the parsed path tree.

    Raises:
        ParsingError: If the path is malformed.
        MaxSizeExceededError: If the path exceeds maximum size.
    """
    parser = ExpandPathParser(config)
    return parser.parse(path)
