"""Tests for FTS table creation helpers."""

import pytest

from hippo.core.storage.fts import (
    FTSTableMetadata,
    generate_fts_boolean_query,
    generate_fts_column_definitions,
    generate_fts_create_sql,
    generate_fts_phrase_query,
    generate_fts_query,
    normalize_bm25_score,
)


class TestFTSTableMetadata:
    def test_generate_table_name(self):
        assert FTSTableMetadata.generate_table_name("Sample", "title") == (
            "fts_sample_title"
        )

    def test_get_fts_columns(self):
        from hippo.core.storage.fts import FTSFieldMetadata

        meta = FTSTableMetadata(
            table_name="fts_sample_title",
            source_entity_type="Sample",
            fts_version="fts5",
            content_table="entities",
            content_rowid="rowid",
            fields=[
                FTSFieldMetadata(
                    field_name="title",
                    field_type="string",
                    search_type="fts5",
                    source_entity_type="Sample",
                )
            ],
        )
        assert meta.get_fts_columns() == ["title"]


class TestFTSColumnDefinitions:
    def test_generate_fts_column_definitions(self):
        columns = generate_fts_column_definitions(["title", "description"])
        assert "entity_id" in columns
        assert "title" in columns
        assert "description" in columns

    def test_generate_fts_column_definitions_without_entity_id(self):
        columns = generate_fts_column_definitions(["title"], include_entity_id=False)
        assert "entity_id" not in columns
        assert "title" in columns


class TestFTSCreateSQL:
    def test_basic(self):
        sql = generate_fts_create_sql(
            table_name="fts_sample_title", columns=["entity_id", "title"]
        )
        assert "CREATE VIRTUAL TABLE IF NOT EXISTS fts_sample_title" in sql
        assert "USING fts5" in sql

    def test_with_external_content(self):
        sql = generate_fts_create_sql(
            table_name="fts_sample_title",
            columns=["entity_id", "title"],
            content_table="entities",
            content_rowid="rowid",
        )
        assert "content='entities'" in sql
        assert "content_rowid='rowid'" in sql


class TestFTSQueryGeneration:
    def test_basic(self):
        assert generate_fts_query("test") == "test"

    def test_prefix(self):
        assert generate_fts_query("test", prefix_search=True) == "test*"

    def test_with_field(self):
        assert generate_fts_query("test", field_name="title") == "title:test"

    def test_phrase(self):
        assert generate_fts_phrase_query("hello world") == '"hello world"'

    def test_boolean_and(self):
        assert generate_fts_boolean_query(["test", "example"]) == "test AND example"

    def test_boolean_or(self):
        assert (
            generate_fts_boolean_query(["test", "example"], operator="OR")
            == "test OR example"
        )


class TestBM25ScoreNormalization:
    def test_zero_score(self):
        assert 0.0 <= normalize_bm25_score(0.0) <= 1.0

    def test_negative_score(self):
        assert 0.0 <= normalize_bm25_score(-5.0) <= 1.0

    def test_positive_score(self):
        assert 0.0 <= normalize_bm25_score(5.0) <= 1.0

    def test_clamping(self):
        assert normalize_bm25_score(100.0) <= 1.0
        assert normalize_bm25_score(-100.0) >= 0.0

    def test_default_parameters(self):
        assert normalize_bm25_score(0.0, k=0.5, threshold=0.0) == 0.5

    def test_custom_k(self):
        assert normalize_bm25_score(1.0, k=0.1) != normalize_bm25_score(1.0, k=10.0)
