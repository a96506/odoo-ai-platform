"""Unit tests for Phase 1 SQLAlchemy models — verifies all 13 tables can be created and queried."""

from datetime import datetime, date
from decimal import Decimal

import pytest

from app.models.audit import (
    AuditLog,
    AutomationRule,
    WebhookEvent,
    ActionStatus,
    AutomationType,
    MonthEndClosing,
    ClosingStep,
    ReconciliationSession,
    DocumentProcessingJob,
    ExtractionCorrection,
    DeduplicationScan,
    DuplicateGroup,
    CreditScore,
    ReportJob,
    CashForecast,
    ForecastScenario,
    ForecastAccuracyLog,
    DailyDigest,
)


class TestPhase0Models:
    def test_create_audit_log(self, db_session):
        log = AuditLog(
            automation_type=AutomationType.CRM,
            action_name="score_lead",
            odoo_model="crm.lead",
            odoo_record_id=1,
            status=ActionStatus.EXECUTED,
            confidence=0.92,
            ai_reasoning="High-value lead",
        )
        db_session.add(log)
        db_session.flush()
        assert log.id is not None

    def test_create_automation_rule(self, db_session):
        rule = AutomationRule(
            name="Test Rule",
            automation_type=AutomationType.ACCOUNTING,
            action_name="categorize",
            enabled=True,
        )
        db_session.add(rule)
        db_session.flush()
        assert rule.id is not None
        assert rule.confidence_threshold == 0.85


class TestMonthEndClosing:
    def test_create_closing_with_steps(self, db_session):
        closing = MonthEndClosing(
            period="2026-02",
            started_by="admin",
        )
        db_session.add(closing)
        db_session.flush()

        step = ClosingStep(
            closing_id=closing.id,
            step_name="reconcile_bank",
            step_order=1,
            items_found=12,
        )
        db_session.add(step)
        db_session.flush()

        assert closing.id is not None
        assert step.closing_id == closing.id

    def test_closing_step_relationship(self, db_session):
        closing = MonthEndClosing(period="2026-01")
        closing.steps = [
            ClosingStep(step_name="reconcile_bank", step_order=1),
            ClosingStep(step_name="review_drafts", step_order=2),
        ]
        db_session.add(closing)
        db_session.flush()
        assert len(closing.steps) == 2


class TestReconciliationSession:
    def test_create_session(self, db_session):
        session_obj = ReconciliationSession(
            user_id="admin",
            journal_id=1,
            total_lines=120,
            auto_matched=85,
            remaining=35,
        )
        db_session.add(session_obj)
        db_session.flush()
        assert session_obj.id is not None
        assert session_obj.status == "active"


class TestDocumentProcessing:
    def test_create_job_with_corrections(self, db_session):
        job = DocumentProcessingJob(
            file_name="invoice_042.pdf",
            file_type="pdf",
            document_type="invoice",
            status="completed",
            overall_confidence=Decimal("0.9650"),
        )
        db_session.add(job)
        db_session.flush()

        correction = ExtractionCorrection(
            job_id=job.id,
            field_name="vendor",
            original_value="Acme Corp",
            corrected_value="Acme Corporation Ltd",
            corrected_by="admin",
        )
        db_session.add(correction)
        db_session.flush()

        assert job.id is not None
        assert correction.job_id == job.id


class TestDeduplication:
    def test_create_scan_with_groups(self, db_session):
        scan = DeduplicationScan(
            scan_type="contacts",
            total_records=500,
            duplicates_found=12,
        )
        db_session.add(scan)
        db_session.flush()

        group = DuplicateGroup(
            scan_id=scan.id,
            odoo_model="res.partner",
            record_ids=[42, 67],
            similarity_score=Decimal("0.9400"),
            match_fields=["name", "email"],
        )
        db_session.add(group)
        db_session.flush()

        assert scan.id is not None
        assert group.scan_id == scan.id


class TestCreditScore:
    def test_create_credit_score(self, db_session):
        score = CreditScore(
            customer_id=42,
            customer_name="Acme Corp",
            credit_score=Decimal("78.50"),
            credit_limit=Decimal("25000.00"),
            current_exposure=Decimal("18000.00"),
            risk_level="watch",
        )
        db_session.add(score)
        db_session.flush()
        assert score.id is not None
        assert score.hold_active is False


class TestReportJob:
    def test_create_report_job(self, db_session):
        job = ReportJob(
            request_text="Sales by product category for Q4 2025",
            requested_by="admin",
            format="table",
        )
        db_session.add(job)
        db_session.flush()
        assert job.id is not None
        assert job.status == "pending"


class TestCashForecast:
    def test_create_forecast_with_scenario(self, db_session):
        forecast = CashForecast(
            forecast_date=date(2026, 2, 26),
            target_date=date(2026, 3, 26),
            predicted_balance=Decimal("125000.00"),
            confidence_low=Decimal("110000.00"),
            confidence_high=Decimal("140000.00"),
            model_version="v1.0",
        )
        db_session.add(forecast)
        db_session.flush()

        scenario = ForecastScenario(
            name="Customer X pays late",
            base_forecast_id=forecast.id,
            adjustments={"delay_customer_42": 30},
            created_by="cfo",
        )
        db_session.add(scenario)
        db_session.flush()

        assert forecast.id is not None
        assert scenario.base_forecast_id == forecast.id

    def test_accuracy_log(self, db_session):
        forecast = CashForecast(
            forecast_date=date(2026, 2, 1),
            target_date=date(2026, 2, 28),
            predicted_balance=Decimal("100000.00"),
        )
        db_session.add(forecast)
        db_session.flush()

        accuracy = ForecastAccuracyLog(
            forecast_id=forecast.id,
            target_date=date(2026, 2, 28),
            predicted_balance=Decimal("100000.00"),
            actual_balance=Decimal("102500.00"),
            error_pct=Decimal("2.5000"),
        )
        db_session.add(accuracy)
        db_session.flush()
        assert accuracy.id is not None


class TestDailyDigest:
    def test_create_digest(self, db_session):
        digest = DailyDigest(
            user_role="cfo",
            digest_date=date(2026, 2, 26),
            content={
                "headline": "3 items need attention",
                "key_metrics": [{"ar_aging": 45000}],
            },
        )
        db_session.add(digest)
        db_session.flush()
        assert digest.id is not None
        assert digest.delivered is False
