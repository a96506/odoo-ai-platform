"""
Tests for Phase 2 Agentic AI: BaseAgent, ProcureToPayAgent, CollectionAgent,
MonthEndCloseAgent, AgentOrchestrator, and /api/agents endpoints.
"""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from app.models.audit import (
    AgentRun,
    AgentRunStatus,
    AgentStep,
    AgentStepStatus,
    AgentSuspension,
    Base,
)


# ---------------------------------------------------------------------------
# BaseAgent unit tests
# ---------------------------------------------------------------------------


class TestBaseAgent:
    """Test the BaseAgent guardrails and lifecycle."""

    def _make_agent(self):
        from app.agents.base_agent import BaseAgent, AgentState
        from langgraph.graph import StateGraph, START, END

        class DummyState(AgentState, total=False):
            counter: int

        class DummyAgent(BaseAgent):
            agent_type = "test_dummy"
            description = "Test agent"
            max_steps = 5
            max_tokens = 1000

            def get_state_schema(self):
                return DummyState

            def build_graph(self):
                graph = StateGraph(DummyState)
                graph.add_node("step_a", lambda state: {"counter": state.get("counter", 0) + 1})
                graph.add_node("step_b", lambda state: {"counter": state.get("counter", 0) + 10})
                graph.add_edge(START, "step_a")
                graph.add_edge("step_a", "step_b")
                graph.add_edge("step_b", END)
                return graph

        return DummyAgent()

    @patch("app.agents.base_agent.get_db_session")
    @patch("app.agents.base_agent.get_settings")
    def test_run_completes_successfully(self, mock_settings, mock_db):
        settings = MagicMock()
        settings.agent_max_steps = 30
        settings.agent_max_tokens = 50000
        settings.agent_loop_threshold = 3
        settings.auto_approve_threshold = 0.95
        settings.default_confidence_threshold = 0.85
        mock_settings.return_value = settings

        session = MagicMock()
        mock_db.return_value.__enter__ = MagicMock(return_value=session)
        mock_db.return_value.__exit__ = MagicMock(return_value=False)

        run_mock = MagicMock()
        run_mock.id = 1

        def add_side_effect(obj):
            if hasattr(obj, "id") and obj.id is None:
                obj.id = 1

        session.add = MagicMock(side_effect=add_side_effect)
        session.flush = MagicMock()
        session.get = MagicMock(return_value=run_mock)

        agent = self._make_agent()
        result = agent.run(trigger_type="test", trigger_id="t1", initial_state={"counter": 0})

        assert result["status"] == "completed"
        assert result["run_id"] == 1

    @patch("app.agents.base_agent.get_db_session")
    @patch("app.agents.base_agent.get_settings")
    def test_guardrail_step_limit(self, mock_settings, mock_db):
        """Agent with a loop should hit step limit guardrail."""
        from app.agents.base_agent import BaseAgent, AgentState, GuardrailViolation
        from langgraph.graph import StateGraph, START, END

        settings = MagicMock()
        settings.agent_max_steps = 2
        settings.agent_max_tokens = 50000
        settings.agent_loop_threshold = 10
        mock_settings.return_value = settings

        session = MagicMock()
        mock_db.return_value.__enter__ = MagicMock(return_value=session)
        mock_db.return_value.__exit__ = MagicMock(return_value=False)
        run_mock = MagicMock()
        run_mock.id = 2
        run_mock.status = AgentRunStatus.RUNNING
        session.get.return_value = run_mock

        class TinyState(AgentState, total=False):
            val: int

        class StepLimitAgent(BaseAgent):
            agent_type = "test_steplimit"
            max_steps = 2
            max_tokens = 50000

            def get_state_schema(self):
                return TinyState

            def build_graph(self):
                graph = StateGraph(TinyState)
                graph.add_node("a", lambda s: {"val": 1})
                graph.add_node("b", lambda s: {"val": 2})
                graph.add_node("c", lambda s: {"val": 3})
                graph.add_edge(START, "a")
                graph.add_edge("a", "b")
                graph.add_edge("b", "c")
                graph.add_edge("c", END)
                return graph

        agent = StepLimitAgent()
        result = agent.run("test", "t2", {"val": 0})

        assert result["status"] == "failed"
        assert "Step limit exceeded" in result["error"]

    def test_should_auto_execute_boundaries(self):
        from app.agents.base_agent import BaseAgent

        with patch("app.agents.base_agent.get_settings") as m:
            settings = MagicMock()
            settings.auto_approve_threshold = 0.95
            settings.default_confidence_threshold = 0.85
            settings.agent_max_steps = 30
            settings.agent_max_tokens = 50000
            settings.agent_loop_threshold = 3
            m.return_value = settings

            agent = self._make_agent()
            assert agent.should_auto_execute(0.95) is True
            assert agent.should_auto_execute(0.96) is True
            assert agent.should_auto_execute(0.94) is False
            assert agent.needs_approval(0.90) is True
            assert agent.needs_approval(0.80) is False
            assert agent.needs_approval(0.95) is False


