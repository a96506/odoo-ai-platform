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


def _publish_dashboard_event(event_type: str, data: dict, role: str | None = None):
    """Publish a real-time event to the dashboard WebSocket channel via Redis."""
    try:
        from app.routers.websocket import publish_event
        publish_event(event_type, data, role)
    except Exception:
        pass


def _send_slack_approval_request(audit: "AuditLog"):
    """Send a Slack interactive message for actions needing approval."""
    try:
        from app.config import get_settings
        from app.notifications.slack import SlackChannel

        settings = get_settings()
        if not settings.slack_enabled or not settings.slack_default_channel:
            return

        slack = SlackChannel()
        slack.send_approval_request(
            channel=settings.slack_default_channel,
            audit_log_id=audit.id,
            automation_type=str(audit.automation_type),
            action_name=audit.action_name,
            model=audit.odoo_model,
            record_id=audit.odoo_record_id or 0,
            confidence=audit.confidence or 0.0,
            reasoning=audit.ai_reasoning or "",
        )
    except Exception as exc:
        logger.warning("slack_approval_request_failed", error=str(exc))


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

            if handler and 'audit' in dir() and audit:
                event_type = "automation_completed" if audit.status == ActionStatus.EXECUTED else "approval_needed"
                _publish_dashboard_event(
                    event_type,
                    {"audit_log_id": audit.id, "automation_type": handler.automation_type, "action": audit.action_name},
                )
                if audit.status == ActionStatus.PENDING:
                    _send_slack_approval_request(audit)

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


# ---------------------------------------------------------------------------
# Sprint 2 — Deduplication
# ---------------------------------------------------------------------------

@celery_app.task
def run_dedup_scan():
    """Weekly deduplication scan across all entity types."""
    try:
        from app.automations.deduplication import DeduplicationAutomation
        from app.models.audit import DeduplicationScan, DuplicateGroup

        automation = DeduplicationAutomation()
        result = automation.run_full_scan()

        with get_db_session() as session:
            if not _is_automation_enabled(session, "deduplication", "weekly_scan"):
                logger.info("dedup_scan_skipped_disabled")
                return

            for scan_type, scan_result in result["entity_results"].items():
                scan = DeduplicationScan(
                    scan_type=scan_type,
                    status="completed",
                    total_records=scan_result["total_records"],
                    duplicates_found=scan_result["duplicates_found"],
                    pending_review=len(scan_result["groups"]),
                )
                session.add(scan)
                session.flush()

                for g in scan_result["groups"]:
                    group = DuplicateGroup(
                        scan_id=scan.id,
                        odoo_model=g["odoo_model"],
                        record_ids=g["record_ids"],
                        master_record_id=g["master_record_id"],
                        similarity_score=g["similarity_score"],
                        match_fields=g["match_fields"],
                        status="pending",
                    )
                    session.add(group)

            audit = AuditLog(
                automation_type="deduplication",
                action_name="weekly_scan",
                odoo_model="deduplication.scan",
                odoo_record_id=0,
                status=ActionStatus.EXECUTED,
                ai_reasoning=f"Weekly scan: {result['total_groups']} groups, {result['total_duplicates']} duplicates",
                output_data={
                    "total_groups": result["total_groups"],
                    "total_duplicates": result["total_duplicates"],
                },
                executed_at=datetime.utcnow(),
            )
            session.add(audit)

        logger.info(
            "dedup_scan_complete",
            total_groups=result["total_groups"],
            total_duplicates=result["total_duplicates"],
        )

    except Exception as exc:
        logger.error("dedup_scan_failed", error=str(exc))


# ---------------------------------------------------------------------------
# Sprint 2 — Credit Management
# ---------------------------------------------------------------------------

@celery_app.task
def run_credit_scoring():
    """Daily credit score recalculation for all active customers."""
    try:
        from app.automations.credit import CreditManagementAutomation

        with get_db_session() as session:
            if not _is_automation_enabled(session, "credit_management", "calculate_scores"):
                logger.info("credit_scoring_skipped_disabled")
                return

        automation = CreditManagementAutomation()
        result = automation.calculate_all_scores()

        with get_db_session() as session:
            audit = AuditLog(
                automation_type="credit_management",
                action_name="daily_credit_scoring",
                odoo_model="res.partner",
                odoo_record_id=0,
                status=ActionStatus.EXECUTED,
                ai_reasoning=f"Scored {result['updated']}/{result['total_customers']} customers ({result['errors']} errors)",
                output_data=result,
                executed_at=datetime.utcnow(),
            )
            session.add(audit)

        logger.info("credit_scoring_complete", **result)

    except Exception as exc:
        logger.error("credit_scoring_failed", error=str(exc))


