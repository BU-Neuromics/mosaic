"""CEL Validator Engine - Exception Classes."""

from typing import Any, Optional


class ValidationError(Exception):
    """Base exception class for CEL validation errors."""

    def __init__(self, message: str, **context: Any):
        self.message = message
        self.context = context
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        if self.context:
            context_str = ", ".join(f"{k}={v!r}" for k, v in self.context.items())
            return f"{self.message} ({context_str})"
        return self.message


class CELParseError(ValidationError):
    """Exception raised for CEL syntax/parsing errors.

    Contains line number information for locating errors in validators.yaml.
    """

    def __init__(
        self,
        message: str,
        line_number: Optional[int] = None,
        expression: Optional[str] = None,
        **context: Any,
    ):
        self.line_number = line_number
        self.expression = expression
        context["line_number"] = line_number
        context["expression"] = expression
        super().__init__(message, **context)


class CELEvaluationError(ValidationError):
    """Exception raised for CEL runtime evaluation errors.

    Contains field reference information for locating errors in entity data.
    """

    def __init__(
        self,
        message: str,
        field_reference: Optional[str] = None,
        expression: Optional[str] = None,
        **context: Any,
    ):
        self.field_reference = field_reference
        self.expression = expression
        context["field_reference"] = field_reference
        context["expression"] = expression
        super().__init__(message, **context)
