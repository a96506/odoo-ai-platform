"""Tests for role-based dashboard endpoints and WebSocket support."""

from datetime import datetime, date, timedelta
from unittest.mock import patch, MagicMock

import pytest

from app.models.audit import (
    AuditLog,
    ActionStatus,
    MonthEndClosing,
    ClosingStep,
    CashForecast,
    CreditScore,
    DailyDigest,
)


# ---------------------------------------------------------------------------
# CFO Dashboard
# ---------------------------------------------------------------------------

class TestCFODashboard:
    def test_cfo_empty_db(self, client, auth_headers):
        with patch("app.routers.role_dashboard._safe_odoo_client", return_value=None):
            res = client.get("/api/dashboard/cfo", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["cash_position"] == 0.0
        assert data["total_ar"] == 0.0
        assert data["total_ap"] == 0.0
        assert len(data["ar_aging"]) == 4
        assert len(data["ap_aging"]) == 4
        assert data["pending_approvals"] == 0
        assert data["cash_forecast"] == []
        assert data["anomalies"] == []

    def test_cfo_requires_auth(self, client):
        res = client.get("/api/dashboard/cfo")
        assert res.status_code == 401

    def test_cfo_with_forecast_data(self, client, auth_headers, db_session):
        today = date.today()
        for i in range(5):
            f = CashForecast(
                forecast_date=today,
                target_date=today + timedelta(days=i),
                predicted_balance=100000 - i * 5000,
                confidence_low=90000 - i * 5000,
                confidence_high=110000 - i * 5000,
                ar_expected=50000.0,
                ap_expected=30000.0,
            )
            db_session.add(f)
        db_session.commit()

        with patch("app.routers.role_dashboard._safe_odoo_client", return_value=None):
            res = client.get("/api/dashboard/cfo", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert len(data["cash_forecast"]) == 5
        assert data["cash_position"] == 100000.0

    def test_cfo_with_pending_approvals(self, client, auth_headers, db_session):
        audit = AuditLog(
            automation_type="accounting",
            action_name="categorize",
            odoo_model="account.move",
            odoo_record_id=1,
            status=ActionStatus.PENDING,
            confidence=0.9,
        )
        db_session.add(audit)
        db_session.commit()

        with patch("app.routers.role_dashboard._safe_odoo_client", return_value=None):
            res = client.get("/api/dashboard/cfo", headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["pending_approvals"] == 1

    def test_cfo_with_close_status(self, client, auth_headers, db_session):
        closing = MonthEndClosing(
            period=datetime.utcnow().strftime("%Y-%m"),
            status="in_progress",
            started_by="admin",
        )
        db_session.add(closing)
        db_session.flush()

        for i, name in enumerate(["reconcile_bank", "review_drafts", "check_depreciation"]):
            step = ClosingStep(
                closing_id=closing.id,
                step_name=name,
                step_order=i,
                status="complete" if i < 2 else "pending",
            )
            db_session.add(step)
        db_session.commit()

        with patch("app.routers.role_dashboard._safe_odoo_client", return_value=None):
            res = client.get("/api/dashboard/cfo", headers=auth_headers)
        assert res.status_code == 200
        cs = res.json()["close_status"]
        assert cs["status"] == "in_progress"
        assert cs["steps_completed"] == 2
        assert cs["steps_total"] == 3

    def test_cfo_with_anomalies(self, client, auth_headers, db_session):
        digest = DailyDigest(
            user_role="cfo",
            digest_date=date.today(),
            content={
                "headline": "Test",
                "anomalies": [
                    {"description": "Unusual expense spike", "severity": "high", "source": "accounting"},
                    {"description": "Late payment trend", "severity": "medium", "source": "ar"},
                ],
            },
        )
        db_session.add(digest)
        db_session.commit()

        with patch("app.routers.role_dashboard._safe_odoo_client", return_value=None):
            res = client.get("/api/dashboard/cfo", headers=auth_headers)
        assert res.status_code == 200
        anomalies = res.json()["anomalies"]
        assert len(anomalies) == 2
        assert anomalies[0]["severity"] == "high"

    def test_cfo_with_odoo_aging(self, client, auth_headers):
        mock_odoo = MagicMock()
        yesterday = (datetime.utcnow() - timedelta(days=10)).strftime("%Y-%m-%d")
        mock_odoo.search_read.side_effect = [
            [{"amount_residual": 5000.0, "invoice_date_due": yesterday}],
            [{"amount_residual": 3000.0, "invoice_date_due": yesterday}],
            [], [],
        ]
        with patch("app.routers.role_dashboard._safe_odoo_client", return_value=mock_odoo):
            res = client.get("/api/dashboard/cfo", headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["total_ar"] == 5000.0

    def test_cfo_generated_at(self, client, auth_headers):
        with patch("app.routers.role_dashboard._safe_odoo_client", return_value=None):
            res = client.get("/api/dashboard/cfo", headers=auth_headers)
        assert res.json()["generated_at"] is not None


# ---------------------------------------------------------------------------
# Sales Dashboard
# ---------------------------------------------------------------------------

class TestSalesDashboard:
    def test_sales_empty(self, client, auth_headers):
        with patch("app.routers.role_dashboard._safe_odoo_client", return_value=None):
            res = client.get("/api/dashboard/sales", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["pipeline_value"] == 0.0
        assert data["pipeline_stages"] == []
        assert data["at_risk_deals"] == []
        assert data["win_rate"] == 0.0

    def test_sales_requires_auth(self, client):
        res = client.get("/api/dashboard/sales")
        assert res.status_code == 401

    def test_sales_with_odoo_leads(self, client, auth_headers):
        mock_odoo = MagicMock()
        mock_odoo.search_read.side_effect = [
            [
                {
                    "id": 1,
                    "name": "Big Deal",
                    "expected_revenue": 50000,
                    "probability": 60,
                    "stage_id": [1, "Qualification"],
                    "date_deadline": datetime.utcnow().strftime("%Y-%m-%d"),
                    "write_date": (datetime.utcnow() - timedelta(days=5)).strftime("%Y-%m-%d"),
                    "partner_id": [1, "Customer"],
                },
                {
                    "id": 2,
                    "name": "Stale Deal",
                    "expected_revenue": 20000,
                    "probability": 20,
                    "stage_id": [2, "Proposal"],
                    "date_deadline": None,
                    "write_date": (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d"),
                    "partner_id": [2, "Other"],
                },
            ],
            [],
        ]
        mock_odoo.search_count.side_effect = [5, 10]

        with patch("app.routers.role_dashboard._safe_odoo_client", return_value=mock_odoo):
            res = client.get("/api/dashboard/sales", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["pipeline_value"] == 70000.0
        assert len(data["pipeline_stages"]) == 2
        assert data["deals_closing_this_month"] >= 1
        assert len(data["at_risk_deals"]) >= 1
        assert data["win_rate"] > 0

    def test_sales_recent_automations(self, client, auth_headers, db_session):
        for i in range(3):
            audit = AuditLog(
                automation_type="crm",
                action_name="score_lead",
                odoo_model="crm.lead",
                odoo_record_id=i,
                status=ActionStatus.EXECUTED,
                confidence=0.9,
            )
            db_session.add(audit)
        db_session.commit()

        with patch("app.routers.role_dashboard._safe_odoo_client", return_value=None):
            res = client.get("/api/dashboard/sales", headers=auth_headers)
        assert res.json()["recent_automations"] == 3

    def test_sales_generated_at(self, client, auth_headers):
        with patch("app.routers.role_dashboard._safe_odoo_client", return_value=None):
            res = client.get("/api/dashboard/sales", headers=auth_headers)
        assert res.json()["generated_at"] is not None


# ---------------------------------------------------------------------------
# Warehouse Dashboard
# ---------------------------------------------------------------------------

class TestWarehouseDashboard:
    def test_warehouse_empty(self, client, auth_headers):
        with patch("app.routers.role_dashboard._safe_odoo_client", return_value=None):
            res = client.get("/api/dashboard/warehouse", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["total_products"] == 0
        assert data["below_reorder"] == 0
        assert data["stock_alerts"] == []

    def test_warehouse_requires_auth(self, client):
        res = client.get("/api/dashboard/warehouse")
        assert res.status_code == 401

    def test_warehouse_with_products(self, client, auth_headers):
        mock_odoo = MagicMock()
        mock_odoo.search_read.side_effect = [
            [
                {"id": 1, "name": "Widget A", "qty_available": 5, "reorder_min_qty": 10},
                {"id": 2, "name": "Widget B", "qty_available": 50, "reorder_min_qty": 20},
                {"id": 3, "name": "Widget C", "qty_available": 0, "reorder_min_qty": 5},
            ],
            [{"state": "assigned"}, {"state": "waiting"}],
            [{"state": "assigned"}],
        ]

        with patch("app.routers.role_dashboard._safe_odoo_client", return_value=mock_odoo):
            res = client.get("/api/dashboard/warehouse", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["total_products"] == 3
        assert data["below_reorder"] == 2
        assert len(data["stock_alerts"]) == 2
        assert data["stock_alerts"][0]["status"] == "critical"
        assert data["stock_alerts"][1]["status"] == "low"
        assert data["shipments"]["incoming_count"] == 2
        assert data["shipments"]["incoming_ready"] == 1

    def test_warehouse_recent_automations(self, client, auth_headers, db_session):
        audit = AuditLog(
            automation_type="inventory",
            action_name="auto_reorder",
            odoo_model="product.product",
            odoo_record_id=1,
            status=ActionStatus.EXECUTED,
            confidence=0.95,
        )
        db_session.add(audit)
        db_session.commit()

        with patch("app.routers.role_dashboard._safe_odoo_client", return_value=None):
            res = client.get("/api/dashboard/warehouse", headers=auth_headers)
        assert res.json()["recent_automations"] == 1

    def test_warehouse_generated_at(self, client, auth_headers):
        with patch("app.routers.role_dashboard._safe_odoo_client", return_value=None):
            res = client.get("/api/dashboard/warehouse", headers=auth_headers)
        assert res.json()["generated_at"] is not None


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

class TestWebSocket:
    def test_ws_connect_disconnect(self, client):
        with client.websocket_connect("/ws/dashboard") as ws:
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            assert data["type"] == "pong"
            assert "timestamp" in data

    def test_ws_connect_with_role(self, client):
        with client.websocket_connect("/ws/dashboard?role=cfo") as ws:
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            assert data["type"] == "pong"

    def test_connection_manager_broadcast(self):
        import asyncio
        from app.routers.websocket import ConnectionManager

        mgr = ConnectionManager()
        assert mgr.count == 0

    def test_publish_event_without_redis(self):
        from app.routers.websocket import publish_event
        publish_event("test_event", {"key": "value"})


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TestDashboardSchemas:
    def test_cfo_response_defaults(self):
        from app.models.schemas import CFODashboardResponse
        r = CFODashboardResponse()
        assert r.cash_position == 0.0
        assert r.ar_aging == []
        assert r.anomalies == []

    def test_sales_response_defaults(self):
        from app.models.schemas import SalesDashboardResponse
        r = SalesDashboardResponse()
        assert r.pipeline_value == 0.0
        assert r.pipeline_stages == []

    def test_warehouse_response_defaults(self):
        from app.models.schemas import WarehouseDashboardResponse
        r = WarehouseDashboardResponse()
        assert r.total_products == 0
        assert r.stock_alerts == []

    def test_aging_bucket(self):
        from app.models.schemas import AgingBucket
        b = AgingBucket(bucket="0-30", amount=5000.0, count=3)
        assert b.bucket == "0-30"
        assert b.amount == 5000.0

    def test_pipeline_stage(self):
        from app.models.schemas import PipelineStage
        s = PipelineStage(stage="Qualification", count=5, value=25000)
        assert s.stage == "Qualification"

    def test_at_risk_deal(self):
        from app.models.schemas import AtRiskDeal
        d = AtRiskDeal(lead_id=1, name="Test", value=10000, probability=20, days_stale=45, stage="Proposal")
        assert d.days_stale == 45

    def test_stock_alert(self):
        from app.models.schemas import StockAlert
        a = StockAlert(product_id=1, product_name="Widget", qty_available=5, reorder_point=10, status="low")
        assert a.status == "low"

    def test_websocket_message(self):
        from app.models.schemas import WebSocketMessage
        m = WebSocketMessage(type="automation_completed", data={"id": 1})
        assert m.type == "automation_completed"

    def test_close_status_summary(self):
        from app.models.schemas import CloseStatusSummary
        c = CloseStatusSummary(period="2026-02", status="in_progress", progress_pct=60.0, steps_total=10, steps_completed=6)
        assert c.progress_pct == 60.0

    def test_pl_summary(self):
        from app.models.schemas import PLSummary
        p = PLSummary(total_revenue=100000, total_expenses=80000, net_income=20000, period="2026-02")
        assert p.net_income == 20000

    def test_shipment_summary(self):
        from app.models.schemas import ShipmentSummary
        s = ShipmentSummary(incoming_count=5, incoming_ready=3, outgoing_count=8, outgoing_ready=6)
        assert s.incoming_ready == 3


# ---------------------------------------------------------------------------
# Celery event publishing
# ---------------------------------------------------------------------------

class TestCeleryEventPublishing:
    def test_publish_dashboard_event_import(self):
        from app.tasks.celery_tasks import _publish_dashboard_event
        _publish_dashboard_event("test", {"key": "value"})

    def test_publish_dashboard_event_with_role(self):
        from app.tasks.celery_tasks import _publish_dashboard_event
        _publish_dashboard_event("forecast_updated", {"date": "2026-02-26"}, role="cfo")
