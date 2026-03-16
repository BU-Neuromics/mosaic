"""Tests for FTS table creation functionality."""

import pytest
from hippo.config.models import FieldDefinition, SchemaConfig
from hippo.core.storage.fts import (
    FTSTableMetadata,
    fts_table_exists,
    generate_fts_column_definitions,
    generate_fts_create_sql,
    generate_fts_query,
    generate_fts_phrase_query,
    generate_fts_boolean_query,
    normalize_bm25_score,
)


class TestFieldDefinitionFTS:
    """Tests for FTS field configuration."""

    def test_field_definition_with_fts(self):
        """Test field definition with FTS search option."""
        field = FieldDefinition(
            name="description",
            type="string",
            search="fts5",
        )
        assert field.search == "fts5"
        assert field.name == "description"

    def test_field_definition_fts_validation(self):
        """Test that only valid search values are accepted."""
        with pytest.raises(ValueError):
            FieldDefinition(
                name="test",
                type="string",
                search="invalid",
            )

    def test_schema_config_fts_fields(self):
        """Test schema config FTS field detection."""
        schema = SchemaConfig(
            name="Sample",
            version="1.0",
            fields=[
                FieldDefinition(name="id", type="string", primary_key=True),
                FieldDefinition(name="title", type="string", search="fts5"),
                FieldDefinition(name="description", type="string", search="fts"),
                FieldDefinition(name="count", type="integer"),
            ],
        )

        fts_fields = schema.get_fts_fields()
        assert len(fts_fields) == 2
        assert schema.is_fts_field("title")
        assert schema.is_fts_field("description")
        assert not schema.is_fts_field("count")

    def test_schema_config_fts_field_names(self):
        """Test getting FTS field names."""
        schema = SchemaConfig(
            name="Sample",
            version="1.0",
            fields=[
                FieldDefinition(name="title", type="string", search="fts5"),
                FieldDefinition(name="description", type="string", search="fts"),
            ],
        )

        assert schema.get_fts_field_names() == ["title", "description"]


class TestFTSTableMetadata:
    """Tests for FTS table metadata."""

    def test_generate_table_name(self):
        """Test FTS table name generation."""
        table_name = FTSTableMetadata.generate_table_name("Sample", "title")
        assert table_name == "fts_sample_title"

    def test_from_field(self):
        """Test creating FTS metadata from field definition."""
        field = FieldDefinition(
            name="description",
            type="string",
            search="fts5",
        )
        metadata = FTSTableMetadata.from_field(field, "Sample")

        assert metadata.table_name == "fts_sample_description"
        assert metadata.source_entity_type == "Sample"
        assert metadata.fts_version == "fts5"
        assert len(metadata.fields) == 1

    def test_get_fts_columns(self):
        """Test getting FTS column names."""
        field = FieldDefinition(name="title", type="string", search="fts5")
        metadata = FTSTableMetadata.from_field(field, "Sample")

        assert metadata.get_fts_columns() == ["title"]


class TestFTSColumnDefinitions:
    """Tests for FTS column definitions."""

    def test_generate_fts_column_definitions(self):
        """Test generating FTS column definitions."""
        columns = generate_fts_column_definitions(["title", "description"])
        assert "entity_id" in columns
        assert "title" in columns
        assert "description" in columns

    def test_generate_fts_column_definitions_without_entity_id(self):
        """Test generating FTS columns without entity_id."""
        columns = generate_fts_column_definitions(["title"], include_entity_id=False)
        assert "entity_id" not in columns
        assert "title" in columns


class TestFTSCreateSQL:
    """Tests for FTS create SQL generation."""

    def test_generate_fts_create_sql_basic(self):
        """Test basic FTS table creation SQL."""
        sql = generate_fts_create_sql(
            table_name="fts_sample_title",
            columns=["entity_id", "title"],
        )
        assert "CREATE VIRTUAL TABLE IF NOT EXISTS fts_sample_title" in sql
        assert "USING fts5" in sql

    def test_generate_fts_create_sql_with_content(self):
        """Test FTS table creation with external content."""
        sql = generate_fts_create_sql(
            table_name="fts_sample_title",
            columns=["entity_id", "title"],
            content_table="entities",
            content_rowid="rowid",
        )
        assert "content='entities'" in sql
        assert "content_rowid='rowid'" in sql


class TestFTSQueryGeneration:
    """Tests for FTS query generation."""

    def test_generate_fts_query_basic(self):
        """Test basic FTS query generation."""
        query = generate_fts_query("test")
        assert query == "test"

    def test_generate_fts_query_prefix(self):
        """Test prefix search query generation."""
        query = generate_fts_query("test", prefix_search=True)
        assert query == "test*"

    def test_generate_fts_query_with_field(self):
        """Test field-specific FTS query."""
        query = generate_fts_query("test", field_name="title")
        assert query == "title:test"

    def test_generate_fts_phrase_query(self):
        """Test phrase query generation."""
        query = generate_fts_phrase_query("hello world")
        assert query == '"hello world"'

    def test_generate_fts_boolean_query(self):
        """Test boolean query generation."""
        query = generate_fts_boolean_query(["test", "example"])
        assert query == "test AND example"

    def test_generate_fts_boolean_query_or(self):
        """Test OR boolean query."""
        query = generate_fts_boolean_query(["test", "example"], operator="OR")
        assert query == "test OR example"


class TestBM25ScoreNormalization:
    """Tests for BM25 score normalization."""

    def test_normalize_bm25_zero_score(self):
        """Test normalizing a zero BM25 score."""
        result = normalize_bm25_score(0.0)
        assert 0.0 <= result <= 1.0

    def test_normalize_bm25_negative_score(self):
        """Test normalizing a negative BM25 score."""
        result = normalize_bm25_score(-5.0)
        assert 0.0 <= result <= 1.0

    def test_normalize_bm25_positive_score(self):
        """Test normalizing a positive BM25 score."""
        result = normalize_bm25_score(5.0)
        assert 0.0 <= result <= 1.0

    def test_normalize_bm25_clamping(self):
        """Test that normalized scores are clamped to [0.0, 1.0]."""
        result = normalize_bm25_score(100.0)
        assert result <= 1.0
        result = normalize_bm25_score(-100.0)
        assert result >= 0.0

    def test_normalize_bm25_default_parameters(self):
        """Test normalization with default parameters."""
        result = normalize_bm25_score(0.0, k=0.5, threshold=0.0)
        assert result == 0.5

    def test_normalize_bm25_custom_k(self):
        """Test normalization with custom k parameter."""
        result_low_k = normalize_bm25_score(1.0, k=0.1)
        result_high_k = normalize_bm25_score(1.0, k=10.0)
        assert result_low_k != result_high_k
