"""Tests for CEL validator engine."""

import pytest
import tempfile
import os

from hippo.core.validators import (
    CELCondition,
    ValidationContext,
    ValidatorEngine,
    ValidationResult,
    CELParseError,
    CELEvaluationError,
)


class TestValidationContext:
    def test_context_creation_with_entity_data(self):
        context = ValidationContext({"name": "test", "age": 25})
        assert context["entity"] == {"name": "test", "age": 25}

    def test_context_creation_with_existing_entity(self):
        context = ValidationContext(
            {"name": "new"},
            existing_entity={"name": "old"},
        )
        assert context["entity"] == {"name": "new"}
        assert context["existing"] == {"name": "old"}

    def test_context_to_dict(self):
        context = ValidationContext({"name": "test"})
        assert context.to_dict() == {"entity": {"name": "test"}}

    def test_context_get_method(self):
        context = ValidationContext({"name": "test"})
        assert context.get("entity") == {"name": "test"}
        assert context.get("nonexistent", "default") == "default"


class TestValidationContextEntityMaps:
    def test_entity_maps_merge_last_wins(self):
        context = ValidationContext(
            entity_maps=[
                {"name": "first", "value": 1},
                {"name": "second", "value": 2},
            ]
        )
        assert context.get_merged_context() == {"name": "second", "value": 2}

    def test_entity_maps_deep_merge(self):
        context = ValidationContext(
            entity_maps=[
                {"user": {"name": "Alice", "age": 30}},
                {"user": {"age": 31, "city": "NYC"}},
            ]
        )
        result = context.get_merged_context()
        assert result["user"] == {"name": "Alice", "age": 31, "city": "NYC"}

    def test_entity_maps_dot_notation_expansion(self):
        context = ValidationContext(
            entity_maps=[{"user.profile.name": "Alice", "user.profile.age": 30}]
        )
        result = context.get_merged_context()
        assert result == {"user": {"profile": {"name": "Alice", "age": 30}}}


class TestValidationContextTypeCoercion:
    def test_type_coercion_string_to_number(self):
        context = ValidationContext(
            entity_maps=[{"value": "42"}],
            type_coercion_enabled=True,
        )
        result = context.get_merged_context()
        assert result["value"] == 42

    def test_type_coercion_string_to_float(self):
        context = ValidationContext(
            entity_maps=[{"value": "3.14"}],
            type_coercion_enabled=True,
        )
        result = context.get_merged_context()
        assert result["value"] == 3.14

    def test_type_coercion_string_true_to_boolean(self):
        context = ValidationContext(
            entity_maps=[{"active": "true"}],
            type_coercion_enabled=True,
        )
        result = context.get_merged_context()
        assert result["active"] is True

    def test_type_coercion_string_false_to_boolean(self):
        context = ValidationContext(
            entity_maps=[{"active": "false"}],
            type_coercion_enabled=True,
        )
        result = context.get_merged_context()
        assert result["active"] is False

    def test_type_coercion_number_to_boolean(self):
        context = ValidationContext(
            entity_maps=[{"active": 1}, {"other": 0}],
            type_coercion_enabled=True,
        )
        result = context.get_merged_context()
        assert result["active"] is True
        assert result["other"] is False

    def test_type_coercion_number_to_string(self):
        context = ValidationContext(
            entity_maps=[{"num": 42}],
            type_coercion_enabled=True,
        )
        result = context.get_merged_context()
        assert result["num"] == "42"

    def test_type_coercion_precedence_string_wins(self):
        context = ValidationContext(
            entity_maps=[{"value": 42}, {"value": "text"}],
            type_coercion_enabled=True,
        )
        result = context.get_merged_context()
        assert result["value"] == "text"

    def test_type_coercion_precedence_number_wins_over_boolean(self):
        context = ValidationContext(
            entity_maps=[{"value": True}, {"value": 42}],
            type_coercion_enabled=True,
        )
        result = context.get_merged_context()
        assert result["value"] == 42

    def test_coercion_warnings_logged(self):
        context = ValidationContext(
            entity_maps=[{"value": "42"}],
            type_coercion_enabled=True,
        )
        warnings = context.get_coercion_warnings()
        assert len(warnings) > 0
        assert "Coerced" in warnings[0]


