"""
Webhook endpoint handlers — receives events from Odoo and dispatches to Celery.
"""

import hmac
import hashlib
from datetime import datetime

from fastapi import APIRouter, Request, HTTPException, Depends
import structlog

from app.config import get_settings, Settings
from app.models.schemas import WebhookPayload
from app.models.audit import get_session_factory, WebhookEvent
from app.tasks.celery_tasks import process_webhook_event

logger = structlog.get_logger()
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


async def verify_webhook_signature(request: Request, settings: Settings):
    signature = request.headers.get("X-Webhook-Signature", "")
    if not signature:
        return
    body = await request.body()
    expected = hmac.new(
        settings.webhook_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")


@router.post("/odoo")
async def receive_odoo_webhook(payload: WebhookPayload, request: Request):
    """
    Receives webhook events from the Odoo AI Bridge module.
    Stores the event and dispatches it to Celery for async processing.
    """
    settings = get_settings()
    await verify_webhook_signature(request, settings)

    Session = get_session_factory()
    session = Session()

    try:
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
        session.commit()
        event_id = event.id

        process_webhook_event.delay(event_id)

        logger.info(
            "webhook_received",
            event_type=payload.event_type,
            model=payload.model,
            record_id=payload.record_id,
        )

        return {"status": "queued", "event_id": event_id}

    except Exception as exc:
        session.rollback()
        logger.error("webhook_store_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to process webhook")
    finally:
        session.close()


@router.post("/odoo/batch")
async def receive_odoo_webhook_batch(payloads: list[WebhookPayload]):
    """Receive multiple webhook events in a single request."""
    Session = get_session_factory()
    session = Session()
    event_ids = []

    try:
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

        session.commit()

        for eid in event_ids:
            process_webhook_event.delay(eid)

        return {"status": "queued", "event_ids": event_ids}

    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        session.close()
