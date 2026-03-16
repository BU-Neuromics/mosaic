"""Tests for validation module."""

import pytest

from hippo.core.validation import (
    ValidationResult,
    WriteOperation,
    WriteValidator,
    ValidatorPipeline,
    ValidatorRegistry,
)


class TestValidationResult:
    def test_validation_result_valid(self):
        result = ValidationResult(is_valid=True, errors=[])
        assert result.is_valid is True
        assert result.errors == []

    def test_validation_result_invalid_with_errors(self):
        result = ValidationResult(is_valid=False, errors=["Error 1", "Error 2"])
        assert result.is_valid is False
        assert result.errors == ["Error 1", "Error 2"]

    def test_validation_result_with_string_conversion(self):
        result = ValidationResult(is_valid=False, errors="single error")
        assert result.errors == ["single error"]

    def test_validation_result_with_tuple_conversion(self):
        result = ValidationResult(is_valid=True, errors=("a", "b"))
        assert result.errors == ["a", "b"]

    def test_validation_result_is_valid_must_be_bool(self):
        with pytest.raises(TypeError, match="is_valid must be a boolean"):
            ValidationResult(is_valid="true", errors=[])

    def test_validation_result_errors_must_be_iterable(self):
        with pytest.raises(TypeError, match="errors must be an iterable"):
            ValidationResult(is_valid=True, errors=123)


class TestWriteOperation:
    def test_write_operation_valid(self):
        op = WriteOperation(
            operation="insert", entity_type="sample", data={"name": "test"}
        )
        assert op.operation == "insert"
        assert op.entity_type == "sample"
        assert op.data == {"name": "test"}

    def test_write_operation_with_empty_data(self):
        op = WriteOperation(operation="update", entity_type="sample", data={})
        assert op.data == {}

    def test_write_operation_operation_must_be_string(self):
        with pytest.raises(TypeError, match="operation must be a string"):
            WriteOperation(operation=123, entity_type="sample", data={})

    def test_write_operation_entity_type_must_be_string(self):
        with pytest.raises(TypeError, match="entity_type must be a string"):
            WriteOperation(operation="insert", entity_type=123, data={})

    def test_write_operation_data_must_be_dict(self):
        with pytest.raises(TypeError, match="data must be a dictionary"):
            WriteOperation(operation="insert", entity_type="sample", data="{}")


class TestWriteValidatorABC:
    def test_cannot_instantiate_abstract_validator(self):
        with pytest.raises(TypeError):
            WriteValidator()

    def test_concrete_validator_must_implement_validate(self):
        class IncompleteValidator(WriteValidator):
            pass

        with pytest.raises(TypeError):
            IncompleteValidator()

    def test_concrete_validator_implementation(self):
        class ConcreteValidator(WriteValidator):
            def validate(self, operation: WriteOperation) -> ValidationResult:
                if not operation.data.get("name"):
                    return ValidationResult(is_valid=False, errors=["name is required"])
                return ValidationResult(is_valid=True, errors=[])

        validator = ConcreteValidator()
        assert isinstance(validator, WriteValidator)

        valid_op = WriteOperation(
            operation="insert", entity_type="sample", data={"name": "test"}
        )
        result = validator.validate(valid_op)
        assert result.is_valid is True

        invalid_op = WriteOperation(operation="insert", entity_type="sample", data={})
        result = validator.validate(invalid_op)
        assert result.is_valid is False
        assert "name is required" in result.errors

    def test_validator_default_priority_is_zero(self):
        class ConcreteValidator(WriteValidator):
            def validate(self, operation: WriteOperation) -> ValidationResult:
                return ValidationResult(is_valid=True)

        validator = ConcreteValidator()
        assert validator.priority == 0

    def test_validator_custom_priority(self):
        class HighPriorityValidator(WriteValidator):
            @property
            def priority(self) -> int:
                return 10

            def validate(self, operation: WriteOperation) -> ValidationResult:
                return ValidationResult(is_valid=True)

        validator = HighPriorityValidator()
        assert validator.priority == 10


