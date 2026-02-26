"""Health check endpoint."""

from fastapi import APIRouter

from app.config import get_settings
from app.models.audit import get_session_factory
from app.models.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    odoo_ok = False
    redis_ok = False
    db_ok = False

    try:
        from app.odoo_client import get_odoo_client

        client = get_odoo_client()
        client.version()
        odoo_ok = True
    except Exception:
        pass

    try:
        import redis as redis_lib

        settings = get_settings()
        r = redis_lib.from_url(settings.redis_url)
        r.ping()
        redis_ok = True
    except Exception:
        pass

    try:
        from sqlalchemy import text

        Session = get_session_factory()
        session = Session()
        session.execute(text("SELECT 1"))
        session.close()
        db_ok = True
    except Exception:
        pass

    return HealthResponse(
        status="healthy" if all([odoo_ok, redis_ok, db_ok]) else "degraded",
        odoo_connected=odoo_ok,
        redis_connected=redis_ok,
        db_connected=db_ok,
    )
