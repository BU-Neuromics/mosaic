"""Mosaic API module.

Provides FastAPI application factory and related components for the REST API transport layer.
"""

from mosaic.api.exceptions import EntityNotFoundError
from mosaic.api.factory import create_app
from mosaic.api.schemas import ErrorResponse

__all__ = ["create_app", "EntityNotFoundError", "ErrorResponse"]
