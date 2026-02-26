"""Tests for Customer Credit Management (deliverable 1.6)."""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest

from app.models.audit import CreditScore, AuditLog
from app.automations.credit import CreditManagementAutomation


# ---------------------------------------------------------------------------
# Unit tests — credit scoring engine
# ---------------------------------------------------------------------------


class TestCreditScoringEngine:

    def _make_automation(self):
        with patch("app.automations.base.get_settings") as mock_s:
            mock_s.return_value = MagicMock(
                auto_approve_threshold=0.95,
                default_confidence_threshold=0.85,
            )
            return CreditManagementAutomation()

    def test_payment_history_all_on_time(self):
        invoices = [
            {"payment_state": "paid", "invoice_date_due": "2026-03-01", "invoice_date": "2026-02-15"},
            {"payment_state": "paid", "invoice_date_due": "2026-02-01", "invoice_date": "2026-01-20"},
        ]
        score = CreditManagementAutomation._score_payment_history(invoices, [])
        assert score >= 90.0

    def test_payment_history_no_invoices(self):
        score = CreditManagementAutomation._score_payment_history([], [])
        assert score == 50.0

    def test_payment_history_no_paid(self):
        invoices = [
            {"payment_state": "not_paid", "invoice_date_due": "2026-01-01"},
        ]
        score = CreditManagementAutomation._score_payment_history(invoices, [])
        assert score == 30.0

    def test_order_volume_high(self):
        invoices = [{"id": i} for i in range(55)]
        score = CreditManagementAutomation._score_order_volume(invoices, [])
        assert score == 95.0

    def test_order_volume_moderate(self):
        invoices = [{"id": i} for i in range(12)]
        score = CreditManagementAutomation._score_order_volume(invoices, [])
        assert score == 65.0

    def test_order_volume_zero(self):
        score = CreditManagementAutomation._score_order_volume([], [])
        assert score == 30.0

    def test_overdue_ratio_none_overdue(self):
        invoices = [
            {"payment_state": "not_paid", "amount_residual": 1000, "invoice_date_due": "2099-12-31"},
        ]
        score = CreditManagementAutomation._score_overdue_ratio(invoices)
        assert score == 100.0

    def test_overdue_ratio_all_overdue(self):
        invoices = [
            {"payment_state": "not_paid", "amount_residual": 1000, "invoice_date_due": "2020-01-01"},
        ]
        score = CreditManagementAutomation._score_overdue_ratio(invoices)
        assert score == 0.0

    def test_overdue_ratio_no_open(self):
        invoices = [
            {"payment_state": "paid", "amount_residual": 0},
        ]
        score = CreditManagementAutomation._score_overdue_ratio(invoices)
        assert score == 100.0

    def test_relationship_age_new(self):
        partner = {"create_date": datetime.utcnow().isoformat()}
        score = CreditManagementAutomation._score_relationship_age(partner)
        assert score == 30.0

    def test_relationship_age_old(self):
        old_date = (datetime.utcnow() - timedelta(days=800)).isoformat()
        partner = {"create_date": old_date}
        score = CreditManagementAutomation._score_relationship_age(partner)
        assert score == 95.0

    def test_relationship_age_missing(self):
        score = CreditManagementAutomation._score_relationship_age({})
        assert score == 50.0

    def test_classify_risk_low(self):
        assert CreditManagementAutomation._classify_risk(85.0) == "low"

    def test_classify_risk_normal(self):
        assert CreditManagementAutomation._classify_risk(65.0) == "normal"

    def test_classify_risk_elevated(self):
        assert CreditManagementAutomation._classify_risk(45.0) == "elevated"

    def test_classify_risk_high(self):
        assert CreditManagementAutomation._classify_risk(25.0) == "high"

    def test_classify_risk_critical(self):
        assert CreditManagementAutomation._classify_risk(10.0) == "critical"

    def test_calculate_exposure(self):
        invoices = [
            {"payment_state": "not_paid", "amount_residual": 5000},
            {"payment_state": "partial", "amount_residual": 2000},
            {"payment_state": "paid", "amount_residual": 0},
        ]
        orders = [
            {"amount_total": 3000},
        ]
        exposure = CreditManagementAutomation._calculate_exposure(invoices, orders)
        assert exposure == 10000.0

    def test_calculate_overdue(self):
        invoices = [
            {"payment_state": "not_paid", "amount_residual": 5000, "invoice_date_due": "2020-01-01"},
            {"payment_state": "not_paid", "amount_residual": 3000, "invoice_date_due": "2099-12-31"},
        ]
        overdue = CreditManagementAutomation._calculate_overdue(invoices)
        assert overdue == 5000.0

    def test_build_hold_reason(self):
        reason = CreditManagementAutomation._build_hold_reason("high", 60000, 50000, 10000)
        assert "high" in reason.lower() or "Risk" in reason
        assert "60000" in reason or "Exposure" in reason

    def test_calculate_credit_score_full(self):
        auto = self._make_automation()
        with patch.object(auto, "fetch_record_context") as mock_partner:
            mock_partner.return_value = {
                "id": 1, "name": "Good Customer", "credit_limit": 100000,
                "total_invoiced": 50000, "total_due": 5000, "customer_rank": 1,
                "create_date": (datetime.utcnow() - timedelta(days=400)).isoformat(),
            }
            with patch.object(auto, "_fetch_customer_invoices") as mock_inv:
                mock_inv.return_value = [
                    {"payment_state": "paid", "amount_residual": 0, "invoice_date_due": "2026-01-01", "invoice_date": "2025-12-15", "amount_total": 10000},
                ] * 15
                with patch.object(auto, "_fetch_customer_payments") as mock_pay:
                    mock_pay.return_value = [{"amount": 10000}] * 15
                    with patch.object(auto, "_fetch_open_orders") as mock_orders:
                        mock_orders.return_value = []
                        result = auto.calculate_credit_score(1)

        assert "error" not in result
        assert result["customer_id"] == 1
        assert result["credit_score"] > 0
        assert result["risk_level"] in ("low", "normal", "elevated", "high", "critical")
        assert "breakdown" in result

    def test_calculate_credit_score_not_found(self):
        auto = self._make_automation()
        with patch.object(auto, "fetch_record_context", return_value=None):
            result = auto.calculate_credit_score(999)
        assert "error" in result

    def test_check_credit_on_order_allowed(self):
        auto = self._make_automation()
        with patch.object(auto, "calculate_credit_score") as mock_score:
            mock_score.return_value = {
                "customer_id": 1, "credit_score": 85, "risk_level": "low",
                "credit_limit": 100000, "current_exposure": 20000,
                "overdue_amount": 0, "hold_active": False,
                "breakdown": {"payment_history": 90, "order_volume": 80},
            }
            result = auto.check_credit_on_order(1, 5000)
        assert result["allowed"] is True
        assert result["remaining_credit"] == 75000.0

    def test_check_credit_on_order_over_limit(self):
        auto = self._make_automation()
        with patch.object(auto, "calculate_credit_score") as mock_score:
            mock_score.return_value = {
                "customer_id": 1, "credit_score": 60, "risk_level": "normal",
                "credit_limit": 50000, "current_exposure": 48000,
                "overdue_amount": 0, "hold_active": False,
                "breakdown": {"payment_history": 60, "order_volume": 60},
            }
            result = auto.check_credit_on_order(1, 5000)
        assert result["allowed"] is False
        assert result["over_limit_by"] == 3000.0

    def test_check_credit_on_order_hold_active(self):
        auto = self._make_automation()
        with patch.object(auto, "calculate_credit_score") as mock_score:
            mock_score.return_value = {
                "customer_id": 1, "credit_score": 15, "risk_level": "critical",
                "credit_limit": 50000, "current_exposure": 60000,
                "overdue_amount": 30000, "hold_active": True,
                "hold_reason": "Risk level: critical; Overdue amount: 30000.00",
                "breakdown": {"payment_history": 20, "order_volume": 10},
            }
            result = auto.check_credit_on_order(1, 1000)
        assert result["allowed"] is False
        assert "hold" in result["reason"].lower()

    def test_on_create_sale_order_passed(self):
        auto = self._make_automation()
        with patch.object(auto, "check_credit_on_order") as mock_check:
            mock_check.return_value = {
                "allowed": True, "reason": "Credit check passed",
                "credit_score": 85, "risk_level": "low",
                "remaining_credit": 75000,
            }
            result = auto.on_create_sale_order(
                model="sale.order", record_id=1,
                values={"partner_id": 10, "amount_total": 5000},
            )
        assert result.success
        assert result.action == "credit_check_passed"
        assert not result.needs_approval

    def test_on_create_sale_order_failed(self):
        auto = self._make_automation()
        with patch.object(auto, "check_credit_on_order") as mock_check:
            mock_check.return_value = {
                "allowed": False, "reason": "Over limit",
                "credit_score": 40, "risk_level": "elevated",
            }
            result = auto.on_create_sale_order(
                model="sale.order", record_id=1,
                values={"partner_id": 10, "amount_total": 50000},
            )
        assert result.success
        assert result.action == "credit_check_failed"
        assert result.needs_approval

    def test_on_create_sale_order_no_partner(self):
        auto = self._make_automation()
        result = auto.on_create_sale_order(
            model="sale.order", record_id=1,
            values={"amount_total": 5000},
        )
        assert result.action == "credit_check_skipped"

    def test_on_payment_received(self):
        auto = self._make_automation()
        with patch.object(auto, "calculate_credit_score") as mock_score:
            mock_score.return_value = {
                "customer_id": 10, "customer_name": "Test",
                "credit_score": 75, "risk_level": "normal",
                "credit_limit": 50000, "current_exposure": 10000,
                "overdue_amount": 0, "hold_active": False,
                "breakdown": {"payment_history": 80, "order_volume": 70},
            }
            result = auto.on_create_account_payment(
                model="account.payment", record_id=5,
                values={"partner_id": 10, "amount": 5000},
            )
        assert result.success
        assert result.action == "credit_recalculated"


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestCreditManagementEndpoints:

    def test_get_credit_score_from_db(self, client, auth_headers, db_session):
        cs = CreditScore(
            customer_id=1, customer_name="Test Corp",
            credit_score=Decimal("82.50"), credit_limit=Decimal("100000"),
            current_exposure=Decimal("25000"), overdue_amount=Decimal("0"),
            payment_history_score=Decimal("90"), order_volume_score=Decimal("75"),
            risk_level="low", hold_active=False,
        )
        db_session.add(cs)
        db_session.commit()

        resp = client.get("/api/credit/1", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["customer_id"] == 1
        assert data["credit_score"] == 82.5
        assert data["risk_level"] == "low"

    def test_get_credit_score_not_in_db(self, client, auth_headers, db_session):
        with patch(
            "app.routers.credit.CreditManagementAutomation"
        ) as MockCredit:
            instance = MockCredit.return_value
            instance.calculate_credit_score.return_value = {
                "customer_id": 5, "customer_name": "New Corp",
                "credit_score": 70, "risk_level": "normal",
                "credit_limit": 50000, "current_exposure": 10000,
                "overdue_amount": 0, "hold_active": False,
                "breakdown": {"payment_history": 75, "order_volume": 65},
            }

            resp = client.get("/api/credit/5", headers=auth_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["credit_score"] == 70

    def test_get_credit_score_customer_not_found(self, client, auth_headers, db_session):
        with patch(
            "app.routers.credit.CreditManagementAutomation"
        ) as MockCredit:
            instance = MockCredit.return_value
            instance.calculate_credit_score.return_value = {"error": "Customer 999 not found"}

            resp = client.get("/api/credit/999", headers=auth_headers)
            assert resp.status_code == 404

    def test_recalculate_creates_new(self, client, auth_headers, db_session):
        with patch(
            "app.routers.credit.CreditManagementAutomation"
        ) as MockCredit:
            instance = MockCredit.return_value
            instance.calculate_credit_score.return_value = {
                "customer_id": 1, "customer_name": "Test Corp",
                "credit_score": 85, "risk_level": "low",
                "credit_limit": 100000, "current_exposure": 20000,
                "overdue_amount": 0, "hold_active": False,
                "breakdown": {"payment_history": 90, "order_volume": 80},
            }

            resp = client.post("/api/credit/1/recalculate", headers=auth_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["credit_score"] == 85

    def test_recalculate_updates_existing(self, client, auth_headers, db_session):
        cs = CreditScore(
            customer_id=1, customer_name="Old Name",
            credit_score=Decimal("50"), credit_limit=Decimal("50000"),
            current_exposure=Decimal("30000"), overdue_amount=Decimal("10000"),
            risk_level="elevated", hold_active=False,
        )
        db_session.add(cs)
        db_session.commit()

        with patch(
            "app.routers.credit.CreditManagementAutomation"
        ) as MockCredit:
            instance = MockCredit.return_value
            instance.calculate_credit_score.return_value = {
                "customer_id": 1, "customer_name": "Old Name",
                "credit_score": 80, "risk_level": "low",
                "credit_limit": 75000, "current_exposure": 15000,
                "overdue_amount": 0, "hold_active": False,
                "breakdown": {"payment_history": 85, "order_volume": 75},
            }

            resp = client.post("/api/credit/1/recalculate", headers=auth_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["credit_score"] == 80

    def test_check_credit_allowed(self, client, auth_headers, db_session):
        with patch(
            "app.routers.credit.CreditManagementAutomation"
        ) as MockCredit:
            instance = MockCredit.return_value
            instance.check_credit_on_order.return_value = {
                "allowed": True, "reason": "Credit check passed",
                "credit_score": 85, "risk_level": "low",
                "remaining_credit": 75000,
            }

            resp = client.post(
                "/api/credit/check",
                json={"customer_id": 1, "order_amount": 5000},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["allowed"] is True

    def test_check_credit_denied(self, client, auth_headers, db_session):
        with patch(
            "app.routers.credit.CreditManagementAutomation"
        ) as MockCredit:
            instance = MockCredit.return_value
            instance.check_credit_on_order.return_value = {
                "allowed": False, "reason": "Over limit",
                "credit_score": 40, "risk_level": "elevated",
                "current_exposure": 48000, "credit_limit": 50000,
                "over_limit_by": 3000,
            }

            resp = client.post(
                "/api/credit/check",
                json={"customer_id": 1, "order_amount": 5000},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["allowed"] is False

    def test_list_credit_scores(self, client, auth_headers, db_session):
        for i in range(3):
            cs = CreditScore(
                customer_id=i + 1, customer_name=f"Customer {i}",
                credit_score=Decimal(str(50 + i * 15)),
                risk_level=["elevated", "normal", "low"][i],
            )
            db_session.add(cs)
        db_session.commit()

        resp = client.get("/api/credit/", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3

    def test_list_credit_scores_filter_risk(self, client, auth_headers, db_session):
        cs1 = CreditScore(customer_id=1, customer_name="A", credit_score=Decimal("30"), risk_level="high")
        cs2 = CreditScore(customer_id=2, customer_name="B", credit_score=Decimal("85"), risk_level="low")
        db_session.add_all([cs1, cs2])
        db_session.commit()

        resp = client.get("/api/credit/?risk_level=high", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["risk_level"] == "high"

    def test_list_hold_only(self, client, auth_headers, db_session):
        cs1 = CreditScore(customer_id=1, customer_name="Held", credit_score=Decimal("20"), hold_active=True, hold_reason="Test")
        cs2 = CreditScore(customer_id=2, customer_name="OK", credit_score=Decimal("85"), hold_active=False)
        db_session.add_all([cs1, cs2])
        db_session.commit()

        resp = client.get("/api/credit/?hold_only=true", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["hold_active"] is True

    def test_batch_recalculate(self, client, auth_headers, db_session):
        with patch(
            "app.routers.credit.CreditManagementAutomation"
        ) as MockCredit:
            instance = MockCredit.return_value
            instance.calculate_all_scores.return_value = {
                "total_customers": 10, "updated": 8, "errors": 2,
            }

            resp = client.post("/api/credit/batch-recalculate", headers=auth_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["total_customers"] == 10
            assert data["updated"] == 8

    def test_check_hold_releases(self, client, auth_headers, db_session):
        with patch(
            "app.routers.credit.CreditManagementAutomation"
        ) as MockCredit:
            instance = MockCredit.return_value
            instance.check_payment_releases.return_value = [
                {"customer_id": 1, "customer_name": "Released", "new_score": 75, "new_risk": "normal"},
            ]

            resp = client.post("/api/credit/releases", headers=auth_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["releases"]) == 1

    def test_requires_auth(self, client):
        resp = client.get("/api/credit/1")
        assert resp.status_code == 401