# ---------------------------------------------------------------------------
# AgentOrchestrator tests
# ---------------------------------------------------------------------------


class TestAgentOrchestrator:
    def test_unknown_agent_type(self):
        from app.agents.orchestrator import AgentOrchestrator

        orch = AgentOrchestrator()
        result = orch.run_agent("nonexistent", "test", "t1", {})
        assert result["status"] == "error"
        assert "Unknown agent type" in result["error"]

    @patch("app.agents.orchestrator.get_agent_class")
    def test_run_agent_delegates(self, mock_get):
        from app.agents.orchestrator import AgentOrchestrator

        mock_agent = MagicMock()
        mock_agent.return_value.run.return_value = {"run_id": 1, "status": "completed"}
        mock_get.return_value = mock_agent

        orch = AgentOrchestrator()
        result = orch.run_agent("test", "manual", "1", {"key": "val"})
        assert result["status"] == "completed"
        mock_agent.return_value.run.assert_called_once()

    @patch("app.models.audit.get_db_session")
    def test_get_run_status_not_found(self, mock_db):
        from app.agents.orchestrator import AgentOrchestrator

        session = MagicMock()
        session.get.return_value = None
        mock_db.return_value.__enter__ = MagicMock(return_value=session)
        mock_db.return_value.__exit__ = MagicMock(return_value=False)

        orch = AgentOrchestrator()
        assert orch.get_run_status(999) is None


# ---------------------------------------------------------------------------
# Agent registry tests
# ---------------------------------------------------------------------------


class TestAgentRegistry:
    def test_register_and_list(self):
        from app.agents import _AGENT_REGISTRY, register_agent, list_agent_types, get_agent_class

        class FakeAgent:
            agent_type = "test_registry_agent"

        register_agent(FakeAgent)
        assert "test_registry_agent" in list_agent_types()
        assert get_agent_class("test_registry_agent") is FakeAgent

        del _AGENT_REGISTRY["test_registry_agent"]


# ---------------------------------------------------------------------------
# ProcureToPayAgent tests
# ---------------------------------------------------------------------------


class TestProcureToPayAgent:
    @patch("app.agents.base_agent.get_db_session")
    @patch("app.agents.base_agent.get_settings")
    def test_graph_builds(self, mock_settings, mock_db):
        settings = MagicMock()
        settings.agent_max_steps = 30
        settings.agent_max_tokens = 50000
        settings.agent_loop_threshold = 3
        settings.auto_approve_threshold = 0.95
        settings.default_confidence_threshold = 0.85
        mock_settings.return_value = settings

        from app.agents.procure_to_pay import ProcureToPayAgent
        agent = ProcureToPayAgent()
        graph = agent.build_graph()
        compiled = graph.compile()
        assert compiled is not None

    def test_route_after_extraction(self):
        from app.agents.procure_to_pay import ProcureToPayAgent

        with patch("app.agents.base_agent.get_settings") as m:
            m.return_value = MagicMock(
                agent_max_steps=30, agent_max_tokens=50000,
                agent_loop_threshold=3, auto_approve_threshold=0.95,
                default_confidence_threshold=0.85,
            )
            agent = ProcureToPayAgent()
            assert agent._route_after_extraction({"extracted_data": {"vendor": "X"}}) == "success"
            assert agent._route_after_extraction({"extracted_data": {}}) == "failure"
            assert agent._route_after_extraction({"error": "fail"}) == "failure"

    def test_route_approval_decision(self):
        from app.agents.procure_to_pay import ProcureToPayAgent

        with patch("app.agents.base_agent.get_settings") as m:
            m.return_value = MagicMock(
                agent_max_steps=30, agent_max_tokens=50000,
                agent_loop_threshold=3, auto_approve_threshold=0.95,
                default_confidence_threshold=0.85,
            )
            agent = ProcureToPayAgent()
            assert agent._route_approval_decision({"approval_decision": "auto_approve"}) == "auto_approve"
            assert agent._route_approval_decision({"approval_decision": "needs_approval"}) == "needs_approval"
            assert agent._route_approval_decision({}) == "escalate"

    def test_validate_amounts_no_discrepancy(self):
        from app.agents.procure_to_pay import ProcureToPayAgent

        with patch("app.agents.base_agent.get_settings") as m:
            m.return_value = MagicMock(
                agent_max_steps=30, agent_max_tokens=50000,
                agent_loop_threshold=3, auto_approve_threshold=0.95,
                default_confidence_threshold=0.85,
            )
            agent = ProcureToPayAgent()
            result = agent._validate_amounts({
                "extracted_data": {"total_amount": 1000},
                "matched_po": {"amount_total": 1005},
            })
            assert result["discrepancies"] == []

    def test_validate_amounts_with_discrepancy(self):
        from app.agents.procure_to_pay import ProcureToPayAgent

        with patch("app.agents.base_agent.get_settings") as m:
            m.return_value = MagicMock(
                agent_max_steps=30, agent_max_tokens=50000,
                agent_loop_threshold=3, auto_approve_threshold=0.95,
                default_confidence_threshold=0.85,
            )
            agent = ProcureToPayAgent()
            result = agent._validate_amounts({
                "extracted_data": {"total_amount": 1000},
                "matched_po": {"amount_total": 1500},
            })
            assert len(result["discrepancies"]) == 1


