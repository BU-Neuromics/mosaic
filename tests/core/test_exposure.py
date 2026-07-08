"""Tests for the exposure-report tool + Bundle manifest (PTS-340 / sec11 §11.6).

The exposure report is the *pre-migration warning* half of the S4 acceptance
criterion ("an extension with a stranded field is flagged pre-migration ...").
It intersects a base migration's structural write-set with an installed
extension's referenced elements: empty ⇒ safe; non-empty ⇒ the lab must
supply a complementary step (or the end-to-end gate will block it).
"""

import pytest

from mosaic.core.exceptions import ConfigError
from mosaic.core.loaders.bundle import Bundle
from mosaic.core.loaders.exposure import (
    SchemaElement,
    compute_write_set,
    exposure_report,
    extension_referenced_elements,
)


# ---------------------------------------------------------------------------
# Write-set diff
# ---------------------------------------------------------------------------


class TestWriteSet:
    def test_added_removed_changed(self) -> None:
        old = {
            "classes": {
                "Diagnosis": {
                    "attributes": {"code": {"range": "string"}},
                }
            }
        }
        # Base major: split `code` into primary/secondary (remove + add),
        # which also changes the Diagnosis class definition.
        new = {
            "classes": {
                "Diagnosis": {
                    "attributes": {
                        "code_primary": {"range": "string"},
                        "code_secondary": {"range": "string"},
                    },
                }
            }
        }
        ws = compute_write_set(old, new)
        assert SchemaElement("slot", "code") in ws.removed
        assert SchemaElement("slot", "code_primary") in ws.added
        assert SchemaElement("slot", "code_secondary") in ws.added
        assert SchemaElement("class", "Diagnosis") in ws.changed
        assert not ws.is_empty()

    def test_identical_schemas_empty(self) -> None:
        schema = {"classes": {"X": {"attributes": {"a": {"range": "string"}}}}}
        assert compute_write_set(schema, schema).is_empty()


# ---------------------------------------------------------------------------
# Extension reference extraction
# ---------------------------------------------------------------------------


class TestReferencedElements:
    def test_is_a_slot_usage_and_added_slot_range(self) -> None:
        fragment = {
            "classes": {
                "LabDiagnosis": {
                    "is_a": "Diagnosis",  # references base class
                    "slot_usage": {"code": {"required": True}},  # refines base slot
                    "attributes": {
                        "confidence": {"range": "integer"},  # own slot, prim range
                        "linked_sample": {"range": "Sample"},  # dep on base class
                    },
                }
            }
        }
        refs = extension_referenced_elements(fragment)
        assert SchemaElement("class", "Diagnosis") in refs
        assert SchemaElement("slot", "code") in refs
        assert SchemaElement("class", "Sample") in refs
        # The extension's own class is not a self-reference.
        assert SchemaElement("class", "LabDiagnosis") not in refs

    def test_own_classes_excluded(self) -> None:
        fragment = {
            "classes": {
                "A": {"attributes": {"x": {"range": "string"}}},
                "B": {"is_a": "A"},  # is_a an own class → not a base ref
            }
        }
        refs = extension_referenced_elements(fragment)
        assert SchemaElement("class", "A") not in refs

    def test_mixins_collected(self) -> None:
        # A class-level `mixins` list references base classes (alongside is_a).
        fragment = {
            "classes": {
                "LabSample": {
                    "is_a": "Sample",
                    "mixins": ["Timestamped", "Auditable"],
                }
            }
        }
        refs = extension_referenced_elements(fragment)
        assert SchemaElement("class", "Sample") in refs
        assert SchemaElement("class", "Timestamped") in refs
        assert SchemaElement("class", "Auditable") in refs

    def test_class_level_slots_list_collected(self) -> None:
        # A class-level `slots` list names base slots the extension pulls in.
        fragment = {
            "classes": {
                "LabSample": {
                    "is_a": "Sample",
                    "slots": ["collected_at", "operator"],
                }
            }
        }
        refs = extension_referenced_elements(fragment)
        assert SchemaElement("slot", "collected_at") in refs
        assert SchemaElement("slot", "operator") in refs

    def test_fragment_level_slots_list_collected(self) -> None:
        # A (non-standard) fragment-level `slots` *list* is collected the same
        # way as fragment-level `slot_usage`.
        fragment = {
            "slots": ["external_id", "label"],
            "classes": {"LabSample": {"is_a": "Sample"}},
        }
        refs = extension_referenced_elements(fragment)
        assert SchemaElement("slot", "external_id") in refs
        assert SchemaElement("slot", "label") in refs

    def test_fragment_level_slots_mapping_not_collected(self) -> None:
        # A *standard* top-level `slots:` mapping defines the extension's OWN
        # slots, not base references — collecting them would be a false
        # positive, so the list-only guard must skip the mapping form.
        fragment = {
            "slots": {"my_own_slot": {"range": "string"}},
            "classes": {"LabSample": {"is_a": "Sample"}},
        }
        refs = extension_referenced_elements(fragment)
        assert SchemaElement("slot", "my_own_slot") not in refs

    def test_lowercase_class_range_is_false_negative(self) -> None:
        # Documents the known isupper() limitation (PTS-346 item 2): a slot
        # whose range is a *lowercase-named* class is dropped as if primitive.
        # This is the dangerous false-negative direction; pinning it keeps the
        # behaviour visible should the heuristic ever be tightened.
        fragment = {
            "classes": {
                "LabSample": {
                    "attributes": {"ref": {"range": "lowercaseclass"}},
                }
            }
        }
        refs = extension_referenced_elements(fragment)
        assert SchemaElement("class", "lowercaseclass") not in refs


