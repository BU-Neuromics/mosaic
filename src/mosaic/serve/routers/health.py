"""Health check router for Mosaic API."""

from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict:
    """Health check endpoint.

    Returns:
        Health status information.
    """
    return {"status": "healthy", "service": "mosaic"}


@router.get("/")
async def root() -> dict:
    """Root endpoint.

    Returns:
        API information.
    """
    return {
        "service": "Mosaic API",
        "version": "0.1.0",
        "docs": "/docs",
    }
