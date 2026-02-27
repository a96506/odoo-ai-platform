"""
BaseAgent — graph-based multi-step agent using LangGraph StateGraph.

Provides:
- State persistence (PostgreSQL for audit, AgentRun/AgentStep tables)
- Guardrails: token budget, step limit, loop detection
- Human-in-the-loop via suspend/resume
- Full audit trail of every step and AI decision

Subclasses override `build_graph()` to define their workflow,
and add node functions that receive/return AgentState dicts.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections import Counter
from datetime import datetime
from typing import Any, TypedDict

import structlog
from langgraph.graph import END, START, StateGraph

from app.config import get_settings
from app.models.audit import (
    AgentDecision,
    AgentRun,
    AgentRunStatus,
    AgentStep,
    AgentStepStatus,
    AgentSuspension,
    AuditLog,
    ActionStatus,
    get_db_session,
)
from app.odoo_client import get_odoo_client
from app.claude_client import get_claude_client

logger = structlog.get_logger()


class AgentState(TypedDict, total=False):
    """Base state flowing through every agent graph.

    Subclasses extend this with domain-specific fields via
    a TypedDict that inherits from AgentState.
    """

    run_id: int
    step_count: int
    token_count: int
    error: str | None
    needs_suspension: bool
    suspension_reason: str | None
    current_step: str


class GuardrailViolation(Exception):
    """Raised when an agent exceeds its safety limits."""


class BaseAgent(ABC):
    """Abstract base for all multi-step LangGraph agents."""

    agent_type: str = ""
    description: str = ""
    max_steps: int | None = None
    max_tokens: int | None = None

    def __init__(self):
        self.settings = get_settings()
        self._effective_max_steps = self.max_steps or self.settings.agent_max_steps
        self._effective_max_tokens = self.max_tokens or self.settings.agent_max_tokens
        self._step_visit_counts: Counter = Counter()
        self._compiled_graph = None

    @property
    def odoo(self):
        return get_odoo_client()

    @property
    def claude(self):
        return get_claude_client()

    # ------------------------------------------------------------------
    # Abstract interface — subclasses must implement
    # ------------------------------------------------------------------

    @abstractmethod
    def build_graph(self) -> StateGraph:
        """Return a configured StateGraph (not yet compiled).

        Subclasses add nodes, edges, and conditional routing here.
        The graph's state schema should extend AgentState.
        """

    @abstractmethod
    def get_state_schema(self) -> type:
        """Return the TypedDict subclass used as graph state."""

    # ------------------------------------------------------------------
    # Graph compilation (cached)
    # ------------------------------------------------------------------

    def _get_compiled(self):
        if self._compiled_graph is None:
            graph = self.build_graph()
            self._compiled_graph = graph.compile()
        return self._compiled_graph

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run(
        self,
        trigger_type: str,
        trigger_id: str,
        initial_state: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute the agent graph end-to-end.

        Creates an AgentRun record, invokes the graph with guardrail-
        wrapped node functions, logs every step, and returns the final
        state dictionary along with the run metadata.
        """
        run_id = self._create_run(trigger_type, trigger_id, initial_state)

        state = {
            **initial_state,
            "run_id": run_id,
            "step_count": 0,
            "token_count": 0,
            "error": None,
            "needs_suspension": False,
            "suspension_reason": None,
            "current_step": "",
        }

        self._step_visit_counts.clear()

        try:
            compiled = self._get_compiled()

            final_state = self._execute_with_guardrails(compiled, state, run_id)

            if final_state.get("needs_suspension"):
                self._suspend_run(run_id, final_state)
                status = AgentRunStatus.SUSPENDED
            elif final_state.get("error"):
                status = AgentRunStatus.FAILED
            else:
                status = AgentRunStatus.COMPLETED

            self._complete_run(run_id, status, final_state)

            return {
                "run_id": run_id,
                "status": status.value,
                "total_steps": final_state.get("step_count", 0),
                "token_usage": final_state.get("token_count", 0),
                "error": final_state.get("error"),
                "final_state": final_state,
            }

        except GuardrailViolation as exc:
            self._complete_run(run_id, AgentRunStatus.FAILED, state, error=str(exc))
            logger.warning("agent_guardrail_violation", run_id=run_id, error=str(exc))
            return {
                "run_id": run_id,
                "status": "failed",
                "total_steps": state.get("step_count", 0),
                "error": str(exc),
            }

        except Exception as exc:
            self._complete_run(run_id, AgentRunStatus.FAILED, state, error=str(exc))
            logger.error("agent_execution_error", run_id=run_id, error=str(exc))
            return {
                "run_id": run_id,
                "status": "failed",
                "total_steps": state.get("step_count", 0),
                "error": str(exc),
            }

    def resume(self, run_id: int, event_data: dict[str, Any]) -> dict[str, Any]:
        """Resume a suspended agent with new event data (e.g. approval result)."""
        with get_db_session() as session:
            agent_run = session.get(AgentRun, run_id)
            if not agent_run or agent_run.status != AgentRunStatus.SUSPENDED:
                return {"run_id": run_id, "status": "error", "error": "Run not found or not suspended"}

            suspension = (
                session.query(AgentSuspension)
                .filter(AgentSuspension.agent_run_id == run_id, AgentSuspension.resumed_at.is_(None))
                .first()
            )

            frozen_state = agent_run.final_state or agent_run.initial_state or {}
            frozen_state.update(event_data)
            frozen_state["needs_suspension"] = False
            frozen_state["suspension_reason"] = None

            agent_run.status = AgentRunStatus.RUNNING
            if suspension:
                suspension.resumed_at = datetime.utcnow()
                suspension.resume_data = event_data

        self._step_visit_counts.clear()

        try:
            compiled = self._get_compiled()
            final_state = self._execute_with_guardrails(compiled, frozen_state, run_id)

            if final_state.get("needs_suspension"):
                self._suspend_run(run_id, final_state)
                status = AgentRunStatus.SUSPENDED
            elif final_state.get("error"):
                status = AgentRunStatus.FAILED
            else:
                status = AgentRunStatus.COMPLETED

            self._complete_run(run_id, status, final_state)
            return {
                "run_id": run_id,
                "status": status.value,
                "total_steps": final_state.get("step_count", 0),
                "error": final_state.get("error"),
            }

        except Exception as exc:
            self._complete_run(run_id, AgentRunStatus.FAILED, frozen_state, error=str(exc))
            return {"run_id": run_id, "status": "failed", "error": str(exc)}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _execute_with_guardrails(self, compiled, state: dict, run_id: int) -> dict:
        """Stream graph execution, enforcing guardrails at each step."""
        for event in compiled.stream(state, stream_mode="updates"):
            for node_name, node_output in event.items():
                if node_name == "__end__":
                    continue

                state.update(node_output)
                state["step_count"] = state.get("step_count", 0) + 1
                state["current_step"] = node_name

                self._log_step(run_id, node_name, state)
                self._enforce_guardrails(state, node_name)

                if state.get("needs_suspension"):
                    return state

        return state

    def _enforce_guardrails(self, state: dict, node_name: str):
        step_count = state.get("step_count", 0)
        if step_count > self._effective_max_steps:
            raise GuardrailViolation(
                f"Step limit exceeded: {step_count} > {self._effective_max_steps}"
            )

        token_count = state.get("token_count", 0)
        if token_count > self._effective_max_tokens:
            raise GuardrailViolation(
                f"Token budget exceeded: {token_count} > {self._effective_max_tokens}"
            )

        self._step_visit_counts[node_name] += 1
        if self._step_visit_counts[node_name] > self.settings.agent_loop_threshold:
            raise GuardrailViolation(
                f"Loop detected: node '{node_name}' visited "
                f"{self._step_visit_counts[node_name]} times "
                f"(threshold: {self.settings.agent_loop_threshold})"
            )

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _create_run(self, trigger_type: str, trigger_id: str, initial_state: dict) -> int:
        with get_db_session() as session:
            run = AgentRun(
                agent_type=self.agent_type,
                trigger_type=trigger_type,
                trigger_id=trigger_id,
                status=AgentRunStatus.RUNNING,
                initial_state=initial_state,
            )
            session.add(run)
            session.flush()
            run_id = run.id
        return run_id

    def _complete_run(
        self,
        run_id: int,
        status: AgentRunStatus,
        final_state: dict,
        error: str | None = None,
    ):
        with get_db_session() as session:
            run = session.get(AgentRun, run_id)
            if run:
                run.status = status
                run.completed_at = datetime.utcnow()
                run.total_steps = final_state.get("step_count", 0)
                run.token_usage = final_state.get("token_count", 0)
                run.final_state = final_state
                run.error = error or final_state.get("error")

    def _suspend_run(self, run_id: int, state: dict):
        with get_db_session() as session:
            run = session.get(AgentRun, run_id)
            if run:
                run.status = AgentRunStatus.SUSPENDED
                run.final_state = state

            timeout_hours = self.settings.agent_suspension_timeout_hours
            timeout_at = datetime.utcnow() + __import__("datetime").timedelta(hours=timeout_hours)

            suspension = AgentSuspension(
                agent_run_id=run_id,
                resume_condition=state.get("suspension_reason", "awaiting_approval"),
                suspended_at_step=state.get("current_step", ""),
                timeout_at=timeout_at,
            )
            session.add(suspension)

    def _log_step(self, run_id: int, node_name: str, state: dict):
        with get_db_session() as session:
            step = AgentStep(
                agent_run_id=run_id,
                step_name=node_name,
                step_index=state.get("step_count", 0),
                status=AgentStepStatus.COMPLETED,
                input_data={"current_step": node_name},
                output_data={
                    k: v
                    for k, v in state.items()
                    if k not in ("run_id",) and not callable(v)
                },
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
            )
            session.add(step)

    def _log_decision(
        self,
        run_id: int,
        step_name: str,
        prompt_hash: str,
        response_data: dict,
        confidence: float,
        tokens_input: int = 0,
        tokens_output: int = 0,
    ):
        """Log an AI decision made during a step."""
        with get_db_session() as session:
            step = (
                session.query(AgentStep)
                .filter(AgentStep.agent_run_id == run_id, AgentStep.step_name == step_name)
                .order_by(AgentStep.step_index.desc())
                .first()
            )
            if step:
                decision = AgentDecision(
                    agent_step_id=step.id,
                    prompt_hash=prompt_hash,
                    response=response_data,
                    confidence=confidence,
                    tokens_input=tokens_input,
                    tokens_output=tokens_output,
                )
                session.add(decision)

    # ------------------------------------------------------------------
    # Convenience methods for node functions
    # ------------------------------------------------------------------

    def analyze_with_tools(
        self,
        system_prompt: str,
        user_message: str,
        tools: list[dict],
        state: dict | None = None,
    ) -> dict[str, Any]:
        """Claude tool-use call with automatic token tracking."""
        result = self.claude.analyze(
            system_prompt=system_prompt,
            user_message=user_message,
            tools=tools,
        )
        if state is not None:
            state["token_count"] = state.get("token_count", 0) + result.get("tokens_used", 0)
        return result

    def fetch_record(self, model: str, record_id: int, fields: list[str] | None = None) -> dict | None:
        return self.odoo.get_record(model, record_id, fields)

    def search_records(self, model: str, domain: list, fields: list[str] | None = None, limit: int = 50) -> list[dict]:
        return self.odoo.search_read(model, domain, fields=fields, limit=limit)

    def update_record(self, model: str, record_id: int, values: dict) -> bool:
        return self.odoo.write(model, [record_id], values)

    def create_record(self, model: str, values: dict) -> int:
        return self.odoo.create(model, values)

    def notify(self, channel: str, recipient: str, subject: str, body: str, **kwargs) -> bool:
        try:
            from app.notifications.service import get_notification_service
            svc = get_notification_service()
            return svc.send(channel, recipient, subject, body, **kwargs)
        except Exception as exc:
            logger.warning("agent_notification_failed", channel=channel, error=str(exc))
            return False

    def should_auto_execute(self, confidence: float) -> bool:
        return confidence >= self.settings.auto_approve_threshold

    def needs_approval(self, confidence: float) -> bool:
        return (
            confidence >= self.settings.default_confidence_threshold
            and confidence < self.settings.auto_approve_threshold
        )
