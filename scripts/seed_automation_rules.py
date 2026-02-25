#!/usr/bin/env python3
"""
Seed default automation rules into the AI Service via its REST API.
Skips seeding if rules already exist.

Usage:
    python3 scripts/seed_automation_rules.py

Environment variables:
    AI_SERVICE_URL  – AI service base URL (default: http://localhost:8000)
"""

import os
import sys

try:
    import httpx
except ImportError:
    print("ERROR: httpx is required. Install it:  pip install httpx")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://localhost:8000")

DEFAULT_RULES = [
    # --- Accounting ---
    {
        "name": "Auto-categorize bank transactions",
        "automation_type": "accounting",
        "action_name": "categorize_transaction",
        "enabled": True,
        "confidence_threshold": 0.85,
        "auto_approve": True,
        "auto_approve_threshold": 0.95,
    },
    {
        "name": "Auto-reconcile bank statements",
        "automation_type": "accounting",
        "action_name": "reconcile_transaction",
        "enabled": True,
        "confidence_threshold": 0.85,
        "auto_approve": False,
        "auto_approve_threshold": 0.95,
    },
    {
        "name": "Flag anomalous transactions",
        "automation_type": "accounting",
        "action_name": "flag_anomaly",
        "enabled": True,
        "confidence_threshold": 0.80,
        "auto_approve": False,
        "auto_approve_threshold": 0.95,
    },

    # --- CRM ---
    {
        "name": "AI lead scoring",
        "automation_type": "crm",
        "action_name": "score_lead",
        "enabled": True,
        "confidence_threshold": 0.80,
        "auto_approve": True,
        "auto_approve_threshold": 0.90,
    },
    {
        "name": "Auto-assign leads to sales reps",
        "automation_type": "crm",
        "action_name": "assign_lead",
        "enabled": True,
        "confidence_threshold": 0.85,
        "auto_approve": True,
        "auto_approve_threshold": 0.95,
    },
    {
        "name": "Generate follow-up emails",
        "automation_type": "crm",
        "action_name": "generate_followup",
        "enabled": True,
        "confidence_threshold": 0.85,
        "auto_approve": False,
        "auto_approve_threshold": 0.98,
    },
    {
        "name": "Detect duplicate leads",
        "automation_type": "crm",
        "action_name": "detect_duplicates",
        "enabled": True,
        "confidence_threshold": 0.80,
        "auto_approve": False,
        "auto_approve_threshold": 0.98,
    },

    # --- Sales ---
    {
        "name": "Generate quotations from requirements",
        "automation_type": "sales",
        "action_name": "generate_quotation",
        "enabled": True,
        "confidence_threshold": 0.85,
        "auto_approve": False,
        "auto_approve_threshold": 0.95,
    },
    {
        "name": "Optimize pricing strategies",
        "automation_type": "sales",
        "action_name": "optimize_pricing",
        "enabled": True,
        "confidence_threshold": 0.85,
        "auto_approve": False,
        "auto_approve_threshold": 0.95,
    },
    {
        "name": "Forecast sales pipeline",
        "automation_type": "sales",
        "action_name": "forecast_pipeline",
        "enabled": True,
        "confidence_threshold": 0.80,
        "auto_approve": True,
        "auto_approve_threshold": 0.90,
    },

    # --- Purchase ---
    {
        "name": "Auto-create purchase orders",
        "automation_type": "purchase",
        "action_name": "auto_create_po",
        "enabled": True,
        "confidence_threshold": 0.85,
        "auto_approve": False,
        "auto_approve_threshold": 0.95,
    },
    {
        "name": "Select best vendor",
        "automation_type": "purchase",
        "action_name": "select_vendor",
        "enabled": True,
        "confidence_threshold": 0.85,
        "auto_approve": False,
        "auto_approve_threshold": 0.95,
    },
    {
        "name": "Match vendor bills to POs",
        "automation_type": "purchase",
        "action_name": "match_bills",
        "enabled": True,
        "confidence_threshold": 0.85,
        "auto_approve": False,
        "auto_approve_threshold": 0.95,
    },

    # --- Inventory ---
    {
        "name": "Demand forecasting",
        "automation_type": "inventory",
        "action_name": "forecast_demand",
        "enabled": True,
        "confidence_threshold": 0.80,
        "auto_approve": True,
        "auto_approve_threshold": 0.90,
    },
    {
        "name": "Auto-reorder stock",
        "automation_type": "inventory",
        "action_name": "auto_reorder",
        "enabled": True,
        "confidence_threshold": 0.85,
        "auto_approve": False,
        "auto_approve_threshold": 0.95,
    },
    {
        "name": "Categorize products",
        "automation_type": "inventory",
        "action_name": "categorize_products",
        "enabled": True,
        "confidence_threshold": 0.85,
        "auto_approve": True,
        "auto_approve_threshold": 0.95,
    },

    # --- HR ---
    {
        "name": "Auto-approve leave requests",
        "automation_type": "hr",
        "action_name": "approve_leave",
        "enabled": True,
        "confidence_threshold": 0.90,
        "auto_approve": False,
        "auto_approve_threshold": 0.98,
    },
    {
        "name": "Process employee expenses",
        "automation_type": "hr",
        "action_name": "process_expense",
        "enabled": True,
        "confidence_threshold": 0.85,
        "auto_approve": False,
        "auto_approve_threshold": 0.95,
    },

    # --- Project ---
    {
        "name": "Auto-assign tasks to team members",
        "automation_type": "project",
        "action_name": "assign_task",
        "enabled": True,
        "confidence_threshold": 0.85,
        "auto_approve": True,
        "auto_approve_threshold": 0.95,
    },
    {
        "name": "Estimate task duration",
        "automation_type": "project",
        "action_name": "estimate_duration",
        "enabled": True,
        "confidence_threshold": 0.80,
        "auto_approve": True,
        "auto_approve_threshold": 0.90,
    },

    # --- Helpdesk ---
    {
        "name": "Categorize support tickets",
        "automation_type": "helpdesk",
        "action_name": "categorize_ticket",
        "enabled": True,
        "confidence_threshold": 0.85,
        "auto_approve": True,
        "auto_approve_threshold": 0.95,
    },
    {
        "name": "Auto-assign tickets to agents",
        "automation_type": "helpdesk",
        "action_name": "assign_ticket",
        "enabled": True,
        "confidence_threshold": 0.85,
        "auto_approve": True,
        "auto_approve_threshold": 0.95,
    },

    # --- Manufacturing ---
    {
        "name": "Optimize production scheduling",
        "automation_type": "manufacturing",
        "action_name": "schedule_production",
        "enabled": True,
        "confidence_threshold": 0.85,
        "auto_approve": False,
        "auto_approve_threshold": 0.95,
    },

    # --- Marketing ---
    {
        "name": "Segment contacts for campaigns",
        "automation_type": "marketing",
        "action_name": "segment_contacts",
        "enabled": True,
        "confidence_threshold": 0.80,
        "auto_approve": True,
        "auto_approve_threshold": 0.90,
    },
]


