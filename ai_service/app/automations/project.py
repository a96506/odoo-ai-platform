"""
Project automations: task assignment, duration estimation, status summaries, risk detection.
"""

import json

import structlog

from app.automations.base import BaseAutomation
from app.models.schemas import AutomationResult

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are an expert Project Management AI assistant integrated with Odoo ERP.
You optimize task assignment, estimate durations, detect project risks, and generate status reports.
Base decisions on team capacity, historical performance, and project context.
Always provide confidence scores and clear reasoning."""

ASSIGN_TOOLS = [
    {
        "name": "assign_task",
        "description": "Assign a project task to the best-fit team member",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Recommended assignee user IDs",
                },
                "estimated_hours": {
                    "type": "number",
                    "description": "Estimated hours to complete",
                },
                "priority": {
                    "type": "string",
                    "enum": ["0", "1"],
                    "description": "0=Normal, 1=Urgent",
                },
                "confidence": {"type": "number"},
                "reasoning": {"type": "string"},
            },
            "required": ["user_ids", "estimated_hours", "priority", "confidence", "reasoning"],
        },
    }
]

ESTIMATE_TOOLS = [
    {
        "name": "estimate_duration",
        "description": "Estimate task duration based on historical data and task characteristics",
        "input_schema": {
            "type": "object",
            "properties": {
                "estimated_hours": {"type": "number"},
                "range_low": {"type": "number", "description": "Optimistic estimate"},
                "range_high": {"type": "number", "description": "Pessimistic estimate"},
                "complexity": {"type": "string", "enum": ["low", "medium", "high"]},
                "risk_factors": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Factors that could affect duration",
                },
                "confidence": {"type": "number"},
                "reasoning": {"type": "string"},
            },
            "required": ["estimated_hours", "range_low", "range_high", "complexity", "confidence", "reasoning"],
        },
    }
]

RISK_TOOLS = [
    {
        "name": "detect_project_risk",
        "description": "Analyze a project for risks and generate a status summary",
        "input_schema": {
            "type": "object",
            "properties": {
                "overall_health": {
                    "type": "string",
                    "enum": ["on_track", "at_risk", "critical"],
                },
                "risks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "risk": {"type": "string"},
                            "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                            "mitigation": {"type": "string"},
                        },
                    },
                },
                "summary": {"type": "string", "description": "Brief project status summary"},
                "recommendations": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "confidence": {"type": "number"},
                "reasoning": {"type": "string"},
            },
            "required": ["overall_health", "risks", "summary", "recommendations", "confidence", "reasoning"],
        },
    }
]


class ProjectAutomation(BaseAutomation):
    automation_type = "project"
    watched_models = ["project.task"]

    def on_create_project_task(
        self, model: str, record_id: int, values: dict
    ) -> AutomationResult:
        """When a new task is created, assign it and estimate duration."""
        record = self.fetch_record_context(model, record_id)
        if not record:
            return AutomationResult(
                success=False, action="process_new_task",
                model=model, record_id=record_id, reasoning="Record not found",
            )

        estimate = self._estimate_duration(record)

        has_assignee = record.get("user_ids")
        if isinstance(has_assignee, (list, tuple)):
            has_assignee = len(has_assignee) > 0

        if not has_assignee:
            assignment = self._assign_task(record, estimate)
            if assignment.get("confidence", 0) >= self.settings.default_confidence_threshold:
                changes = {"user_ids": assignment.get("user_ids", [])}
                if estimate.get("estimated_hours"):
                    changes["planned_hours"] = estimate["estimated_hours"]

                if self.should_auto_execute(assignment["confidence"]):
                    self.update_record(model, record_id, changes)

                return AutomationResult(
                    success=True,
                    action="assign_task",
                    model=model,
                    record_id=record_id,
                    confidence=assignment["confidence"],
                    reasoning=assignment.get("reasoning", ""),
                    changes_made={**assignment, **estimate},
                    needs_approval=self.needs_approval(assignment["confidence"]),
                )

        if estimate.get("estimated_hours") and self.should_auto_execute(estimate.get("confidence", 0)):
            self.update_record(model, record_id, {"planned_hours": estimate["estimated_hours"]})

        return AutomationResult(
            success=True,
            action="estimate_duration",
            model=model,
            record_id=record_id,
            confidence=estimate.get("confidence", 0),
            reasoning=estimate.get("reasoning", ""),
            changes_made=estimate,
            needs_approval=False,
        )

    def on_write_project_task(
        self, model: str, record_id: int, values: dict
    ) -> AutomationResult:
        """When a task stage changes, check project health."""
        if "stage_id" not in values:
            return AutomationResult(
                success=True, action="no_action",
                model=model, record_id=record_id,
                reasoning="No stage change",
            )

        record = self.fetch_record_context(model, record_id)
        if not record:
            return AutomationResult(
                success=False, action="check_project_health",
                model=model, record_id=record_id, reasoning="Record not found",
            )

        project_id = record.get("project_id")
        if isinstance(project_id, (list, tuple)):
            project_id = project_id[0]

        if project_id:
            return self._check_project_health(project_id)

        return AutomationResult(
            success=True, action="no_action",
            model=model, record_id=record_id,
            reasoning="Task updated, no project to check",
        )

    # --- Internal methods ---

    def _assign_task(self, record: dict, estimate: dict) -> dict:
        project_id = record.get("project_id")
        if isinstance(project_id, (list, tuple)):
            project_id = project_id[0]

        team_members = self.fetch_related_records(
            "res.users",
            [("share", "=", False), ("active", "=", True)],
            fields=["id", "name"],
            limit=50,
        )

        workload = {}
        for member in team_members:
            open_tasks = self.odoo.search_count(
                "project.task",
                [("user_ids", "in", [member["id"]]), ("stage_id.fold", "=", False)],
            )
            workload[member["id"]] = open_tasks

        similar_tasks = self.fetch_related_records(
            "project.task",
            [("project_id", "=", project_id), ("stage_id.fold", "=", True)],
            fields=["name", "user_ids", "planned_hours", "tag_ids"],
            limit=30,
        )

        user_msg = f"""Assign this task to the best team member:

