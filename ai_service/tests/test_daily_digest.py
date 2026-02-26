"""Tests for Proactive AI Daily Digest (deliverable 1.11)."""

from datetime import datetime, date, timedelta
from unittest.mock import patch, MagicMock

import pytest

from app.models.audit import DailyDigest, AuditLog
from app.automations.daily_digest import (
    DailyDigestAutomation,
    ROLE_CONFIGS,
    DEFAULT_DIGEST_CONFIG,
    _format_data_for_prompt,
)


# ---------------------------------------------------------------------------
# Unit tests — data aggregation
# ---------------------------------------------------------------------------


class TestRoleConfiguration:

    def test_all_roles_have_configs(self):
        assert "cfo" in ROLE_CONFIGS
        assert "sales_manager" in ROLE_CONFIGS
        assert "warehouse_manager" in ROLE_CONFIGS

    def test_all_roles_have_default_digest_config(self):
        for role in ROLE_CONFIGS:
            assert role in DEFAULT_DIGEST_CONFIG
            assert "channels" in DEFAULT_DIGEST_CONFIG[role]
            assert "send_time" in DEFAULT_DIGEST_CONFIG[role]
            assert "enabled" in DEFAULT_DIGEST_CONFIG[role]

    def test_role_config_has_data_sources(self):
        for role, config in ROLE_CONFIGS.items():
            assert "title" in config
            assert "data_sources" in config
            assert len(config["data_sources"]) > 0


class TestFallbackDigest:

    def _make_automation(self):
        with patch("app.automations.base.get_settings") as mock_s:
            mock_s.return_value = MagicMock(
                auto_approve_threshold=0.95,
                default_confidence_threshold=0.85,
            )
            return DailyDigestAutomation()

    def test_cfo_fallback_with_overdue(self):
        automation = self._make_automation()
        raw_data = {
            "overdue_ar_count": 5,
            "overdue_ar_total": 12500.00,
            "open_ap_count": 10,
            "open_ap_total": 35000.00,
            "overdue_ap_count": 2,
            "overdue_ap_total": 8000.00,
            "pending_approvals": 3,
            "anomalies": [],
        }
        result = automation._build_fallback_digest("cfo", raw_data, date.today())

        assert result["headline"]
        assert result["summary"]
        assert len(result["key_metrics"]) >= 3
        assert any(m["name"] == "Overdue AR" for m in result["key_metrics"])
        assert len(result["attention_items"]) >= 1
        assert result["attention_items"][0]["priority"] == "high"

    def test_sales_manager_fallback(self):
        automation = self._make_automation()
        raw_data = {
            "total_pipeline_value": 500000.00,
            "weighted_pipeline_value": 150000.00,
            "total_opportunities": 42,
            "at_risk_count": 3,
            "at_risk_value": 75000.00,
            "won_last_7_days": 5,
            "won_value_last_7_days": 45000.00,
            "lost_last_7_days": 2,
            "lost_value_last_7_days": 20000.00,
            "overdue_followups": 8,
        }
        result = automation._build_fallback_digest("sales_manager", raw_data, date.today())

        assert len(result["key_metrics"]) >= 3
        assert any(m["name"] == "Pipeline Value" for m in result["key_metrics"])
        assert len(result["attention_items"]) >= 1

    def test_warehouse_manager_fallback(self):
        automation = self._make_automation()
        raw_data = {
            "low_stock_count": 8,
            "low_stock_items": [],
            "pending_receipts_count": 5,
            "overdue_deliveries_count": 3,
            "pending_deliveries_today": 12,
        }
        result = automation._build_fallback_digest("warehouse_manager", raw_data, date.today())

        assert len(result["key_metrics"]) >= 3
        assert any(m["name"] == "Low Stock Items" for m in result["key_metrics"])
        assert len(result["attention_items"]) >= 1

    def test_cfo_fallback_no_issues(self):
        automation = self._make_automation()
        raw_data = {
            "overdue_ar_count": 0,
            "overdue_ar_total": 0.0,
            "open_ap_count": 0,
            "open_ap_total": 0.0,
            "overdue_ap_count": 0,
            "overdue_ap_total": 0.0,
            "pending_approvals": 0,
            "anomalies": [],
        }
        result = automation._build_fallback_digest("cfo", raw_data, date.today())
        assert len(result["attention_items"]) == 0


