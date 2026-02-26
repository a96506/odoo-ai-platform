"""Tests for Cash Flow Forecasting (deliverable 1.8)."""

from datetime import datetime, date, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest

from app.models.audit import CashForecast, ForecastScenario, ForecastAccuracyLog, AuditLog
from app.automations.cash_flow import CashFlowForecastingAutomation


# ---------------------------------------------------------------------------
# Unit tests — forecasting engine
# ---------------------------------------------------------------------------


class TestCashFlowEngine:

    def _make_automation(self):
        with patch("app.automations.base.get_settings") as mock_s:
            mock_s.return_value = MagicMock(
                auto_approve_threshold=0.95,
                default_confidence_threshold=0.85,
            )
            return CashFlowForecastingAutomation()

    def test_sum_for_date_matches(self):
        items = [
            {"amount": 1000.0, "due_date": "2026-03-01"},
            {"amount": 500.0, "due_date": "2026-03-01"},
            {"amount": 200.0, "due_date": "2026-03-02"},
        ]
        total = CashFlowForecastingAutomation._sum_for_date(items, date(2026, 3, 1))
        assert total == 1500.0

    def test_sum_for_date_no_match(self):
        items = [{"amount": 1000.0, "due_date": "2026-03-01"}]
        total = CashFlowForecastingAutomation._sum_for_date(items, date(2026, 3, 5))
        assert total == 0.0

    def test_recurring_for_date_first_of_month(self):
        items = [{"amount": 5000.0}, {"amount": 3000.0}]
        total = CashFlowForecastingAutomation._recurring_for_date(items, date(2026, 3, 1))
        assert total == 8000.0

    def test_recurring_for_date_other_day(self):
        items = [{"amount": 5000.0}]
        total = CashFlowForecastingAutomation._recurring_for_date(items, date(2026, 3, 15))
        assert total == 0.0

    def test_recurring_for_date_empty(self):
        total = CashFlowForecastingAutomation._recurring_for_date([], date(2026, 3, 1))
        assert total == 0.0

    def test_apply_ar_adjustments_delay(self):
        ar_data = [
            {"amount": 1000.0, "due_date": "2026-03-01", "partner_id": 42},
        ]
        adjustments = {"delay_customer_42": 30}
        result = CashFlowForecastingAutomation._apply_ar_adjustments(ar_data, adjustments)
        assert result[0]["due_date"] == "2026-03-31"

    def test_apply_ar_adjustments_reduce(self):
        ar_data = [{"amount": 1000.0, "due_date": "2026-03-01", "partner_id": 1}]
        adjustments = {"reduce_ar_by": 20}
        result = CashFlowForecastingAutomation._apply_ar_adjustments(ar_data, adjustments)
        assert result[0]["amount"] == 800.0

    def test_apply_ar_adjustments_no_change(self):
        ar_data = [{"amount": 1000.0, "due_date": "2026-03-01", "partner_id": 1}]
        result = CashFlowForecastingAutomation._apply_ar_adjustments(ar_data, {})
        assert result[0]["amount"] == 1000.0

    def test_apply_pipeline_adjustments_remove(self):
        pipeline = [
            {"amount": 5000.0, "due_date": "2026-04-01", "reference": "Deal-ABC", "partner_id": 1},
            {"amount": 3000.0, "due_date": "2026-05-01", "reference": "Deal-XYZ", "partner_id": 2},
        ]
        adjustments = {"remove_deal_ABC": True}
        result = CashFlowForecastingAutomation._apply_pipeline_adjustments(pipeline, adjustments)
        assert len(result) == 1
        assert result[0]["reference"] == "Deal-XYZ"

    def test_apply_pipeline_no_removal(self):
        pipeline = [{"amount": 5000.0, "due_date": "2026-04-01", "reference": "Deal-A", "partner_id": 1}]
        result = CashFlowForecastingAutomation._apply_pipeline_adjustments(pipeline, {})
        assert len(result) == 1

    def test_apply_ap_adjustments_increase(self):
        ap_data = [{"amount": 2000.0, "due_date": "2026-03-01"}]
        adjustments = {"increase_ap_by": 10}
        result = CashFlowForecastingAutomation._apply_ap_adjustments(ap_data, adjustments)
        assert result[0]["amount"] == 2200.0

    def test_apply_ap_adjustments_no_change(self):
        ap_data = [{"amount": 2000.0, "due_date": "2026-03-01"}]
        result = CashFlowForecastingAutomation._apply_ap_adjustments(ap_data, {})
        assert result[0]["amount"] == 2000.0

    def test_apply_recurring_adjustments(self):
        recurring = [{"amount": 5000.0, "reference": "rent"}]
        adjustments = {"adjust_expense_rent": 1.5}
        result = CashFlowForecastingAutomation._apply_recurring_adjustments(recurring, adjustments)
        assert result[0]["amount"] == 7500.0

    def test_generate_forecast_basic(self):
        auto = self._make_automation()

        with patch.object(auto, "_get_current_balance", return_value=100000.0):
            with patch.object(auto, "_collect_ar_aging", return_value=[
                {"amount": 5000.0, "due_date": (date.today() + timedelta(days=5)).isoformat(), "partner_id": 1},
            ]):
                with patch.object(auto, "_collect_ap_commitments", return_value=[
                    {"amount": 3000.0, "due_date": (date.today() + timedelta(days=10)).isoformat(), "partner_id": 2},
                ]):
                    with patch.object(auto, "_collect_pipeline_weighted", return_value=[]):
                        with patch.object(auto, "_collect_recurring_expenses", return_value=[]):
                            result = auto.generate_forecast(horizon_days=30)

        assert "forecasts" in result
        assert len(result["forecasts"]) == 30
        assert result["current_balance"] == 100000.0
        assert result["horizon_days"] == 30
        assert result["model_version"] == "v1.0-statistical"

        day_5 = result["forecasts"][4]
        assert day_5["ar_expected"] == 5000.0
        assert day_5["balance"] > 100000.0

    def test_generate_forecast_with_gaps(self):
        auto = self._make_automation()

        with patch.object(auto, "_get_current_balance", return_value=1000.0):
            with patch.object(auto, "_collect_ar_aging", return_value=[]):
                with patch.object(auto, "_collect_ap_commitments", return_value=[
                    {"amount": 5000.0, "due_date": (date.today() + timedelta(days=3)).isoformat(), "partner_id": 1},
                ]):
                    with patch.object(auto, "_collect_pipeline_weighted", return_value=[]):
                        with patch.object(auto, "_collect_recurring_expenses", return_value=[]):
                            result = auto.generate_forecast(horizon_days=10)

        assert len(result["cash_gap_dates"]) > 0

    def test_generate_forecast_confidence_bands(self):
        auto = self._make_automation()

        with patch.object(auto, "_get_current_balance", return_value=50000.0):
            with patch.object(auto, "_collect_ar_aging", return_value=[]):
                with patch.object(auto, "_collect_ap_commitments", return_value=[]):
                    with patch.object(auto, "_collect_pipeline_weighted", return_value=[]):
                        with patch.object(auto, "_collect_recurring_expenses", return_value=[]):
                            result = auto.generate_forecast(horizon_days=30)

        last_day = result["forecasts"][-1]
        assert last_day["low"] <= last_day["balance"] <= last_day["high"]

    def test_run_scenario_delay_customer(self):
        auto = self._make_automation()

        ar_item = {
            "amount": 10000.0,
            "due_date": (date.today() + timedelta(days=5)).isoformat(),
            "partner_id": 42,
        }

        with patch.object(auto, "_get_current_balance", return_value=50000.0):
            with patch.object(auto, "_collect_ar_aging", return_value=[ar_item]):
                with patch.object(auto, "_collect_ap_commitments", return_value=[]):
                    with patch.object(auto, "_collect_pipeline_weighted", return_value=[]):
                        with patch.object(auto, "_collect_recurring_expenses", return_value=[]):
                            result = auto.run_scenario(
                                name="Customer 42 pays late",
                                adjustments={"delay_customer_42": 30},
                            )

        assert "impact" in result
        assert "forecasts" in result
        assert result["name"] == "Customer 42 pays late"

    def test_run_scenario_remove_deal(self):
        auto = self._make_automation()

        pipeline_item = {
            "amount": 15000.0,
            "due_date": (date.today() + timedelta(days=20)).isoformat(),
            "partner_id": 10,
            "reference": "Big-Deal-123",
            "probability": 0.7,
        }

        with patch.object(auto, "_get_current_balance", return_value=50000.0):
            with patch.object(auto, "_collect_ar_aging", return_value=[]):
                with patch.object(auto, "_collect_ap_commitments", return_value=[]):
                    with patch.object(auto, "_collect_pipeline_weighted", return_value=[pipeline_item]):
                        with patch.object(auto, "_collect_recurring_expenses", return_value=[]):
                            result = auto.run_scenario(
                                name="Lose big deal",
                                adjustments={"remove_deal_Big-Deal-123": True},
                            )

        assert result["impact"]["end_balance_change"] < 0

    def test_check_accuracy_empty(self):
        auto = self._make_automation()
        result = auto.check_accuracy()
        assert result["total_comparisons"] == 0

    def test_on_create_invoice(self):
        auto = self._make_automation()
        result = auto.on_create_account_move(
            model="account.move",
            record_id=1,
            values={"move_type": "out_invoice", "amount_total": 5000},
        )
        assert result.success
        assert result.action == "forecast_data_updated"

    def test_on_create_irrelevant_move(self):
        auto = self._make_automation()
        result = auto.on_create_account_move(
            model="account.move",
            record_id=1,
            values={"move_type": "entry", "amount_total": 1000},
        )
        assert result.action == "forecast_no_action"


