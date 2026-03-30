"""Health check router."""
from fastapi import APIRouter, status
from datetime import datetime

from models.schemas import HealthResponse
from config import config

router = APIRouter()


@router.get("/health", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def health_check():
    """
    Health check endpoint.

    Returns service status and timestamp.
    """
    return HealthResponse(
        status="healthy",
        service=config.SERVICE_NAME,
        timestamp=datetime.utcnow()
    )


@router.get("/", response_model=dict, status_code=status.HTTP_200_OK)
async def root():
    """Root endpoint."""
    return {
        "service": config.SERVICE_NAME,
        "version": "1.0.0",
        "status": "running"
    }
