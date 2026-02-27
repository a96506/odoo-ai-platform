"""
AgentOrchestrator — selects, instantiates, and runs the appropriate agent
for a given trigger.  Singleton accessed via `get_orchestrator()`.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import structlog

from app.agents import get_agent_class, list_agent_types

logger = structlog.get_logger()


class AgentOrchestrator:
    """Central coordinator for multi-step agent workflows."""

    def run_agent(
        self,
        agent_type: str,
        trigger_type: str,
        trigger_id: str,
        initial_state: dict[str, Any],
    ) -> dict[str, Any]:
        """Instantiate and run an agent of the given type."""
        agent_cls = get_agent_class(agent_type)
        if agent_cls is None:
            available = list_agent_types()
            return {
                "status": "error",
                "error": f"Unknown agent type '{agent_type}'. Available: {available}",
            }

        agent = agent_cls()
        logger.info(
            "agent_starting",
            agent_type=agent_type,
            trigger_type=trigger_type,
            trigger_id=trigger_id,
        )

        return agent.run(
            trigger_type=trigger_type,
            trigger_id=trigger_id,
            initial_state=initial_state,
        )

    def resume_agent(self, run_id: int, event_data: dict[str, Any]) -> dict[str, Any]:
        """Resume a suspended agent run after receiving an external event."""
        from app.models.audit import AgentRun, get_db_session

        with get_db_session() as session:
            run = session.get(AgentRun, run_id)
            if not run:
                return {"status": "error", "error": f"Agent run {run_id} not found"}
            agent_type = run.agent_type

        agent_cls = get_agent_class(agent_type)
        if agent_cls is None:
            return {"status": "error", "error": f"Agent class for '{agent_type}' not found"}

        agent = agent_cls()
        logger.info("agent_resuming", run_id=run_id, agent_type=agent_type)

        return agent.resume(run_id=run_id, event_data=event_data)

    def get_run_status(self, run_id: int) -> dict[str, Any] | None:
        """Return metadata for a specific agent run."""
        from app.models.audit import AgentRun, AgentStep, get_db_session

        with get_db_session() as session:
            run = session.get(AgentRun, run_id)
            if not run:
                return None

            steps = (
                session.query(AgentStep)
                .filter(AgentStep.agent_run_id == run_id)
                .order_by(AgentStep.step_index)
                .all()
            )

            return {
                "run_id": run.id,
                "agent_type": run.agent_type,
                "trigger_type": run.trigger_type,
                "trigger_id": run.trigger_id,
                "status": run.status.value if run.status else None,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                "total_steps": run.total_steps,
                "token_usage": run.token_usage,
                "error": run.error,
                "steps": [
                    {
                        "step_name": s.step_name,
                        "step_index": s.step_index,
                        "status": s.status.value if s.status else None,
                        "started_at": s.started_at.isoformat() if s.started_at else None,
                        "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                    }
                    for s in steps
                ],
            }

    def list_runs(
        self,
        agent_type: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """List recent agent runs with optional filters."""
        from app.models.audit import AgentRun, AgentRunStatus, get_db_session

        with get_db_session() as session:
            query = session.query(AgentRun).order_by(AgentRun.started_at.desc())

            if agent_type:
                query = query.filter(AgentRun.agent_type == agent_type)
            if status:
                try:
                    query = query.filter(AgentRun.status == AgentRunStatus(status))
                except ValueError:
                    pass

            runs = query.limit(limit).all()
            return [
                {
                    "run_id": r.id,
                    "agent_type": r.agent_type,
                    "trigger_type": r.trigger_type,
                    "status": r.status.value if r.status else None,
                    "started_at": r.started_at.isoformat() if r.started_at else None,
                    "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                    "total_steps": r.total_steps,
                    "token_usage": r.token_usage,
                    "error": r.error,
                }
                for r in runs
            ]


@lru_cache
def get_orchestrator() -> AgentOrchestrator:
    return AgentOrchestrator()
