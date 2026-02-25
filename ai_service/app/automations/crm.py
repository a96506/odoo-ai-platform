"""
CRM automations: lead scoring, auto-assignment, follow-up generation, duplicate detection.
"""

import json
from typing import Any

import structlog

from app.automations.base import BaseAutomation
from app.models.schemas import AutomationResult

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are an expert CRM AI assistant integrated with Odoo ERP.
You analyze leads and opportunities to maximize conversion rates.
Base your decisions on historical data patterns, lead quality signals, and team capacity.
Always provide confidence scores and clear reasoning."""

SCORE_TOOLS = [
    {
        "name": "score_lead",
        "description": "Assign a quality score to a CRM lead based on available data",
        "input_schema": {
            "type": "object",
            "properties": {
                "score": {
                    "type": "integer",
                    "description": "Lead score from 0 to 100",
                },
                "priority": {
                    "type": "string",
                    "enum": ["0", "1", "2", "3"],
                    "description": "Priority: 0=Normal, 1=Low, 2=High, 3=Very High",
                },
                "signals": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Quality signals detected",
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence score 0.0-1.0",
                },
                "reasoning": {
                    "type": "string",
                    "description": "Explanation of the score",
                },
            },
            "required": ["score", "priority", "signals", "confidence", "reasoning"],
        },
    }
]

ASSIGN_TOOLS = [
    {
        "name": "assign_lead",
        "description": "Assign a lead to the best-fit salesperson based on capacity and expertise",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "integer",
                    "description": "The res.users ID of the assigned salesperson",
                },
                "team_id": {
                    "type": "integer",
                    "description": "The crm.team ID to assign",
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence score 0.0-1.0",
                },
                "reasoning": {
                    "type": "string",
                    "description": "Why this salesperson is the best fit",
                },
            },
            "required": ["user_id", "team_id", "confidence", "reasoning"],
        },
    }
]

FOLLOWUP_TOOLS = [
    {
        "name": "generate_followup",
        "description": "Generate a personalized follow-up email for a lead",
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {
                    "type": "string",
                    "description": "Email subject line",
                },
                "body": {
                    "type": "string",
                    "description": "Email body in plain text",
                },
                "followup_date": {
                    "type": "string",
                    "description": "Suggested next follow-up date (ISO format)",
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence score 0.0-1.0",
                },
                "reasoning": {
                    "type": "string",
                    "description": "Strategy behind the follow-up",
                },
            },
            "required": ["subject", "body", "followup_date", "confidence", "reasoning"],
        },
    }
]

DUPLICATE_TOOLS = [
    {
        "name": "detect_duplicates",
        "description": "Identify potential duplicate leads/contacts",
        "input_schema": {
            "type": "object",
            "properties": {
                "duplicate_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "IDs of potentially duplicate crm.lead records",
                },
                "merge_recommended": {
                    "type": "boolean",
                    "description": "Whether merging is recommended",
                },
                "primary_id": {
                    "type": "integer",
                    "description": "The lead ID that should be kept as primary",
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence score 0.0-1.0",
                },
                "reasoning": {
                    "type": "string",
                    "description": "Explanation of the duplicate detection",
                },
            },
            "required": ["duplicate_ids", "merge_recommended", "primary_id", "confidence", "reasoning"],
        },
    }
]


class CRMAutomation(BaseAutomation):
    automation_type = "crm"
    watched_models = ["crm.lead"]

    def on_create_crm_lead(
        self, model: str, record_id: int, values: dict
    ) -> AutomationResult:
        """When a new lead is created: score it, check duplicates, assign it."""
        record = self.fetch_record_context(model, record_id)
        if not record:
            return AutomationResult(
                success=False, action="process_new_lead",
                model=model, record_id=record_id, reasoning="Record not found",
            )

        dup_result = self._detect_duplicates(record)
        if dup_result.get("duplicate_ids") and dup_result.get("confidence", 0) >= self.settings.default_confidence_threshold:
            return AutomationResult(
                success=True,
                action="detect_duplicates",
                model=model,
                record_id=record_id,
                confidence=dup_result["confidence"],
                reasoning=dup_result["reasoning"],
                changes_made=dup_result,
                needs_approval=True,
            )

        score_result = self._score_lead(record)
        if score_result.get("confidence", 0) >= self.settings.default_confidence_threshold:
            updates: dict[str, Any] = {"priority": score_result.get("priority", "0")}
            if self.should_auto_execute(score_result["confidence"]):
                self.update_record(model, record_id, updates)

        if not record.get("user_id") or (isinstance(record.get("user_id"), (list, tuple)) and not record["user_id"][0]):
            assign_result = self._assign_lead(record, score_result)
            if assign_result.get("confidence", 0) >= self.settings.default_confidence_threshold:
                if self.should_auto_execute(assign_result["confidence"]):
                    self.update_record(model, record_id, {
                        "user_id": assign_result["user_id"],
                        "team_id": assign_result.get("team_id"),
                    })
                return AutomationResult(
                    success=True,
                    action="assign_lead",
                    model=model,
                    record_id=record_id,
                    confidence=assign_result["confidence"],
                    reasoning=assign_result["reasoning"],
                    changes_made={**score_result, **assign_result},
                    needs_approval=self.needs_approval(assign_result["confidence"]),
                )

        return AutomationResult(
            success=True,
            action="score_lead",
            model=model,
            record_id=record_id,
            confidence=score_result.get("confidence", 0),
            reasoning=score_result.get("reasoning", ""),
            changes_made=score_result,
            needs_approval=self.needs_approval(score_result.get("confidence", 0)),
        )

    def on_write_crm_lead(
        self, model: str, record_id: int, values: dict
    ) -> AutomationResult:
        """When a lead is updated (e.g. stage change), generate follow-up if needed."""
        if "stage_id" not in values:
            return AutomationResult(
                success=True, action="no_action",
                model=model, record_id=record_id,
                reasoning="No stage change, no follow-up needed",
            )

        record = self.fetch_record_context(model, record_id)
        if not record:
            return AutomationResult(
                success=False, action="generate_followup",
                model=model, record_id=record_id, reasoning="Record not found",
            )

        return self._generate_followup(model, record_id, record)

    # --- Scheduled scans ---

    def scan_score_leads(self):
        """Periodically re-score leads that haven't been scored recently."""
        unscored = self.fetch_related_records(
            "crm.lead",
            [("type", "=", "lead"), ("active", "=", True), ("probability", "=", 0)],
            fields=["name", "partner_name", "email_from", "phone", "expected_revenue",
                     "source_id", "medium_id", "country_id", "description"],
            limit=50,
        )
        logger.info("scanning_unscored_leads", count=len(unscored))
        for lead in unscored:
            try:
                result = self._score_lead(lead)
                if result.get("confidence", 0) >= self.settings.auto_approve_threshold:
                    self.update_record("crm.lead", lead["id"], {
                        "priority": result.get("priority", "0"),
                    })
            except Exception as exc:
                logger.error("lead_scoring_scan_error", record_id=lead["id"], error=str(exc))

    # --- Internal methods ---

    def _score_lead(self, record: dict) -> dict:
        won_leads = self.fetch_related_records(
            "crm.lead",
            [("type", "=", "opportunity"), ("stage_id.is_won", "=", True)],
            fields=["partner_name", "email_from", "source_id", "medium_id",
                     "expected_revenue", "country_id", "tag_ids"],
            limit=30,
        )

        lost_leads = self.fetch_related_records(
            "crm.lead",
            [("active", "=", False), ("probability", "=", 0)],
            fields=["partner_name", "email_from", "source_id", "medium_id",
                     "expected_revenue", "country_id", "tag_ids"],
            limit=30,
        )

        user_msg = f"""Score this CRM lead based on quality and conversion likelihood:

Lead to score:
- Name: {record.get('name', 'N/A')}
- Company: {record.get('partner_name', 'N/A')}
- Email: {record.get('email_from', 'N/A')}
- Phone: {record.get('phone', 'N/A')}
- Expected Revenue: {record.get('expected_revenue', 0)}
- Source: {record.get('source_id', 'N/A')}
- Medium: {record.get('medium_id', 'N/A')}
- Country: {record.get('country_id', 'N/A')}
- Description: {record.get('description', 'N/A')}

Historical won deals (patterns of success):
{json.dumps(won_leads[:15], indent=2, default=str)}

Historical lost deals (patterns to avoid):
{json.dumps(lost_leads[:15], indent=2, default=str)}

Score from 0-100 based on how likely this lead is to convert.
Set priority: 0=Normal, 1=Low priority, 2=High priority, 3=Very High (hot lead)."""

        result = self.analyze_with_tools(SYSTEM_PROMPT, user_msg, SCORE_TOOLS)
        if result["tool_calls"]:
            return result["tool_calls"][0]["input"]
        return {"score": 50, "priority": "0", "signals": [], "confidence": 0}

    def _assign_lead(self, record: dict, score_result: dict) -> dict:
        salespeople = self.fetch_related_records(
            "res.users",
            [("share", "=", False), ("active", "=", True)],
            fields=["id", "name", "login"],
            limit=50,
        )

        teams = self.fetch_related_records(
            "crm.team",
            [("active", "=", True)],
            fields=["id", "name", "member_ids"],
            limit=20,
        )

        workload = {}
        for sp in salespeople:
            count = self.odoo.search_count(
                "crm.lead",
                [("user_id", "=", sp["id"]), ("active", "=", True), ("type", "=", "lead")],
            )
            workload[sp["id"]] = count

        user_msg = f"""Assign this lead to the best-fit salesperson:

Lead:
- Name: {record.get('name', 'N/A')}
- Company: {record.get('partner_name', 'N/A')}
- Expected Revenue: {record.get('expected_revenue', 0)}
- Country: {record.get('country_id', 'N/A')}
- Lead Score: {score_result.get('score', 50)}
- Priority: {score_result.get('priority', '0')}
- Quality Signals: {score_result.get('signals', [])}

Available salespeople and their current workload:
{json.dumps([{**sp, 'current_leads': workload.get(sp['id'], 0)} for sp in salespeople], indent=2, default=str)}

Sales teams:
{json.dumps(teams, indent=2, default=str)}

Assign based on:
- Current workload (balance the distribution)
- Team expertise if discernible
- High-value leads should go to experienced team members"""

        result = self.analyze_with_tools(SYSTEM_PROMPT, user_msg, ASSIGN_TOOLS)
        if result["tool_calls"]:
            return result["tool_calls"][0]["input"]
        return {"user_id": 0, "team_id": 0, "confidence": 0}

    def _generate_followup(
        self, model: str, record_id: int, record: dict
    ) -> AutomationResult:
        stage = record.get("stage_id", "Unknown")
        partner = record.get("partner_name", record.get("partner_id", ""))

        messages = self.fetch_related_records(
            "mail.message",
            [("res_id", "=", record_id), ("model", "=", "crm.lead")],
            fields=["date", "body", "author_id", "subject"],
            limit=10,
        )

        user_msg = f"""Generate a personalized follow-up email for this lead:

Lead:
- Name: {record.get('name', 'N/A')}
- Contact: {partner}
- Email: {record.get('email_from', 'N/A')}
- Stage: {stage}
- Expected Revenue: {record.get('expected_revenue', 0)}
- Description: {record.get('description', 'N/A')}

Recent communication history:
{json.dumps(messages[:5], indent=2, default=str)}

Write a professional, concise follow-up that:
- References the current stage in the sales process
- Provides value (not just "checking in")
- Has a clear call to action
- Is personalized to the contact/company"""

        result = self.analyze_with_tools(SYSTEM_PROMPT, user_msg, FOLLOWUP_TOOLS)

        if result["tool_calls"]:
            tool_result = result["tool_calls"][0]["input"]
            confidence = tool_result.get("confidence", 0)

            return AutomationResult(
                success=True,
                action="generate_followup",
                model=model,
                record_id=record_id,
                confidence=confidence,
                reasoning=tool_result.get("reasoning", ""),
                changes_made=tool_result,
                needs_approval=True,
            )

        return AutomationResult(
            success=False,
            action="generate_followup",
            model=model,
            record_id=record_id,
            reasoning="Failed to generate follow-up",
        )

    def _detect_duplicates(self, record: dict) -> dict:
        email = record.get("email_from", "")
        phone = record.get("phone", "")
        partner_name = record.get("partner_name", "")

        domain = [("id", "!=", record.get("id", 0)), ("active", "=", True)]
        sub_domains = []
        if email:
            sub_domains.append([("email_from", "ilike", email)])
        if phone:
            sub_domains.append([("phone", "=", phone)])
        if partner_name:
            sub_domains.append([("partner_name", "ilike", partner_name)])

        if not sub_domains:
            return {"duplicate_ids": [], "confidence": 0}

        combined_domain = domain + ["|"] * (len(sub_domains) - 1)
        for sd in sub_domains:
            combined_domain.extend(sd)

        candidates = self.fetch_related_records(
            "crm.lead",
            combined_domain,
            fields=["name", "partner_name", "email_from", "phone", "user_id", "stage_id", "create_date"],
            limit=20,
        )

        if not candidates:
            return {"duplicate_ids": [], "confidence": 0}

        user_msg = f"""Check if any of these existing leads are duplicates of the new lead:

New lead:
- Name: {record.get('name', 'N/A')}
- Company: {partner_name}
- Email: {email}
- Phone: {phone}

Potential duplicates:
{json.dumps(candidates, indent=2, default=str)}

Consider: same person/company with different spellings, same email, same phone number."""

        result = self.analyze_with_tools(SYSTEM_PROMPT, user_msg, DUPLICATE_TOOLS)
        if result["tool_calls"]:
            return result["tool_calls"][0]["input"]
        return {"duplicate_ids": [], "confidence": 0}
