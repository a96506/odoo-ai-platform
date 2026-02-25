"""
Base automation class that all module-specific automations inherit from.
Provides common patterns: Odoo data fetching, Claude analysis, confidence-gated execution.
"""

from abc import ABC, abstractmethod
from typing import Any

import structlog

from app.config import get_settings
from app.odoo_client import get_odoo_client
from app.claude_client import get_claude_client
from app.models.schemas import AutomationResult

logger = structlog.get_logger()


class BaseAutomation(ABC):
    """
    Base class for all Odoo automation handlers.

    Subclasses must define:
    - automation_type: str identifying the module (e.g. "accounting")
    - watched_models: list of Odoo model names this handler processes
    - handle_event(): process a webhook event
    """

    automation_type: str = ""
    watched_models: list[str] = []

    def __init__(self):
        self.settings = get_settings()

    @property
    def odoo(self):
        return get_odoo_client()

    @property
    def claude(self):
        return get_claude_client()

    def handle_event(
        self,
        event_type: str,
        model: str,
        record_id: int,
        values: dict[str, Any],
    ) -> AutomationResult:
        """Route an incoming event to the appropriate handler method."""
        method_name = f"on_{event_type}_{model.replace('.', '_')}"
        handler = getattr(self, method_name, None)

        if handler is None:
            handler = getattr(self, f"on_{event_type}", None)

        if handler is None:
            return AutomationResult(
                success=False,
                action="no_handler",
                model=model,
                record_id=record_id,
                reasoning=f"No handler for {event_type} on {model}",
            )

        try:
            return handler(model=model, record_id=record_id, values=values)
        except Exception as exc:
            logger.error(
                "automation_error",
                type=self.automation_type,
                model=model,
                record_id=record_id,
                error=str(exc),
            )
            return AutomationResult(
                success=False,
                action=method_name,
                model=model,
                record_id=record_id,
                reasoning=f"Error: {exc}",
            )

    def run_action(
        self, action: str, model: str, record_id: int
    ) -> AutomationResult:
        """Run a named action directly (not from a webhook)."""
        handler = getattr(self, f"action_{action}", None)
        if handler is None:
            return AutomationResult(
                success=False,
                action=action,
                model=model,
                record_id=record_id,
                reasoning=f"Unknown action: {action}",
            )
        return handler(model=model, record_id=record_id)

    def execute_approved(
        self, action: str, model: str, record_id: int, data: dict
    ) -> AutomationResult:
        """Execute a previously approved action with stored data."""
        handler = getattr(self, f"execute_{action}", None)
        if handler is None:
            return AutomationResult(
                success=False,
                action=action,
                model=model,
                record_id=record_id,
                reasoning=f"No execute handler for: {action}",
            )
        return handler(model=model, record_id=record_id, data=data)

    def scheduled_scan(self, action: str):
        """Override in subclasses to implement periodic scanning logic."""
        handler = getattr(self, f"scan_{action}", None)
        if handler:
            handler()

    def should_auto_execute(self, confidence: float) -> bool:
        """Check if confidence is high enough for auto-execution."""
        return confidence >= self.settings.auto_approve_threshold

    def needs_approval(self, confidence: float) -> bool:
        """Check if the action needs human approval."""
        return (
            confidence >= self.settings.default_confidence_threshold
            and confidence < self.settings.auto_approve_threshold
        )

    def analyze_with_tools(
        self,
        system_prompt: str,
        user_message: str,
        tools: list[dict],
    ) -> dict[str, Any]:
        """Send data to Claude for analysis with structured tool output."""
        return self.claude.analyze(
            system_prompt=system_prompt,
            user_message=user_message,
            tools=tools,
        )

    def fetch_record_context(
        self, model: str, record_id: int, fields: list[str] | None = None
    ) -> dict | None:
        """Fetch a record from Odoo with optional field filtering."""
        return self.odoo.get_record(model, record_id, fields)

    def fetch_related_records(
        self,
        model: str,
        domain: list,
        fields: list[str] | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Fetch related records for context building."""
        return self.odoo.search_read(model, domain, fields=fields, limit=limit)

    def update_record(
        self, model: str, record_id: int, values: dict
    ) -> bool:
        """Update an Odoo record."""
        return self.odoo.write(model, [record_id], values)

    def create_record(self, model: str, values: dict) -> int:
        """Create a new Odoo record."""
        return self.odoo.create(model, values)