@celery_app.task
def run_credit_hold_check():
    """Hourly check for credit holds that can be released."""
    try:
        from app.automations.credit import CreditManagementAutomation

        with get_db_session() as session:
            if not _is_automation_enabled(session, "credit_management", "auto_release"):
                logger.info("credit_hold_check_skipped_disabled")
                return

        automation = CreditManagementAutomation()
        releases = automation.check_payment_releases()

        if releases:
            with get_db_session() as session:
                for release in releases:
                    audit = AuditLog(
                        automation_type="credit_management",
                        action_name="credit_hold_released",
                        odoo_model="res.partner",
                        odoo_record_id=release["customer_id"],
                        status=ActionStatus.EXECUTED,
                        confidence=release["new_score"] / 100.0,
                        ai_reasoning=f"Hold released: score {release['new_score']}, risk {release['new_risk']}",
                        executed_at=datetime.utcnow(),
                    )
                    session.add(audit)

        logger.info("credit_hold_check_complete", releases=len(releases))

    except Exception as exc:
        logger.error("credit_hold_check_failed", error=str(exc))


# ---------------------------------------------------------------------------
# Sprint 3 — Daily Digest
# ---------------------------------------------------------------------------

@celery_app.task
def run_daily_digest():
    """Generate and deliver daily digests for all configured roles."""
    try:
        from app.automations.daily_digest import DailyDigestAutomation, DEFAULT_DIGEST_CONFIG
        from app.models.audit import DailyDigest

        with get_db_session() as session:
            if not _is_automation_enabled(session, "reporting", "generate_digest"):
                logger.info("daily_digest_skipped_disabled")
                return

        automation = DailyDigestAutomation()
        results = automation.generate_all_digests()

        with get_db_session() as session:
            for result in results:
                if "error" in result and "content" not in result:
                    logger.warning("digest_generation_error", role=result.get("role"), error=result["error"])
                    continue

                role = result["role"]
                digest = DailyDigest(
                    user_role=role,
                    digest_date=datetime.strptime(result["digest_date"], "%Y-%m-%d").date(),
                    content=result["content"],
                    channels_sent=[],
                    delivered=False,
                )
                session.add(digest)
                session.flush()

                channels = result.get("channels", ["email"])
                config = DEFAULT_DIGEST_CONFIG.get(role, {})
                sent_channels = []

                for channel in channels:
                    recipient = ""
                    if channel == "slack":
                        from app.config import get_settings as _gs
                        recipient = _gs().slack_default_channel
                    delivered = automation.deliver_digest(
                        role=role,
                        channel=channel,
                        recipient=recipient,
                        content=result["content"],
                    )
                    if delivered:
                        sent_channels.append(channel)

                digest.channels_sent = sent_channels
                digest.delivered = bool(sent_channels)

            audit = AuditLog(
                automation_type="reporting",
                action_name="daily_digest_batch",
                odoo_model="daily.digest",
                odoo_record_id=0,
                status=ActionStatus.EXECUTED,
                ai_reasoning=f"Generated {len(results)} digests for roles: {[r.get('role') for r in results]}",
                output_data={"roles_generated": [r.get("role") for r in results]},
                executed_at=datetime.utcnow(),
            )
            session.add(audit)

        _publish_dashboard_event("automation_completed", {
            "automation_type": "reporting",
            "action": "daily_digest_batch",
            "roles": [r.get("role") for r in results],
        })

        logger.info("daily_digest_complete", roles=len(results))

    except Exception as exc:
        logger.error("daily_digest_failed", error=str(exc))


# ---------------------------------------------------------------------------
# Sprint 4 — Cash Flow Forecasting
# ---------------------------------------------------------------------------

@celery_app.task
def run_cash_flow_forecast():
    """Daily cash flow forecast regeneration."""
    try:
        from app.automations.cash_flow import CashFlowForecastingAutomation

        with get_db_session() as session:
            if not _is_automation_enabled(session, "forecasting", "generate_forecast"):
                logger.info("cash_flow_forecast_skipped_disabled")
                return

        automation = CashFlowForecastingAutomation()
        result = automation.generate_forecast(horizon_days=90)
        automation.persist_forecast(result)

        with get_db_session() as session:
            audit = AuditLog(
                automation_type="forecasting",
                action_name="daily_forecast",
                odoo_model="cash.forecast",
                odoo_record_id=0,
                status=ActionStatus.EXECUTED,
                confidence=0.85,
                ai_reasoning=f"90-day forecast: {len(result.get('cash_gap_dates', []))} cash gap warnings, balance at day 90: {result['forecasts'][-1]['balance']:.2f}" if result.get("forecasts") else "Forecast generated",
                output_data={
                    "horizon_days": 90,
                    "cash_gaps": len(result.get("cash_gap_dates", [])),
                    "current_balance": result.get("current_balance", 0),
                },
                executed_at=datetime.utcnow(),
            )
            session.add(audit)

        _publish_dashboard_event("forecast_updated", {
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
            "cash_gaps": len(result.get("cash_gap_dates", [])),
        }, role="cfo")

        logger.info(
            "cash_flow_forecast_complete",
            data_points=len(result.get("forecasts", [])),
            cash_gaps=len(result.get("cash_gap_dates", [])),
        )

    except Exception as exc:
        logger.error("cash_flow_forecast_failed", error=str(exc))


