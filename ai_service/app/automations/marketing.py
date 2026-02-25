"""
Marketing automations: contact segmentation, campaign optimization, send time optimization.
"""

import json

import structlog

from app.automations.base import BaseAutomation
from app.models.schemas import AutomationResult

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are an expert Marketing AI assistant integrated with Odoo ERP.
You help optimize marketing campaigns through smart segmentation,
content suggestions, and send-time optimization.
Base decisions on engagement data, customer behavior, and best practices.
Always provide confidence scores and clear reasoning."""

SEGMENT_TOOLS = [
    {
        "name": "segment_contacts",
        "description": "Create smart contact segments for targeted marketing",
        "input_schema": {
            "type": "object",
            "properties": {
                "segments": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                            "criteria": {"type": "string", "description": "Odoo domain filter as string"},
                            "estimated_size": {"type": "integer"},
                            "best_for": {"type": "string", "description": "What campaigns this segment is best for"},
                        },
                    },
                },
                "confidence": {"type": "number"},
                "reasoning": {"type": "string"},
            },
            "required": ["segments", "confidence", "reasoning"],
        },
    }
]

CAMPAIGN_TOOLS = [
    {
        "name": "optimize_campaign",
        "description": "Suggest optimizations for a marketing campaign",
        "input_schema": {
            "type": "object",
            "properties": {
                "subject_suggestions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Alternative subject lines to test",
                },
                "optimal_send_time": {
                    "type": "string",
                    "description": "Best time to send (ISO format)",
                },
                "optimal_send_day": {
                    "type": "string",
                    "enum": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
                },
                "target_segment_suggestions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Audience refinement suggestions",
                },
                "content_tips": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Content improvement suggestions",
                },
                "predicted_open_rate": {"type": "number"},
                "confidence": {"type": "number"},
                "reasoning": {"type": "string"},
            },
            "required": ["subject_suggestions", "optimal_send_day", "content_tips", "confidence", "reasoning"],
        },
    }
]

PERFORMANCE_TOOLS = [
    {
        "name": "analyze_campaign_performance",
        "description": "Analyze campaign results and provide actionable insights",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "key_metrics": {
                    "type": "object",
                    "properties": {
                        "open_rate_assessment": {"type": "string"},
                        "click_rate_assessment": {"type": "string"},
                        "overall_grade": {"type": "string", "enum": ["A", "B", "C", "D", "F"]},
                    },
                },
                "improvements": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific improvements for next campaign",
                },
                "confidence": {"type": "number"},
                "reasoning": {"type": "string"},
            },
            "required": ["summary", "key_metrics", "improvements", "confidence", "reasoning"],
        },
    }
]


class MarketingAutomation(BaseAutomation):
    automation_type = "marketing"
    watched_models = ["mailing.mailing"]

    def on_create(
        self, model: str, record_id: int, values: dict
    ) -> AutomationResult:
        """When a new campaign is created, suggest optimizations."""
        record = self.fetch_record_context(model, record_id)
        if not record:
            return AutomationResult(
                success=False, action="optimize_campaign",
                model=model, record_id=record_id, reasoning="Record not found",
            )
        return self._optimize_campaign(model, record_id, record)

    def on_write(
        self, model: str, record_id: int, values: dict
    ) -> AutomationResult:
        if "state" in values and values.get("state") == "done":
            record = self.fetch_record_context(model, record_id)
            if record:
                return self._analyze_performance(model, record_id, record)
        return AutomationResult(
            success=True, action="no_action",
            model=model, record_id=record_id,
            reasoning="Campaign update logged",
        )

    # --- Scheduled scans ---

    def scan_segment_contacts(self):
        """Analyze contact base and suggest segments."""
        contacts = self.fetch_related_records(
            "res.partner",
            [("is_company", "=", False), ("email", "!=", False), ("active", "=", True)],
            fields=["id", "name", "email", "country_id", "city",
                     "customer_rank", "supplier_rank", "create_date"],
            limit=200,
        )

        if not contacts:
            return

        past_campaigns = self.fetch_related_records(
            "mailing.mailing",
            [("state", "=", "done")],
            fields=["subject", "sent", "opened", "clicked", "replied", "bounced"],
            limit=20,
        )

        user_msg = f"""Analyze the contact base and suggest marketing segments:

Contacts sample ({len(contacts)} total):
{json.dumps(contacts[:50], indent=2, default=str)}

Past campaign performance:
{json.dumps(past_campaigns, indent=2, default=str)}

Create 3-5 smart segments based on:
- Customer value (high vs low revenue)
- Geographic patterns
- Engagement level
- Lifecycle stage (new vs returning)"""

        result = self.analyze_with_tools(SYSTEM_PROMPT, user_msg, SEGMENT_TOOLS)
        if result["tool_calls"]:
            segments = result["tool_calls"][0]["input"]
            logger.info(
                "contact_segmentation_complete",
                segments=len(segments.get("segments", [])),
            )

    # --- Internal methods ---

    def _optimize_campaign(
        self, model: str, record_id: int, record: dict
    ) -> AutomationResult:
        past_campaigns = self.fetch_related_records(
            "mailing.mailing",
            [("state", "=", "done")],
            fields=["subject", "sent", "opened", "clicked", "schedule_date"],
            limit=15,
        )

        user_msg = f"""Optimize this marketing campaign before sending:

Campaign:
- Subject: {record.get('subject', 'N/A')}
- Body Preview: {str(record.get('body_html', ''))[:500]}
- Scheduled: {record.get('schedule_date', 'Not scheduled')}
- Recipients: {record.get('mailing_model_id', 'N/A')}

Past campaign results for reference:
{json.dumps(past_campaigns, indent=2, default=str)}

Suggest:
- Alternative subject lines for A/B testing
- Optimal send day and time
- Content improvements
- Audience refinement"""

        result = self.analyze_with_tools(SYSTEM_PROMPT, user_msg, CAMPAIGN_TOOLS)

        if result["tool_calls"]:
            tool_result = result["tool_calls"][0]["input"]
            return AutomationResult(
                success=True,
                action="optimize_campaign",
                model=model,
                record_id=record_id,
                confidence=tool_result.get("confidence", 0),
                reasoning=tool_result.get("reasoning", ""),
                changes_made=tool_result,
                needs_approval=True,
            )

        return AutomationResult(
            success=False, action="optimize_campaign",
            model=model, record_id=record_id,
            reasoning="Campaign optimization produced no result",
        )

    def _analyze_performance(
        self, model: str, record_id: int, record: dict
    ) -> AutomationResult:
        user_msg = f"""Analyze this completed campaign's performance:

Campaign Results:
- Subject: {record.get('subject', 'N/A')}
- Sent: {record.get('sent', 0)}
- Opened: {record.get('opened', 0)}
- Clicked: {record.get('clicked', 0)}
- Replied: {record.get('replied', 0)}
- Bounced: {record.get('bounced', 0)}

Provide:
- Overall performance grade
- What worked well
- Specific improvements for the next campaign"""

        result = self.analyze_with_tools(SYSTEM_PROMPT, user_msg, PERFORMANCE_TOOLS)

        if result["tool_calls"]:
            tool_result = result["tool_calls"][0]["input"]
            return AutomationResult(
                success=True,
                action="analyze_performance",
                model=model,
                record_id=record_id,
                confidence=tool_result.get("confidence", 0),
                reasoning=tool_result.get("reasoning", ""),
                changes_made=tool_result,
                needs_approval=False,
            )

        return AutomationResult(
            success=True, action="analyze_performance",
            model=model, record_id=record_id,
            reasoning="Performance analysis completed",
        )
