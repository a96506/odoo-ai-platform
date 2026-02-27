"""
Tests for supply chain intelligence: risk scoring, disruption prediction,
single-source detection, anomaly detection, and /api/supply-chain endpoints.
"""

import math
from datetime import datetime, date, timedelta
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from app.models.audit import (
    SupplierRiskScore,
    SupplyChainAlert,
    DisruptionPrediction,
    RiskClassification,
    AlertSeverity,
)


# ---------------------------------------------------------------------------
# Anomaly Detection — Benford's Law
# ---------------------------------------------------------------------------


class TestBenfordAnalysis:
    def test_insufficient_data(self):
        from app.automations.anomaly_detection import AnomalyDetector

        result = AnomalyDetector.benford_analysis([100, 200, 300])
        assert result["is_anomalous"] is False
        assert result["reason"] == "insufficient_data"

    def test_benford_conforming_distribution(self):
        """A large set following Benford's Law should NOT be flagged."""
        from app.automations.anomaly_detection import AnomalyDetector, BENFORD_EXPECTED
        import random

        random.seed(42)
        amounts = []
        for digit, freq in BENFORD_EXPECTED.items():
            count = int(freq * 500)
            for _ in range(count):
                amounts.append(digit * 10 ** random.uniform(1, 4))

        result = AnomalyDetector.benford_analysis(amounts)
        assert result["is_anomalous"] is False
        assert result["sample_size"] >= 400

    def test_benford_uniform_distribution_flagged(self):
        """A uniform leading-digit distribution should be flagged."""
        from app.automations.anomaly_detection import AnomalyDetector

        amounts = []
        for digit in range(1, 10):
            amounts.extend([digit * 100 + i for i in range(60)])

        result = AnomalyDetector.benford_analysis(amounts)
        assert result["is_anomalous"] is True
        assert result["chi_squared"] > result["threshold"]

    def test_benford_with_zero_amounts(self):
        """Zero amounts should be ignored gracefully."""
        from app.automations.anomaly_detection import AnomalyDetector

        amounts = [0.0] * 100 + [100, 200, 300]
        result = AnomalyDetector.benford_analysis(amounts)
        assert result["is_anomalous"] is False


# ---------------------------------------------------------------------------
# Anomaly Detection — Z-score
# ---------------------------------------------------------------------------


class TestZscoreAnalysis:
    def test_no_outliers_in_normal_data(self):
        from app.automations.anomaly_detection import AnomalyDetector

        transactions = [
            {"id": i, "name": f"INV/{i:04d}", "amount_total": 100 + i, "journal_id": [1, "Sales"]}
            for i in range(50)
        ]
        outliers = AnomalyDetector.zscore_analysis(transactions, threshold=3.0)
        assert len(outliers) == 0

    def test_detects_outlier(self):
        from app.automations.anomaly_detection import AnomalyDetector

        transactions = [
            {"id": i, "name": f"INV/{i:04d}", "amount_total": 100, "journal_id": [1, "Sales"]}
            for i in range(50)
        ]
        transactions.append(
            {"id": 999, "name": "INV/OUTLIER", "amount_total": 100000, "journal_id": [1, "Sales"]}
        )

        outliers = AnomalyDetector.zscore_analysis(transactions, threshold=3.0)
        assert len(outliers) >= 1
        assert outliers[0]["move_name"] == "INV/OUTLIER"
        assert abs(outliers[0]["zscore"]) > 3.0

    def test_groups_by_journal(self):
        from app.automations.anomaly_detection import AnomalyDetector

        journal_a = [
            {"id": i, "name": f"A/{i}", "amount_total": 100, "journal_id": [1, "Sales"]}
            for i in range(20)
        ]
        journal_b = [
            {"id": i + 100, "name": f"B/{i}", "amount_total": 5000, "journal_id": [2, "Purchases"]}
            for i in range(20)
        ]
        transactions = journal_a + journal_b

        outliers = AnomalyDetector.zscore_analysis(transactions, threshold=3.0)
        assert len(outliers) == 0

    def test_insufficient_data_per_journal(self):
        from app.automations.anomaly_detection import AnomalyDetector

        transactions = [
            {"id": i, "name": f"T/{i}", "amount_total": i * 100, "journal_id": [1, "Sales"]}
            for i in range(5)
        ]
        outliers = AnomalyDetector.zscore_analysis(transactions)
        assert len(outliers) == 0


# ---------------------------------------------------------------------------
# SupplyChainAutomation — risk scoring
# ---------------------------------------------------------------------------


