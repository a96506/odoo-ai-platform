"""
AI Onboarding Assistant — contextual help and proactive tips.

Provides:
- Role-based tips for new users
- Contextual suggestions based on current activity
- Progressive disclosure of platform capabilities
- "What can I do?" command support
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger()

ROLE_TIPS: dict[str, list[dict[str, str]]] = {
    "cfo": [
        {
            "id": "cfo_cash_forecast",
            "title": "Cash Flow Forecasting",
            "tip": "Ask me 'Show me the 90-day cash flow forecast' to see predicted balances with confidence bands.",
            "category": "finance",
        },
        {
            "id": "cfo_month_end",
            "title": "Month-End Close Assistant",
            "tip": "Say 'Start month-end close for 2026-02' to run a full pre-close scan with issue classification.",
            "category": "finance",
        },
        {
            "id": "cfo_anomalies",
            "title": "Transaction Anomaly Detection",
            "tip": "I automatically check transactions using Benford's Law and Z-score analysis. Ask 'Show anomalies for last month'.",
            "category": "finance",
        },
        {
            "id": "cfo_ar_aging",
            "title": "AR Aging Analysis",
            "tip": "Ask 'Show me overdue invoices' or 'Which customers owe the most?' for instant AR insights.",
            "category": "finance",
        },
        {
            "id": "cfo_reports",
            "title": "Natural Language Reports",
            "tip": "Try 'Generate a report of all invoices over $10,000 this quarter' — I'll create it as a table, Excel, or PDF.",
            "category": "reporting",
        },
    ],
    "sales_manager": [
        {
            "id": "sales_pipeline",
            "title": "Pipeline Overview",
            "tip": "Ask 'Show me the sales pipeline' or 'Which deals are at risk?' for real-time pipeline intelligence.",
            "category": "sales",
        },
        {
            "id": "sales_leads",
            "title": "Lead Scoring",
            "tip": "I automatically score and prioritize new leads. Ask 'Show top leads' to see the highest-potential opportunities.",
            "category": "sales",
        },
        {
            "id": "sales_dedup",
            "title": "Duplicate Detection",
            "tip": "I watch for duplicate contacts and leads. Ask 'Check for duplicates' to run a scan.",
            "category": "data_quality",
        },
        {
            "id": "sales_credit",
            "title": "Credit Risk Alerts",
            "tip": "Before large orders, I check customer credit scores. Ask 'Show credit status for [customer]'.",
            "category": "risk",
        },
    ],
    "warehouse_manager": [
        {
            "id": "wh_stock_levels",
            "title": "Stock Level Monitoring",
            "tip": "Ask 'Which products are below reorder point?' to see items needing replenishment.",
            "category": "inventory",
        },
        {
            "id": "wh_supplier_risk",
            "title": "Supplier Risk Monitoring",
            "tip": "I score all your suppliers daily. Ask 'Show high-risk vendors' to see who needs attention.",
            "category": "supply_chain",
        },
        {
            "id": "wh_single_source",
            "title": "Single-Source Risk",
            "tip": "Ask 'Which products have only one supplier?' to identify supply chain vulnerabilities.",
            "category": "supply_chain",
        },
        {
            "id": "wh_deliveries",
            "title": "Delivery Tracking",
            "tip": "Ask 'Show pending deliveries' or 'Which suppliers are late?' for delivery intelligence.",
            "category": "logistics",
        },
    ],
    "general": [
        {
            "id": "gen_chat",
            "title": "Natural Language Interface",
            "tip": "You can ask me anything about your ERP data in plain English. Try 'How many invoices were created today?'",
            "category": "getting_started",
        },
        {
            "id": "gen_digest",
            "title": "Daily Digest",
            "tip": "I generate daily briefings for your role. Ask 'Show me today's digest' to see your personalized summary.",
            "category": "getting_started",
        },
        {
            "id": "gen_agents",
            "title": "AI Workflows",
            "tip": "I can run multi-step workflows autonomously. Try 'Process this invoice end-to-end' for the full procure-to-pay pipeline.",
            "category": "automation",
        },
        {
            "id": "gen_approvals",
            "title": "Approval Queue",
            "tip": "When I'm not confident enough to act alone, I'll ask for your approval. Check the approval queue regularly.",
            "category": "getting_started",
        },
    ],
}

CONTEXTUAL_SUGGESTIONS: dict[str, list[str]] = {
    "invoice_created": [
        "I can match this invoice to a purchase order automatically.",
        "Would you like me to check for vendor duplicates?",
        "I can run a credit check on this customer.",
    ],
    "lead_created": [
        "I've scored this lead and assigned a priority. Ask to see the details.",
        "I checked for duplicate contacts — none found." ,
        "Say 'Show similar leads' to see related opportunities.",
    ],
    "month_end": [
        "Ready for month-end? Ask me to 'Start pre-close scan' for a full check.",
        "I can identify all unreconciled transactions and stale drafts.",
        "Try 'Show month-end readiness score' for a quick status.",
    ],
    "low_stock": [
        "I detected low stock levels. Ask 'Show reorder suggestions' for recommended POs.",
        "I can check supplier risk scores before creating purchase orders.",
        "Say 'Find alternative suppliers for [product]' if your primary vendor is at risk.",
    ],
}

CAPABILITY_SUMMARY = """Here's what I can do for you:

**Data & Reporting**
- Search and read any data in your ERP (invoices, leads, orders, stock, HR, projects)
- Generate reports in natural language — just describe what you need
- Export to Excel or PDF

**Automations**
- Score and prioritize leads automatically
- Categorize transactions and reconcile bank statements
- Detect duplicate contacts, leads, and products
- Process vendor invoices end-to-end (extract → match PO → create bill)
- Monitor customer credit risk and enforce limits

**Intelligence**
- Daily briefings customized to your role (CFO, Sales, Warehouse)
- Cash flow forecasting with scenario planning
- Supplier risk scoring and disruption prediction
- Single-source supply risk identification
- Transaction anomaly detection (Benford's Law, Z-score)

**Workflows**
- Procure-to-Pay: invoice to payment in one autonomous workflow
- Collection: overdue invoice follow-up with escalation
- Month-End Close: continuous scanning with readiness scoring

Just ask in plain English — I'll figure out the right action!"""


def get_tips_for_role(role: str) -> list[dict[str, str]]:
    """Return onboarding tips for a given role, plus general tips."""
    tips = ROLE_TIPS.get(role, [])
    tips = tips + ROLE_TIPS.get("general", [])
    return tips


def get_contextual_suggestions(context: str) -> list[str]:
    """Return proactive suggestions for a given context."""
    return CONTEXTUAL_SUGGESTIONS.get(context, [])


def get_capability_summary() -> str:
    """Return a formatted summary of all platform capabilities."""
    return CAPABILITY_SUMMARY


def get_onboarding_prompt_injection(role: str) -> str:
    """Return a system prompt extension for onboarding-aware chat."""
    tips = get_tips_for_role(role)
    tip_text = "\n".join(f"- {t['title']}: {t['tip']}" for t in tips[:5])

    return (
        f"\n\nYou also serve as an onboarding assistant. The user's role is '{role}'. "
        f"When they seem new or ask 'what can you do', share relevant tips:\n{tip_text}\n"
        f"Be proactive but not overwhelming — share one tip per conversation turn."
    )
