"""
Tests for Slack integration: channel, Block Kit messages, interaction router, digest delivery.
"""

import hashlib
import hmac
import json
import time
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings
from app.models.audit import AuditLog, ActionStatus, AutomationType


# ---------------------------------------------------------------------------
# SlackChannel unit tests
# ---------------------------------------------------------------------------


class TestSlackChannel:
    def test_not_configured_by_default(self):
        from app.notifications.slack import SlackChannel

        ch = SlackChannel()
        with patch("app.notifications.slack.get_settings") as m:
            m.return_value = Settings()
            assert ch.is_configured() is False

    def test_configured_with_token(self):
        from app.notifications.slack import SlackChannel

        ch = SlackChannel()
        with patch("app.notifications.slack.get_settings") as m:
            m.return_value = Settings(slack_bot_token="xoxb-test-token")
            assert ch.is_configured() is True

    def test_send_plain_text(self):
        from app.notifications.slack import SlackChannel

        ch = SlackChannel()
        mock_client = MagicMock()
        mock_client.chat_postMessage.return_value = {"ts": "1234567890.123456"}

        with (
            patch("app.notifications.slack.get_settings") as m_settings,
            patch.object(ch, "_get_client", return_value=mock_client),
        ):
            m_settings.return_value = Settings(
                slack_bot_token="xoxb-test",
                slack_default_channel="#general",
            )
            result = ch.send("#alerts", "Test Subject", "Test body")

        assert result is True
        mock_client.chat_postMessage.assert_called_once()
        call_kwargs = mock_client.chat_postMessage.call_args
        assert call_kwargs.kwargs["channel"] == "#alerts"
        assert "Test Subject" in call_kwargs.kwargs["text"]

    def test_send_with_blocks(self):
        from app.notifications.slack import SlackChannel

        ch = SlackChannel()
        mock_client = MagicMock()
        mock_client.chat_postMessage.return_value = {"ts": "1234567890.123456"}
        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "Hello"}}]

        with (
            patch("app.notifications.slack.get_settings") as m_settings,
            patch.object(ch, "_get_client", return_value=mock_client),
        ):
            m_settings.return_value = Settings(
                slack_bot_token="xoxb-test",
                slack_default_channel="#general",
            )
            result = ch.send("#alerts", "Subject", "Body", blocks=blocks)

        assert result is True
        call_kwargs = mock_client.chat_postMessage.call_args
        assert call_kwargs.kwargs["blocks"] == blocks

    def test_send_uses_default_channel(self):
        from app.notifications.slack import SlackChannel

        ch = SlackChannel()
        mock_client = MagicMock()
        mock_client.chat_postMessage.return_value = {"ts": "123"}

        with (
            patch("app.notifications.slack.get_settings") as m_settings,
            patch.object(ch, "_get_client", return_value=mock_client),
        ):
            m_settings.return_value = Settings(
                slack_bot_token="xoxb-test",
                slack_default_channel="#fallback",
            )
            ch.send("", "Subject", "Body")

        call_kwargs = mock_client.chat_postMessage.call_args
        assert call_kwargs.kwargs["channel"] == "#fallback"

    def test_send_failure_returns_false(self):
        from app.notifications.slack import SlackChannel

        ch = SlackChannel()
        mock_client = MagicMock()
        mock_client.chat_postMessage.side_effect = Exception("API error")

        with (
            patch("app.notifications.slack.get_settings") as m_settings,
            patch.object(ch, "_get_client", return_value=mock_client),
        ):
            m_settings.return_value = Settings(
                slack_bot_token="xoxb-test",
                slack_default_channel="#general",
            )
            result = ch.send("#alerts", "Subject", "Body")

        assert result is False

    def test_send_not_configured_returns_false(self):
        from app.notifications.slack import SlackChannel

        ch = SlackChannel()
        with patch("app.notifications.slack.get_settings") as m_settings:
            m_settings.return_value = Settings()
            result = ch.send("#alerts", "Subject", "Body")
        assert result is False

    def test_send_with_thread_ts(self):
        from app.notifications.slack import SlackChannel

        ch = SlackChannel()
        mock_client = MagicMock()
        mock_client.chat_postMessage.return_value = {"ts": "123"}

        with (
            patch("app.notifications.slack.get_settings") as m_settings,
            patch.object(ch, "_get_client", return_value=mock_client),
        ):
            m_settings.return_value = Settings(
                slack_bot_token="xoxb-test",
                slack_default_channel="#general",
            )
            ch.send("#alerts", "Subject", "Body", thread_ts="111.222")

        call_kwargs = mock_client.chat_postMessage.call_args
        assert call_kwargs.kwargs["thread_ts"] == "111.222"


