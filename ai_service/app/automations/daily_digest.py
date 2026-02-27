"""
Proactive AI Daily Digest — role-based morning briefing per user.

Aggregates data from Odoo per role (CFO, Sales Manager, Warehouse Manager),
sends it to Claude for narrative summary generation, and delivers the digest
via email (primary) with in-DB storage for dashboard access.
"""

from datetime import datetime, timedelta, date
from typing import Any

import structlog

from app.automations.base import BaseAutomation
from app.models.schemas import AutomationResult

logger = structlog.get_logger()

DIGEST_PROMPT = """You are an AI business analyst generating a morning briefing digest
for an ERP user. Write a concise, actionable summary (<500 words) that tells the user
exactly what needs their attention today.

Structure your response using the generate_digest tool with:
- A punchy headline summarizing the most important thing
- Key metrics compared to yesterday where possible
- Prioritized attention items (most urgent first)
- Any anomalies or unusual patterns detected
- A brief narrative summary tying everything together

Be specific with numbers. Use business language appropriate for the role.
Focus on what's ACTIONABLE — skip status updates that require no action."""

DIGEST_TOOLS = [
    {
        "name": "generate_digest",
        "description": "Generate a structured daily digest for a specific role",
        "input_schema": {
            "type": "object",
            "properties": {
                "headline": {
                    "type": "string",
                    "description": "One-line headline summarizing the most important item",
                },
                "summary": {
                    "type": "string",
                    "description": "Brief narrative summary (2-3 sentences)",
                },
                "key_metrics": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "value": {"type": "string"},
                            "change": {"type": "number", "description": "Percentage change vs yesterday"},
                            "change_label": {"type": "string", "description": "e.g. 'up 12% from yesterday'"},
                        },
                        "required": ["name", "value"],
                    },
                },
                "attention_items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                        },
                        "required": ["title", "description", "priority"],
                    },
                },
                "anomalies": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "description": {"type": "string"},
                            "severity": {"type": "string", "enum": ["high", "medium", "low"]},
                            "source": {"type": "string"},
                        },
                        "required": ["description", "severity"],
                    },
                },
            },
            "required": ["headline", "summary", "key_metrics", "attention_items", "anomalies"],
        },
    }
]

ROLE_CONFIGS: dict[str, dict[str, Any]] = {
    "cfo": {
        "title": "CFO / Finance Manager",
        "data_sources": [
            "ar_aging", "ap_aging", "cash_position", "overdue_invoices",
            "pending_approvals", "recent_anomalies", "month_end_status",
        ],
    },
    "sales_manager": {
        "title": "Sales Manager",
        "data_sources": [
            "pipeline_summary", "at_risk_deals", "overdue_followups",
            "conversion_metrics", "top_opportunities", "lost_deals",
        ],
    },
    "warehouse_manager": {
        "title": "Warehouse Manager",
        "data_sources": [
            "low_stock_alerts", "pending_deliveries", "overdue_shipments",
            "incoming_shipments", "stock_valuation",
        ],
    },
}

DEFAULT_DIGEST_CONFIG: dict[str, dict[str, Any]] = {
    "cfo": {"channels": ["email"], "send_time": "07:00", "enabled": True},
    "sales_manager": {"channels": ["email"], "send_time": "07:30", "enabled": True},
    "warehouse_manager": {"channels": ["email"], "send_time": "06:30", "enabled": True},
}