class TestCashFlowDataCollection:

    def _make_automation(self):
        with patch("app.automations.base.get_settings") as mock_s:
            mock_s.return_value = MagicMock(
                auto_approve_threshold=0.95,
                default_confidence_threshold=0.85,
            )
            return CashFlowForecastingAutomation()

    def test_get_current_balance(self):
        auto = self._make_automation()
        with patch.object(auto, "fetch_related_records") as mock_fetch:
            mock_fetch.side_effect = [
                [{"id": 1, "name": "Bank", "default_account_id": [10, "Bank Account"]}],
                [{"balance": 50000.0}, {"balance": 25000.0}],
            ]
            balance = auto._get_current_balance()
        assert balance == 75000.0

    def test_get_current_balance_no_journals(self):
        auto = self._make_automation()
        with patch.object(auto, "fetch_related_records", return_value=[]):
            balance = auto._get_current_balance()
        assert balance == 0.0

    def test_collect_ar_aging(self):
        auto = self._make_automation()
        with patch.object(auto, "fetch_related_records") as mock_fetch:
            mock_fetch.return_value = [
                {"partner_id": [1, "Customer A"], "amount_residual": 5000, "invoice_date_due": "2026-04-01", "name": "INV/001"},
                {"partner_id": [2, "Customer B"], "amount_residual": 3000, "invoice_date_due": "2026-04-15", "name": "INV/002"},
            ]
            result = auto._collect_ar_aging()

        assert len(result) == 2
        assert result[0]["type"] == "ar"
        assert result[0]["amount"] == 5000.0
        assert result[0]["partner_id"] == 1

    def test_collect_ar_aging_no_due_date(self):
        auto = self._make_automation()
        with patch.object(auto, "fetch_related_records") as mock_fetch:
            mock_fetch.return_value = [
                {"partner_id": 1, "amount_residual": 1000, "invoice_date_due": None, "name": "INV/003"},
            ]
            result = auto._collect_ar_aging()

        assert len(result) == 1
        assert result[0]["due_date"] != ""

    def test_collect_ap_commitments(self):
        auto = self._make_automation()
        with patch.object(auto, "fetch_related_records") as mock_fetch:
            mock_fetch.return_value = [
                {"partner_id": [5, "Vendor A"], "amount_residual": 8000, "invoice_date_due": "2026-03-20", "name": "BILL/001"},
            ]
            result = auto._collect_ap_commitments()

        assert len(result) == 1
        assert result[0]["type"] == "ap"
        assert result[0]["amount"] == 8000.0

    def test_collect_pipeline_weighted(self):
        auto = self._make_automation()
        with patch.object(auto, "fetch_related_records") as mock_fetch:
            mock_fetch.return_value = [
                {"name": "Big Deal", "expected_revenue": 100000, "probability": 50, "date_deadline": "2026-05-01", "partner_id": 1},
                {"name": "Small Deal", "expected_revenue": 10000, "probability": 80, "date_deadline": "2026-04-01", "partner_id": 2},
            ]
            result = auto._collect_pipeline_weighted()

        assert len(result) == 2
        assert result[0]["amount"] == 50000.0  # 100k * 50%
        assert result[1]["amount"] == 8000.0   # 10k * 80%

    def test_collect_pipeline_zero_revenue(self):
        auto = self._make_automation()
        with patch.object(auto, "fetch_related_records") as mock_fetch:
            mock_fetch.return_value = [
                {"name": "Dead Deal", "expected_revenue": 0, "probability": 50, "date_deadline": None, "partner_id": 1},
            ]
            result = auto._collect_pipeline_weighted()

        assert len(result) == 0

    def test_collect_recurring_expenses(self):
        auto = self._make_automation()
        with patch.object(auto, "fetch_related_records") as mock_fetch:
            mock_fetch.return_value = [
                {"partner_id": [10, "Landlord"], "amount_total": 5000, "invoice_date": "2026-01-01", "name": "BILL/R1"},
                {"partner_id": [10, "Landlord"], "amount_total": 5100, "invoice_date": "2026-02-01", "name": "BILL/R2"},
                {"partner_id": [10, "Landlord"], "amount_total": 4900, "invoice_date": "2025-12-01", "name": "BILL/R3"},
            ]
            result = auto._collect_recurring_expenses()

        assert len(result) == 1
        assert result[0]["type"] == "recurring"
        assert result[0]["frequency"] == "monthly"
        assert 4900 <= result[0]["amount"] <= 5100

    def test_collect_recurring_non_recurring(self):
        auto = self._make_automation()
        with patch.object(auto, "fetch_related_records") as mock_fetch:
            mock_fetch.return_value = [
                {"partner_id": 1, "amount_total": 500, "invoice_date": "2026-01-01", "name": "BILL/1"},
                {"partner_id": 1, "amount_total": 50000, "invoice_date": "2026-02-01", "name": "BILL/2"},
            ]
            result = auto._collect_recurring_expenses()

        assert len(result) == 0

    def test_collect_recurring_error(self):
        auto = self._make_automation()
        with patch.object(auto, "fetch_related_records", side_effect=Exception("Odoo down")):
            result = auto._collect_recurring_expenses()
        assert result == []


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestForecastEndpoints:

    def test_get_forecast(self, client, auth_headers, db_session):
        with patch(
            "app.routers.forecast.CashFlowForecastingAutomation"
        ) as MockForecast:
            instance = MockForecast.return_value
            instance.generate_forecast.return_value = {
                "generated_at": datetime.utcnow().isoformat(),
                "horizon_days": 30,
                "current_balance": 100000.0,
                "forecasts": [
                    {
                        "date": "2026-03-01", "balance": 105000.0,
                        "low": 95000.0, "high": 115000.0,
                        "ar_expected": 5000.0, "ap_expected": 0.0,
                        "pipeline_expected": 0.0, "recurring_expected": 0.0,
                    },
                ],
                "ar_summary": {"total_ar": 50000.0, "total_ap": 0.0, "total_pipeline": 0.0, "total_recurring": 0.0, "net_position": 50000.0},
                "ap_summary": {"total_ar": 0.0, "total_ap": 30000.0, "total_pipeline": 20000.0, "total_recurring": 10000.0, "net_position": -40000.0},
                "cash_gap_dates": [],
                "model_version": "v1.0-statistical",
            }

            resp = client.get("/api/forecast/cashflow?horizon=30", headers=auth_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["horizon_days"] == 30
            assert data["current_balance"] == 100000.0
            assert len(data["forecasts"]) == 1
            assert data["forecasts"][0]["balance"] == 105000.0
            assert data["cash_gap_dates"] == []

    def test_get_forecast_default_horizon(self, client, auth_headers, db_session):
        with patch(
            "app.routers.forecast.CashFlowForecastingAutomation"
        ) as MockForecast:
            instance = MockForecast.return_value
            instance.generate_forecast.return_value = {
                "generated_at": datetime.utcnow().isoformat(),
                "horizon_days": 90,
                "current_balance": 50000.0,
                "forecasts": [],
                "ar_summary": {},
                "ap_summary": {},
                "cash_gap_dates": [],
                "model_version": "v1.0",
            }

            resp = client.get("/api/forecast/cashflow", headers=auth_headers)
            assert resp.status_code == 200
            instance.generate_forecast.assert_called_with(horizon_days=90)

    def test_create_scenario(self, client, auth_headers, db_session):
        with patch(
            "app.routers.forecast.CashFlowForecastingAutomation"
        ) as MockForecast:
            instance = MockForecast.return_value
            instance.run_scenario.return_value = {
                "name": "Customer pays late",
                "description": "",
                "adjustments": {"delay_customer_42": 30},
                "forecasts": [
                    {
                        "date": "2026-03-01", "balance": 95000.0,
                        "low": 85000.0, "high": 105000.0,
                        "ar_expected": 0.0, "ap_expected": 0.0,
                        "pipeline_expected": 0.0, "recurring_expected": 0.0,
                    },
                ],
                "impact": {
                    "end_balance_change": -10000.0,
                    "worst_balance": 80000.0,
                    "worst_date": "2026-03-15",
                    "has_cash_gap": False,
                },
            }

            resp = client.post(
                "/api/forecast/scenario",
                json={
                    "name": "Customer pays late",
                    "adjustments": {"delay_customer_42": 30},
                },
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["name"] == "Customer pays late"
            assert data["impact"]["end_balance_change"] == -10000.0
            assert data["scenario_id"] > 0

    def test_get_accuracy(self, client, auth_headers, db_session):
        with patch(
            "app.routers.forecast.CashFlowForecastingAutomation"
        ) as MockForecast:
            instance = MockForecast.return_value
            instance.check_accuracy.return_value = {
                "last_30_days": {"mae": 2500.0, "mape": 3.2},
                "last_60_days": {"mae": 3000.0, "mape": 4.1},
                "last_90_days": {"mae": 3500.0, "mape": 5.0},
                "total_comparisons": 45,
            }

            resp = client.get("/api/forecast/accuracy", headers=auth_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["last_30_days"]["mae"] == 2500.0
            assert data["total_comparisons"] == 45

    def test_list_scenarios(self, client, auth_headers, db_session):
        sc = ForecastScenario(
            name="Test Scenario",
            adjustments={"delay_customer_1": 15},
            result_data={"forecasts": [], "impact": {"has_cash_gap": False}},
        )
        db_session.add(sc)
        db_session.commit()

        resp = client.get("/api/forecast/scenarios", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Test Scenario"

    def test_get_scenario_by_id(self, client, auth_headers, db_session):
        sc = ForecastScenario(
            name="Specific Scenario",
            adjustments={"reduce_ar_by": 10},
            result_data={
                "forecasts": [
                    {
                        "date": "2026-03-01", "balance": 90000.0,
                        "low": 80000.0, "high": 100000.0,
                        "ar_expected": 0.0, "ap_expected": 0.0,
                        "pipeline_expected": 0.0, "recurring_expected": 0.0,
                    },
                ],
                "impact": {"end_balance_change": -5000.0},
            },
        )
        db_session.add(sc)
        db_session.commit()

        resp = client.get(f"/api/forecast/scenarios/{sc.id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Specific Scenario"
        assert len(data["forecasts"]) == 1

    def test_get_scenario_not_found(self, client, auth_headers, db_session):
        resp = client.get("/api/forecast/scenarios/999", headers=auth_headers)
        assert resp.status_code == 404

    def test_requires_auth(self, client):
        resp = client.get("/api/forecast/cashflow")
        assert resp.status_code == 401

    def test_scenario_requires_auth(self, client):
        resp = client.post("/api/forecast/scenario", json={"name": "test", "adjustments": {}})
        assert resp.status_code == 401