# ---------------------------------------------------------------------------
# Exposure intersection
# ---------------------------------------------------------------------------


class TestExposureReport:
    def _base_split(self):
        old = {"classes": {"Diagnosis": {"attributes": {"code": {"range": "string"}}}}}
        new = {
            "classes": {
                "Diagnosis": {
                    "attributes": {"code_primary": {"range": "string"}}
                }
            }
        }
        return compute_write_set(old, new)

    def test_non_empty_intersection_flags_extension(self) -> None:
        # Extension refines the base `code` slot the migration removed → exposed.
        ext = {
            "classes": {
                "LabDiagnosis": {
                    "is_a": "Diagnosis",
                    "slot_usage": {"code": {"required": True}},
                }
            }
        }
        report = exposure_report(
            self._base_split(), ext, extension_name="labdiagnosis"
        )
        assert not report.is_safe
        assert "code" in report.exposed_slots
        assert "Diagnosis" in report.exposed_classes
        assert "labdiagnosis" in report.render()

    def test_empty_intersection_is_safe(self) -> None:
        # Extension touches an unrelated base class/slot → unaffected.
        ext = {
            "classes": {
                "LabNote": {
                    "is_a": "Note",
                    "attributes": {"text": {"range": "string"}},
                }
            }
        }
        report = exposure_report(
            self._base_split(), ext, extension_name="labnote"
        )
        assert report.is_safe
        assert report.exposed_slots == []
        assert "unaffected" in report.render()


# ---------------------------------------------------------------------------
# Bundle manifest + generated requires:
# ---------------------------------------------------------------------------


class TestBundle:
    def test_from_manifest_and_to_requires(self) -> None:
        bundle = Bundle.from_manifest(
            {
                "name": "brainbank-bundle",
                "version": "2024.1",
                "ontology_snapshot": "2024-01",
                "packages": {"core": "2.0.0", "subject": "1.4.0"},
                "coordinates": [{"core": "1.3.0"}, {"core": "1.4.0"}],
            }
        )
        assert bundle.name == "brainbank-bundle"
        assert bundle.packages == {"core": "2.0.0", "subject": "1.4.0"}
        # Generated requires: block — exact pins, sorted.
        assert bundle.to_requires() == {
            "core": "==2.0.0",
            "subject": "==1.4.0",
        }
        # The hop sequence is intermediates then target.
        seq = bundle.coordinate_sequence()
        assert seq == [
            {"core": "1.3.0"},
            {"core": "1.4.0"},
            {"core": "2.0.0", "subject": "1.4.0"},
        ]

    def test_missing_packages_rejected(self) -> None:
        with pytest.raises(ConfigError):
            Bundle.from_manifest({"name": "x"})

    def test_missing_name_rejected(self) -> None:
        with pytest.raises(ConfigError):
            Bundle.from_manifest({"packages": {"core": "1.0.0"}})

    def test_non_string_version_rejected(self) -> None:
        # A non-string *package* version pin.
        with pytest.raises(ConfigError):
            Bundle.from_manifest({"name": "x", "packages": {"core": 1.0}})

    def test_non_string_bundle_version_rejected(self) -> None:
        # The optional top-level `version` field: `version: 1.0` parses to a
        # float and must be rejected, not stored silently (PTS-346 item 1).
        with pytest.raises(ConfigError, match="version"):
            Bundle.from_manifest(
                {"name": "x", "packages": {"core": "1.0.0"}, "version": 1.0}
            )

    def test_non_string_ontology_snapshot_rejected(self) -> None:
        with pytest.raises(ConfigError, match="ontology_snapshot"):
            Bundle.from_manifest(
                {
                    "name": "x",
                    "packages": {"core": "1.0.0"},
                    "ontology_snapshot": 202401,
                }
            )

    def test_optional_metadata_absent_is_ok(self) -> None:
        # Both optional fields may be omitted (None) — that is the common case.
        bundle = Bundle.from_manifest(
            {"name": "x", "packages": {"core": "1.0.0"}}
        )
        assert bundle.version is None
        assert bundle.ontology_snapshot is None


# ---------------------------------------------------------------------------
# compute_exposure SDK entrypoint (backs `mosaic reference exposure`)
# ---------------------------------------------------------------------------


class TestComputeExposureEntrypoint:
    def _write(self, tmp_path, name, schema) -> str:
        import yaml as _yaml

        p = tmp_path / name
        p.write_text(_yaml.safe_dump(schema), encoding="utf-8")
        return str(p)

    def test_reports_exposure_from_schema_files(self, tmp_path) -> None:
        from mosaic.cli.commands.reference import compute_exposure

        old = self._write(
            tmp_path,
            "old.yaml",
            {"classes": {"Diagnosis": {"attributes": {"code": {"range": "string"}}}}},
        )
        new = self._write(
            tmp_path,
            "new.yaml",
            {
                "classes": {
                    "Diagnosis": {"attributes": {"code_primary": {"range": "string"}}}
                }
            },
        )
        # Explicit fragment → no entry-point discovery needed.
        ext_fragment = {
            "classes": {
                "LabDiagnosis": {
                    "is_a": "Diagnosis",
                    "slot_usage": {"code": {"required": True}},
                }
            }
        }
        report = compute_exposure(
            old, new, "labdiagnosis", extension_fragment=ext_fragment
        )
        assert not report.is_safe
        assert "code" in report.exposed_slots
