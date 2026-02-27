"""
Slack interaction endpoint — receives button clicks from Slack interactive messages.

Slack sends interaction payloads as application/x-www-form-urlencoded with a
JSON-encoded `payload` field. This router verifies the Slack signing secret,
parses the action, and routes approve/reject to the existing approval workflow.
"""

import hashlib
import hmac
import json
import time
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy.orm import Session
import structlog

from app.config import get_settings
from app.models.audit import AuditLog, ActionStatus, get_db_session
from app.tasks.celery_tasks import execute_approved_action

logger = structlog.get_logger()

router = APIRouter(prefix="/api/slack", tags=["slack"])


def _verify_slack_signature(
    body: bytes,
    timestamp: str,
    signature: str,
) -> bool:
    """Verify the request came from Slack using the signing secret."""
    settings = get_settings()
    if not settings.slack_signing_secret:
        logger.warning("slack_signing_secret_not_configured")
        return False

    if abs(time.time() - float(timestamp)) > 300:
        return False

    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    expected = (
        "v0="
        + hmac.new(
            settings.slack_signing_secret.encode(),
            sig_basestring.encode(),
            hashlib.sha256,
        ).hexdigest()
    )
    return hmac.compare_digest(expected, signature)


@router.post("/interactions")
async def handle_slack_interaction(request: Request):
    """
    Handle Slack interactive component payloads (button clicks, menu selects).

    Slack sends POST with Content-Type: application/x-www-form-urlencoded
    containing a `payload` field with a JSON string.
    """
    body = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    if signature and not _verify_slack_signature(body, timestamp, signature):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    form = await request.form()
    payload_str = form.get("payload")
    if not payload_str:
        raise HTTPException(status_code=400, detail="Missing payload")

    try:
        payload = json.loads(payload_str)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid payload JSON")

    payload_type = payload.get("type")
    if payload_type == "block_actions":
        return _handle_block_actions(payload)

    logger.info("slack_unhandled_payload_type", type=payload_type)
    return Response(status_code=200)


def _handle_block_actions(payload: dict) -> dict:
    """Route block action button clicks to the right handler."""
    actions = payload.get("actions", [])
    user = payload.get("user", {})
    slack_user = user.get("username", user.get("name", "slack_user"))

    for action in actions:
        action_id = action.get("action_id", "")
        value = action.get("value", "")

        if action_id == "approve_action":
            return _process_approval(
                audit_log_id=int(value),
                approved=True,
                approved_by=slack_user,
                payload=payload,
            )
        elif action_id == "reject_action":
            return _process_approval(
                audit_log_id=int(value),
                approved=False,
                approved_by=slack_user,
                payload=payload,
            )
        else:
            logger.info("slack_unknown_action", action_id=action_id)

    return {"text": "Action received"}


def _process_approval(
    audit_log_id: int,
    approved: bool,
    approved_by: str,
    payload: dict,
) -> dict:
    """Process an approve/reject action from Slack and update the original message."""
    with get_db_session() as session:
        audit = session.get(AuditLog, audit_log_id)

        if not audit:
            _update_slack_message(
                payload, f"Action #{audit_log_id} not found."
            )
            return {"text": f"Action #{audit_log_id} not found"}

        if audit.status != ActionStatus.PENDING:
            _update_slack_message(
                payload,
                f"Action #{audit_log_id} is no longer pending (status: {audit.status}).",
            )
            return {"text": f"Action already {audit.status}"}

        if approved:
            audit.status = ActionStatus.APPROVED
            audit.approved_by = approved_by
            session.flush()
            execute_approved_action.delay(audit.id)
            _update_slack_message(
                payload,
                f"\u2705 *Approved* by {approved_by}\n"
                f"`{audit.action_name}` on `{audit.odoo_model}` #{audit.odoo_record_id}\n"
                f"_Queued for execution._",
            )
            logger.info(
                "slack_approval_approved",
                audit_log_id=audit_log_id,
                by=approved_by,
            )
            return {"text": "Approved"}
        else:
            audit.status = ActionStatus.REJECTED
            audit.approved_by = approved_by
            _update_slack_message(
                payload,
                f"\u274c *Rejected* by {approved_by}\n"
                f"`{audit.action_name}` on `{audit.odoo_model}` #{audit.odoo_record_id}",
            )
            logger.info(
                "slack_approval_rejected",
                audit_log_id=audit_log_id,
                by=approved_by,
            )
            return {"text": "Rejected"}


def _update_slack_message(payload: dict, replacement_text: str):
    """Replace the original Slack message with a status update (removes buttons)."""
    settings = get_settings()
    if not settings.slack_enabled:
        return

    response_url = payload.get("response_url")
    if not response_url:
        return

    try:
        import httpx

        httpx.post(
            response_url,
            json={
                "replace_original": "true",
                "blocks": [
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": replacement_text},
                    },
                ],
            },
            timeout=10,
        )
    except Exception as exc:
        logger.warning("slack_message_update_failed", error=str(exc))
