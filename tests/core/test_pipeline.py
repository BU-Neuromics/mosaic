"""Tests for ValidationPipeline and HippoClient."""

import pytest

from hippo.core.client import HippoClient
from hippo.core.exceptions import ValidationFailure
from hippo.core.pipeline import ValidationPipeline, create_pipeline
from hippo.core.validation import (
    ValidationResult,
    WriteOperation,
    WriteValidator,
)


class TestValidationPipeline:
    """Tests for the ValidationPipeline class."""

    def test_pipeline_empty_initially(self):
        pipeline = ValidationPipeline()
        assert pipeline.get_validator_count() == 0

    def test_add_validator(self):
        class TestValidator(WriteValidator):
            def validate(self, operation: WriteOperation) -> ValidationResult:
                return ValidationResult(is_valid=True)

        pipeline = ValidationPipeline()
        pipeline.add_validator(TestValidator())
        assert pipeline.get_validator_count() == 1

    def test_execute_with_no_validators_returns_success(self):
        pipeline = ValidationPipeline()
        op = WriteOperation(
            operation="insert", entity_type="sample", data={"id": "123"}
        )
        result = pipeline.execute(op)
        assert result.is_valid is True

    def test_execute_fail_fast_on_first_failure(self):
        call_order = []

        class FirstValidator(WriteValidator):
            def validate(self, operation: WriteOperation) -> ValidationResult:
                call_order.append("first")
                return ValidationResult(is_valid=False, errors=["First error"])

        class SecondValidator(WriteValidator):
            def validate(self, operation: WriteOperation) -> ValidationResult:
                call_order.append("second")
                return ValidationResult(is_valid=True)

        pipeline = ValidationPipeline()
        pipeline.add_validator(FirstValidator())
        pipeline.add_validator(SecondValidator())

        op = WriteOperation(
            operation="insert", entity_type="sample", data={"id": "123"}
        )
        result = pipeline.execute(op)

        assert result.is_valid is False
        assert "First error" in result.errors
        assert call_order == ["first"]

    def test_execute_all_reports_all_failures(self):
        call_order = []

        class FirstValidator(WriteValidator):
            def validate(self, operation: WriteOperation) -> ValidationResult:
                call_order.append("first")
                return ValidationResult(is_valid=False, errors=["First error"])

        class SecondValidator(WriteValidator):
            def validate(self, operation: WriteOperation) -> ValidationResult:
                call_order.append("second")
                return ValidationResult(is_valid=False, errors=["Second error"])

        pipeline = ValidationPipeline()
        pipeline.add_validator(FirstValidator())
        pipeline.add_validator(SecondValidator())

        op = WriteOperation(
            operation="insert", entity_type="sample", data={"id": "123"}
        )
        result = pipeline.execute_all(op)

        assert result.is_valid is False
        assert "First error" in result.errors
        assert "Second error" in result.errors
        assert call_order == ["first", "second"]

    def test_execute_all_success_when_all_pass(self):
        class PassingValidator(WriteValidator):
            def validate(self, operation: WriteOperation) -> ValidationResult:
                return ValidationResult(is_valid=True)

        pipeline = ValidationPipeline()
        pipeline.add_validator(PassingValidator())
        pipeline.add_validator(PassingValidator())

        op = WriteOperation(
            operation="insert", entity_type="sample", data={"id": "123"}
        )
        result = pipeline.execute_all(op)
        assert result.is_valid is True

    def test_validator_order_preserved(self):
        order = []

        class FirstValidator(WriteValidator):
            def validate(self, operation: WriteOperation) -> ValidationResult:
                order.append(1)
                return ValidationResult(is_valid=True)

        class SecondValidator(WriteValidator):
            def validate(self, operation: WriteOperation) -> ValidationResult:
                order.append(2)
                return ValidationResult(is_valid=True)

        pipeline = ValidationPipeline()
        pipeline.add_validator(FirstValidator())
        pipeline.add_validator(SecondValidator())

        op = WriteOperation(
            operation="insert", entity_type="sample", data={"id": "123"}
        )
        pipeline.execute(op)

        assert order == [1, 2]

    def test_exactly_once_execution(self):
        call_count = 0

        class CountingValidator(WriteValidator):
            def validate(self, operation: WriteOperation) -> ValidationResult:
                nonlocal call_count
                call_count += 1
                return ValidationResult(is_valid=True)

        pipeline = ValidationPipeline()
        pipeline.add_validator(CountingValidator())

        op = WriteOperation(
            operation="insert", entity_type="sample", data={"id": "123"}
        )
        pipeline.execute(op)
        assert call_count == 1

        pipeline.execute(op)
        assert call_count == 2

    def test_clear_validators(self):
        class TestValidator(WriteValidator):
            def validate(self, operation: WriteOperation) -> ValidationResult:
                return ValidationResult(is_valid=True)

        pipeline = ValidationPipeline()
        pipeline.add_validator(TestValidator())
        assert pipeline.get_validator_count() == 1

        pipeline.clear_validators()
        assert pipeline.get_validator_count() == 0

    def test_exception_handling_in_execute(self):
        class ExceptionValidator(WriteValidator):
            def validate(self, operation: WriteOperation) -> ValidationResult:
                raise RuntimeError("Unexpected error")

        pipeline = ValidationPipeline()
        pipeline.add_validator(ExceptionValidator())

        op = WriteOperation(
            operation="insert", entity_type="sample", data={"id": "123"}
        )
        result = pipeline.execute(op)

        assert result.is_valid is False
        assert "Unexpected error" in result.errors[0]

    def test_get_validators_returns_copy(self):
        class TestValidator(WriteValidator):
            def validate(self, operation: WriteOperation) -> ValidationResult:
                return ValidationResult(is_valid=True)

        pipeline = ValidationPipeline()
        pipeline.add_validator(TestValidator())

        validators = pipeline.get_validators()
        assert len(validators) == 1

        validators.clear()
        assert pipeline.get_validator_count() == 1


