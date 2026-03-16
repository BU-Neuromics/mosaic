"""Hippo API module.

Provides FastAPI application factory and related components for the REST API transport layer.
"""

from hippo.api.exceptions import EntityNotFoundError
from hippo.api.factory import create_app
from hippo.api.schemas import ErrorResponse

__all__ = ["create_app", "EntityNotFoundError", "ErrorResponse"]