class TestEmailFormatting:

    def _make_automation(self):
        with patch("app.automations.base.get_settings") as mock_s:
            mock_s.return_value = MagicMock(
                auto_approve_threshold=0.95,
                default_confidence_threshold=0.85,
            )
            return DailyDigestAutomation()

    def test_plain_text_format(self):
        automation = self._make_automation()
        content = {
            "headline": "5 Overdue Invoices Need Attention",
            "summary": "AR aging increased by 12% overnight.",
            "key_metrics": [
                {"name": "AR Total", "value": "$125,000", "change_label": "up 12%"},
                {"name": "AP Total", "value": "$80,000", "change_label": ""},
            ],
            "attention_items": [
                {"title": "Customer ABC overdue", "description": "$5,000 past 60 days", "priority": "high"},
            ],
            "anomalies": [
                {"description": "Unusual transaction pattern", "severity": "medium"},
            ],
        }
        text = automation._format_digest_email("cfo", content)
        assert "5 Overdue Invoices" in text
        assert "AR Total" in text
        assert "Customer ABC" in text
        assert "[HIGH]" in text
        assert "[MEDIUM]" in text

    def test_html_format(self):
        automation = self._make_automation()
        content = {
            "headline": "Daily Briefing",
            "summary": "All clear today.",
            "key_metrics": [
                {"name": "Revenue", "value": "$50,000"},
            ],
            "attention_items": [],
            "anomalies": [],
        }
        html = automation._format_digest_html("cfo", content)
        assert "Daily Briefing" in html
        assert "Revenue" in html
        assert "CFO" in html
        assert "<div" in html


class TestDigestGeneration:

    def _make_automation(self):
        with patch("app.automations.base.get_settings") as mock_s:
            mock_s.return_value = MagicMock(
                auto_approve_threshold=0.95,
                default_confidence_threshold=0.85,
            )
            return DailyDigestAutomation()

    @patch("app.automations.base.get_odoo_client")
    @patch("app.automations.base.get_claude_client")
    def test_generate_digest_with_ai(self, mock_claude_fn, mock_odoo_fn):
        mock_odoo = MagicMock()
        mock_odoo.search_read.return_value = []
        mock_odoo_fn.return_value = mock_odoo

        mock_claude = MagicMock()
        mock_claude.analyze.return_value = {
            "text": "",
            "tool_calls": [{
                "name": "generate_digest",
                "input": {
                    "headline": "Strong Q1 Close",
                    "summary": "Finances are in good shape.",
                    "key_metrics": [{"name": "Revenue", "value": "$1M"}],
                    "attention_items": [],
                    "anomalies": [],
                },
            }],
        }
        mock_claude_fn.return_value = mock_claude

        automation = self._make_automation()
        with patch.object(automation, "_count_pending_approvals", return_value=0), \
             patch.object(automation, "_fetch_recent_anomalies", return_value=[]):
            result = automation.generate_digest("cfo", date.today())

        assert result["role"] == "cfo"
        assert result["content"]["headline"] == "Strong Q1 Close"

    def test_generate_digest_unknown_role(self):
        automation = self._make_automation()
        result = automation.generate_digest("unknown_role")
        assert "error" in result

    @patch("app.automations.base.get_odoo_client")
    @patch("app.automations.base.get_claude_client")
    def test_generate_digest_ai_fails_uses_fallback(self, mock_claude_fn, mock_odoo_fn):
        mock_odoo = MagicMock()
        mock_odoo.search_read.return_value = []
        mock_odoo_fn.return_value = mock_odoo

        mock_claude = MagicMock()
        mock_claude.analyze.side_effect = Exception("Claude API unavailable")
        mock_claude_fn.return_value = mock_claude

        automation = self._make_automation()
        with patch.object(automation, "_count_pending_approvals", return_value=0), \
             patch.object(automation, "_fetch_recent_anomalies", return_value=[]):
            result = automation.generate_digest("cfo", date.today())

        assert result["role"] == "cfo"
        assert "content" in result
        assert "AI narrative unavailable" in result["content"]["summary"]