@celery_app.task
def run_forecast_accuracy_check():
    """Check forecast accuracy by comparing predictions with actual balances."""
    try:
        from app.automations.cash_flow import CashFlowForecastingAutomation
        from app.models.audit import CashForecast
        from datetime import date

        with get_db_session() as session:
            if not _is_automation_enabled(session, "forecasting", "accuracy_tracking"):
                logger.info("forecast_accuracy_check_skipped_disabled")
                return

        automation = CashFlowForecastingAutomation()
        current_balance = automation._get_current_balance()
        automation.record_actual_balance(date.today(), current_balance)

        accuracy = automation.check_accuracy()

        with get_db_session() as session:
            audit = AuditLog(
                automation_type="forecasting",
                action_name="accuracy_check",
                odoo_model="forecast.accuracy",
                odoo_record_id=0,
                status=ActionStatus.EXECUTED,
                ai_reasoning=f"Accuracy check: 30d MAE={accuracy['last_30_days'].get('mae', 0):.2f}, MAPE={accuracy['last_30_days'].get('mape', 0):.1f}%",
                output_data=accuracy,
                executed_at=datetime.utcnow(),
            )
            session.add(audit)

        logger.info("forecast_accuracy_check_complete", comparisons=accuracy.get("total_comparisons", 0))

    except Exception as exc:
        logger.error("forecast_accuracy_check_failed", error=str(exc))


# ---------------------------------------------------------------------------
# Sprint 4 — Scheduled Reports
# ---------------------------------------------------------------------------

@celery_app.task
def run_scheduled_reports():
    """Execute all scheduled reports that are due."""
    try:
        from app.automations.report_builder import ReportBuilderAutomation
        from app.models.audit import ReportJob

        with get_db_session() as session:
            if not _is_automation_enabled(session, "reporting", "scheduled_report"):
                logger.info("scheduled_reports_skipped_disabled")
                return

            scheduled_jobs = (
                session.query(ReportJob)
                .filter(
                    ReportJob.schedule_cron.isnot(None),
                    ReportJob.status == "scheduled",
                )
                .all()
            )

            if not scheduled_jobs:
                logger.info("no_scheduled_reports")
                return

            automation = ReportBuilderAutomation()
            executed = 0

            for job in scheduled_jobs:
                try:
                    result = automation.generate_report(job.request_text)
                    job.parsed_query = result.get("parsed_query")
                    job.result_data = result.get("result_data")

                    if job.format == "excel":
                        file_path = automation.export_excel(result["result_data"])
                        job.file_path = file_path
                    elif job.format == "pdf":
                        file_path = automation.export_pdf(result["result_data"])
                        job.file_path = file_path

                    executed += 1

                except Exception as exc:
                    logger.warning("scheduled_report_failed", job_id=job.id, error=str(exc))

            audit = AuditLog(
                automation_type="reporting",
                action_name="scheduled_reports_batch",
                odoo_model="report.job",
                odoo_record_id=0,
                status=ActionStatus.EXECUTED,
                ai_reasoning=f"Executed {executed}/{len(scheduled_jobs)} scheduled reports",
                output_data={"total": len(scheduled_jobs), "executed": executed},
                executed_at=datetime.utcnow(),
            )
            session.add(audit)

        logger.info("scheduled_reports_complete", executed=executed)

    except Exception as exc:
        logger.error("scheduled_reports_failed", error=str(exc))


# ---------------------------------------------------------------------------
# Phase 2 — Agent Workflow Execution
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, max_retries=2)
def run_agent_workflow(self, agent_type: str, trigger_type: str, trigger_id: str, initial_state: dict):
    """Execute a multi-step agent workflow via the Agent Orchestrator."""
    try:
        from app.agents.orchestrator import get_orchestrator

        orchestrator = get_orchestrator()
        result = orchestrator.run_agent(
            agent_type=agent_type,
            trigger_type=trigger_type,
            trigger_id=trigger_id,
            initial_state=initial_state,
        )

        _publish_dashboard_event("agent_completed", {
            "agent_type": agent_type,
            "run_id": result.get("run_id"),
            "status": result.get("status"),
            "total_steps": result.get("total_steps", 0),
        })

        logger.info(
            "agent_workflow_complete",
            agent_type=agent_type,
            run_id=result.get("run_id"),
            status=result.get("status"),
            steps=result.get("total_steps", 0),
        )

    except Exception as exc:
        logger.error("agent_workflow_failed", agent_type=agent_type, error=str(exc))
        raise self.retry(exc=exc, countdown=120)


