"""
API key authentication dependency for FastAPI endpoints.
"""

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

from app.config import get_settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(
    api_key: str | None = Security(_api_key_header),
) -> str:
    """Validate the X-API-Key header against the configured secret."""
    settings = get_settings()
    if not api_key or api_key != settings.ai_secret_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
        )
    return api_key
