"""
Agent workflow API endpoints.

POST /api/agents/run          — start a new agent workflow
POST /api/agents/{run_id}/resume — resume a suspended agent
GET  /api/agents/runs         — list recent runs
GET  /api/agents/runs/{run_id} — get run details with step history
GET  /api/agents/types        — list available agent types
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Any

from app.auth import require_api_key
from app.agents.orchestrator import get_orchestrator
from app.agents import list_agent_types

router = APIRouter(prefix="/api/agents", tags=["agents"], dependencies=[Depends(require_api_key)])


class AgentRunRequest(BaseModel):
    agent_type: str
    trigger_type: str = "manual"
    trigger_id: str = ""
    initial_state: dict[str, Any] = Field(default_factory=dict)


class AgentResumeRequest(BaseModel):
    event_data: dict[str, Any] = Field(default_factory=dict)


@router.post("/run")
def start_agent(request: AgentRunRequest):
    orchestrator = get_orchestrator()
    result = orchestrator.run_agent(
        agent_type=request.agent_type,
        trigger_type=request.trigger_type,
        trigger_id=request.trigger_id,
        initial_state=request.initial_state,
    )
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/runs/{run_id}/resume")
def resume_agent(run_id: int, request: AgentResumeRequest):
    orchestrator = get_orchestrator()
    result = orchestrator.resume_agent(run_id=run_id, event_data=request.event_data)
    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/runs")
def list_runs(
    agent_type: str | None = None,
    status: str | None = None,
    limit: int = 20,
):
    orchestrator = get_orchestrator()
    return orchestrator.list_runs(agent_type=agent_type, status=status, limit=limit)


@router.get("/runs/{run_id}")
def get_run(run_id: int):
    orchestrator = get_orchestrator()
    result = orchestrator.get_run_status(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return result


@router.get("/types")
def get_agent_types():
    return {"agent_types": list_agent_types()}
