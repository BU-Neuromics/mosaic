"""Tests for the sec9 §9.9 three-tier validation envelope."""

from __future__ import annotations

import pytest

from hippo.core.exceptions import ValidationFailed
from hippo.core.validation.validators import (
    ValidationFailure,
    ValidationResult,
    ValidatorPipeline,
    ValidatorRegistry,
    WriteOperation,
    WriteValidator,
)
from hippo.linkml_bridge import SchemaRegistry


class TestValidationResultEnvelope:
    """sec9 §9.9 envelope shape on ValidationResult."""

    def test_legacy_errors_synthesize_failures(self):
        """Constructing with just errors=[...] gives a failures list
        with tier='python', rule='legacy' for each string."""
        r = ValidationResult(is_valid=False, errors=["boom", "kapow"])

        assert len(r.failures) == 2
        assert r.failures[0].tier == "python"
        assert r.failures[0].rule == "legacy"
        assert r.failures[0].message == "boom"
        assert r.failures[1].message == "kapow"

    def test_failures_synthesize_errors(self):
        """Constructing with failures=[...] gives an errors list with
        the raw messages (no tier prefix — preserves legacy substring
        assertions)."""
        r = ValidationResult(
            is_valid=False,
            failures=[
                ValidationFailure(
                    tier="linkml", rule="required", message="name is required"
                ),
            ],
        )

        assert r.errors == ["name is required"]

    def test_passed_alias(self):
        """`passed` is an alias for `is_valid` (sec9 §9.9 spelling)."""
        assert ValidationResult(is_valid=True).passed is True
        assert ValidationResult(is_valid=False, errors=["x"]).passed is False

    def test_failures_for_tier_filter(self):
        r = ValidationResult(
            is_valid=False,
            failures=[
                ValidationFailure(tier="linkml", rule="r1", message="a"),
                ValidationFailure(tier="cel", rule="r2", message="b"),
                ValidationFailure(tier="linkml", rule="r3", message="c"),
            ],
        )
        assert len(r.failures_for_tier("linkml")) == 2
        assert len(r.failures_for_tier("cel")) == 1
        assert r.failures_for_tier("python") == []

    def test_to_envelope_rest_shape(self):
        r = ValidationResult(
            is_valid=False,
            failures=[
                ValidationFailure(
                    tier="cel",
                    rule="age_range",
                    message="age must be positive",
                    field="age",
                    details={"min": 0},
                )
            ],
        )
        env = r.to_envelope()

        assert env["passed"] is False
        assert len(env["failures"]) == 1
        f = env["failures"][0]
        assert f["tier"] == "cel"
        assert f["rule"] == "age_range"
        assert f["field"] == "age"
        assert f["message"] == "age must be positive"
        assert f["details"] == {"min": 0}

    def test_to_string_formats_tier_prefix(self):
        f = ValidationFailure(
            tier="linkml", rule="required", message="name is required"
        )
        assert "[linkml:required]" in f.to_string()

        f2 = ValidationFailure(
            tier="cel",
            rule="age_range",
            message="age must be positive",
            field="age",
        )
        s = f2.to_string()
        assert "[cel:age_range]" in s
        assert "age:" in s


class TestPipelineAggregation:
    """Pipeline aggregates tier-tagged failures across validators."""

    def _pipeline_with(self, *validators: WriteValidator) -> ValidatorPipeline:
        class Mock:
            def get_validators(self):
                return list(validators)

        return ValidatorPipeline(registry=Mock())

    def test_aggregated_failures_preserve_tier_tags(self):
        class LinkmlLike(WriteValidator):
            @property
            def tier(self):
                return "linkml"

            def validate(self, op):
                return ValidationResult(
                    is_valid=False,
                    failures=[
                        ValidationFailure(
                            tier="linkml",
                            rule="required",
                            message="x required",
                        )
                    ],
                )

        class CelLike(WriteValidator):
            @property
            def tier(self):
                return "cel"

            def validate(self, op):
                return ValidationResult(
                    is_valid=False,
                    failures=[
                        ValidationFailure(
                            tier="cel", rule="age", message="age must be positive"
                        )
                    ],
                )

        pipeline = self._pipeline_with(LinkmlLike(), CelLike())
        op = WriteOperation(operation="insert", entity_type="S", data={})
        result = pipeline.validate(op)

        assert result.passed is False
        tiers = [f.tier for f in result.failures]
        assert tiers == ["linkml", "cel"]


class TestLinkmlValidateEnvelope:
    """SchemaRegistry.validate_envelope() returns tier='linkml' failures."""

    def _registry(self) -> SchemaRegistry:
        yaml_text = (
            "id: https://example.org/test\n"
            "name: test\n"
            "prefixes: {linkml: 'https://w3id.org/linkml/'}\n"
            "default_range: string\n"
            "imports: [linkml:types]\n"
            "classes:\n"
            "  Thing:\n"
            "    attributes:\n"
            "      id: {identifier: true}\n"
            "      age: {range: integer, required: true}\n"
        )
        return SchemaRegistry.from_yaml(yaml_text)

    def test_valid_instance_yields_no_failures(self):
        reg = self._registry()
        failures = reg.validate_envelope({"id": "x", "age": 30}, "Thing")
        assert failures == []

    def test_invalid_instance_yields_linkml_tier_failures(self):
        reg = self._registry()
        # Missing required `age`
        failures = reg.validate_envelope({"id": "x"}, "Thing")
        assert len(failures) >= 1
        for f in failures:
            assert f.tier == "linkml"
            assert f.rule  # non-empty rule identifier
            assert f.details.get("target_class") == "Thing"


class TestValidationFailedException:
    """ValidationFailed carries the sec9 envelope."""

    def test_carries_result(self):
        r = ValidationResult(
            is_valid=False,
            failures=[
                ValidationFailure(
                    tier="python", rule="custom", message="nope"
                )
            ],
        )
        exc = ValidationFailed(
            "validation failed", result=r, entity_type="Sample", entity_id="id-1"
        )
        assert exc.result is r
        assert exc.entity_type == "Sample"
        assert exc.entity_id == "id-1"
        assert "validation failed" in str(exc)
