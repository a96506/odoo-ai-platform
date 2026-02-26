"""Proactive AI Daily Digest API endpoints."""

from datetime import datetime, date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.models.audit import (
    DailyDigest,
    AuditLog,
    ActionStatus,
    AutomationType,
    get_db,
)
from app.models.schemas import (
    DigestResponse,
    DigestContent,
    DigestSendRequest,
    DigestSendResponse,
    DigestConfigRequest,
    DigestConfigResponse,
)
from app.automations.daily_digest import (
    DailyDigestAutomation,
    DEFAULT_DIGEST_CONFIG,
    ROLE_CONFIGS,
)

router = APIRouter(
    prefix="/api/digest",
    tags=["daily-digest"],
    dependencies=[Depends(require_api_key)],
)


@router.get("/latest", response_model=DigestResponse)
async def get_latest_digest(
    role: str = Query(..., description="Role: cfo, sales_manager, warehouse_manager"),
    session: Session = Depends(get_db),
):
    """Get the latest digest for a role, or generate one if none exists today."""
    if role not in ROLE_CONFIGS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown role: {role}. Available: {list(ROLE_CONFIGS.keys())}",
        )

    today = date.today()
    existing = (
        session.query(DailyDigest)
        .filter(DailyDigest.user_role == role, DailyDigest.digest_date == today)
        .first()
    )

    if existing:
        return DigestResponse(
            digest_id=existing.id,
            digest_date=existing.digest_date.isoformat(),
            role=existing.user_role,
            content=DigestContent(**(existing.content or {})),
            channels_sent=existing.channels_sent or [],
            delivered=existing.delivered or False,
            generated_at=existing.generated_at,
        )

    automation = DailyDigestAutomation()
    result = automation.generate_digest(role, today)

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    digest = DailyDigest(
        user_role=role,
        digest_date=today,
        content=result["content"],
        channels_sent=[],
        delivered=False,
    )
    session.add(digest)
    session.flush()

    audit = AuditLog(
        automation_type=AutomationType.REPORTING,
        action_name="generate_digest",
        odoo_model="daily.digest",
        odoo_record_id=digest.id,
        status=ActionStatus.EXECUTED,
        confidence=1.0,
        ai_reasoning=f"Daily digest generated for {role}: {result['content'].get('headline', '')}",
        executed_at=datetime.utcnow(),
    )
    session.add(audit)

    return DigestResponse(
        digest_id=digest.id,
        digest_date=today.isoformat(),
        role=role,
        content=DigestContent(**result["content"]),
        channels_sent=[],
        delivered=False,
        generated_at=digest.generated_at,
    )


@router.post("/send", response_model=DigestSendResponse)
async def send_digest(
    request: DigestSendRequest,
    session: Session = Depends(get_db),
):
    """Send a digest for a role via a specific channel."""
    if request.role not in ROLE_CONFIGS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown role: {request.role}. Available: {list(ROLE_CONFIGS.keys())}",
        )

    today = date.today()
    existing = (
        session.query(DailyDigest)
        .filter(DailyDigest.user_role == request.role, DailyDigest.digest_date == today)
        .first()
    )

    if not existing:
        automation = DailyDigestAutomation()
        result = automation.generate_digest(request.role, today)

        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])

        existing = DailyDigest(
            user_role=request.role,
            digest_date=today,
            content=result["content"],
            channels_sent=[],
            delivered=False,
        )
        session.add(existing)
        session.flush()

    automation = DailyDigestAutomation()
    recipient = request.recipient
    if not recipient:
        raise HTTPException(status_code=400, detail="Recipient is required for sending")

    sent = automation.deliver_digest(
        role=request.role,
        channel=request.channel,
        recipient=recipient,
        content=existing.content or {},
    )

    if sent:
        channels = existing.channels_sent or []
        if request.channel not in channels:
            channels.append(request.channel)
        existing.channels_sent = channels
        existing.delivered = True

    audit = AuditLog(
        automation_type=AutomationType.REPORTING,
        action_name="send_digest",
        odoo_model="daily.digest",
        odoo_record_id=existing.id,
        status=ActionStatus.EXECUTED if sent else ActionStatus.FAILED,
        ai_reasoning=f"Digest {'sent' if sent else 'failed'} to {recipient} via {request.channel}",
        executed_at=datetime.utcnow(),
    )
    session.add(audit)

    return DigestSendResponse(
        sent=sent,
        channel=request.channel,
        role=request.role,
    )


@router.put("/config", response_model=DigestConfigResponse)
async def update_digest_config(
    request: DigestConfigRequest,
    session: Session = Depends(get_db),
):
    """Update digest configuration for a role."""
    if request.role not in ROLE_CONFIGS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown role: {request.role}. Available: {list(ROLE_CONFIGS.keys())}",
        )

    DEFAULT_DIGEST_CONFIG[request.role] = {
        "channels": request.channels,
        "send_time": request.send_time,
        "enabled": request.enabled,
    }

    return DigestConfigResponse(
        updated=True,
        role=request.role,
        channels=request.channels,
        send_time=request.send_time,
    )


@router.get("/history", response_model=list[DigestResponse])
async def get_digest_history(
    role: str | None = None,
    limit: int = 7,
    session: Session = Depends(get_db),
):
    """Get digest history, optionally filtered by role."""
    query = session.query(DailyDigest)

    if role:
        if role not in ROLE_CONFIGS:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown role: {role}. Available: {list(ROLE_CONFIGS.keys())}",
            )
        query = query.filter(DailyDigest.user_role == role)

    digests = (
        query.order_by(DailyDigest.digest_date.desc())
        .limit(limit)
        .all()
    )

    return [
        DigestResponse(
            digest_id=d.id,
            digest_date=d.digest_date.isoformat(),
            role=d.user_role,
            content=DigestContent(**(d.content or {})),
            channels_sent=d.channels_sent or [],
            delivered=d.delivered or False,
            generated_at=d.generated_at,
        )
        for d in digests
    ]


@router.get("/preview", response_model=DigestResponse)
async def preview_digest(
    role: str = Query(..., description="Role: cfo, sales_manager, warehouse_manager"),
):
    """Preview a digest without saving or sending it."""
    if role not in ROLE_CONFIGS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown role: {role}. Available: {list(ROLE_CONFIGS.keys())}",
        )

    automation = DailyDigestAutomation()
    result = automation.generate_digest(role)

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return DigestResponse(
        digest_date=result["digest_date"],
        role=role,
        content=DigestContent(**result["content"]),
    )