Task:
- Name: {record.get('name', 'N/A')}
- Project: {record.get('project_id', 'N/A')}
- Description: {record.get('description', 'N/A')}
- Tags: {record.get('tag_ids', [])}
- Estimated Hours: {estimate.get('estimated_hours', 'unknown')}
- Complexity: {estimate.get('complexity', 'unknown')}
- Deadline: {record.get('date_deadline', 'N/A')}

Team members and workload:
{json.dumps([{**m, 'open_tasks': workload.get(m['id'], 0)} for m in team_members], indent=2, default=str)}

Similar completed tasks in this project:
{json.dumps(similar_tasks[:15], indent=2, default=str)}

Assign based on:
- Current workload (balance the team)
- Past task patterns (who worked on similar tasks)
- Task complexity vs member experience
- Deadline urgency"""

        result = self.analyze_with_tools(SYSTEM_PROMPT, user_msg, ASSIGN_TOOLS)
        if result["tool_calls"]:
            return result["tool_calls"][0]["input"]
        return {"user_ids": [], "confidence": 0}

    def _estimate_duration(self, record: dict) -> dict:
        project_id = record.get("project_id")
        if isinstance(project_id, (list, tuple)):
            project_id = project_id[0]

        completed_tasks = self.fetch_related_records(
            "project.task",
            [("project_id", "=", project_id), ("stage_id.fold", "=", True)],
            fields=["name", "planned_hours", "effective_hours", "tag_ids", "description"],
            limit=30,
        )

        user_msg = f"""Estimate the duration for this task:

Task:
- Name: {record.get('name', 'N/A')}
- Description: {record.get('description', 'N/A')}
- Tags: {record.get('tag_ids', [])}
- Deadline: {record.get('date_deadline', 'N/A')}

Completed tasks in the same project for reference:
{json.dumps(completed_tasks[:20], indent=2, default=str)}

Provide:
- Best estimate in hours
- Optimistic and pessimistic estimates
- Complexity classification
- Risk factors that could affect duration"""

        result = self.analyze_with_tools(SYSTEM_PROMPT, user_msg, ESTIMATE_TOOLS)
        if result["tool_calls"]:
            return result["tool_calls"][0]["input"]
        return {"estimated_hours": 0, "confidence": 0}

    def _check_project_health(self, project_id: int) -> AutomationResult:
        project = self.odoo.get_record(
            "project.project", project_id,
            ["name", "date_start", "date", "task_count"],
        )

        tasks = self.fetch_related_records(
            "project.task",
            [("project_id", "=", project_id)],
            fields=["name", "stage_id", "user_ids", "date_deadline",
                     "planned_hours", "effective_hours", "priority"],
            limit=100,
        )

        overdue = [t for t in tasks if t.get("date_deadline") and t.get("stage_id", [False, ""])[1] != "Done"]

        user_msg = f"""Analyze this project's health:

Project: {project.get('name', 'N/A') if project else 'Unknown'}
Start Date: {project.get('date_start', 'N/A') if project else 'N/A'}
End Date: {project.get('date', 'N/A') if project else 'N/A'}

All tasks:
{json.dumps(tasks[:50], indent=2, default=str)}

Potentially overdue tasks:
{json.dumps(overdue[:20], indent=2, default=str)}

Assess:
- Overall project health
- Key risks (overdue tasks, resource bottlenecks, scope creep)
- Recommendations to get back on track
- Brief status summary suitable for a weekly report"""

        result = self.analyze_with_tools(SYSTEM_PROMPT, user_msg, RISK_TOOLS)

        if result["tool_calls"]:
            tool_result = result["tool_calls"][0]["input"]
            return AutomationResult(
                success=True,
                action="project_health_check",
                model="project.project",
                record_id=project_id,
                confidence=tool_result.get("confidence", 0),
                reasoning=tool_result.get("reasoning", ""),
                changes_made=tool_result,
                needs_approval=tool_result.get("overall_health") == "critical",
            )

        return AutomationResult(
            success=False, action="project_health_check",
            model="project.project", record_id=project_id,
            reasoning="Health check produced no result",
        )
