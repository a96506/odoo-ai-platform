#!/usr/bin/env python3
"""
Setup script: connects to Odoo and verifies the AI Bridge module is installed,
configures the webhook URL + secret, and runs a connectivity test.

Usage:
    python3 scripts/setup_odoo_webhooks.py

Environment variables (or set in .env):
    ODOO_URL          – Odoo base URL  (default: http://localhost:8069)
    ODOO_DB           – Odoo database  (default: odoo)
    ODOO_USERNAME     – Odoo user      (default: admin)
    ODOO_PASSWORD     – Odoo password  (default: admin)
    AI_SERVICE_URL    – AI service URL reachable from Odoo  (default: http://ai-service:8000)
    WEBHOOK_SECRET    – Shared HMAC secret for webhook signatures
"""

import os
import sys
import xmlrpc.client
import urllib.request
import json

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ODOO_URL = os.getenv("ODOO_URL", "http://localhost:8069")
ODOO_DB = os.getenv("ODOO_DB", "odoo")
ODOO_USER = os.getenv("ODOO_USERNAME", "admin")
ODOO_PASS = os.getenv("ODOO_PASSWORD", "admin")
AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://ai-service:8000")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")

SEPARATOR = "-" * 55


def check_ai_service():
    """Verify the AI Service is reachable from this machine."""
    local_url = AI_SERVICE_URL.replace("ai-service", "localhost")
    print(f"\n{SEPARATOR}")
    print("Step 0: Checking AI Service health")
    print(SEPARATOR)
    try:
        req = urllib.request.urlopen(f"{local_url}/health", timeout=10)
        health = json.loads(req.read().decode())
        status = health.get("status", "unknown")
        print(f"  AI Service status: {status}")
        print(f"  Odoo connected:    {health.get('odoo_connected', '?')}")
        print(f"  Redis connected:   {health.get('redis_connected', '?')}")
        print(f"  DB connected:      {health.get('db_connected', '?')}")
        if status != "healthy":
            print("  WARNING: Service is not fully healthy — some connections may fail")
        return True
    except Exception as e:
        print(f"  WARNING: Cannot reach AI Service at {local_url}: {e}")
        print("  (This is OK if running inside Docker — Odoo connects via internal network)")
        return False


def connect_odoo():
    """Authenticate with Odoo and return (uid, models proxy)."""
    print(f"\n{SEPARATOR}")
    print("Step 1: Connecting to Odoo")
    print(SEPARATOR)
    print(f"  URL:      {ODOO_URL}")
    print(f"  Database: {ODOO_DB}")
    print(f"  User:     {ODOO_USER}")

    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")

    try:
        version = common.version()
        print(f"  Odoo version: {version.get('server_version', 'unknown')}")
    except Exception as e:
        print(f"\n  ERROR: Cannot connect to Odoo at {ODOO_URL}")
        print(f"  Detail: {e}")
        sys.exit(1)

    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASS, {})
    if not uid:
        print("\n  ERROR: Authentication failed — check credentials")
        sys.exit(1)

    print(f"  Authenticated as UID {uid}")
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
    return uid, models


def check_module(uid, models):
    """Verify odoo_ai_bridge module is installed."""
    print(f"\n{SEPARATOR}")
    print("Step 2: Checking AI Bridge module")
    print(SEPARATOR)

    module = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "ir.module.module", "search_read",
        [[("name", "=", "odoo_ai_bridge")]],
        {"fields": ["name", "state"], "limit": 1},
    )

    if not module:
        print("  Module NOT FOUND in Odoo.")
        print("\n  To install:")
        print("    1. Copy the odoo_ai_bridge/ folder into your Odoo addons path")
        print("    2. Restart Odoo")
        print("    3. Go to Settings > Apps > Update Apps List")
        print("    4. Search for 'AI Bridge' and click Install")
        print("    5. Re-run this script")
        sys.exit(1)

    state = module[0].get("state", "uninstalled")
    if state != "installed":
        print(f"  Module found but state is '{state}' (expected 'installed')")
        print("  Please install it from Settings > Apps")
        sys.exit(1)

    print("  AI Bridge module: INSTALLED")


def configure_webhook(uid, models):
    """Set the AI service URL and webhook secret in Odoo's ai.config."""
    print(f"\n{SEPARATOR}")
    print("Step 3: Configuring webhook endpoint")
    print(SEPARATOR)
    print(f"  AI Service URL: {AI_SERVICE_URL}")
    print(f"  Webhook secret: {'***' + WEBHOOK_SECRET[-4:] if len(WEBHOOK_SECRET) > 4 else '(not set)'}")

    config = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "ai.config", "search_read",
        [[]],
        {"fields": ["ai_service_url", "webhook_secret", "enabled"], "limit": 1},
    )

    write_vals = {
        "ai_service_url": AI_SERVICE_URL,
        "enabled": True,
    }
    if WEBHOOK_SECRET:
        write_vals["webhook_secret"] = WEBHOOK_SECRET

    if config:
        cfg = config[0]
        current_url = cfg.get("ai_service_url", "")
        print(f"  Current URL in Odoo: {current_url or '(empty)'}")

        if current_url == AI_SERVICE_URL:
            print("  URL already correct — no update needed")
        else:
            models.execute_kw(
                ODOO_DB, uid, ODOO_PASS,
                "ai.config", "write",
                [[cfg["id"]], write_vals],
            )
            print("  Configuration updated")
    else:
        print("  No configuration record found — creating one...")
        models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            "ai.config", "create",
            [write_vals],
        )
        print("  Configuration created")


def list_enabled_modules(uid, models):
    """Show which Odoo models have AI webhooks active."""
    print(f"\n{SEPARATOR}")
    print("Step 4: Webhook-enabled models")
    print(SEPARATOR)

    target_models = [
        ("account.move", "Accounting (Invoices/Bills)"),
        ("crm.lead", "CRM (Leads/Opportunities)"),
        ("sale.order", "Sales (Quotations/Orders)"),
        ("purchase.order", "Purchase (Purchase Orders)"),
        ("stock.picking", "Inventory (Transfers)"),
        ("hr.leave", "HR (Leave Requests)"),
        ("hr.expense", "HR (Expenses)"),
        ("project.task", "Project (Tasks)"),
        ("helpdesk.ticket", "Helpdesk (Tickets)"),
        ("mrp.production", "Manufacturing (Production Orders)"),
        ("mailing.mailing", "Marketing (Campaigns)"),
    ]

    for model_name, label in target_models:
        try:
            models.execute_kw(
                ODOO_DB, uid, ODOO_PASS,
                model_name, "search_count", [[]],
            )
            print(f"  {label:42s} — available")
        except Exception:
            print(f"  {label:42s} — not available (module not installed)")


def main():
    print("=" * 55)
    print("  Odoo AI Bridge — Setup & Configuration")
    print("=" * 55)

    check_ai_service()
    uid, models = connect_odoo()
    check_module(uid, models)
    configure_webhook(uid, models)
    list_enabled_modules(uid, models)

    print(f"\n{SEPARATOR}")
    print("  Setup Complete")
    print(SEPARATOR)
    print()
    print("  The AI Bridge module will now send webhooks to the")
    print(f"  AI Service at {AI_SERVICE_URL} on create/update/delete")
    print("  of records in all enabled modules.")
    print()
    print("  Optional: run the rule seeder to populate automation rules:")
    print("    python3 scripts/seed_automation_rules.py")
    print()


if __name__ == "__main__":
    main()
