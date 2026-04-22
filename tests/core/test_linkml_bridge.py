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
    """Tests use sample_schema.yaml which imports hippo_core (sec9). Sample
    inherits `is_available` from Entity, so every valid instance must include
    it. Typically the SDK fills it in on create; these tests exercise the raw
    validator interface directly and therefore supply it explicitly.
    """

    def test_valid_instance_passes(self, registry: SchemaRegistry):
        errors = registry.validate(
            {"id": "s1", "name": "tissue A", "is_available": True}, "Sample"
        )
        assert errors == []

    def test_missing_required_field_rejected(self, registry: SchemaRegistry):
        errors = registry.validate({"id": "s1", "is_available": True}, "Sample")
        assert len(errors) == 1
        assert "'name'" in errors[0]
        assert "required" in errors[0]

    def test_wrong_type_rejected(self, registry: SchemaRegistry):
        errors = registry.validate(
            {
                "id": "s1",
                "name": "ok",
                "is_available": True,
                "volume_ml": "not-a-number",
            },
            "Sample",
        )
        assert any("not of type" in e for e in errors)

    def test_bad_enum_value_rejected(self, registry: SchemaRegistry):
        errors = registry.validate(
            {"id": "s1", "name": "ok", "is_available": True, "status": "bogus"},
            "Sample",
        )
        assert any("not one of" in e for e in errors)
        assert any("active" in e for e in errors)

    def test_closed_schema_rejects_extra_fields(self, registry: SchemaRegistry):
        errors = registry.validate(
            {"id": "s1", "name": "ok", "is_available": True, "nope": 1}, "Sample"
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


class TestHippoExtValidation:
    """SchemaRegistry validates every hippo_* annotation against hippo_ext at load.

    See sec9 §9.4 and design/reference_hippo_ext.md for the declared vocabulary.
    """

    def _build(self, extra_annotations: dict, on: str = "slot") -> str:
        """Construct a minimal user-schema YAML with the given annotations.

        `on` is either "slot" (attach to `Thing.name`) or "class" (attach to
        `Thing` itself).
        """
        def _fmt(v):
            if isinstance(v, bool):
                return "true" if v else "false"
            if isinstance(v, str):
                return f'"{v}"'
            return str(v)

        if on == "slot":
            # annotations under Thing.name require 10-space indent
            ann_yaml = "\n".join(
                f"          {k}: {_fmt(v)}" for k, v in extra_annotations.items()
            )
            return (
                "id: https://example.org/test\n"
                "name: test\n"
                "prefixes: {linkml: 'https://w3id.org/linkml/'}\n"
                "default_range: string\n"
                "imports: [linkml:types]\n"
                "classes:\n"
                "  Thing:\n"
                "    attributes:\n"
                "      id: {identifier: true}\n"
                "      name:\n"
                "        range: string\n"
                "        annotations:\n"
                f"{ann_yaml}\n"
            )
        # class-level annotations on Thing require 6-space indent
        ann_yaml = "\n".join(
            f"      {k}: {_fmt(v)}" for k, v in extra_annotations.items()
        )
        return (
            "id: https://example.org/test\n"
            "name: test\n"
            "prefixes: {linkml: 'https://w3id.org/linkml/'}\n"
            "default_range: string\n"
            "imports: [linkml:types]\n"
            "classes:\n"
            "  Thing:\n"
            "    annotations:\n"
            f"{ann_yaml}\n"
            "    attributes:\n"
            "      id: {identifier: true}\n"
        )

    def test_declared_annotation_passes(self):
        # hippo_index: true is valid on a slot
        yaml_text = self._build({"hippo_index": True})
        reg = SchemaRegistry.from_yaml(yaml_text)
        assert "Thing" in reg.class_names()

    def test_undeclared_annotation_fails_with_actionable_message(self):
        from hippo.core.exceptions import SchemaError

        yaml_text = self._build({"hippo_bogus": True})
        with pytest.raises(SchemaError) as exc:
            SchemaRegistry.from_yaml(yaml_text)
        msg = str(exc.value)
        assert "hippo_bogus" in msg
        assert "Thing.name" in msg
        assert "not declared in hippo_ext" in msg

    def test_wrong_value_type_fails(self):
        from hippo.core.exceptions import SchemaError

        # hippo_index expects boolean, got string
        yaml_text = self._build({"hippo_index": "yes"})
        with pytest.raises(SchemaError) as exc:
            SchemaRegistry.from_yaml(yaml_text)
        msg = str(exc.value)
        assert "hippo_index" in msg
        assert "expected boolean" in msg

    def test_class_annotation_on_slot_fails(self):
        # hippo_append_only is a class-only annotation, but in Wave 1 it's
        # not yet declared in hippo_ext — so this surfaces as "undeclared"
        # rather than "wrong applies_to". When Wave 2 lands and declares
        # hippo_append_only, this test would shift to the wrong-target case.
        from hippo.core.exceptions import SchemaError

        yaml_text = self._build({"hippo_append_only": True})
        with pytest.raises(SchemaError) as exc:
            SchemaRegistry.from_yaml(yaml_text)
        msg = str(exc.value)
        assert "hippo_append_only" in msg

    def test_slot_annotation_on_class_fails(self):
        # hippo_index is a slot annotation; attaching it to a class should fail.
        from hippo.core.exceptions import SchemaError

        yaml_text = self._build({"hippo_index": True}, on="class")
        with pytest.raises(SchemaError) as exc:
            SchemaRegistry.from_yaml(yaml_text)
        msg = str(exc.value)
        assert "hippo_index" in msg
        # The error message mentions the annotation may only attach to slots
        assert "slot_annotation" in msg or "slot" in msg.lower()

    def test_multiple_errors_aggregate_into_one_exception(self):
        from hippo.core.exceptions import SchemaError

        yaml_text = self._build(
            {"hippo_bogus1": True, "hippo_bogus2": True, "hippo_index": "not-bool"}
        )
        with pytest.raises(SchemaError) as exc:
            SchemaRegistry.from_yaml(yaml_text)
        msg = str(exc.value)
        assert "3 hippo_* annotation error(s)" in msg
        assert "hippo_bogus1" in msg
        assert "hippo_bogus2" in msg
        assert "hippo_index" in msg

    def test_non_hippo_annotations_are_not_validated(self):
        # Only hippo_* keys get validated against hippo_ext. Custom user
        # annotations in other namespaces (prov:, skos:, custom_*) pass
        # through unchecked.
        yaml_text = self._build({"custom_tag": "anything"})
        reg = SchemaRegistry.from_yaml(yaml_text)
        assert "Thing" in reg.class_names()

    def test_hippo_search_accepts_any_string_value(self):
        # Per Decision 9.4.C: hippo_search range is `string`, not an enum.
        # The adapter is the authority on which modes it supports; schema-level
        # validation is permissive.
        yaml_text = self._build({"hippo_search": "fts5"})
        reg1 = SchemaRegistry.from_yaml(yaml_text)
        assert "Thing" in reg1.class_names()

        # Non-canonical mode also passes at schema load (adapter would fail
        # at startup if it doesn't support this mode).
        yaml_text2 = self._build({"hippo_search": "embedding"})
        reg2 = SchemaRegistry.from_yaml(yaml_text2)
        assert "Thing" in reg2.class_names()


class TestHippoCoreImport:
    """Tests that `imports: [hippo_core]` resolves and user classes can
    `is_a: Entity`. See sec9 §9.3 and §9.5.
    """

    def _user_schema(self, include_hippo_core_import: bool = True) -> str:
        imports = ["linkml:types"]
        if include_hippo_core_import:
            imports.append("hippo_core")
        imports_block = "\n".join(f"  - {i}" for i in imports)
        return (
            "id: https://example.org/test\n"
            "name: test\n"
            "prefixes: {linkml: 'https://w3id.org/linkml/'}\n"
            "default_range: string\n"
            "imports:\n"
            f"{imports_block}\n"
            "classes:\n"
            "  MySample:\n"
            "    is_a: Entity\n"
            "    attributes:\n"
            "      barcode:\n"
            "        range: string\n"
            "        required: true\n"
        )

    def test_hippo_core_importable_and_entity_resolves(self):
        reg = SchemaRegistry.from_yaml(self._user_schema())
        # Entity flows in from hippo_core; MySample inherits id + is_available.
        names = set(reg.class_names())
        assert "Entity" in names
        assert "MySample" in names
        slot_names = {s.name for s in reg.induced_slots("MySample")}
        assert {"id", "is_available", "barcode"}.issubset(slot_names)

    def test_hippo_core_enums_available_in_user_view(self):
        reg = SchemaRegistry.from_yaml(self._user_schema())
        sv = reg.schema_view
        enums = sv.all_enums()
        assert "Status" in enums
        assert "Operation" in enums
        op_values = set(enums["Operation"].permissible_values.keys())
        assert {"create", "update", "supersede", "migration_applied"}.issubset(
            op_values
        )

    def test_without_hippo_core_import_entity_unresolved(self):
        # Without `imports: hippo_core`, SchemaView loads successfully but
        # LinkML can't resolve `is_a: Entity` when induced slots are
        # requested — SchemaView raises ValueError("No such class: Entity").
        # This is acceptable load-time failure behavior; the error points at
        # the missing import.
        reg = SchemaRegistry.from_yaml(
            self._user_schema(include_hippo_core_import=False)
        )
        with pytest.raises(ValueError, match="Entity"):
            reg.induced_slots("MySample")

    def test_entity_is_available_inherited_with_default(self):
        reg = SchemaRegistry.from_yaml(self._user_schema())
        slots = {s.name: s for s in reg.induced_slots("MySample")}
        assert "is_available" in slots
        is_avail = slots["is_available"]
        assert is_avail.required is True
        # ifabsent is stored as a string form in LinkML; slot_default coerces
        # boolean-ranged strings back to Python bools.
        from hippo.linkml_bridge import slot_default
        assert slot_default(is_avail) is True