def main():
    print("=" * 50)
    print("  Seed Automation Rules")
    print("=" * 50)
    print(f"\n  AI Service: {AI_SERVICE_URL}")

    # Health check
    print("\n  Checking AI Service health...")
    try:
        resp = httpx.get(f"{AI_SERVICE_URL}/health", timeout=10)
        resp.raise_for_status()
        health = resp.json()
        print(f"  Status: {health.get('status', 'unknown')}")
    except httpx.ConnectError:
        print(f"\n  ERROR: Cannot connect to AI Service at {AI_SERVICE_URL}")
        print("  Make sure the service is running (./scripts/deploy.sh)")
        sys.exit(1)
    except Exception as e:
        print(f"\n  ERROR: Health check failed: {e}")
        sys.exit(1)

    # Check existing rules
    try:
        existing = httpx.get(f"{AI_SERVICE_URL}/api/rules", timeout=10).json()
    except Exception:
        existing = []

    if existing:
        print(f"\n  Found {len(existing)} existing rules:")
        for r in existing:
            status = "enabled" if r.get("enabled") else "disabled"
            print(f"    - {r['name']} ({r['automation_type']}/{r['action_name']}) [{status}]")
        print(f"\n  Skipping seed — rules already exist.")
        print("  To re-seed, delete existing rules first via the Dashboard or API.")
        return

    # Seed rules
    print(f"\n  Seeding {len(DEFAULT_RULES)} automation rules...\n")
    success = 0
    failed = 0

    for rule in DEFAULT_RULES:
        try:
            resp = httpx.post(
                f"{AI_SERVICE_URL}/api/rules",
                json=rule,
                timeout=10,
            )
            if resp.status_code == 200:
                print(f"    + {rule['name']}")
                success += 1
            else:
                print(f"    x {rule['name']} — HTTP {resp.status_code}: {resp.text[:100]}")
                failed += 1
        except Exception as e:
            print(f"    x {rule['name']} — {e}")
            failed += 1

    print(f"\n  Done: {success} created, {failed} failed")
    if failed == 0:
        print("  All automation rules seeded successfully!")


if __name__ == "__main__":
    main()