class TestValidatorRegistry:
    def test_registry_get_validators_returns_list(self):
        registry = ValidatorRegistry()
        result = registry.get_validators()
        assert isinstance(result, list)

    def test_registry_discovers_validators(self):
        registry = ValidatorRegistry()
        validators = registry.get_validators()
        assert isinstance(validators, list)

    def test_registry_empty_when_no_validators(self, monkeypatch):
        import sys
        from unittest.mock import MagicMock, patch

        mock_eps = MagicMock()
        mock_eps.select.return_value = []
        mock_eps.get.return_value = []

        class MockEntryPoints:
            def select(self, group=None):
                return []

            def get(self, group, default=None):
                return []

        with patch(
            "hippo.core.validation.validators.entry_points",
            return_value=MockEntryPoints(),
        ):
            registry = ValidatorRegistry()
            validators = registry.get_validators()
            assert validators == []

    def test_registry_validators_ordered_by_priority_descending(self):
        class LowPriorityValidator(WriteValidator):
            @property
            def priority(self) -> int:
                return 5

            def validate(self, operation: WriteOperation) -> ValidationResult:
                return ValidationResult(is_valid=True)

        class HighPriorityValidator(WriteValidator):
            @property
            def priority(self) -> int:
                return 10

            def validate(self, operation: WriteOperation) -> ValidationResult:
                return ValidationResult(is_valid=True)

        class MediumPriorityValidator(WriteValidator):
            @property
            def priority(self) -> int:
                return 7

            def validate(self, operation: WriteOperation) -> ValidationResult:
                return ValidationResult(is_valid=True)

        from unittest.mock import MagicMock

        mock_ep1 = MagicMock()
        mock_ep1.load.return_value = LowPriorityValidator

        mock_ep2 = MagicMock()
        mock_ep2.load.return_value = HighPriorityValidator

        mock_ep3 = MagicMock()
        mock_ep3.load.return_value = MediumPriorityValidator

        class MockEntryPoints:
            def select(self, group=None):
                return [mock_ep2, mock_ep1, mock_ep3]

        from unittest.mock import patch

        with patch(
            "hippo.core.validation.validators.entry_points",
            return_value=MockEntryPoints(),
        ):
            registry = ValidatorRegistry()
            validators = registry.get_validators()
            assert len(validators) == 3
            assert validators[0].priority == 10
            assert validators[1].priority == 7
            assert validators[2].priority == 5


class TestValidatorPipeline:
    def test_pipeline_execute_returns_list_of_results(self):
        class TestValidator(WriteValidator):
            def validate(self, operation: WriteOperation) -> ValidationResult:
                return ValidationResult(is_valid=True)

        class MockRegistry:
            def get_validators(self):
                return [TestValidator()]

        pipeline = ValidatorPipeline(registry=MockRegistry())
        op = WriteOperation(
            operation="insert", entity_type="sample", data={"name": "test"}
        )
        results = pipeline.execute(op)
        assert isinstance(results, list)
        assert len(results) == 1

    def test_pipeline_validates_all_validators(self):
        call_count = 0

        class CountingValidator(WriteValidator):
            def validate(self, operation: WriteOperation) -> ValidationResult:
                nonlocal call_count
                call_count += 1
                return ValidationResult(is_valid=True)

        class MockRegistry:
            def get_validators(self):
                return [CountingValidator(), CountingValidator()]

        pipeline = ValidatorPipeline(registry=MockRegistry())
        op = WriteOperation(
            operation="insert", entity_type="sample", data={"name": "test"}
        )
        results = pipeline.execute(op)
        assert call_count == 2

    def test_pipeline_validate_aggregates_results(self):
        class FailingValidator(WriteValidator):
            def validate(self, operation: WriteOperation) -> ValidationResult:
                return ValidationResult(is_valid=False, errors=["error 1"])

        class PassingValidator(WriteValidator):
            def validate(self, operation: WriteOperation) -> ValidationResult:
                return ValidationResult(is_valid=True, errors=[])

        class MockRegistry:
            def get_validators(self):
                return [FailingValidator(), PassingValidator()]

        pipeline = ValidatorPipeline(registry=MockRegistry())
        op = WriteOperation(
            operation="insert", entity_type="sample", data={"name": "test"}
        )
        result = pipeline.validate(op)
        assert result.is_valid is False
        assert "error 1" in result.errors

    def test_pipeline_validate_all_pass_returns_success(self):
        class PassingValidator(WriteValidator):
            def validate(self, operation: WriteOperation) -> ValidationResult:
                return ValidationResult(is_valid=True)

        class MockRegistry:
            def get_validators(self):
                return [PassingValidator(), PassingValidator()]

        pipeline = ValidatorPipeline(registry=MockRegistry())
        op = WriteOperation(
            operation="insert", entity_type="sample", data={"name": "test"}
        )
        result = pipeline.validate(op)
        assert result.is_valid is True
        assert result.errors == []