class TestValidationContextDefaultValues:
    def test_default_values_applied(self):
        context = ValidationContext(
            entity_maps=[{"name": "Alice"}],
            default_values={"age": 30, "city": "NYC"},
        )
        assert context.get_field_with_default("name") == "Alice"
        assert context.get_field_with_default("age") == 30
        assert context.get_field_with_default("city") == "NYC"

    def test_missing_field_returns_null(self):
        context = ValidationContext(
            entity_maps=[{"name": "Alice"}],
            default_values={"age": 30},
        )
        assert context.get_field_with_default("nonexistent") is None

    def test_nested_default_values(self):
        context = ValidationContext(
            entity_maps=[{"user": {"name": "Alice"}}],
            default_values={"user.age": 30},
        )
        assert context.get_field_with_default("user.name") == "Alice"
        assert context.get_field_with_default("user.age") == 30


class TestValidationContextAPI:
    def test_get_merged_context(self):
        context = ValidationContext(entity_maps=[{"name": "Alice", "age": 30}])
        merged = context.get_merged_context()
        assert merged == {"name": "Alice", "age": 30}

    def test_get_field_dot_notation(self):
        context = ValidationContext(
            entity_maps=[{"user": {"profile": {"name": "Alice"}}}]
        )
        assert context.get_field("user.profile.name") == "Alice"

    def test_get_field_nested_missing(self):
        context = ValidationContext(entity_maps=[{"user": {"name": "Alice"}}])
        assert context.get_field("user.profile.name") is None

    def test_get_coercion_warnings_empty_when_disabled(self):
        context = ValidationContext(
            entity_maps=[{"value": "42"}],
            type_coercion_enabled=False,
        )
        assert context.get_coercion_warnings() == []

    def test_get_coercion_warnings_returns_events(self):
        context = ValidationContext(
            entity_maps=[{"value": "42"}],
            type_coercion_enabled=True,
        )
        warnings = context.get_coercion_warnings()
        assert isinstance(warnings, list)


class TestCELCondition:
    def test_cel_condition_valid_expression(self):
        cond = CELCondition("1 + 1 == 2")
        assert cond.is_valid is True

    def test_cel_condition_evaluate(self):
        cond = CELCondition("x + y > 10")
        result = cond.evaluate({"x": 5, "y": 10})
        assert result is True

    def test_cel_condition_evaluate_with_entity(self):
        cond = CELCondition("entity.age > 18")
        result = cond.evaluate({"entity": {"age": 25}})
        assert result is True

    def test_cel_condition_missing_field_returns_false(self):
        cond = CELCondition("entity.missing_field > 0")
        result = cond.evaluate({"entity": {}})
        assert result is False