class TestCreatePipeline:
    """Tests for the create_pipeline helper function."""

    def test_create_empty_pipeline(self):
        pipeline = create_pipeline()
        assert pipeline.get_validator_count() == 0

    def test_create_pipeline_with_validators(self):
        class TestValidator(WriteValidator):
            def validate(self, operation: WriteOperation) -> ValidationResult:
                return ValidationResult(is_valid=True)

        pipeline = create_pipeline([TestValidator()])
        assert pipeline.get_validator_count() == 1


class TestHippoClientValidation:
    """Tests for HippoClient validation integration."""

    def test_client_without_pipeline_allows_writes(self):
        client = HippoClient()
        op = WriteOperation(
            operation="insert", entity_type="sample", data={"id": "123"}
        )
        result = client.validate(op)
        assert result.is_valid is True

    def test_client_with_bypass_validation_flag(self):
        client = HippoClient(bypass_validation=True)
        op = WriteOperation(
            operation="insert", entity_type="sample", data={"id": "123"}
        )
        result = client.validate(op)
        assert result.is_valid is True

    def test_client_with_pipeline_validates(self):
        class FailingValidator(WriteValidator):
            def validate(self, operation: WriteOperation) -> ValidationResult:
                return ValidationResult(is_valid=False, errors=["Validation failed"])

        pipeline = ValidationPipeline()
        pipeline.add_validator(FailingValidator())

        client = HippoClient(pipeline=pipeline)
        op = WriteOperation(
            operation="insert", entity_type="sample", data={"id": "123"}
        )
        result = client.validate(op)

        assert result.is_valid is False
        assert "Validation failed" in result.errors

    def test_client_add_validator_creates_pipeline(self):
        class TestValidator(WriteValidator):
            def validate(self, operation: WriteOperation) -> ValidationResult:
                return ValidationResult(is_valid=True)

        client = HippoClient()
        assert client.pipeline is None

        client.add_validator(TestValidator())
        assert client.pipeline is not None
        assert client.pipeline.get_validator_count() == 1


class TestHippoClientWriteOperations:
    """Tests for HippoClient write operations with validation."""

    def test_create_success(self):
        client = HippoClient()
        result = client.create("Sample", {"id": "123", "name": "test"})
        assert result["id"] == "123"

    def test_create_with_validation_failure_raises_exception(self):
        class FailingValidator(WriteValidator):
            def validate(self, operation: WriteOperation) -> ValidationResult:
                return ValidationResult(is_valid=False, errors=["Invalid data"])

        pipeline = ValidationPipeline()
        pipeline.add_validator(FailingValidator())

        client = HippoClient(pipeline=pipeline)

        with pytest.raises(ValidationFailure) as exc_info:
            client.create("Sample", {"id": "123"})
        assert "Invalid data" in str(exc_info.value)

    def test_create_with_bypass_validation(self):
        class FailingValidator(WriteValidator):
            def validate(self, operation: WriteOperation) -> ValidationResult:
                return ValidationResult(is_valid=False, errors=["Invalid data"])

        pipeline = ValidationPipeline()
        pipeline.add_validator(FailingValidator())

        client = HippoClient(pipeline=pipeline)
        result = client.create("Sample", {"id": "123"}, bypass_validation=True)
        assert result["id"] == "123"

    def test_update_success(self):
        client = HippoClient()
        result = client.update("Sample", "123", {"name": "updated"})
        assert result["id"] == "123"

    def test_delete_success(self):
        client = HippoClient()
        result = client.delete("Sample", "123")
        assert result is True