# ---------------------------------------------------------------------------
# CollectionAgent tests
# ---------------------------------------------------------------------------


class TestCollectionAgent:
    def test_graph_builds(self):
        from app.agents.collection import CollectionAgent

        with patch("app.agents.base_agent.get_settings") as m:
            m.return_value = MagicMock(
                agent_max_steps=30, agent_max_tokens=50000,
                agent_loop_threshold=3, auto_approve_threshold=0.95,
                default_confidence_threshold=0.85,
                slack_enabled=False, slack_default_channel="",
            )
            agent = CollectionAgent()
            graph = agent.build_graph()
            compiled = graph.compile()
            assert compiled is not None

    def test_determine_strategy_gentle(self):
        from app.agents.collection import CollectionAgent

        with patch("app.agents.base_agent.get_settings") as m:
            m.return_value = MagicMock(
                agent_max_steps=30, agent_max_tokens=50000,
                agent_loop_threshold=3, auto_approve_threshold=0.95,
                default_confidence_threshold=0.85,
            )
            agent = CollectionAgent()
            result = agent._determine_strategy({"overdue_days": 3, "amount_due": 500})
            assert result["collection_strategy"] == "gentle_reminder"

    def test_determine_strategy_firm(self):
        from app.agents.collection import CollectionAgent

        with patch("app.agents.base_agent.get_settings") as m:
            m.return_value = MagicMock(
                agent_max_steps=30, agent_max_tokens=50000,
                agent_loop_threshold=3, auto_approve_threshold=0.95,
                default_confidence_threshold=0.85,
            )
            agent = CollectionAgent()
            result = agent._determine_strategy({"overdue_days": 20, "amount_due": 500})
            assert result["collection_strategy"] == "firm_notice"

    def test_determine_strategy_escalate_high_amount(self):
        from app.agents.collection import CollectionAgent

        with patch("app.agents.base_agent.get_settings") as m:
            m.return_value = MagicMock(
                agent_max_steps=30, agent_max_tokens=50000,
                agent_loop_threshold=3, auto_approve_threshold=0.95,
                default_confidence_threshold=0.85,
            )
            agent = CollectionAgent()
            result = agent._determine_strategy({"overdue_days": 20, "amount_due": 75000})
            assert result["collection_strategy"] == "escalate"

    def test_credit_score_impact_levels(self):
        from app.agents.collection import CollectionAgent

        with patch("app.agents.base_agent.get_settings") as m:
            m.return_value = MagicMock(
                agent_max_steps=30, agent_max_tokens=50000,
                agent_loop_threshold=3, auto_approve_threshold=0.95,
                default_confidence_threshold=0.85,
            )
            agent = CollectionAgent()
            assert agent._update_credit_score({"overdue_days": 5})["credit_score_impact"] == -1.0
            assert agent._update_credit_score({"overdue_days": 20})["credit_score_impact"] == -3.0
            assert agent._update_credit_score({"overdue_days": 45})["credit_score_impact"] == -8.0
            assert agent._update_credit_score({"overdue_days": 90})["credit_score_impact"] == -15.0


# ---------------------------------------------------------------------------
# MonthEndCloseAgent tests
# ---------------------------------------------------------------------------


