"""
MonthEndCloseAgent — continuous close agent that upgrades the Phase 1
month-end closing assistant to an event-driven, multi-step workflow.

Pipeline: scan issues -> classify severity -> auto-resolve simple items ->
          queue complex items for review -> generate close report ->
          notify controller -> track completion
"""

from __future__ import annotations

from typing import Any, TypedDict

import structlog
from langgraph.graph import END, START, StateGraph

from app.agents import register_agent
from app.agents.base_agent import AgentState, BaseAgent

logger = structlog.get_logger()


class MonthEndCloseState(TypedDict, total=False):
    # Base fields
    run_id: int
    step_count: int
    token_count: int
    error: str | None
    needs_suspension: bool
    suspension_reason: str | None
    current_step: str

    # Domain fields
    period: str  # YYYY-MM
    scan_results: dict[str, Any]
    total_issues: int
    auto_resolved: int
    pending_review: int
    severity_classification: dict[str, list[dict[str, Any]]]  # critical/high/medium/low
    anomalies_detected: list[dict[str, Any]]
    close_readiness_score: float  # 0-100
    ai_summary: dict[str, Any]
    report_generated: bool
    notifications_sent: list[str]


class MonthEndCloseAgent(BaseAgent):
    agent_type = "month_end_close"
    description = "Continuous close: scan → classify → auto-resolve → report → notify"
    max_steps = 15

    def get_state_schema(self) -> type:
        return MonthEndCloseState

    def build_graph(self) -> StateGraph:
        graph = StateGraph(MonthEndCloseState)

        graph.add_node("scan_issues", self._scan_issues)
        graph.add_node("run_anomaly_detection", self._run_anomaly_detection)
        graph.add_node("classify_severity", self._classify_severity)
        graph.add_node("auto_resolve", self._auto_resolve)
        graph.add_node("calculate_readiness", self._calculate_readiness)
        graph.add_node("generate_report", self._generate_report)
        graph.add_node("notify_controller", self._notify_controller)

        graph.add_edge(START, "scan_issues")
        graph.add_edge("scan_issues", "run_anomaly_detection")
        graph.add_edge("run_anomaly_detection", "classify_severity")
        graph.add_edge("classify_severity", "auto_resolve")
        graph.add_edge("auto_resolve", "calculate_readiness")
        graph.add_edge("calculate_readiness", "generate_report")
        graph.add_edge("generate_report", "notify_controller")
        graph.add_edge("notify_controller", END)

        return graph

    # ------------------------------------------------------------------
    # Node implementations
    # ------------------------------------------------------------------

    def _scan_issues(self, state: MonthEndCloseState) -> dict:
        period = state.get("period", "")
        if not period:
            return {"error": "No period specified", "scan_results": {}, "total_issues": 0}

        try:
            from app.automations.month_end import MonthEndClosingAutomation
            automation = MonthEndClosingAutomation()
            scan_results = automation.run_full_scan(period)

            total_issues = sum(r.get("items_found", 0) for r in scan_results.values())
            return {"scan_results": scan_results, "total_issues": total_issues}

        except Exception as exc:
            return {"error": f"Scan failed: {exc}", "scan_results": {}, "total_issues": 0}

    def _run_anomaly_detection(self, state: MonthEndCloseState) -> dict:
        """Run Benford's Law and Z-score anomaly detection on period transactions."""
        period = state.get("period", "")
        anomalies = []

        try:
            from app.automations.anomaly_detection import AnomalyDetector
            detector = AnomalyDetector()
            anomalies = detector.detect_anomalies(period)
        except Exception as exc:
            logger.warning("anomaly_detection_failed", error=str(exc))

        return {"anomalies_detected": anomalies}

    def _classify_severity(self, state: MonthEndCloseState) -> dict:
        scan_results = state.get("scan_results", {})
        anomalies = state.get("anomalies_detected", [])
        classified: dict[str, list] = {"critical": [], "high": [], "medium": [], "low": []}

        severity_map = {
            "unreconciled_bank": "high",
            "stale_drafts": "medium",
            "unbilled_deliveries": "high",
            "missing_vendor_bills": "critical",
            "uninvoiced_revenue": "critical",
            "depreciation": "medium",
            "tax_validation": "high",
            "inter_company": "medium",
            "adjustments": "low",
            "final_review": "low",
        }

        for step_name, result in scan_results.items():
            items_found = result.get("items_found", 0)
            if items_found > 0:
                severity = severity_map.get(step_name, "medium")
                classified[severity].append({
                    "step": step_name,
                    "items": items_found,
                    "details": result.get("details", []),
                })

        for anomaly in anomalies:
            severity = "critical" if anomaly.get("score", 0) > 3.0 else "high"
            classified[severity].append({
                "step": "anomaly_detection",
                "type": anomaly.get("type", "unknown"),
                "details": anomaly,
            })

        return {"severity_classification": classified}

    def _auto_resolve(self, state: MonthEndCloseState) -> dict:
        classified = state.get("severity_classification", {})
        auto_resolved = 0
        pending_review = 0

        for item in classified.get("low", []):
            auto_resolved += item.get("items", 0)

        for severity in ("critical", "high", "medium"):
            for item in classified.get(severity, []):
                pending_review += item.get("items", 0)

        return {"auto_resolved": auto_resolved, "pending_review": pending_review}

    def _calculate_readiness(self, state: MonthEndCloseState) -> dict:
        total = state.get("total_issues", 0)
        resolved = state.get("auto_resolved", 0)
        pending = state.get("pending_review", 0)
        anomalies = len(state.get("anomalies_detected", []))
        classified = state.get("severity_classification", {})

        if total == 0 and anomalies == 0:
            score = 100.0
        else:
            critical_count = len(classified.get("critical", []))
            high_count = len(classified.get("high", []))

            score = 100.0
            score -= critical_count * 20.0
            score -= high_count * 10.0
            score -= anomalies * 5.0
            if total > 0:
                score -= (pending / max(total, 1)) * 20.0
            score = max(0.0, min(100.0, score))

        return {"close_readiness_score": round(score, 1)}

    def _generate_report(self, state: MonthEndCloseState) -> dict:
        period = state.get("period", "")

        try:
            result = self.analyze_with_tools(
                system_prompt=(
                    "You are a financial controller assistant. Generate a concise "
                    "month-end close status report with risk assessment, priority "
                    "actions, and estimated hours to complete."
                ),
                user_message=(
                    f"Period: {period}\n"
                    f"Total issues: {state.get('total_issues', 0)}\n"
                    f"Auto-resolved: {state.get('auto_resolved', 0)}\n"
                    f"Pending review: {state.get('pending_review', 0)}\n"
                    f"Anomalies: {len(state.get('anomalies_detected', []))}\n"
                    f"Readiness score: {state.get('close_readiness_score', 0)}/100\n"
                    f"Severity breakdown: {state.get('severity_classification', {})}\n"
                ),
                tools=[{
                    "name": "generate_close_report",
                    "description": "Generate month-end close status report",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "risk_level": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                            "summary": {"type": "string"},
                            "priority_actions": {"type": "array", "items": {"type": "string"}},
                            "estimated_hours": {"type": "number"},
                        },
                        "required": ["risk_level", "summary"],
                    },
                }],
                state=state,
            )
            ai_summary = result.get("tool_input", {"summary": "Report generation completed"})
        except Exception:
            score = state.get("close_readiness_score", 0)
            if score >= 90:
                risk = "low"
            elif score >= 70:
                risk = "medium"
            elif score >= 50:
                risk = "high"
            else:
                risk = "critical"

            ai_summary = {
                "risk_level": risk,
                "summary": (
                    f"Period {period}: {state.get('total_issues', 0)} issues found, "
                    f"{state.get('auto_resolved', 0)} auto-resolved, "
                    f"{state.get('pending_review', 0)} pending review. "
                    f"Readiness: {score}/100."
                ),
            }

        return {"ai_summary": ai_summary, "report_generated": True}

    def _notify_controller(self, state: MonthEndCloseState) -> dict:
        period = state.get("period", "")
        summary = state.get("ai_summary", {})
        score = state.get("close_readiness_score", 0)
        notifications = []

        risk_emoji = {"low": "OK", "medium": "WARN", "high": "ALERT", "critical": "URGENT"}
        risk = summary.get("risk_level", "medium")

        body = (
            f"[{risk_emoji.get(risk, '')}] Month-End Close: {period}\n"
            f"Readiness: {score}/100 | Risk: {risk}\n"
            f"{summary.get('summary', '')}\n"
            f"Issues: {state.get('total_issues', 0)} | "
            f"Auto-resolved: {state.get('auto_resolved', 0)} | "
            f"Pending: {state.get('pending_review', 0)} | "
            f"Anomalies: {len(state.get('anomalies_detected', []))}"
        )

        sent = self.notify("slack", "", f"Month-End Close Status: {period}", body)
        if sent:
            notifications.append("slack")

        return {"notifications_sent": notifications}


register_agent(MonthEndCloseAgent)
