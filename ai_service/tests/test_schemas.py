"""Unit tests for Pydantic schemas."""

import pytest
from pydantic import ValidationError

from app.models.schemas import (
    WebhookPayload,
    AutomationResult,
    AutomationRuleCreate,
    DashboardStats,
    HealthResponse,
    ApprovalRequest,
)


class TestWebhookPayload:
    def test_valid_minimal(self):
        p = WebhookPayload(event_type="create", model="crm.lead", record_id=1)
        assert p.event_type == "create"
        assert p.values == {}

    def test_valid_full(self):
        p = WebhookPayload(
            event_type="write",
            model="account.move",
            record_id=42,
            values={"state": "posted"},
            old_values={"state": "draft"},
            timestamp="2026-02-26T10:00:00",
            user_id=2,
        )
        assert p.old_values == {"state": "draft"}
        assert p.user_id == 2

    def test_missing_required_field(self):
        with pytest.raises(ValidationError):
            WebhookPayload(event_type="create", model="crm.lead")


class TestAutomationResult:
    def test_defaults(self):
        r = AutomationResult(success=True, action="score", model="crm.lead", record_id=1)
        assert r.confidence == 0.0
        assert r.needs_approval is False
        assert r.changes_made == {}

    def test_with_approval(self):
        r = AutomationResult(
            success=True,
            action="approve_leave",
            model="hr.leave",
            record_id=5,
            confidence=0.88,
            needs_approval=True,
        )
        assert r.needs_approval is True


class TestAutomationRuleCreate:
    def test_defaults(self):
        r = AutomationRuleCreate(
            name="Score leads", automation_type="crm", action_name="score_lead"
        )
        assert r.enabled is True
        assert r.confidence_threshold == 0.85
        assert r.auto_approve is False

    def test_custom_thresholds(self):
        r = AutomationRuleCreate(
            name="Auto-categorize",
            automation_type="accounting",
            action_name="categorize",
            confidence_threshold=0.70,
            auto_approve=True,
            auto_approve_threshold=0.90,
        )
        assert r.auto_approve_threshold == 0.90


class TestDashboardStats:
    def test_defaults(self):
        s = DashboardStats()
        assert s.total_automations == 0
        assert s.by_type == {}

    def test_custom_values(self):
        s = DashboardStats(
            total_automations=100,
            success_rate=95.5,
            by_type={"crm": 30, "accounting": 70},
        )
        assert s.by_type["crm"] == 30


class TestHealthResponse:
    def test_healthy(self):
        h = HealthResponse(
            status="healthy",
            odoo_connected=True,
            redis_connected=True,
            db_connected=True,
        )
        assert h.version == "1.0.0"


class TestApprovalRequest:
    def test_approve(self):
        a = ApprovalRequest(audit_log_id=1, approved=True)
        assert a.approved_by == "admin"

    def test_reject(self):
        a = ApprovalRequest(audit_log_id=1, approved=False, approved_by="cfo")
        assert a.approved_by == "cfo"
