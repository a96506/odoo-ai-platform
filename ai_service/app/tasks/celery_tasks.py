"""
Celery task definitions for async automation processing.
"""

from datetime import datetime

import structlog

from app.tasks.celery_app import celery_app
from app.models.audit import (
    get_db_session,
    AuditLog,
    AutomationRule,
    WebhookEvent,
    ActionStatus,
)

logger = structlog.get_logger()


def _is_automation_enabled(session, automation_type: str, action_name: str | None = None) -> bool:
    """Check if any matching automation rule is enabled."""
    query = session.query(AutomationRule).filter(
        AutomationRule.automation_type == automation_type,
        AutomationRule.enabled == True,  # noqa: E712
    )
    if action_name:
        query = query.filter(AutomationRule.action_name == action_name)
    return query.first() is not None


@celery_app.task(bind=True, max_retries=3)
def process_webhook_event(self, event_id: int):
    """Process a webhook event by routing to the appropriate automation."""
    try:
        with get_db_session() as session:
            event = session.get(WebhookEvent, event_id)
            if not event or event.processed:
                return

            event.processing_started_at = datetime.utcnow()
            session.flush()

            from app.automations import get_automation_handler

            handler = get_automation_handler(event.odoo_model)
            if handler and _is_automation_enabled(session, handler.automation_type):
                result = handler.handle_event(
                    event_type=event.event_type,
                    model=event.odoo_model,
                    record_id=event.odoo_record_id,
                    values=event.payload or {},
                )

                audit = AuditLog(
                    automation_type=handler.automation_type,
                    action_name=result.action,
                    odoo_model=event.odoo_model,
                    odoo_record_id=event.odoo_record_id,
                    status=(
                        ActionStatus.EXECUTED
                        if result.success and not result.needs_approval
                        else ActionStatus.PENDING
                        if result.needs_approval
                        else ActionStatus.FAILED
                    ),
                    confidence=result.confidence,
                    ai_reasoning=result.reasoning,
                    input_data=event.payload,
                    output_data=result.changes_made,
                    executed_at=datetime.utcnow() if result.success else None,
                )
                session.add(audit)

            event.processed = True
            event.processing_completed_at = datetime.utcnow()

        logger.info("webhook_processed", event_id=event_id)

    except Exception as exc:
        logger.error("webhook_processing_failed", event_id=event_id, error=str(exc))
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(bind=True, max_retries=3)
def run_automation(self, automation_type: str, action: str, record_id: int, model: str):
    """Run a specific automation action on a record."""
    try:
        with get_db_session() as session:
            from app.automations import get_automation_handler_by_type

            handler = get_automation_handler_by_type(automation_type)
            if not handler:
                logger.warning("no_handler", automation_type=automation_type)
                return

            if not _is_automation_enabled(session, automation_type, action):
                logger.info("automation_disabled", automation_type=automation_type, action=action)
                return

            result = handler.run_action(action, model, record_id)

            audit = AuditLog(
                automation_type=automation_type,
                action_name=action,
                odoo_model=model,
                odoo_record_id=record_id,
                status=(
                    ActionStatus.EXECUTED if result.success else ActionStatus.FAILED
                ),
                confidence=result.confidence,
                ai_reasoning=result.reasoning,
                output_data=result.changes_made,
                executed_at=datetime.utcnow() if result.success else None,
            )
            session.add(audit)

    except Exception as exc:
        logger.error("automation_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=60)


@celery_app.task
def scheduled_scan(automation_type: str, action: str):
    """Periodic scan to find records needing automation."""
    try:
        with get_db_session() as session:
            if not _is_automation_enabled(session, automation_type):
                logger.info("scheduled_scan_skipped_disabled", type=automation_type, action=action)
                return

        from app.automations import get_automation_handler_by_type

        handler = get_automation_handler_by_type(automation_type)
        if handler:
            handler.scheduled_scan(action)
            logger.info("scheduled_scan_complete", type=automation_type, action=action)
    except Exception as exc:
        logger.error("scheduled_scan_failed", error=str(exc))


@celery_app.task
def execute_approved_action(audit_log_id: int):
    """Execute an action that was pending human approval."""
    try:
        with get_db_session() as session:
            audit = session.get(AuditLog, audit_log_id)
            if not audit or audit.status != ActionStatus.APPROVED:
                return

            from app.automations import get_automation_handler_by_type

            handler = get_automation_handler_by_type(audit.automation_type)
            if handler:
                result = handler.execute_approved(
                    action=audit.action_name,
                    model=audit.odoo_model,
                    record_id=audit.odoo_record_id,
                    data=audit.output_data or {},
                )
                audit.status = (
                    ActionStatus.EXECUTED if result.success else ActionStatus.FAILED
                )
                audit.executed_at = datetime.utcnow()
                if not result.success:
                    audit.error_message = result.reasoning

    except Exception as exc:
        logger.error("approved_action_failed", audit_id=audit_log_id, error=str(exc))


@celery_app.task
def run_cross_app_intelligence():
    """Run cross-module intelligence analysis."""
    try:
        from app.automations.cross_app import CrossAppIntelligence

        intelligence = CrossAppIntelligence()
        result = intelligence.run_full_analysis()
        insights_count = len(result.get("insights", []))
        logger.info("cross_app_intelligence_complete", insights=insights_count)

        with get_db_session() as session:
            audit = AuditLog(
                automation_type="cross_app",
                action_name="cross_app_intelligence",
                odoo_model="cross_app.intelligence",
                odoo_record_id=0,
                status=ActionStatus.EXECUTED,
                confidence=result.get("confidence", 0),
                ai_reasoning=result.get("executive_summary", ""),
                output_data=result,
                executed_at=datetime.utcnow(),
            )
            session.add(audit)

    except Exception as exc:
        logger.error("cross_app_intelligence_failed", error=str(exc))


# ---------------------------------------------------------------------------
# Sprint 1 — Month-End Closing
# ---------------------------------------------------------------------------

@celery_app.task
def run_month_end_preclose_scan(period: str):
    """
    Automated pre-close scan: runs all closing checks for a period and
    updates or creates the closing record.
    """
    try:
        from app.automations.month_end import MonthEndClosingAutomation
        from app.models.audit import MonthEndClosing, ClosingStep

        automation = MonthEndClosingAutomation()
        scan_results = automation.run_full_scan(period)
        ai_summary = automation.generate_ai_summary(period, scan_results)

        total_issues = sum(r.get("items_found", 0) for r in scan_results.values())
        logger.info(
            "month_end_preclose_scan_complete",
            period=period,
            total_issues=total_issues,
            risk_level=ai_summary.get("risk_level", "unknown"),
        )

        with get_db_session() as session:
            audit = AuditLog(
                automation_type="month_end",
                action_name="preclose_scan",
                odoo_model="month_end.closing",
                odoo_record_id=0,
                status=ActionStatus.EXECUTED,
                confidence=ai_summary.get("confidence", 0.5),
                ai_reasoning=ai_summary.get("summary", ""),
                output_data={
                    "period": period,
                    "scan_results": {k: v.get("items_found", 0) for k, v in scan_results.items()},
                    "risk_level": ai_summary.get("risk_level", "unknown"),
                },
                executed_at=datetime.utcnow(),
            )
            session.add(audit)

    except Exception as exc:
        logger.error("month_end_preclose_scan_failed", period=period, error=str(exc))
