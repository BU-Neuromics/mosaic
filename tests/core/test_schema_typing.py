"""Tests for the shared schema-typing core (issue #47)."""

from __future__ import annotations

from pathlib import Path

from hippo.core.schema_typing import (
    INFRASTRUCTURE_CLASSES,
    SYSTEM_FIELDS,
    EntityTypeModel,
    FieldRole,
    SlotKind,
    build_type_model,
    exposed_class_names,
)
from hippo.linkml_bridge import SchemaRegistry

_FIXTURE_SCHEMA = (
    Path(__file__).parents[1] / "fixtures" / "schemas" / "sample_schema.yaml"
)


def _registry() -> SchemaRegistry:
    return SchemaRegistry.from_path(_FIXTURE_SCHEMA)


def test_exposed_classes_excludes_infrastructure_and_abstract():
    names = exposed_class_names(_registry())
    # Behaviour-preserving: matches the typed-client / GraphQL selection.
    # ExternalID is a concrete hippo_core class NOT in the 5-class
    # infrastructure set, so it is exposed today (see issue #47 follow-up on
    # whether it should be treated as infrastructure — the TUI excludes it).
    assert names == ["ExternalID", "Project", "Sample"]
    assert not (set(names) & INFRASTRUCTURE_CLASSES)


def test_build_type_model_keys():
    model = build_type_model(_registry())
    assert set(model) == {"ExternalID", "Project", "Sample"}
    assert all(isinstance(v, EntityTypeModel) for v in model.values())


def test_scalar_slot_classification():
    sample = build_type_model(_registry())["Sample"]
    by_name = {f.name: f for f in sample.fields}
    assert by_name["volume_ml"].kind is SlotKind.SCALAR
    assert by_name["volume_ml"].range == "float"
    assert by_name["name"].required is True
    assert by_name["name"].role is FieldRole.USER


def test_enum_slot_classification():
    sample = build_type_model(_registry())["Sample"]
    status = {f.name: f for f in sample.fields}["status"]
    assert status.kind is SlotKind.ENUM
    assert status.enum_name == "SampleStatus"
    assert status.enum_values == ("active", "archived", "distributed")


def test_reference_slot_classification():
    sample = build_type_model(_registry())["Sample"]
    project_id = {f.name: f for f in sample.fields}["project_id"]
    assert project_id.kind is SlotKind.REFERENCE
    assert project_id.target_class == "Project"
    # And it surfaces via the relationships convenience.
    assert "project_id" in {r.name for r in sample.relationships}


def test_system_fields_partitioned_from_user_fields():
    sample = build_type_model(_registry())["Sample"]
    system = {f.name for f in sample.system_fields}
    assert "id" in system and "is_available" in system
    assert system <= SYSTEM_FIELDS
    # User fields exclude system fields.
    assert "id" not in {f.name for f in sample.user_fields}
    assert "name" in {f.name for f in sample.user_fields}


def test_accessor_name_present():
    project = build_type_model(_registry())["Project"]
    assert project.accessor_name  # canonical plural accessor, non-empty
