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


class TestHippoCoreProcess:
    """Process class shipped in hippo_core (sec9 §9.5). Composite activity
    grouping that callers can `is_a: Process` for domain-specific executions
    like Cappella PipelineRuns.
    """

    def _schema_with_process_subclass(self) -> str:
        return (
            "id: https://example.org/test\n"
            "name: test\n"
            "prefixes: {linkml: 'https://w3id.org/linkml/'}\n"
            "default_range: string\n"
            "imports:\n"
            "  - linkml:types\n"
            "  - hippo_core\n"
            "classes:\n"
            "  PipelineRun:\n"
            "    is_a: Process\n"
            "    attributes:\n"
            "      pipeline_name:\n"
            "        range: string\n"
            "        required: true\n"
        )

    def test_process_class_present_in_hippo_core(self):
        # A user schema that imports hippo_core sees Process available.
        reg = SchemaRegistry.from_yaml(
            "id: https://example.org/t\n"
            "name: t\n"
            "prefixes: {linkml: 'https://w3id.org/linkml/'}\n"
            "default_range: string\n"
            "imports:\n  - linkml:types\n  - hippo_core\n"
            "classes: {}\n"
        )
        assert "Process" in reg.class_names()

    def test_process_inherits_entity_slots(self):
        reg = SchemaRegistry.from_yaml(self._schema_with_process_subclass())
        slot_names = {s.name for s in reg.induced_slots("Process")}
        # id + is_available from Entity
        assert "id" in slot_names
        assert "is_available" in slot_names
        # Process-specific slots
        expected = {
            "parent_process_id",
            "operation_kind",
            "started_at",
            "ended_at",
            "actor_id",
        }
        assert expected.issubset(slot_names)

    def test_process_subclass_inherits_all_slots(self):
        reg = SchemaRegistry.from_yaml(self._schema_with_process_subclass())
        slot_names = {s.name for s in reg.induced_slots("PipelineRun")}
        # Entity-inherited
        assert "id" in slot_names
        assert "is_available" in slot_names
        # Process-inherited
        assert "operation_kind" in slot_names
        assert "started_at" in slot_names
        assert "actor_id" in slot_names
        assert "parent_process_id" in slot_names
        # PipelineRun-declared
        assert "pipeline_name" in slot_names

    def test_process_class_uri_is_prov_activity(self):
        reg = SchemaRegistry.from_yaml(self._schema_with_process_subclass())
        proc_cls = reg.get_class("Process")
        assert proc_cls is not None
        # class_uri may be returned as the literal string or the expanded form;
        # accept either.
        assert (
            proc_cls.class_uri == "prov:Activity"
            or "Activity" in (proc_cls.class_uri or "")
        )

    def test_parent_process_id_is_self_reference(self):
        reg = SchemaRegistry.from_yaml(self._schema_with_process_subclass())
        slots = {s.name: s for s in reg.induced_slots("Process")}
        ppid = slots["parent_process_id"]
        assert ppid.range == "Process"
        assert ppid.required is False

    def test_process_operation_kind_is_indexed(self):
        # operation_kind annotated hippo_index: true — verify annotation reaches
        # the induced slot via the existing annotation_value helper.
        reg = SchemaRegistry.from_yaml(self._schema_with_process_subclass())
        slots = {s.name: s for s in reg.induced_slots("Process")}
        from hippo.linkml_bridge import annotation_value, HIPPO_INDEX
        assert annotation_value(slots["operation_kind"], HIPPO_INDEX) is True
        assert annotation_value(slots["started_at"], HIPPO_INDEX) is True