class DailyDigestAutomation(BaseAutomation):
    """AI-curated daily briefing per role."""

    automation_type = "reporting"
    watched_models: list[str] = []

    def generate_digest(self, role: str, target_date: date | None = None) -> dict[str, Any]:
        """
        Generate a daily digest for a given role.
        Aggregates data from Odoo, sends to Claude for narrative, returns structured content.
        """
        if role not in ROLE_CONFIGS:
            return {"error": f"Unknown role: {role}. Available: {list(ROLE_CONFIGS.keys())}"}

        target = target_date or date.today()
        role_config = ROLE_CONFIGS[role]

        raw_data = self._aggregate_role_data(role, target)

        digest_content = self._generate_ai_narrative(role, role_config, raw_data, target)
        if "error" in digest_content:
            digest_content = self._build_fallback_digest(role, raw_data, target)

        return {
            "role": role,
            "digest_date": target.isoformat(),
            "content": digest_content,
        }

    def generate_all_digests(self) -> list[dict[str, Any]]:
        """Generate digests for all configured roles."""
        results = []
        target = date.today()

        for role in ROLE_CONFIGS:
            config = DEFAULT_DIGEST_CONFIG.get(role, {})
            if not config.get("enabled", True):
                continue

            try:
                result = self.generate_digest(role, target)
                result["channels"] = config.get("channels", ["email"])
                results.append(result)
            except Exception as exc:
                logger.error("digest_generation_failed", role=role, error=str(exc))
                results.append({
                    "role": role,
                    "digest_date": target.isoformat(),
                    "error": str(exc),
                })

        return results

    def deliver_digest(
        self, role: str, channel: str, recipient: str, content: dict[str, Any]
    ) -> bool:
        """Deliver a generated digest via the specified channel."""
        if channel == "email":
            subject = f"Your Daily Digest — {content.get('headline', 'Morning Briefing')}"
            body = self._format_digest_email(role, content)
            html = self._format_digest_html(role, content)
            return self.notify("email", recipient, subject, body, html=html)

        if channel == "slack":
            return self._deliver_via_slack(role, recipient, content)

        logger.warning("digest_channel_not_available", channel=channel, role=role)
        return False

    def _deliver_via_slack(
        self, role: str, recipient: str, content: dict[str, Any]
    ) -> bool:
        """Deliver digest as a rich Block Kit message in Slack."""
        try:
            from app.notifications.slack import SlackChannel

            slack = SlackChannel()
            return slack.send_digest(channel=recipient, role=role, content=content)
        except Exception as exc:
            logger.error("slack_digest_delivery_failed", role=role, error=str(exc))
            return False

    # ------------------------------------------------------------------
    # Data aggregation per role
    # ------------------------------------------------------------------

    def _aggregate_role_data(self, role: str, target: date) -> dict[str, Any]:
        """Fetch role-specific data from Odoo."""
        data: dict[str, Any] = {"role": role, "date": target.isoformat()}

        if role == "cfo":
            data.update(self._aggregate_cfo_data(target))
        elif role == "sales_manager":
            data.update(self._aggregate_sales_data(target))
        elif role == "warehouse_manager":
            data.update(self._aggregate_warehouse_data(target))

        return data

    def _aggregate_cfo_data(self, target: date) -> dict[str, Any]:
        """Aggregate finance data for CFO digest."""
        today = target.isoformat()
        yesterday = (target - timedelta(days=1)).isoformat()

        overdue_invoices = self.fetch_related_records(
            "account.move",
            [
                ("move_type", "=", "out_invoice"),
                ("payment_state", "in", ["not_paid", "partial"]),
                ("invoice_date_due", "<", today),
                ("state", "=", "posted"),
            ],
            fields=["name", "partner_id", "amount_residual", "invoice_date_due"],
            limit=50,
        )

        open_ap = self.fetch_related_records(
            "account.move",
            [
                ("move_type", "=", "in_invoice"),
                ("payment_state", "in", ["not_paid", "partial"]),
                ("state", "=", "posted"),
            ],
            fields=["name", "partner_id", "amount_residual", "invoice_date_due"],
            limit=50,
        )

        overdue_ar_total = sum(float(inv.get("amount_residual", 0)) for inv in overdue_invoices)
        total_ap = sum(float(inv.get("amount_residual", 0)) for inv in open_ap)
        overdue_ap = [
            inv for inv in open_ap
            if inv.get("invoice_date_due") and str(inv["invoice_date_due"]) < today
        ]
        overdue_ap_total = sum(float(inv.get("amount_residual", 0)) for inv in overdue_ap)

        pending_approvals = self._count_pending_approvals()

        recent_anomalies = self._fetch_recent_anomalies()

        return {
            "overdue_ar_count": len(overdue_invoices),
            "overdue_ar_total": round(overdue_ar_total, 2),
            "open_ap_count": len(open_ap),
            "open_ap_total": round(total_ap, 2),
            "overdue_ap_count": len(overdue_ap),
            "overdue_ap_total": round(overdue_ap_total, 2),
            "pending_approvals": pending_approvals,
            "anomalies": recent_anomalies,
            "overdue_invoices_detail": [
                {
                    "name": inv.get("name", ""),
                    "partner": inv.get("partner_id", [None, ""])[1] if isinstance(inv.get("partner_id"), (list, tuple)) else "",
                    "amount": float(inv.get("amount_residual", 0)),
                    "due_date": str(inv.get("invoice_date_due", "")),
                }
                for inv in overdue_invoices[:10]
            ],
        }

    def _aggregate_sales_data(self, target: date) -> dict[str, Any]:
        """Aggregate sales pipeline data for Sales Manager digest."""
        today = target.isoformat()

        pipeline = self.fetch_related_records(
            "crm.lead",
            [("type", "=", "opportunity"), ("active", "=", True)],
            fields=["name", "expected_revenue", "probability", "stage_id", "date_deadline", "user_id"],
            limit=200,
        )

        total_pipeline = sum(float(l.get("expected_revenue", 0)) for l in pipeline)
        weighted_pipeline = sum(
            float(l.get("expected_revenue", 0)) * float(l.get("probability", 0)) / 100
            for l in pipeline
        )

        at_risk = [
            l for l in pipeline
            if l.get("date_deadline") and str(l["date_deadline"]) < today
        ]

        recent_won = self.fetch_related_records(
            "crm.lead",
            [
                ("type", "=", "opportunity"),
                ("active", "=", False),
                ("probability", "=", 100),
                ("date_closed", ">=", (target - timedelta(days=7)).isoformat()),
            ],
            fields=["name", "expected_revenue"],
            limit=20,
        )
        won_value = sum(float(l.get("expected_revenue", 0)) for l in recent_won)

        recent_lost = self.fetch_related_records(
            "crm.lead",
            [
                ("type", "=", "opportunity"),
                ("active", "=", False),
                ("probability", "=", 0),
                ("date_closed", ">=", (target - timedelta(days=7)).isoformat()),
            ],
            fields=["name", "expected_revenue"],
            limit=20,
        )
        lost_value = sum(float(l.get("expected_revenue", 0)) for l in recent_lost)

        overdue_activities = self.fetch_related_records(
            "mail.activity",
            [
                ("res_model", "=", "crm.lead"),
                ("date_deadline", "<", today),
            ],
            fields=["res_id", "summary", "date_deadline"],
            limit=20,
        )

        return {
            "total_pipeline_value": round(total_pipeline, 2),
            "weighted_pipeline_value": round(weighted_pipeline, 2),
            "total_opportunities": len(pipeline),
            "at_risk_count": len(at_risk),
            "at_risk_value": round(sum(float(l.get("expected_revenue", 0)) for l in at_risk), 2),
            "won_last_7_days": len(recent_won),
            "won_value_last_7_days": round(won_value, 2),
            "lost_last_7_days": len(recent_lost),
            "lost_value_last_7_days": round(lost_value, 2),
            "overdue_followups": len(overdue_activities),
            "at_risk_deals": [
                {
                    "name": l.get("name", ""),
                    "value": float(l.get("expected_revenue", 0)),
                    "deadline": str(l.get("date_deadline", "")),
                }
                for l in at_risk[:10]
            ],
        }

    def _aggregate_warehouse_data(self, target: date) -> dict[str, Any]:
        """Aggregate warehouse data for Warehouse Manager digest."""
        today = target.isoformat()

        low_stock = self.fetch_related_records(
            "product.product",
            [
                ("type", "=", "product"),
                ("qty_available", "<=", 0),
                ("active", "=", True),
            ],
            fields=["name", "qty_available", "virtual_available", "default_code"],
            limit=50,
        )

        pending_receipts = self.fetch_related_records(
            "stock.picking",
            [
                ("picking_type_code", "=", "incoming"),
                ("state", "in", ["assigned", "confirmed"]),
            ],
            fields=["name", "partner_id", "scheduled_date", "state"],
            limit=30,
        )

        overdue_deliveries = self.fetch_related_records(
            "stock.picking",
            [
                ("picking_type_code", "=", "outgoing"),
                ("state", "in", ["assigned", "confirmed"]),
                ("scheduled_date", "<", today),
            ],
            fields=["name", "partner_id", "scheduled_date", "state"],
            limit=30,
        )

        pending_deliveries = self.fetch_related_records(
            "stock.picking",
            [
                ("picking_type_code", "=", "outgoing"),
                ("state", "in", ["assigned", "confirmed"]),
                ("scheduled_date", ">=", today),
            ],
            fields=["name", "scheduled_date"],
            limit=30,
        )

        return {
            "low_stock_count": len(low_stock),
            "low_stock_items": [
                {"name": p.get("name", ""), "code": p.get("default_code", ""), "qty": float(p.get("qty_available", 0))}
                for p in low_stock[:10]
            ],
            "pending_receipts_count": len(pending_receipts),
            "overdue_deliveries_count": len(overdue_deliveries),
            "pending_deliveries_today": len(pending_deliveries),
            "overdue_deliveries": [
                {
                    "name": p.get("name", ""),
                    "date": str(p.get("scheduled_date", "")),
                }
                for p in overdue_deliveries[:10]
            ],
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _count_pending_approvals(self) -> int:
        """Count pending approvals from audit log."""
        from app.models.audit import AuditLog, ActionStatus, get_db_session

        try:
            with get_db_session() as session:
                return (
                    session.query(AuditLog)
                    .filter(AuditLog.status == ActionStatus.PENDING)
                    .count()
                )
        except Exception:
            return 0

    def _fetch_recent_anomalies(self) -> list[dict[str, Any]]:
        """Fetch anomalies detected in the last 24 hours from audit logs."""
        from app.models.audit import AuditLog, get_db_session

        try:
            with get_db_session() as session:
                cutoff = datetime.utcnow() - timedelta(hours=24)
                anomaly_logs = (
                    session.query(AuditLog)
                    .filter(
                        AuditLog.action_name.in_([
                            "flag_anomaly", "credit_check_failed",
                            "duplicate_check", "preclose_scan",
                        ]),
                        AuditLog.timestamp >= cutoff,
                    )
                    .order_by(AuditLog.timestamp.desc())
                    .limit(10)
                    .all()
                )
                return [
                    {
                        "description": log.ai_reasoning or "",
                        "severity": "high" if log.confidence and log.confidence < 0.5 else "medium",
                        "source": log.action_name,
                    }
                    for log in anomaly_logs
                ]
        except Exception:
            return []

    # ------------------------------------------------------------------
    # AI narrative generation
    # ------------------------------------------------------------------

    def _generate_ai_narrative(
        self,
        role: str,
        role_config: dict[str, Any],
        raw_data: dict[str, Any],
        target: date,
    ) -> dict[str, Any]:
        """Send aggregated data to Claude for narrative digest generation."""
        try:
            user_message = (
                f"Generate a daily digest for {role_config['title']} for {target.isoformat()}.\n\n"
                f"Here is the aggregated ERP data:\n{_format_data_for_prompt(raw_data)}"
            )

            response = self.claude.analyze(
                system_prompt=DIGEST_PROMPT,
                user_message=user_message,
                tools=DIGEST_TOOLS,
                max_tokens=2048,
            )

            for tc in response.get("tool_calls", []):
                if tc["name"] == "generate_digest":
                    return tc["input"]

            if response.get("text"):
                return {
                    "headline": "Your Daily Briefing",
                    "summary": response["text"][:500],
                    "key_metrics": [],
                    "attention_items": [],
                    "anomalies": [],
                }

            return {"error": "No digest generated by AI"}

        except Exception as exc:
            logger.error("ai_digest_generation_failed", role=role, error=str(exc))
            return {"error": str(exc)}

    def _build_fallback_digest(
        self, role: str, raw_data: dict[str, Any], target: date
    ) -> dict[str, Any]:
        """Build a basic digest without AI when Claude is unavailable."""
        headline = f"Daily Briefing — {target.strftime('%B %d, %Y')}"
        metrics = []
        attention_items = []
        anomalies_list = []

        if role == "cfo":
            metrics = [
                {"name": "Overdue AR", "value": f"${raw_data.get('overdue_ar_total', 0):,.2f}", "change": None, "change_label": f"{raw_data.get('overdue_ar_count', 0)} invoices"},
                {"name": "Open AP", "value": f"${raw_data.get('open_ap_total', 0):,.2f}", "change": None, "change_label": f"{raw_data.get('open_ap_count', 0)} bills"},
                {"name": "Pending Approvals", "value": str(raw_data.get("pending_approvals", 0)), "change": None, "change_label": ""},
            ]
            if raw_data.get("overdue_ar_count", 0) > 0:
                attention_items.append({
                    "title": f"{raw_data['overdue_ar_count']} overdue customer invoices",
                    "description": f"Total: ${raw_data.get('overdue_ar_total', 0):,.2f}",
                    "priority": "high",
                })
            for a in raw_data.get("anomalies", []):
                anomalies_list.append(a)

        elif role == "sales_manager":
            metrics = [
                {"name": "Pipeline Value", "value": f"${raw_data.get('total_pipeline_value', 0):,.2f}", "change": None, "change_label": f"{raw_data.get('total_opportunities', 0)} deals"},
                {"name": "Won (7 days)", "value": f"${raw_data.get('won_value_last_7_days', 0):,.2f}", "change": None, "change_label": f"{raw_data.get('won_last_7_days', 0)} deals"},
                {"name": "Lost (7 days)", "value": f"${raw_data.get('lost_value_last_7_days', 0):,.2f}", "change": None, "change_label": f"{raw_data.get('lost_last_7_days', 0)} deals"},
            ]
            if raw_data.get("at_risk_count", 0) > 0:
                attention_items.append({
                    "title": f"{raw_data['at_risk_count']} at-risk deals",
                    "description": f"Value: ${raw_data.get('at_risk_value', 0):,.2f} — past deadline",
                    "priority": "high",
                })
            if raw_data.get("overdue_followups", 0) > 0:
                attention_items.append({
                    "title": f"{raw_data['overdue_followups']} overdue follow-ups",
                    "description": "Activities past their deadline",
                    "priority": "medium",
                })

        elif role == "warehouse_manager":
            metrics = [
                {"name": "Low Stock Items", "value": str(raw_data.get("low_stock_count", 0)), "change": None, "change_label": ""},
                {"name": "Pending Receipts", "value": str(raw_data.get("pending_receipts_count", 0)), "change": None, "change_label": ""},
                {"name": "Deliveries Today", "value": str(raw_data.get("pending_deliveries_today", 0)), "change": None, "change_label": ""},
            ]
            if raw_data.get("overdue_deliveries_count", 0) > 0:
                attention_items.append({
                    "title": f"{raw_data['overdue_deliveries_count']} overdue deliveries",
                    "description": "Shipments past their scheduled date",
                    "priority": "high",
                })
            if raw_data.get("low_stock_count", 0) > 5:
                attention_items.append({
                    "title": f"{raw_data['low_stock_count']} products out of stock",
                    "description": "Immediate reorder needed",
                    "priority": "high",
                })

        return {
            "headline": headline,
            "summary": f"Automated briefing for {ROLE_CONFIGS[role]['title']}. AI narrative unavailable — showing raw metrics.",
            "key_metrics": metrics,
            "attention_items": attention_items,
            "anomalies": anomalies_list,
        }

    # ------------------------------------------------------------------
    # Email formatting
    # ------------------------------------------------------------------

    def _format_digest_email(self, role: str, content: dict[str, Any]) -> str:
        """Format digest as plain text email."""
        lines = [
            f"=== {content.get('headline', 'Daily Digest')} ===",
            "",
            content.get("summary", ""),
            "",
            "--- KEY METRICS ---",
        ]

        for m in content.get("key_metrics", []):
            change = f" ({m.get('change_label', '')})" if m.get("change_label") else ""
            lines.append(f"  {m['name']}: {m['value']}{change}")

        items = content.get("attention_items", [])
        if items:
            lines.append("")
            lines.append("--- NEEDS YOUR ATTENTION ---")
            for item in items:
                priority = f"[{item.get('priority', 'medium').upper()}]"
                lines.append(f"  {priority} {item['title']}")
                lines.append(f"    {item['description']}")

        anomalies = content.get("anomalies", [])
        if anomalies:
            lines.append("")
            lines.append("--- ANOMALIES DETECTED ---")
            for a in anomalies:
                lines.append(f"  [{a.get('severity', 'medium').upper()}] {a['description']}")

        return "\n".join(lines)

    def _format_digest_html(self, role: str, content: dict[str, Any]) -> str:
        """Format digest as HTML email."""
        role_title = ROLE_CONFIGS.get(role, {}).get("title", role)
        headline = content.get("headline", "Daily Digest")
        summary = content.get("summary", "")

        metrics_html = ""
        for m in content.get("key_metrics", []):
            change = f'<span style="color:#888;font-size:12px"> {m.get("change_label", "")}</span>' if m.get("change_label") else ""
            metrics_html += f'<div style="padding:8px 16px;background:#f8f9fa;margin:4px 0;border-radius:4px"><strong>{m["name"]}:</strong> {m["value"]}{change}</div>'

        items_html = ""
        for item in content.get("attention_items", []):
            color = {"high": "#dc3545", "medium": "#fd7e14", "low": "#28a745"}.get(item.get("priority", "medium"), "#fd7e14")
            items_html += f'<div style="padding:8px 16px;border-left:4px solid {color};margin:4px 0;background:#fff"><strong>{item["title"]}</strong><br><span style="color:#666">{item["description"]}</span></div>'

        anomalies_html = ""
        for a in content.get("anomalies", []):
            anomalies_html += f'<div style="padding:8px 16px;background:#fff3cd;margin:4px 0;border-radius:4px">⚠ {a["description"]}</div>'

        return f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto">
            <div style="background:#2c3e50;color:white;padding:20px;border-radius:8px 8px 0 0">
                <h2 style="margin:0">{headline}</h2>
                <p style="margin:4px 0 0;opacity:0.8">{role_title}</p>
            </div>
            <div style="padding:20px;background:#ffffff;border:1px solid #dee2e6">
                <p style="color:#333">{summary}</p>
                <h3 style="color:#2c3e50;border-bottom:2px solid #2c3e50;padding-bottom:4px">Key Metrics</h3>
                {metrics_html}
                {"<h3 style='color:#2c3e50;border-bottom:2px solid #2c3e50;padding-bottom:4px'>Needs Attention</h3>" + items_html if items_html else ""}
                {"<h3 style='color:#2c3e50;border-bottom:2px solid #2c3e50;padding-bottom:4px'>Anomalies</h3>" + anomalies_html if anomalies_html else ""}
            </div>
            <div style="padding:12px;text-align:center;color:#888;font-size:12px;border-radius:0 0 8px 8px;background:#f8f9fa">
                Generated by Smart Odoo AI Platform
            </div>
        </div>
        """


def _format_data_for_prompt(data: dict[str, Any]) -> str:
    """Format raw data dict into a readable string for the AI prompt."""
    import json
    clean = {k: v for k, v in data.items() if k != "role"}
    return json.dumps(clean, indent=2, default=str)