class TestFormatDataForPrompt:

    def test_formats_dict(self):
        data = {"overdue_ar_count": 5, "role": "cfo", "total": 1000.0}
        result = _format_data_for_prompt(data)
        assert "overdue_ar_count" in result
        assert "role" not in result


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestDigestAPI:

    @patch("app.routers.digest.DailyDigestAutomation")
    def test_get_latest_generates_new(self, mock_cls, client, auth_headers, db_session):
        mock_instance = MagicMock()
        mock_instance.generate_digest.return_value = {
            "role": "cfo",
            "digest_date": date.today().isoformat(),
            "content": {
                "headline": "Test Digest",
                "summary": "All good.",
                "key_metrics": [],
                "attention_items": [],
                "anomalies": [],
            },
        }
        mock_cls.return_value = mock_instance

        response = client.get("/api/digest/latest?role=cfo", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "cfo"
        assert data["content"]["headline"] == "Test Digest"

    def test_get_latest_returns_existing(self, client, auth_headers, db_session):
        digest = DailyDigest(
            user_role="cfo",
            digest_date=date.today(),
            content={
                "headline": "Existing Digest",
                "summary": "Already generated.",
                "key_metrics": [],
                "attention_items": [],
                "anomalies": [],
            },
            channels_sent=["email"],
            delivered=True,
        )
        db_session.add(digest)
        db_session.flush()

        response = client.get("/api/digest/latest?role=cfo", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["content"]["headline"] == "Existing Digest"
        assert data["delivered"] is True

    def test_get_latest_unknown_role(self, client, auth_headers):
        response = client.get("/api/digest/latest?role=unknown", headers=auth_headers)
        assert response.status_code == 400

    def test_get_latest_no_auth(self, client):
        response = client.get("/api/digest/latest?role=cfo")
        assert response.status_code == 401

    def test_update_config(self, client, auth_headers):
        response = client.put(
            "/api/digest/config",
            headers=auth_headers,
            json={
                "role": "cfo",
                "channels": ["email", "slack"],
                "send_time": "08:00",
                "enabled": True,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["updated"] is True
        assert "slack" in data["channels"]

    def test_update_config_unknown_role(self, client, auth_headers):
        response = client.put(
            "/api/digest/config",
            headers=auth_headers,
            json={"role": "unknown", "channels": ["email"]},
        )
        assert response.status_code == 400

    def test_digest_history(self, client, auth_headers, db_session):
        for i in range(3):
            d = DailyDigest(
                user_role="cfo",
                digest_date=date.today() - timedelta(days=i),
                content={"headline": f"Day {i}", "summary": "", "key_metrics": [], "attention_items": [], "anomalies": []},
            )
            db_session.add(d)
        db_session.flush()

        response = client.get("/api/digest/history?role=cfo", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3

    def test_digest_history_no_role(self, client, auth_headers, db_session):
        db_session.add(DailyDigest(
            user_role="cfo", digest_date=date.today(),
            content={"headline": "A", "summary": "", "key_metrics": [], "attention_items": [], "anomalies": []},
        ))
        db_session.add(DailyDigest(
            user_role="sales_manager", digest_date=date.today(),
            content={"headline": "B", "summary": "", "key_metrics": [], "attention_items": [], "anomalies": []},
        ))
        db_session.flush()

        response = client.get("/api/digest/history", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    @patch("app.routers.digest.DailyDigestAutomation")
    def test_preview_digest(self, mock_cls, client, auth_headers):
        mock_instance = MagicMock()
        mock_instance.generate_digest.return_value = {
            "role": "sales_manager",
            "digest_date": date.today().isoformat(),
            "content": {
                "headline": "Pipeline Growing",
                "summary": "Strong week.",
                "key_metrics": [{"name": "Pipeline", "value": "$500K"}],
                "attention_items": [],
                "anomalies": [],
            },
        }
        mock_cls.return_value = mock_instance

        response = client.get("/api/digest/preview?role=sales_manager", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["content"]["headline"] == "Pipeline Growing"

    @patch("app.routers.digest.DailyDigestAutomation")
    def test_send_digest(self, mock_cls, client, auth_headers, db_session):
        digest = DailyDigest(
            user_role="cfo",
            digest_date=date.today(),
            content={"headline": "Test", "summary": "Test", "key_metrics": [], "attention_items": [], "anomalies": []},
        )
        db_session.add(digest)
        db_session.flush()

        mock_instance = MagicMock()
        mock_instance.deliver_digest.return_value = True
        mock_cls.return_value = mock_instance

        response = client.post(
            "/api/digest/send",
            headers=auth_headers,
            json={"role": "cfo", "channel": "email", "recipient": "cfo@company.com"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sent"] is True

    def test_send_digest_no_recipient(self, client, auth_headers, db_session):
        digest = DailyDigest(
            user_role="cfo",
            digest_date=date.today(),
            content={"headline": "Test"},
        )
        db_session.add(digest)
        db_session.flush()

        response = client.post(
            "/api/digest/send",
            headers=auth_headers,
            json={"role": "cfo", "channel": "email"},
        )
        assert response.status_code == 400
