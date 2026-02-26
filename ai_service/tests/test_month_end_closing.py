"""Tests for Month-End Closing Assistant (deliverable 1.1)."""

import json
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest

from app.models.audit import (
    MonthEndClosing,
    ClosingStep,
    AuditLog,
    AutomationType,
)
from app.automations.month_end import (
    MonthEndClosingAutomation,
    CLOSING_STEPS,
)


# ---------------------------------------------------------------------------
# Unit tests — MonthEndClosingAutomation logic
# ---------------------------------------------------------------------------


class TestMonthEndClosingAutomation:

    def test_get_period_dates(self):
        auto = MonthEndClosingAutomation()
        first, last = auto.get_period_dates("2026-02")
        assert first == "2026-02-01"
        assert last == "2026-02-28"

    def test_get_period_dates_december(self):
        auto = MonthEndClosingAutomation()
        first, last = auto.get_period_dates("2026-12")
        assert first == "2026-12-01"
        assert last == "2026-12-31"

    def test_get_period_dates_leap_year(self):
        auto = MonthEndClosingAutomation()
        first, last = auto.get_period_dates("2024-02")
        assert first == "2024-02-01"
        assert last == "2024-02-29"

    @patch("app.automations.month_end.MonthEndClosingAutomation.fetch_related_records")
    def test_scan_unreconciled_bank(self, mock_fetch):
        mock_fetch.return_value = [
            {"id": 1, "amount": 100.0, "payment_ref": "PMT-001"},
            {"id": 2, "amount": -50.0, "payment_ref": "PMT-002"},
        ]
        auto = MonthEndClosingAutomation()
        result = auto._scan_unreconciled_bank("2026-02-01", "2026-02-28")
        assert result["items_found"] == 2
        assert result["total_amount"] == 150.0

    @patch("app.automations.month_end.MonthEndClosingAutomation.fetch_related_records")
    def test_scan_stale_drafts(self, mock_fetch):
        mock_fetch.return_value = [
            {"id": 10, "name": "INV/2026/001", "amount_total": 500, "state": "draft"},
        ]
        auto = MonthEndClosingAutomation()
        result = auto._scan_stale_drafts("2026-02-01", "2026-02-28")
        assert result["items_found"] == 1

    @patch("app.automations.month_end.MonthEndClosingAutomation.fetch_related_records")
    def test_scan_uninvoiced_revenue(self, mock_fetch):
        mock_fetch.return_value = [
            {"id": 5, "name": "SO001", "amount_total": 3000, "invoice_status": "to invoice"},
        ]
        auto = MonthEndClosingAutomation()
        result = auto._scan_uninvoiced_revenue("2026-02-01", "2026-02-28")
        assert result["items_found"] == 1
        assert result["total_amount"] == 3000

    @patch("app.automations.month_end.MonthEndClosingAutomation.fetch_related_records")
    def test_scan_tax_issues(self, mock_fetch):
        mock_fetch.return_value = [
            {"id": 1, "name": "INV/001", "amount_tax": 0, "amount_total": 100},
            {"id": 2, "name": "INV/002", "amount_tax": 15, "amount_total": 115},
        ]
        auto = MonthEndClosingAutomation()
        result = auto._scan_tax_issues("2026-02-01", "2026-02-28")
        assert result["items_found"] == 1
        assert result["total_invoices_checked"] == 2

    def test_scan_intercompany_single_company(self):
        auto = MonthEndClosingAutomation()
        result = auto._scan_intercompany("2026-02-01", "2026-02-28")
        assert result["items_found"] == 0

    @patch("app.automations.month_end.MonthEndClosingAutomation.fetch_related_records")
    def test_run_full_scan_returns_all_steps(self, mock_fetch):
        mock_fetch.return_value = []
        auto = MonthEndClosingAutomation()
        with patch.object(auto, "fetch_record_context", return_value=None):
            results = auto.run_full_scan("2026-02")

        for step_def in CLOSING_STEPS:
            assert step_def["name"] in results

    @patch("app.automations.month_end.MonthEndClosingAutomation.analyze_with_tools")
    @patch("app.automations.month_end.MonthEndClosingAutomation.fetch_related_records")
    def test_generate_ai_summary_with_claude(self, mock_fetch, mock_analyze):
        mock_fetch.return_value = []
        mock_analyze.return_value = {
            "tool_calls": [{
                "input": {
                    "summary": "Period looks clean",
                    "risk_level": "low",
                    "priority_actions": ["Post depreciation"],
                    "estimated_completion_hours": 2,
                    "confidence": 0.92,
                }
            }]
        }
        auto = MonthEndClosingAutomation()
        scan_results = {"reconcile_bank": {"items_found": 0}}
        summary = auto.generate_ai_summary("2026-02", scan_results)
        assert summary["risk_level"] == "low"
        assert summary["confidence"] == 0.92

    @patch("app.automations.month_end.MonthEndClosingAutomation.analyze_with_tools")
    def test_generate_ai_summary_fallback(self, mock_analyze):
        mock_analyze.side_effect = Exception("Claude unavailable")
        auto = MonthEndClosingAutomation()
        scan_results = {
            "reconcile_bank": {"items_found": 5},
            "review_stale_drafts": {"items_found": 3},
        }
        summary = auto.generate_ai_summary("2026-02", scan_results)
        assert summary["risk_level"] == "medium"
        assert summary["confidence"] == 0.5

    def test_closing_steps_are_ordered(self):
        orders = [s["order"] for s in CLOSING_STEPS]
        assert orders == sorted(orders)
        assert len(orders) == len(set(orders))


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestClosingEndpoints:

    def test_start_closing(self, client, auth_headers, db_session):
        with patch(
            "app.routers.closing.MonthEndClosingAutomation"
        ) as MockAuto:
            instance = MockAuto.return_value
            instance.run_full_scan.return_value = {
                step["name"]: {"items_found": 0, "details": []}
                for step in CLOSING_STEPS
            }
            instance.generate_ai_summary.return_value = {
                "summary": "All clear",
                "risk_level": "low",
                "priority_actions": [],
                "estimated_completion_hours": 1,
                "confidence": 0.95,
            }

            resp = client.post(
                "/api/close/start",
                json={"period": "2026-02", "started_by": "test"},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["period"] == "2026-02"
            assert data["status"] == "in_progress"
            assert len(data["steps"]) == len(CLOSING_STEPS)

    def test_start_closing_duplicate_period(self, client, auth_headers, db_session):
        closing = MonthEndClosing(period="2026-02", status="in_progress")
        db_session.add(closing)
        db_session.commit()

        resp = client.post(
            "/api/close/start",
            json={"period": "2026-02"},
            headers=auth_headers,
        )
        assert resp.status_code == 409

    def test_get_closing_status(self, client, auth_headers, db_session):
        closing = MonthEndClosing(
            period="2026-03", status="in_progress", summary="Test"
        )
        db_session.add(closing)
        db_session.flush()

        step = ClosingStep(
            closing_id=closing.id,
            step_name="reconcile_bank",
            step_order=1,
            status="needs_attention",
            items_found=5,
        )
        db_session.add(step)
        db_session.commit()

        resp = client.get("/api/close/2026-03/status", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["period"] == "2026-03"
        assert len(data["steps"]) == 1
        assert data["steps"][0]["items_found"] == 5

    def test_get_closing_status_not_found(self, client, auth_headers):
        resp = client.get("/api/close/2099-01/status", headers=auth_headers)
        assert resp.status_code == 404

    def test_complete_step(self, client, auth_headers, db_session):
        closing = MonthEndClosing(period="2026-04", status="in_progress")
        db_session.add(closing)
        db_session.flush()

        step = ClosingStep(
            closing_id=closing.id,
            step_name="reconcile_bank",
            step_order=1,
            status="needs_attention",
            items_found=3,
        )
        db_session.add(step)
        db_session.commit()

        resp = client.post(
            "/api/close/2026-04/step/reconcile_bank/complete",
            json={"completed_by": "admin", "notes": "All good"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["step_name"] == "reconcile_bank"
        assert data["status"] == "complete"

    def test_complete_last_step_completes_closing(self, client, auth_headers, db_session):
        closing = MonthEndClosing(period="2026-05", status="in_progress")
        db_session.add(closing)
        db_session.flush()

        step = ClosingStep(
            closing_id=closing.id,
            step_name="final_review",
            step_order=1,
            status="needs_attention",
            items_found=0,
        )
        db_session.add(step)
        db_session.commit()

        resp = client.post(
            "/api/close/2026-05/step/final_review/complete",
            json={"completed_by": "admin"},
            headers=auth_headers,
        )
        data = resp.json()
        assert data["closing_status"] == "completed"

    def test_complete_step_not_found(self, client, auth_headers, db_session):
        closing = MonthEndClosing(period="2026-06", status="in_progress")
        db_session.add(closing)
        db_session.commit()

        resp = client.post(
            "/api/close/2026-06/step/nonexistent/complete",
            json={"completed_by": "admin"},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_rescan(self, client, auth_headers, db_session):
        closing = MonthEndClosing(period="2026-07", status="in_progress")
        db_session.add(closing)
        db_session.flush()

        step = ClosingStep(
            closing_id=closing.id,
            step_name="reconcile_bank",
            step_order=1,
            status="needs_attention",
            items_found=5,
        )
        db_session.add(step)
        db_session.commit()

        with patch(
            "app.routers.closing.MonthEndClosingAutomation"
        ) as MockAuto:
            instance = MockAuto.return_value
            instance.run_full_scan.return_value = {
                "reconcile_bank": {"items_found": 0, "details": []},
            }
            instance.generate_ai_summary.return_value = {
                "summary": "Issues resolved",
                "risk_level": "low",
                "priority_actions": [],
                "estimated_completion_hours": 0.5,
                "confidence": 0.95,
            }

            resp = client.post("/api/close/2026-07/rescan", headers=auth_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "in_progress"

    def test_invalid_period_format(self, client, auth_headers):
        resp = client.post(
            "/api/close/start",
            json={"period": "Feb-2026"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_requires_auth(self, client):
        resp = client.post("/api/close/start", json={"period": "2026-02"})
        assert resp.status_code == 401