class TestValidatorEngine:
    def test_validator_engine_initialization(self):
        engine = ValidatorEngine()
        assert engine.is_loaded is False

    def test_validator_engine_load_from_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(
                """
validators:
  - name: test_validator
    entity_types: [Sample]
    'on': [create]
    condition: "entity.name != ''"
"""
            )
            f.flush()
            engine = ValidatorEngine()
            engine.load(f.name)
            assert engine.is_loaded is True
            assert len(engine.rules) == 1
            os.unlink(f.name)

    def test_validator_engine_missing_file(self):
        engine = ValidatorEngine()
        with pytest.raises(Exception):
            engine.load("nonexistent.yaml")

    def test_validator_engine_invalid_yaml(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: content:")
            f.flush()
            engine = ValidatorEngine()
            with pytest.raises(Exception):
                engine.load(f.name)
            os.unlink(f.name)

    def test_validator_engine_missing_validators_key(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("other_key: []")
            f.flush()
            engine = ValidatorEngine()
            with pytest.raises(Exception):
                engine.load(f.name)
            os.unlink(f.name)

    def test_validator_engine_validate_valid_entity(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(
                """
validators:
  - name: name_required
    entity_types: [Sample]
    'on': [create]
    condition: "entity.name != ''"
"""
            )
            f.flush()
            engine = ValidatorEngine()
            engine.load(f.name)
            result = engine.validate(
                entity_type="Sample",
                operation="create",
                entity_data={"name": "test"},
            )
            assert result.is_valid is True
            os.unlink(f.name)

    def test_validator_engine_validate_invalid_entity(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(
                """
validators:
  - name: name_required
    entity_types: [Sample]
    'on': [create]
    condition: "entity.name != ''"
"""
            )
            f.flush()
            engine = ValidatorEngine()
            engine.load(f.name)
            result = engine.validate(
                entity_type="Sample",
                operation="create",
                entity_data={"name": ""},
            )
            assert result.is_valid is False
            assert len(result.errors) == 1
            os.unlink(f.name)

    def test_validator_engine_multiple_rules_error_aggregation(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(
                """
validators:
  - name: name_required
    entity_types: [Sample]
    'on': [create]
    condition: "entity.name != ''"
  - name: age_positive
    entity_types: [Sample]
    'on': [create]
    condition: "entity.age > 0"
"""
            )
            f.flush()
            engine = ValidatorEngine()
            engine.load(f.name)
            result = engine.validate(
                entity_type="Sample",
                operation="create",
                entity_data={"name": "", "age": -5},
            )
            assert result.is_valid is False
            assert len(result.errors) == 2
            os.unlink(f.name)

    def test_validator_engine_entity_type_filtering(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(
                """
validators:
  - name: sample_only
    entity_types: [Sample]
    'on': [create]
    condition: "entity.name != ''"
  - name: all_types
    entity_types: []
    'on': [create]
    condition: "entity.name != ''"
"""
            )
            f.flush()
            engine = ValidatorEngine()
            engine.load(f.name)
            result = engine.validate(
                entity_type="OtherType",
                operation="create",
                entity_data={"name": "test"},
            )
            assert result.is_valid is True
            os.unlink(f.name)

    def test_validator_engine_operation_filtering(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(
                """validators:
  - name: create_only
    entity_types: [Sample]
    'on': [create]
    condition: "entity.name != ''"
"""
            )
            f.flush()
            engine = ValidatorEngine()
            engine.load(f.name)
            result = engine.validate(
                entity_type="Sample",
                operation="delete",
                entity_data={"name": ""},
            )
            assert result.is_valid is True
            os.unlink(f.name)

    def test_validator_engine_priority_ordering(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(
                """
validators:
  - name: second
    entity_types: [Sample]
    'on': [create]
    priority: 1
    condition: "entity.age > 0"
  - name: first
    entity_types: [Sample]
    'on': [create]
    priority: 0
    condition: "entity.name != ''"
"""
            )
            f.flush()
            engine = ValidatorEngine()
            engine.load(f.name)
            assert engine.rules[0].name == "second"
            assert engine.rules[1].name == "first"
            os.unlink(f.name)


class TestValidatorEngineWhenCondition:
    def test_validator_engine_when_condition(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(
                """
validators:
  - name: conditional
    entity_types: [Sample]
    'on': [create]
    when: "entity.is_active == true"
    condition: "entity.name != ''"
"""
            )
            f.flush()
            engine = ValidatorEngine()
            engine.load(f.name)
            result = engine.validate(
                entity_type="Sample",
                operation="create",
                entity_data={"name": "test", "is_active": True},
            )
            assert result.is_valid is True
            os.unlink(f.name)

    def test_validator_engine_when_condition_skips(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(
                """
validators:
  - name: conditional
    entity_types: [Sample]
    'on': [create]
    when: "entity.is_active == true"
    condition: "entity.name != ''"
"""
            )
            f.flush()
            engine = ValidatorEngine()
            engine.load(f.name)
            result = engine.validate(
                entity_type="Sample",
                operation="create",
                entity_data={"name": "", "is_active": False},
            )
            assert result.is_valid is True
            os.unlink(f.name)