# ---------------------------------------------------------------------------
# Block Kit builder tests
# ---------------------------------------------------------------------------


class TestBlockKitBuilders:
    def test_approval_blocks_structure(self):
        from app.notifications.slack import build_approval_blocks

        blocks = build_approval_blocks(
            audit_log_id=42,
            automation_type="accounting",
            action_name="categorize_transaction",
            model="account.move",
            record_id=100,
            confidence=0.91,
            reasoning="AI suggests categorizing this as office supplies.",
        )
        assert len(blocks) >= 4
        assert blocks[0]["type"] == "header"
        assert "Approval Required" in blocks[0]["text"]["text"]

        actions_block = next(b for b in blocks if b["type"] == "actions")
        buttons = actions_block["elements"]
        assert len(buttons) == 2
        assert buttons[0]["action_id"] == "approve_action"
        assert buttons[0]["value"] == "42"
        assert buttons[1]["action_id"] == "reject_action"
        assert buttons[1]["value"] == "42"

    def test_alert_blocks_structure(self):
        from app.notifications.slack import build_alert_blocks

        blocks = build_alert_blocks(
            title="High CPU Usage",
            message="Server is at 95% CPU.",
            severity="high",
            source="monitoring",
        )
        assert blocks[0]["type"] == "header"
        assert len(blocks) >= 2
        context = next(b for b in blocks if b["type"] == "context")
        assert "monitoring" in context["elements"][0]["text"]

    def test_alert_blocks_without_source(self):
        from app.notifications.slack import build_alert_blocks

        blocks = build_alert_blocks(
            title="Test",
            message="Test message",
            severity="low",
        )
        assert not any(b["type"] == "context" for b in blocks)

    def test_result_blocks_success(self):
        from app.notifications.slack import build_result_blocks

        blocks = build_result_blocks(
            automation_type="crm",
            action_name="score_lead",
            model="crm.lead",
            record_id=55,
            success=True,
            reasoning="Lead scored at 85 based on email engagement.",
        )
        assert any("Completed" in str(b) for b in blocks)

    def test_result_blocks_failure(self):
        from app.notifications.slack import build_result_blocks

        blocks = build_result_blocks(
            automation_type="crm",
            action_name="score_lead",
            model="crm.lead",
            record_id=55,
            success=False,
            reasoning="Failed to fetch lead data from Odoo.",
        )
        assert any("Failed" in str(b) for b in blocks)

    def test_digest_blocks_full(self):
        from app.notifications.slack import build_digest_blocks

        content = {
            "headline": "3 overdue invoices need attention",
            "summary": "AR is climbing. Focus on collection today.",
            "key_metrics": [
                {"name": "Overdue AR", "value": "$12,500", "change_label": "3 invoices"},
                {"name": "Open AP", "value": "$8,200", "change_label": "5 bills"},
            ],
            "attention_items": [
                {"title": "Invoice #INV-001 overdue", "description": "$5,000 — 15 days past due", "priority": "high"},
            ],
            "anomalies": [
                {"description": "Unusual payment to Vendor X", "severity": "medium"},
            ],
        }
        blocks = build_digest_blocks(role="cfo", content=content)

        assert blocks[0]["type"] == "header"
        assert "3 overdue invoices" in blocks[0]["text"]["text"]
        assert any("Overdue AR" in str(b) for b in blocks)
        assert any("Attention" in str(b) for b in blocks)
        assert any("Anomalies" in str(b) for b in blocks)
        assert blocks[-1]["type"] == "context"
        assert "cfo" in blocks[-1]["elements"][0]["text"]

    def test_digest_blocks_minimal(self):
        from app.notifications.slack import build_digest_blocks

        blocks = build_digest_blocks(role="sales_manager", content={"headline": "All clear"})
        assert len(blocks) >= 2
        assert blocks[0]["text"]["text"] == "All clear"


