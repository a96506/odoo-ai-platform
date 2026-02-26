"""Unit tests for BaseAutomation class."""

from unittest.mock import patch, MagicMock

from app.automations.base import BaseAutomation
from app.models.schemas import AutomationResult


class StubAutomation(BaseAutomation):
    """Concrete subclass for testing the abstract base."""

    automation_type = "test"
    watched_models = ["test.model"]

    def on_create_test_model(self, model, record_id, values):
        return AutomationResult(
            success=True,
            action="create_handled",
            model=model,
            record_id=record_id,
            confidence=0.92,
            reasoning="Handled create event",
        )

    def on_write(self, model, record_id, values):
        return AutomationResult(
            success=True,
            action="generic_write",
            model=model,
            record_id=record_id,
        )

    def action_custom_action(self, model, record_id):
        return AutomationResult(
            success=True,
            action="custom_action",
            model=model,
            record_id=record_id,
            confidence=0.97,
        )

    def execute_custom_action(self, model, record_id, data):
        return AutomationResult(
            success=True,
            action="custom_action",
            model=model,
            record_id=record_id,
            changes_made=data,
        )

    def scan_daily(self):
        pass


class TestHandleEvent:
    @patch("app.automations.base.get_odoo_client")
    @patch("app.automations.base.get_claude_client")
    def test_routes_to_specific_handler(self, _claude, _odoo):
        auto = StubAutomation()
        result = auto.handle_event("create", "test.model", 1, {})
        assert result.success is True
        assert result.action == "create_handled"

    @patch("app.automations.base.get_odoo_client")
    @patch("app.automations.base.get_claude_client")
    def test_falls_back_to_generic_handler(self, _claude, _odoo):
        auto = StubAutomation()
        result = auto.handle_event("write", "test.model", 1, {})
        assert result.success is True
        assert result.action == "generic_write"

    @patch("app.automations.base.get_odoo_client")
    @patch("app.automations.base.get_claude_client")
    def test_no_handler_returns_failure(self, _claude, _odoo):
        auto = StubAutomation()
        result = auto.handle_event("unlink", "test.model", 1, {})
        assert result.success is False
        assert result.action == "no_handler"

    @patch("app.automations.base.get_odoo_client")
    @patch("app.automations.base.get_claude_client")
    def test_handler_exception_is_caught(self, _claude, _odoo):
        auto = StubAutomation()
        auto.on_create_test_model = MagicMock(side_effect=ValueError("boom"))
        result = auto.handle_event("create", "test.model", 1, {})
        assert result.success is False
        assert "boom" in result.reasoning


class TestRunAction:
    @patch("app.automations.base.get_odoo_client")
    @patch("app.automations.base.get_claude_client")
    def test_runs_named_action(self, _claude, _odoo):
        auto = StubAutomation()
        result = auto.run_action("custom_action", "test.model", 1)
        assert result.success is True
        assert result.confidence == 0.97

    @patch("app.automations.base.get_odoo_client")
    @patch("app.automations.base.get_claude_client")
    def test_unknown_action(self, _claude, _odoo):
        auto = StubAutomation()
        result = auto.run_action("nonexistent", "test.model", 1)
        assert result.success is False


class TestExecuteApproved:
    @patch("app.automations.base.get_odoo_client")
    @patch("app.automations.base.get_claude_client")
    def test_execute_with_data(self, _claude, _odoo):
        auto = StubAutomation()
        result = auto.execute_approved(
            "custom_action", "test.model", 1, {"key": "val"}
        )
        assert result.success is True
        assert result.changes_made == {"key": "val"}

    @patch("app.automations.base.get_odoo_client")
    @patch("app.automations.base.get_claude_client")
    def test_execute_no_handler(self, _claude, _odoo):
        auto = StubAutomation()
        result = auto.execute_approved("missing", "test.model", 1, {})
        assert result.success is False


class TestConfidenceGating:
    @patch("app.automations.base.get_odoo_client")
    @patch("app.automations.base.get_claude_client")
    def test_auto_execute_high_confidence(self, _claude, _odoo):
        auto = StubAutomation()
        assert auto.should_auto_execute(0.96) is True
        assert auto.should_auto_execute(0.94) is False

    @patch("app.automations.base.get_odoo_client")
    @patch("app.automations.base.get_claude_client")
    def test_needs_approval_mid_confidence(self, _claude, _odoo):
        auto = StubAutomation()
        assert auto.needs_approval(0.90) is True
        assert auto.needs_approval(0.80) is False
        assert auto.needs_approval(0.96) is False


class TestScheduledScan:
    @patch("app.automations.base.get_odoo_client")
    @patch("app.automations.base.get_claude_client")
    def test_calls_scan_method(self, _claude, _odoo):
        auto = StubAutomation()
        auto.scan_daily = MagicMock()
        auto.scheduled_scan("daily")
        auto.scan_daily.assert_called_once()

    @patch("app.automations.base.get_odoo_client")
    @patch("app.automations.base.get_claude_client")
    def test_noop_for_missing_scan(self, _claude, _odoo):
        auto = StubAutomation()
        auto.scheduled_scan("nonexistent")
