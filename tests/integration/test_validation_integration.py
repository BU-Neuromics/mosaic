"""Integration tests for write path with validation."""

import pytest

from hippo.core.ingestion import IngestionPipeline
from hippo.core.validation import (
    ExecutorConfig,
    ValidationResult,
    ValidatorContext,
    ValidatorExecutor,
    WriteOperation,
    WriteValidator,
)


class FailingValidator(WriteValidator):
    """Validator that always fails for testing."""

    def __init__(self, error_message: str = "Validation failed"):
        self.error_message = error_message

    def validate(self, operation: WriteOperation) -> ValidationResult:
        return ValidationResult(
            is_valid=False,
            errors=[self.error_message],
            entity_id=operation.data.get("id"),
        )


class PassingValidator(WriteValidator):
    """Validator that always passes for testing."""

    def validate(self, operation: WriteOperation) -> ValidationResult:
        return ValidationResult(is_valid=True)


class TestIngestionPipelineWithValidation:
    """Integration tests for IngestionPipeline with validation."""

    def test_ingestion_pipeline_without_validation(self):
        """Test that ingestion pipeline works without validator executor."""
        client = None
        pipeline = IngestionPipeline(client=client, validation_enabled=False)

        assert pipeline._validation_enabled is False

    def test_ingestion_pipeline_with_validation_disabled(self):
        """Test that validation can be disabled on pipeline."""
        client = None
        executor = ValidatorExecutor()

        pipeline = IngestionPipeline(
            client=client,
            validator_executor=executor,
            validation_enabled=False,
        )

        assert pipeline._validation_enabled is False

    def test_before_write_validation_with_disabled_validation(self):
        """Test that validation is skipped when disabled."""
        client = None
        executor = ValidatorExecutor()
        executor.add_validator(FailingValidator())

        pipeline = IngestionPipeline(
            client=client,
            validator_executor=executor,
            validation_enabled=False,
        )

        pipeline.before_write_validation("Sample", {"id": "123"}, "create")

    def test_before_write_validation_with_enabled_validation(self):
        """Test that validation runs when enabled."""
        client = None
        executor = ValidatorExecutor()
        executor.add_validator(PassingValidator())

        pipeline = IngestionPipeline(
            client=client,
            validator_executor=executor,
            validation_enabled=True,
        )

        pipeline.before_write_validation("Sample", {"id": "123"}, "create")

    def test_enable_validation_toggle(self):
        """Test enabling and disabling validation dynamically."""
        client = None

        pipeline = IngestionPipeline(client=client, validation_enabled=False)
        assert pipeline._validation_enabled is False

        pipeline.enable_validation(True)
        assert pipeline._validation_enabled is True

        pipeline.enable_validation(False)
        assert pipeline._validation_enabled is False


class TestValidatorExecutorIntegration:
    """Integration tests for ValidatorExecutor with various scenarios."""

    def test_executor_with_realistic_workflow(self):
        """Test executor with a realistic validation workflow."""
        executor = ExecutorConfig(fail_fast=True, enabled=True)
        validator_exec = ValidatorExecutor(config=executor)

        class NameRequiredValidator(WriteValidator):
            def validate(self, operation: WriteOperation) -> ValidationResult:
                if not operation.data.get("name"):
                    return ValidationResult(
                        is_valid=False,
                        errors=["name is required"],
                        entity_id=operation.data.get("id"),
                    )
                return ValidationResult(is_valid=True)

        validator_exec.add_validator(NameRequiredValidator())

        op = WriteOperation(
            operation="insert", entity_type="Sample", data={"id": "123"}
        )
        result = validator_exec.execute(op)
        assert result.is_valid is False
        assert "name is required" in result.errors

        op_with_name = WriteOperation(
            operation="insert", entity_type="Sample", data={"id": "123", "name": "test"}
        )
        result = validator_exec.execute(op_with_name)
        assert result.is_valid is True

    def test_context_mutation_chain(self):
        """Test that context mutations propagate through validators."""
        executor = ValidatorExecutor()

        class UppercaseNameValidator(WriteValidator):
            def validate(self, operation: WriteOperation) -> ValidationResult:
                if "name" in operation.data:
                    operation.data["name"] = operation.data["name"].upper()
                return ValidationResult(is_valid=True)

        class VerifyUppercaseValidator(WriteValidator):
            def validate(self, operation: WriteOperation) -> ValidationResult:
                name = operation.data.get("name", "")
                if name != name.upper():
                    return ValidationResult(
                        is_valid=False,
                        errors=["Name should be uppercase"],
                        entity_id=operation.data.get("id"),
                    )
                return ValidationResult(is_valid=True)

        executor.add_validator(UppercaseNameValidator())
        executor.add_validator(VerifyUppercaseValidator())

        op = WriteOperation(
            operation="insert", entity_type="Sample", data={"id": "123", "name": "test"}
        )
        result = executor.execute(op)
        assert result.is_valid is True
        assert op.data["name"] == "TEST"


class TestValidatorExecutorTimeout:
    """Tests for validator timeout handling."""

    def test_timeout_with_fast_validator(self):
        """Test that validators completing before timeout succeed."""
        config = ExecutorConfig(timeout_seconds=5.0)
        executor = ValidatorExecutor(config=config)
        executor.add_validator(PassingValidator())

        op = WriteOperation(
            operation="insert", entity_type="Sample", data={"id": "123"}
        )
        result = executor.execute(op)
        assert result.is_valid is True
