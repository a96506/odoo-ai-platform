"""
Webhook endpoint handlers — receives events from Odoo and dispatches to Celery.
"""

import hmac
import hashlib
from datetime import datetime

from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
import structlog

from app.config import get_settings, Settings
from app.models.schemas import WebhookPayload
from app.models.audit import WebhookEvent, get_db
from app.tasks.celery_tasks import process_webhook_event

logger = structlog.get_logger()
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


async def verify_webhook_signature(request: Request):
    """Verify HMAC-SHA256 signature on every incoming webhook. Rejects unsigned requests."""
    settings = get_settings()
    signature = request.headers.get("X-Webhook-Signature")
    if not signature:
        raise HTTPException(status_code=401, detail="Missing webhook signature")
    body = await request.body()
    expected = hmac.new(
        settings.webhook_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")


@router.post("/odoo")
async def receive_odoo_webhook(
    payload: WebhookPayload,
    request: Request,
    session: Session = Depends(get_db),
):
    """
    Receives webhook events from the Odoo AI Bridge module.
    Stores the event and dispatches it to Celery for async processing.
    """
    await verify_webhook_signature(request)

    event = WebhookEvent(
        received_at=datetime.utcnow(),
        event_type=payload.event_type,
        odoo_model=payload.model,
        odoo_record_id=payload.record_id,
        payload={
            "values": payload.values,
            "old_values": payload.old_values,
            "user_id": payload.user_id,
        },
    )
    session.add(event)
    session.flush()
    event_id = event.id

    process_webhook_event.delay(event_id)

    logger.info(
        "webhook_received",
        event_type=payload.event_type,
        model=payload.model,
        record_id=payload.record_id,
    )

    return {"status": "queued", "event_id": event_id}


@router.post("/odoo/batch")
async def receive_odoo_webhook_batch(
    payloads: list[WebhookPayload],
    request: Request,
    session: Session = Depends(get_db),
):
    """Receive multiple webhook events in a single request."""
    await verify_webhook_signature(request)
    event_ids = []

    for payload in payloads:
        event = WebhookEvent(
            received_at=datetime.utcnow(),
            event_type=payload.event_type,
            odoo_model=payload.model,
            odoo_record_id=payload.record_id,
            payload={
                "values": payload.values,
                "old_values": payload.old_values,
                "user_id": payload.user_id,
            },
        )
        session.add(event)
        session.flush()
        event_ids.append(event.id)

    for eid in event_ids:
        process_webhook_event.delay(eid)

    return {"status": "queued", "event_ids": event_ids}
