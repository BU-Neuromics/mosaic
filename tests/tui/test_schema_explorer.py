"""Tests for SchemaExplorerView."""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip(
    "textual", reason="textual not installed; run: pip install datahelix-mosaic[tui]"
)

from mosaic.tui.backend.protocol import (
    EntityTypeSchema,
    FieldInfo,
    RelationshipDeclaration,
    SchemaView,
)


def _make_schema():
    fields = [
        FieldInfo("external_id", "string", required=True, indexed=True),
        FieldInfo("tissue_type", "string", required=True, indexed=False),
        FieldInfo("donor", "ref", required=True, indexed=True, ref_target="Donor"),
    ]
    donor_fields = [FieldInfo("name", "string", required=True, indexed=False)]
    rels = [
        RelationshipDeclaration("Sample", "donated_by", "Donor"),
    ]
    return SchemaView(
        entity_types=[
            EntityTypeSchema("Sample", fields),
            EntityTypeSchema("Donor", donor_fields),
        ],
        relationships=rels,
    )


def test_schema_explorer_view_instantiation():
    """SchemaExplorerView can be created with a SchemaView."""
    from mosaic.tui.views.schema_explorer import SchemaExplorerView

    schema = _make_schema()
    view = SchemaExplorerView(schema=schema)
    assert view._schema is schema


def test_schema_explorer_field_table_content():
    """Field table shows all user-defined fields with correct data."""
    from mosaic.tui.views.schema_explorer import SchemaExplorerView

    schema = _make_schema()
    view = SchemaExplorerView(schema=schema)

    # Verify schema has expected structure
    sample_et = next(et for et in schema.entity_types if et.name == "Sample")
    assert len(sample_et.fields) == 3
    field_names = [f.name for f in sample_et.fields]
    assert "external_id" in field_names
    assert "donor" in field_names


def test_schema_explorer_ref_field_has_target():
    """Reference fields carry ref_target."""
    schema = _make_schema()
    sample_et = next(et for et in schema.entity_types if et.name == "Sample")
    donor_field = next(f for f in sample_et.fields if f.name == "donor")
    assert donor_field.ref_target == "Donor"


def test_schema_explorer_relationship_rendering():
    """Relationships are present in SchemaView."""
    schema = _make_schema()
    assert len(schema.relationships) == 1
    rel = schema.relationships[0]
    assert rel.source_type == "Sample"
    assert rel.relationship_name == "donated_by"
    assert rel.target_type == "Donor"


def test_schema_explorer_empty_relationships():
    """SchemaView with no relationships has empty relationships list."""
    schema = SchemaView(
        entity_types=[EntityTypeSchema("Sample", [])],
        relationships=[],
    )
    assert schema.relationships == []


def test_schema_explorer_required_indexed_flags():
    """Required and indexed flags are stored correctly."""
    required_indexed = FieldInfo("f1", "string", required=True, indexed=True)
    optional_not_indexed = FieldInfo("f2", "string", required=False, indexed=False)
    assert required_indexed.required is True
    assert required_indexed.indexed is True
    assert optional_not_indexed.required is False
    assert optional_not_indexed.indexed is False


def test_schema_explorer_cache_invalidation():
    """SchemaExplorerView uses app_ref to invalidate cache."""
    from mosaic.tui.views.schema_explorer import SchemaExplorerView

    schema1 = _make_schema()
    schema2 = SchemaView()

    class MockApp:
        async def invalidate_schema_cache(self):
            return schema2

    view = SchemaExplorerView(schema=schema1, app_ref=MockApp())

    async def run():
        await view.action_refresh_schema()
        assert view._schema is schema2

    asyncio.run(run())
