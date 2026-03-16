"""Unit tests for expand path parser."""

import pytest

from hippo.core.expand_path_parser import (
    ExpandPathParser,
    MaxSizeExceededError,
    ParserConfig,
    ParseResult,
    ParsingError,
    PathNode,
    Token,
    Tokenizer,
    validate_path,
)


class TestTokenizer:
    """Tests for the Tokenizer class."""

    def test_tokenize_simple_path(self):
        """Test tokenizing a simple expand path."""
        tokenizer = Tokenizer("user.profile")
        tokens = tokenizer.tokenize()

        assert len(tokens) == 4
        assert tokens[0].type == Token.IDENTIFIER
        assert tokens[0].value == "user"
        assert tokens[1].type == Token.DOT
        assert tokens[2].type == Token.IDENTIFIER
        assert tokens[2].value == "profile"
        assert tokens[3].type == Token.EOF

    def test_tokenize_complex_path(self):
        """Test tokenizing a complex nested path."""
        tokenizer = Tokenizer("user.orders.items.product")
        tokens = tokenizer.tokenize()

        assert len(tokens) == 8
        identifiers = [t.value for t in tokens if t.type == Token.IDENTIFIER]
        assert identifiers == ["user", "orders", "items", "product"]

    def test_tokenize_invalid_character(self):
        """Test tokenizing a path with invalid characters."""
        tokenizer = Tokenizer("user@profile")
        with pytest.raises(ParsingError) as exc_info:
            tokenizer.tokenize()
        assert "Invalid character" in str(exc_info.value)


class TestExpandPathParser:
    """Tests for the ExpandPathParser class."""

    def test_parse_simple_path(self):
        """Test parsing a simple expand path."""
        parser = ExpandPathParser()
        result = parser.parse("user.profile")

        assert isinstance(result, ParseResult)
        assert result.raw_path == "user.profile"
        assert result.field_count == 2
        assert result.max_depth == 1

    def test_parse_complex_path(self):
        """Test parsing a complex nested path."""
        parser = ExpandPathParser()
        result = parser.parse("user.orders.items.product")

        assert result.field_count == 4
        assert result.max_depth == 3

    def test_parse_empty_path(self):
        """Test parsing an empty path raises error."""
        parser = ExpandPathParser()
        with pytest.raises(ParsingError) as exc_info:
            parser.parse("")
        assert "cannot be empty" in str(exc_info.value)

    def test_parse_malformed_path_double_dot(self):
        """Test parsing a path with consecutive dots raises error."""
        parser = ExpandPathParser()
        with pytest.raises(ParsingError) as exc_info:
            parser.parse("user..profile")
        assert "Empty segment" in str(exc_info.value)

    def test_parse_path_ending_with_dot(self):
        """Test parsing a path ending with a dot raises error."""
        parser = ExpandPathParser()
        with pytest.raises(ParsingError) as exc_info:
            parser.parse("user.profile.")
        assert "cannot end with a dot" in str(exc_info.value)

    def test_parse_with_custom_max_size(self):
        """Test parsing with custom max size configuration."""
        config = ParserConfig(max_size=50)
        parser = ExpandPathParser(config)

        result = parser.parse("user.profile.settings")
        assert result.field_count == 3

    def test_parse_exceeds_max_size(self):
        """Test parsing a path that exceeds max size raises error."""
        config = ParserConfig(max_size=10)
        parser = ExpandPathParser(config)

        with pytest.raises(MaxSizeExceededError) as exc_info:
            parser.parse("user.profile.settings")
        assert exc_info.value.limit == 10
        assert exc_info.value.actual_size > 10

    def test_parse_exactly_max_size(self):
        """Test parsing a path at exactly max size succeeds."""
        path = "1234567890"
        config = ParserConfig(max_size=len(path))
        parser = ExpandPathParser(config)

        result = parser.parse(path)
        assert result.field_count == 1

    def test_parse_with_custom_max_depth(self):
        """Test parsing with custom max depth configuration."""
        config = ParserConfig(max_depth=5)
        parser = ExpandPathParser(config)

        result = parser.parse("a.b.c.d")
        assert result.max_depth == 3

    def test_parse_exceeds_max_depth(self):
        """Test parsing a path that exceeds max depth raises error."""
        config = ParserConfig(max_depth=2)
        parser = ExpandPathParser(config)

        with pytest.raises(ParsingError) as exc_info:
            parser.parse("a.b.c.d")
        assert "depth exceeds maximum" in str(exc_info.value)


class TestPathNode:
    """Tests for the PathNode class."""

    def test_add_child(self):
        """Test adding a child node."""
        parent = PathNode(name="user")
        child = PathNode(name="profile")

        parent.add_child(child)

        assert child.parent == parent
        assert child.depth == 1
        assert len(parent.children) == 1

    def test_get_full_path(self):
        """Test getting the full path from root to node."""
        root = PathNode(name="user")
        orders = PathNode(name="orders")
        items = PathNode(name="items")

        root.add_child(orders)
        orders.add_child(items)

        assert root.get_full_path() == "user"
        assert orders.get_full_path() == "user.orders"
        assert items.get_full_path() == "user.orders.items"

    def test_get_all_field_names(self):
        """Test getting all field names in the path tree."""
        root = PathNode(name="user")
        profile = PathNode(name="profile")
        settings = PathNode(name="settings")

        root.add_child(profile)
        profile.add_child(settings)

        names = root.get_all_field_names()
        assert names == ["user", "profile", "settings"]

    def test_to_dict(self):
        """Test converting node to dictionary."""
        root = PathNode(name="user")
        child = PathNode(name="profile")
        root.add_child(child)

        result = root.to_dict()
        assert result["name"] == "user"
        assert len(result["children"]) == 1
        assert result["children"][0]["name"] == "profile"


class TestValidatePath:
    """Tests for the validate_path convenience function."""

    def test_validate_path_success(self):
        """Test validating a valid path."""
        result = validate_path("user.profile")
        assert isinstance(result, ParseResult)
        assert result.field_count == 2

    def test_validate_path_raises_parsing_error(self):
        """Test that validate_path raises ParsingError for invalid paths."""
        with pytest.raises(ParsingError):
            validate_path("user..profile")

    def test_validate_path_raises_max_size_error(self):
        """Test that validate_path raises MaxSizeExceededError for long paths."""
        with pytest.raises(MaxSizeExceededError):
            validate_path("a" * 200, ParserConfig(max_size=100))


class TestParseResult:
    """Tests for the ParseResult class."""

    def test_to_dict(self):
        """Test converting parse result to dictionary."""
        root = PathNode(name="user")
        result = ParseResult(
            root=root,
            raw_path="user",
            field_count=1,
            max_depth=0,
        )

        result_dict = result.to_dict()
        assert result_dict["raw_path"] == "user"
        assert result_dict["field_count"] == 1
        assert "root" in result_dict