class TestMonthEndCloseAgent:
    def test_graph_builds(self):
        from app.agents.month_end_close import MonthEndCloseAgent

        with patch("app.agents.base_agent.get_settings") as m:
            m.return_value = MagicMock(
                agent_max_steps=30, agent_max_tokens=50000,
                agent_loop_threshold=3, auto_approve_threshold=0.95,
                default_confidence_threshold=0.85,
            )
            agent = MonthEndCloseAgent()
            graph = agent.build_graph()
            compiled = graph.compile()
            assert compiled is not None

    def test_classify_severity(self):
        from app.agents.month_end_close import MonthEndCloseAgent

        with patch("app.agents.base_agent.get_settings") as m:
            m.return_value = MagicMock(
                agent_max_steps=30, agent_max_tokens=50000,
                agent_loop_threshold=3, auto_approve_threshold=0.95,
                default_confidence_threshold=0.85,
            )
            agent = MonthEndCloseAgent()
            result = agent._classify_severity({
                "scan_results": {
                    "unreconciled_bank": {"items_found": 5},
                    "stale_drafts": {"items_found": 3},
                    "missing_vendor_bills": {"items_found": 2},
                    "adjustments": {"items_found": 1},
                },
                "anomalies_detected": [],
            })
            classified = result["severity_classification"]
            assert len(classified["high"]) == 1
            assert len(classified["medium"]) == 1
            assert len(classified["critical"]) == 1
            assert len(classified["low"]) == 1

    def test_calculate_readiness_perfect(self):
        from app.agents.month_end_close import MonthEndCloseAgent

        with patch("app.agents.base_agent.get_settings") as m:
            m.return_value = MagicMock(
                agent_max_steps=30, agent_max_tokens=50000,
                agent_loop_threshold=3, auto_approve_threshold=0.95,
                default_confidence_threshold=0.85,
            )
            agent = MonthEndCloseAgent()
            result = agent._calculate_readiness({
                "total_issues": 0,
                "auto_resolved": 0,
                "pending_review": 0,
                "anomalies_detected": [],
                "severity_classification": {"critical": [], "high": [], "medium": [], "low": []},
            })
            assert result["close_readiness_score"] == 100.0

    def test_calculate_readiness_with_issues(self):
        from app.agents.month_end_close import MonthEndCloseAgent

        with patch("app.agents.base_agent.get_settings") as m:
            m.return_value = MagicMock(
                agent_max_steps=30, agent_max_tokens=50000,
                agent_loop_threshold=3, auto_approve_threshold=0.95,
                default_confidence_threshold=0.85,
            )
            agent = MonthEndCloseAgent()
            result = agent._calculate_readiness({
                "total_issues": 10,
                "auto_resolved": 2,
                "pending_review": 8,
                "anomalies_detected": [{"score": 4.0}],
                "severity_classification": {
                    "critical": [{"step": "x"}],
                    "high": [{"step": "y"}, {"step": "z"}],
                    "medium": [],
                    "low": [],
                },
            })
            assert result["close_readiness_score"] < 100.0
            assert result["close_readiness_score"] >= 0.0


# ---------------------------------------------------------------------------
# /api/agents endpoint tests
# ---------------------------------------------------------------------------


class TestAgentEndpoints:
    def test_list_agent_types(self, client, auth_headers):
        with patch("app.routers.agents.list_agent_types", return_value=["procure_to_pay", "collection"]):
            resp = client.get("/api/agents/types", headers=auth_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert "agent_types" in data

    def test_list_runs_empty(self, client, auth_headers):
        with patch("app.routers.agents.get_orchestrator") as mock_orch:
            mock_orch.return_value.list_runs.return_value = []
            resp = client.get("/api/agents/runs", headers=auth_headers)
            assert resp.status_code == 200
            assert resp.json() == []

    def test_get_run_not_found(self, client, auth_headers):
        with patch("app.routers.agents.get_orchestrator") as mock_orch:
            mock_orch.return_value.get_run_status.return_value = None
            resp = client.get("/api/agents/runs/999", headers=auth_headers)
            assert resp.status_code == 404

    def test_start_agent_unknown_type(self, client, auth_headers):
        with patch("app.routers.agents.get_orchestrator") as mock_orch:
            mock_orch.return_value.run_agent.return_value = {
                "status": "error",
                "error": "Unknown agent type",
            }
            resp = client.post(
                "/api/agents/run",
                headers=auth_headers,
                json={"agent_type": "nonexistent"},
            )
            assert resp.status_code == 400

    def test_start_agent_success(self, client, auth_headers):
        with patch("app.routers.agents.get_orchestrator") as mock_orch:
            mock_orch.return_value.run_agent.return_value = {
                "run_id": 1,
                "status": "completed",
                "total_steps": 5,
            }
            resp = client.post(
                "/api/agents/run",
                headers=auth_headers,
                json={"agent_type": "procure_to_pay", "initial_state": {"document_id": 42}},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "completed"

    def test_resume_agent_not_found(self, client, auth_headers):
        with patch("app.routers.agents.get_orchestrator") as mock_orch:
            mock_orch.return_value.resume_agent.return_value = {
                "status": "error",
                "error": "Agent run 999 not found",
            }
            resp = client.post(
                "/api/agents/runs/999/resume",
                headers=auth_headers,
                json={"event_data": {"approved": True}},
            )
            assert resp.status_code == 404

    def test_auth_required(self, client):
        resp = client.get("/api/agents/types")
        assert resp.status_code in (401, 403)
