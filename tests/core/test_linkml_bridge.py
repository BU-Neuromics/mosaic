"""Parity tests for the LinkML-backed SchemaRegistry."""

from pathlib import Path

import pytest

from hippo.linkml_bridge import (
    HIPPO_SEARCH,
    HIPPO_INDEX,
    HIPPO_INDEX_PARTIAL,
    SchemaRegistry,
)


FIXTURE = Path(__file__).parent.parent / "fixtures" / "schemas" / "sample_schema.yaml"


@pytest.fixture(scope="module")
def registry() -> SchemaRegistry:
    return SchemaRegistry.from_path(FIXTURE)


class TestSchemaIntrospection:
    def test_class_names_includes_defined_classes(self, registry: SchemaRegistry):
        names = set(registry.class_names())
        assert {"Entity", "Project", "Sample"}.issubset(names)

    def test_identifier_slot_resolves_through_inheritance(
        self, registry: SchemaRegistry
    ):
        ident = registry.identifier_slot("Sample")
        assert ident is not None
        assert ident.name == "id"

    def test_induced_slots_include_inherited_id(self, registry: SchemaRegistry):
        slot_names = {s.name for s in registry.induced_slots("Sample")}
        assert "id" in slot_names
        assert "name" in slot_names
        assert "project_id" in slot_names

    def test_required_slots(self, registry: SchemaRegistry):
        required = {s.name for s in registry.required_slots("Sample")}
        assert "id" in required
        assert "name" in required
        assert "volume_ml" not in required


class TestHippoAnnotations:
    def test_searchable_slots_reads_hippo_search_annotation(
        self, registry: SchemaRegistry
    ):
        searchable = registry.searchable_slots("Sample")
        by_name = {slot.name: mode for slot, mode in searchable}
        assert by_name == {"name": "fts5"}

    def test_indexed_slots_distinguishes_partial(self, registry: SchemaRegistry):
        indexed = {slot.name: partial for slot, partial in registry.indexed_slots("Sample")}
        assert indexed == {"project_id": False, "collected_at": True}

    def test_project_has_two_searchable_slots(self, registry: SchemaRegistry):
        searchable = {slot.name for slot, _ in registry.searchable_slots("Project")}
        assert searchable == {"name", "description"}


class TestReferenceSlots:
    def test_reference_slot_points_to_class_range(self, registry: SchemaRegistry):
        refs = registry.reference_slots("Sample")
        assert ("project_id", "Project") in refs

    def test_non_class_ranges_not_returned_as_references(
        self, registry: SchemaRegistry
    ):
        refs = dict(registry.reference_slots("Sample"))
        assert "name" not in refs
        assert "volume_ml" not in refs
        assert "status" not in refs  # enum, not class


class TestValidation:
    def test_valid_instance_passes(self, registry: SchemaRegistry):
        errors = registry.validate(
            {"id": "s1", "name": "tissue A"}, "Sample"
        )
        assert errors == []

    def test_missing_required_field_rejected(self, registry: SchemaRegistry):
        errors = registry.validate({"id": "s1"}, "Sample")
        assert len(errors) == 1
        assert "'name'" in errors[0]
        assert "required" in errors[0]

    def test_wrong_type_rejected(self, registry: SchemaRegistry):
        errors = registry.validate(
            {"id": "s1", "name": "ok", "volume_ml": "not-a-number"}, "Sample"
        )
        assert any("not of type" in e for e in errors)

    def test_bad_enum_value_rejected(self, registry: SchemaRegistry):
        errors = registry.validate(
            {"id": "s1", "name": "ok", "status": "bogus"}, "Sample"
        )
        assert any("not one of" in e for e in errors)
        assert any("active" in e for e in errors)

    def test_closed_schema_rejects_extra_fields(self, registry: SchemaRegistry):
        errors = registry.validate(
            {"id": "s1", "name": "ok", "nope": 1}, "Sample"
        )
        assert any("Additional properties" in e for e in errors)


class TestLoaders:
    def test_from_dict_matches_from_path(self):
        import yaml

        path_reg = SchemaRegistry.from_path(FIXTURE)
        data = yaml.safe_load(FIXTURE.read_text())
        dict_reg = SchemaRegistry.from_dict(data)
        assert set(path_reg.class_names()) == set(dict_reg.class_names())

    def test_from_yaml_string(self):
        yaml_text = FIXTURE.read_text()
        reg = SchemaRegistry.from_yaml(yaml_text)
        assert "Sample" in reg.class_names()


class TestAnnotationConstants:
    def test_annotation_keys_use_flat_hippo_prefix(self):
        assert HIPPO_SEARCH == "hippo_search"
        assert HIPPO_INDEX == "hippo_index"
        assert HIPPO_INDEX_PARTIAL == "hippo_index_partial"
