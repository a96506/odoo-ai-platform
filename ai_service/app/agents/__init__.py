"""
Agent registry — maps agent types to their agent classes.
Coexists with the automation registry; agents handle multi-step workflows,
automations handle single-action processing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agents.base_agent import BaseAgent

_AGENT_REGISTRY: dict[str, type[BaseAgent]] = {}


def register_agent(agent_cls: type[BaseAgent]):
    _AGENT_REGISTRY[agent_cls.agent_type] = agent_cls


def get_agent_class(agent_type: str) -> type[BaseAgent] | None:
    return _AGENT_REGISTRY.get(agent_type)


def list_agent_types() -> list[str]:
    return list(_AGENT_REGISTRY.keys())


def init_agents():
    """Import agent modules so they self-register."""
    from app.agents.procure_to_pay import ProcureToPayAgent  # noqa: F401
    from app.agents.collection import CollectionAgent  # noqa: F401
    from app.agents.month_end_close import MonthEndCloseAgent  # noqa: F401