class TestHippoCoreProvenanceRecord:
    """ProvenanceRecord class shipped in hippo_core (sec9 §9.6). Declared for
    introspection and downstream use (typed-client, REST surface). The
    adapter-side enforcement and ProvenanceStore migration land with the
    `provenance-migration` change per Decision 9.6.A.
    """

    def _schema_importing_hippo_core(self) -> str:
        return (
            "id: https://example.org/test\n"
            "name: test\n"
            "prefixes: {linkml: 'https://w3id.org/linkml/'}\n"
            "default_range: string\n"
            "imports:\n"
            "  - linkml:types\n"
            "  - hippo_core\n"
            "classes: {}\n"
        )

    def test_provenance_record_present_in_hippo_core(self):
        reg = SchemaRegistry.from_yaml(self._schema_importing_hippo_core())
        assert "ProvenanceRecord" in reg.class_names()

    def test_provenance_record_is_a_entity(self):
        reg = SchemaRegistry.from_yaml(self._schema_importing_hippo_core())
        slot_names = {s.name for s in reg.induced_slots("ProvenanceRecord")}
        # Inherited from Entity
        assert "id" in slot_names
        assert "is_available" in slot_names

    def test_provenance_record_has_sec9_slots(self):
        reg = SchemaRegistry.from_yaml(self._schema_importing_hippo_core())
        slot_names = {s.name for s in reg.induced_slots("ProvenanceRecord")}
        expected = {
            "entity_id",
            "entity_type",
            "operation",
            "actor_id",
            "timestamp",
            "schema_version",
            "derived_from_id",
            "process_id",
            "patch",
            "context",
        }
        assert expected.issubset(slot_names)

    def test_provenance_record_class_uri_is_prov_activity(self):
        reg = SchemaRegistry.from_yaml(self._schema_importing_hippo_core())
        cls = reg.get_class("ProvenanceRecord")
        assert cls is not None
        assert cls.class_uri == "prov:Activity" or "Activity" in (
            cls.class_uri or ""
        )

    def test_provenance_record_has_hippo_append_only_annotation(self):
        reg = SchemaRegistry.from_yaml(self._schema_importing_hippo_core())
        cls = reg.get_class("ProvenanceRecord")
        assert cls is not None
        from hippo.linkml_bridge import annotation_value
        assert annotation_value(cls, "hippo_append_only") is True

    def test_provenance_record_slots_are_indexed(self):
        reg = SchemaRegistry.from_yaml(self._schema_importing_hippo_core())
        slots = {s.name: s for s in reg.induced_slots("ProvenanceRecord")}
        from hippo.linkml_bridge import annotation_value, HIPPO_INDEX
        # Slots that sec9 §9.6 and §9.7 say should be indexed for the
        # canonical query paths
        assert annotation_value(slots["entity_id"], HIPPO_INDEX) is True
        assert annotation_value(slots["timestamp"], HIPPO_INDEX) is True
        assert annotation_value(slots["operation"], HIPPO_INDEX) is True
        assert annotation_value(slots["process_id"], HIPPO_INDEX) is True

    def test_operation_enum_available(self):
        # ProvenanceRecord.operation references the Operation enum declared
        # in hippo_core. The user view should see both.
        reg = SchemaRegistry.from_yaml(self._schema_importing_hippo_core())
        sv = reg.schema_view
        enums = sv.all_enums()
        assert "Operation" in enums


class TestHippoAppendOnlyAnnotation:
    """Validates the hippo_append_only annotation declaration in hippo_ext."""

    def _schema_with_annotation(self, target: str, value: object) -> str:
        """Build a schema attaching hippo_append_only to a class or slot."""
        if target == "class":
            return (
                "id: https://example.org/t\n"
                "name: t\n"
                "prefixes: {linkml: 'https://w3id.org/linkml/'}\n"
                "default_range: string\n"
                "imports: [linkml:types]\n"
                "classes:\n"
                "  LogEntry:\n"
                "    annotations:\n"
                f"      hippo_append_only: {str(value).lower()}\n"
                "    attributes:\n"
                "      id: {identifier: true}\n"
            )
        # target == "slot"
        return (
            "id: https://example.org/t\n"
            "name: t\n"
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
            f"          hippo_append_only: {str(value).lower()}\n"
        )

    def test_hippo_append_only_true_on_class_passes(self):
        reg = SchemaRegistry.from_yaml(
            self._schema_with_annotation("class", True)
        )
        cls = reg.get_class("LogEntry")
        from hippo.linkml_bridge import annotation_value
        assert annotation_value(cls, "hippo_append_only") is True

    def test_hippo_append_only_false_on_class_passes(self):
        reg = SchemaRegistry.from_yaml(
            self._schema_with_annotation("class", False)
        )
        cls = reg.get_class("LogEntry")
        from hippo.linkml_bridge import annotation_value
        assert annotation_value(cls, "hippo_append_only") is False

    def test_hippo_append_only_on_slot_fails(self):
        # hippo_append_only is a class_annotation; attaching it to a slot
        # must fail at schema load with an applies_to violation.
        from hippo.core.exceptions import SchemaError

        with pytest.raises(SchemaError) as exc:
            SchemaRegistry.from_yaml(
                self._schema_with_annotation("slot", True)
            )
        msg = str(exc.value)
        assert "hippo_append_only" in msg
        assert "slot" in msg.lower() or "class_annotation" in msg