class TestSupplierRiskScoring:
    def test_delivery_performance_perfect(self):
        from app.automations.supply_chain import SupplyChainAutomation

        mock_odoo = MagicMock()
        now = datetime.utcnow()
        mock_odoo.search_read.return_value = [
            {"scheduled_date": now.isoformat(), "date_done": now.isoformat()}
            for _ in range(10)
        ]

        with patch("app.automations.base.get_odoo_client", return_value=mock_odoo):
            auto = SupplyChainAutomation()
            score = auto._score_delivery_performance(1)
            assert score == 100.0

    def test_delivery_performance_no_data(self):
        from app.automations.supply_chain import SupplyChainAutomation

        mock_odoo = MagicMock()
        mock_odoo.search_read.return_value = []

        with patch("app.automations.base.get_odoo_client", return_value=mock_odoo):
            auto = SupplyChainAutomation()
            score = auto._score_delivery_performance(1)
            assert score == 70.0

    def test_risk_classification(self):
        from app.automations.supply_chain import _classify_risk, RiskClassification

        assert _classify_risk(90) == RiskClassification.LOW
        assert _classify_risk(80) == RiskClassification.LOW
        assert _classify_risk(70) == RiskClassification.WATCH
        assert _classify_risk(60) == RiskClassification.WATCH
        assert _classify_risk(50) == RiskClassification.ELEVATED
        assert _classify_risk(30) == RiskClassification.CRITICAL

    def test_dependency_concentration_high(self):
        from app.automations.supply_chain import SupplyChainAutomation

        mock_odoo = MagicMock()
        mock_odoo.search_read.side_effect = [
            [{"amount_total": 600000}],
            [{"amount_total": 1000000}],
        ]

        with patch("app.automations.base.get_odoo_client", return_value=mock_odoo):
            auto = SupplyChainAutomation()
            score = auto._score_dependency_concentration(1)
            assert score == 20.0

    def test_communication_fast_response(self):
        from app.automations.supply_chain import SupplyChainAutomation

        mock_odoo = MagicMock()
        now = datetime.utcnow()
        mock_odoo.search_read.return_value = [
            {"date_order": now.isoformat(), "date_approve": now.isoformat()}
            for _ in range(5)
        ]

        with patch("app.automations.base.get_odoo_client", return_value=mock_odoo):
            auto = SupplyChainAutomation()
            score = auto._score_communication(1)
            assert score == 95.0


# ---------------------------------------------------------------------------
# Degradation detection
# ---------------------------------------------------------------------------


class TestDeliveryDegradation:
    def test_no_degradation(self):
        from app.automations.supply_chain import SupplyChainAutomation

        mock_odoo = MagicMock()
        now = datetime.utcnow()
        same_day = [{"scheduled_date": now.isoformat(), "date_done": now.isoformat()} for _ in range(10)]
        mock_odoo.search_read.side_effect = [same_day[:5], same_day[5:]]

        with patch("app.automations.base.get_odoo_client", return_value=mock_odoo):
            auto = SupplyChainAutomation()
            result = auto._check_degradation(1)
            if result:
                assert result["is_degrading"] is False

    def test_insufficient_data_returns_none(self):
        from app.automations.supply_chain import SupplyChainAutomation

        mock_odoo = MagicMock()
        mock_odoo.search_read.side_effect = [[], []]

        with patch("app.automations.base.get_odoo_client", return_value=mock_odoo):
            auto = SupplyChainAutomation()
            result = auto._check_degradation(1)
            assert result is None


# ---------------------------------------------------------------------------
# /api/supply-chain endpoint tests
# ---------------------------------------------------------------------------


class TestSupplyChainEndpoints:
    def test_list_risk_scores_empty(self, client, auth_headers):
        resp = client.get("/api/supply-chain/risk-scores", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_vendor_risk_not_found(self, client, auth_headers):
        resp = client.get("/api/supply-chain/risk-scores/999", headers=auth_headers)
        assert resp.status_code == 404

    def test_list_predictions_empty(self, client, auth_headers):
        resp = client.get("/api/supply-chain/predictions", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_alerts_empty(self, client, auth_headers):
        resp = client.get("/api/supply-chain/alerts", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_resolve_alert_not_found(self, client, auth_headers):
        resp = client.post("/api/supply-chain/alerts/999/resolve", headers=auth_headers)
        assert resp.status_code == 404

    def test_list_single_source_empty(self, client, auth_headers):
        resp = client.get("/api/supply-chain/single-source", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_trigger_scan(self, client, auth_headers):
        with patch("app.tasks.celery_tasks.run_supplier_risk_scoring") as mock_task:
            mock_task.delay = MagicMock()
            resp = client.post("/api/supply-chain/scan", headers=auth_headers)
            assert resp.status_code == 200
            assert resp.json()["status"] == "scan_queued"

    def test_auth_required(self, client):
        resp = client.get("/api/supply-chain/risk-scores")
        assert resp.status_code in (401, 403)

    def test_risk_scores_with_data(self, client, auth_headers, db_session):
        risk_score = SupplierRiskScore(
            vendor_id=42,
            vendor_name="Test Vendor",
            score=75.5,
            classification=RiskClassification.WATCH,
        )
        db_session.add(risk_score)
        db_session.commit()

        resp = client.get("/api/supply-chain/risk-scores", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["vendor_id"] == 42
        assert data[0]["classification"] == "watch"

    def test_alerts_with_data(self, client, auth_headers, db_session):
        alert = SupplyChainAlert(
            vendor_id=42,
            alert_type="delivery_degradation",
            severity=AlertSeverity.HIGH,
            title="Test alert",
            message="Testing",
        )
        db_session.add(alert)
        db_session.commit()

        resp = client.get("/api/supply-chain/alerts", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["severity"] == "high"

    def test_resolve_alert_success(self, client, auth_headers, db_session):
        alert = SupplyChainAlert(
            vendor_id=42,
            alert_type="test",
            severity=AlertSeverity.LOW,
            title="Test",
            message="Test",
        )
        db_session.add(alert)
        db_session.commit()

        resp = client.post(f"/api/supply-chain/alerts/{alert.id}/resolve", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "resolved"