@celery_app.task
def resume_agent_workflow(run_id: int, event_data: dict):
    """Resume a suspended agent after receiving an external event (e.g. approval)."""
    try:
        from app.agents.orchestrator import get_orchestrator

        orchestrator = get_orchestrator()
        result = orchestrator.resume_agent(run_id=run_id, event_data=event_data)

        _publish_dashboard_event("agent_completed", {
            "run_id": run_id,
            "status": result.get("status"),
        })

        logger.info("agent_resumed", run_id=run_id, status=result.get("status"))

    except Exception as exc:
        logger.error("agent_resume_failed", run_id=run_id, error=str(exc))


# ---------------------------------------------------------------------------
# Phase 2 — Supply Chain Intelligence
# ---------------------------------------------------------------------------

@celery_app.task
def run_supplier_risk_scoring():
    """Daily recalculation of risk scores for all vendors."""
    try:
        from app.automations.supply_chain import SupplyChainAutomation

        with get_db_session() as session:
            if not _is_automation_enabled(session, "supply_chain", "risk_scoring"):
                logger.info("supplier_risk_scoring_skipped_disabled")
                return

        automation = SupplyChainAutomation()
        result = automation.calculate_all_risk_scores()

        with get_db_session() as session:
            audit = AuditLog(
                automation_type="supply_chain",
                action_name="daily_risk_scoring",
                odoo_model="res.partner",
                odoo_record_id=0,
                status=ActionStatus.EXECUTED,
                ai_reasoning=f"Scored {result['vendors_scored']} vendors: {result['critical']} critical, {result['elevated']} elevated",
                output_data=result,
                executed_at=datetime.utcnow(),
            )
            session.add(audit)

        _publish_dashboard_event("alert", {
            "type": "supply_chain_risk_update",
            "vendors_scored": result["vendors_scored"],
            "critical": result["critical"],
        })

        logger.info("supplier_risk_scoring_complete", **result)

    except Exception as exc:
        logger.error("supplier_risk_scoring_failed", error=str(exc))


@celery_app.task
def run_delivery_degradation_check():
    """Check for worsening delivery patterns across vendors (every 6 hours)."""
    try:
        from app.automations.supply_chain import SupplyChainAutomation

        with get_db_session() as session:
            if not _is_automation_enabled(session, "supply_chain", "disruption_prediction"):
                logger.info("delivery_degradation_check_skipped_disabled")
                return

        automation = SupplyChainAutomation()
        predictions = automation.detect_delivery_degradation()

        if predictions:
            with get_db_session() as session:
                audit = AuditLog(
                    automation_type="supply_chain",
                    action_name="delivery_degradation_check",
                    odoo_model="res.partner",
                    odoo_record_id=0,
                    status=ActionStatus.EXECUTED,
                    ai_reasoning=f"Detected {len(predictions)} delivery degradation patterns",
                    output_data={"predictions": len(predictions)},
                    executed_at=datetime.utcnow(),
                )
                session.add(audit)

            _publish_dashboard_event("alert", {
                "type": "supply_chain_degradation",
                "predictions": len(predictions),
            })

        logger.info("delivery_degradation_check_complete", predictions=len(predictions))

    except Exception as exc:
        logger.error("delivery_degradation_check_failed", error=str(exc))


@celery_app.task
def run_single_source_scan():
    """Weekly scan identifying products with only one supplier."""
    try:
        from app.automations.supply_chain import SupplyChainAutomation

        with get_db_session() as session:
            if not _is_automation_enabled(session, "supply_chain", "single_source_detection"):
                logger.info("single_source_scan_skipped_disabled")
                return

        automation = SupplyChainAutomation()
        result = automation.detect_single_source_risks()

        with get_db_session() as session:
            audit = AuditLog(
                automation_type="supply_chain",
                action_name="single_source_scan",
                odoo_model="product.template",
                odoo_record_id=0,
                status=ActionStatus.EXECUTED,
                ai_reasoning=f"Found {result['single_source_products']} single-source products, total revenue at risk: {result.get('total_revenue_at_risk', 0):.2f}",
                output_data=result,
                executed_at=datetime.utcnow(),
            )
            session.add(audit)

        logger.info("single_source_scan_complete", products=result["single_source_products"])

    except Exception as exc:
        logger.error("single_source_scan_failed", error=str(exc))