# ---------------------------------------------------------------------------
# Slack interaction router tests
# ---------------------------------------------------------------------------


class TestSlackInteractionRouter:
    def test_approve_action(self, client, db_session, api_key):
        audit = AuditLog(
            automation_type=AutomationType.ACCOUNTING,
            action_name="categorize_transaction",
            odoo_model="account.move",
            odoo_record_id=1,
            status=ActionStatus.PENDING,
            confidence=0.9,
            ai_reasoning="Test reasoning",
        )
        db_session.add(audit)
        db_session.flush()

        payload = {
            "type": "block_actions",
            "user": {"username": "testuser"},
            "actions": [
                {"action_id": "approve_action", "value": str(audit.id)},
            ],
            "response_url": "https://hooks.slack.com/test",
        }

        with patch("app.routers.slack.get_db_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = lambda s: db_session
            mock_ctx.return_value.__exit__ = lambda s, *a: None

            response = client.post(
                "/api/slack/interactions",
                data={"payload": json.dumps(payload)},
            )

        assert response.status_code == 200
        db_session.refresh(audit)
        assert audit.status == ActionStatus.APPROVED
        assert audit.approved_by == "testuser"

    def test_reject_action(self, client, db_session, api_key):
        audit = AuditLog(
            automation_type=AutomationType.ACCOUNTING,
            action_name="categorize_transaction",
            odoo_model="account.move",
            odoo_record_id=1,
            status=ActionStatus.PENDING,
            confidence=0.9,
            ai_reasoning="Test reasoning",
        )
        db_session.add(audit)
        db_session.flush()

        payload = {
            "type": "block_actions",
            "user": {"username": "testuser"},
            "actions": [
                {"action_id": "reject_action", "value": str(audit.id)},
            ],
        }

        with patch("app.routers.slack.get_db_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = lambda s: db_session
            mock_ctx.return_value.__exit__ = lambda s, *a: db_session.flush()

            response = client.post(
                "/api/slack/interactions",
                data={"payload": json.dumps(payload)},
            )

        assert response.status_code == 200
        db_session.refresh(audit)
        assert audit.status == ActionStatus.REJECTED

    def test_missing_payload(self, client):
        response = client.post("/api/slack/interactions", data={})
        assert response.status_code == 400

    def test_invalid_payload_json(self, client):
        response = client.post(
            "/api/slack/interactions",
            data={"payload": "not-json"},
        )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Slack signature verification
# ---------------------------------------------------------------------------


class TestSlackSignatureVerification:
    def test_valid_signature(self):
        from app.routers.slack import _verify_slack_signature

        secret = "test-signing-secret"
        ts = str(int(time.time()))
        body = b"payload=test"
        sig_base = f"v0:{ts}:{body.decode('utf-8')}"
        expected_sig = "v0=" + hmac.new(
            secret.encode(), sig_base.encode(), hashlib.sha256
        ).hexdigest()

        with patch("app.routers.slack.get_settings") as m:
            m.return_value = Settings(
                slack_signing_secret=secret,
                slack_bot_token="xoxb-test",
            )
            assert _verify_slack_signature(body, ts, expected_sig) is True

    def test_invalid_signature(self):
        from app.routers.slack import _verify_slack_signature

        with patch("app.routers.slack.get_settings") as m:
            m.return_value = Settings(
                slack_signing_secret="test-secret",
                slack_bot_token="xoxb-test",
            )
            assert _verify_slack_signature(b"test", str(int(time.time())), "v0=bad") is False

    def test_expired_timestamp(self):
        from app.routers.slack import _verify_slack_signature

        old_ts = str(int(time.time()) - 600)
        with patch("app.routers.slack.get_settings") as m:
            m.return_value = Settings(
                slack_signing_secret="test-secret",
                slack_bot_token="xoxb-test",
            )
            assert _verify_slack_signature(b"test", old_ts, "v0=anything") is False


# ---------------------------------------------------------------------------
# NotificationService integration
# ---------------------------------------------------------------------------


class TestNotificationServiceSlack:
    def test_slack_registered_in_service(self):
        from app.notifications.service import NotificationService

        svc = NotificationService()
        assert "slack" in svc._channels
        assert "email" in svc._channels

    def test_whatsapp_not_registered(self):
        from app.notifications.service import NotificationService

        svc = NotificationService()
        assert "whatsapp" not in svc._channels

    def test_available_channels_includes_slack_when_configured(self):
        from app.notifications.service import NotificationService

        svc = NotificationService()
        with patch("app.notifications.slack.get_settings") as m:
            m.return_value = Settings(slack_bot_token="xoxb-test")
            channels = svc.available_channels()
        assert "slack" in channels


# ---------------------------------------------------------------------------
# Slack digest delivery
# ---------------------------------------------------------------------------


class TestSlackDigestDelivery:
    def test_deliver_via_slack(self):
        from app.automations.daily_digest import DailyDigestAutomation

        auto = DailyDigestAutomation()
        content = {
            "headline": "Test digest",
            "summary": "Summary text",
            "key_metrics": [],
            "attention_items": [],
            "anomalies": [],
        }

        with patch("app.automations.daily_digest.DailyDigestAutomation._deliver_via_slack") as m:
            m.return_value = True
            result = auto.deliver_digest("cfo", "slack", "#cfo-digest", content)

        assert result is True
        m.assert_called_once_with("cfo", "#cfo-digest", content)

    def test_deliver_unknown_channel_returns_false(self):
        from app.automations.daily_digest import DailyDigestAutomation

        auto = DailyDigestAutomation()
        with patch.object(auto, "settings", Settings()):
            result = auto.deliver_digest("cfo", "sms", "+123", {})
        assert result is False


# ---------------------------------------------------------------------------
# Approval request helper
# ---------------------------------------------------------------------------


class TestSlackApprovalRequest:
    def test_send_approval_request_calls_send(self):
        from app.notifications.slack import SlackChannel

        ch = SlackChannel()
        with patch.object(ch, "send", return_value=True) as mock_send:
            result = ch.send_approval_request(
                channel="#approvals",
                audit_log_id=99,
                automation_type="sales",
                action_name="auto_discount",
                model="sale.order",
                record_id=42,
                confidence=0.88,
                reasoning="AI suggests 10% discount.",
            )

        assert result is True
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args
        assert call_kwargs.kwargs["recipient"] == "#approvals"
        assert "blocks" in call_kwargs.kwargs
        blocks = call_kwargs.kwargs["blocks"]
        actions = next(b for b in blocks if b["type"] == "actions")
        assert actions["elements"][0]["value"] == "99"

    def test_send_alert_calls_send(self):
        from app.notifications.slack import SlackChannel

        ch = SlackChannel()
        with patch.object(ch, "send", return_value=True) as mock_send:
            result = ch.send_alert(
                channel="#alerts",
                title="DB Overload",
                message="CPU at 99%",
                severity="critical",
                source="monitoring",
            )

        assert result is True
        mock_send.assert_called_once()
