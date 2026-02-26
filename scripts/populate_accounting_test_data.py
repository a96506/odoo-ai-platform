#!/usr/bin/env python3
"""
Populate Odoo with accounting test data for validating:
  1.1  Month-End Closing Assistant
  1.3  Enhanced Bank Reconciliation

Run AFTER populate_odoo_data.py and setup_chart_of_accounts.py.

What this script does:
  1. Posts some invoices & bills (so they appear as open receivables/payables)
  2. Leaves some invoices in draft (stale drafts for month-end scan)
  3. Validates outgoing deliveries (some SOs left uninvoiced)
  4. Validates incoming receipts (some POs left without bills)
  5. Creates bank statement lines with varied matching quality:
       - Exact reference match
       - Fuzzy / partial reference match
       - Amount with rounding difference
       - Partner match only (no ref)
       - No match at all
  6. Creates a depreciation journal entry in draft
  7. Creates a manual adjustment journal entry (posted)

After running: call POST /api/close/start {"period":"YYYY-MM"} and
POST /api/reconciliation/start {"journal_id": <bank_journal_id>}
to test both features.
"""

import ssl
import sys
import xmlrpc.client
import os
import random
from datetime import datetime, timedelta

ODOO_URL = os.getenv("ODOO_URL", "https://odoo-odoo18-7de73a-65-21-62-16.traefik.me")
ODOO_DB = os.getenv("ODOO_DB", "odoo_db")
ODOO_USER = os.getenv("ODOO_USERNAME", "alfailakawi1000@gmail.com")
ODOO_PASS = os.getenv("ODOO_PASSWORD", "Aniris123123*")
ODOO_API_KEY = os.getenv("ODOO_API_KEY", "6cdaae5e37b537999351554412cdafe94152b80f")
AUTH = ODOO_API_KEY or ODOO_PASS

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common", allow_none=True, context=ctx)
uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASS, {})
if not uid:
    print("ERROR: Authentication failed")
    sys.exit(1)

models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object", allow_none=True, context=ctx)
print(f"Authenticated as uid={uid}")


def x(model, method, *args, **kw):
    return models.execute_kw(ODOO_DB, uid, AUTH, model, method, list(args), kw)


def search(model, domain, **kw):
    return x(model, "search", domain, **kw)


def search_read(model, domain, fields=None, **kw):
    kw2 = {**kw}
    if fields:
        kw2["fields"] = fields
    return x(model, "search_read", domain, **kw2)


def create(model, vals):
    return x(model, "create", vals)


def write(model, ids, vals):
    return x(model, "write", ids, vals)


def search_count(model, domain):
    return x(model, "search_count", domain)


def today_str(offset_days=0):
    return (datetime.now() + timedelta(days=offset_days)).strftime("%Y-%m-%d")


# ── Prerequisites ─────────────────────────────────────────────────────────────

print("\n=== Prerequisites: ensuring accounting permissions & journal config ===")

# Grant full accounting features group to current user
acct_feature_groups = search("res.groups", [("full_name", "=", "Technical / Show Full Accounting Features")], limit=1)
if acct_feature_groups:
    write("res.users", [uid], {"groups_id": [(4, acct_feature_groups[0])]})
    print("  Added 'Show Full Accounting Features' group to user")

# Ensure bank journal has a suspense account (required for BSL creation in Odoo 18)
bank_journals_pre = search_read("account.journal", [("type", "=", "bank")],
                                fields=["id", "suspense_account_id"], limit=1)
if bank_journals_pre and not bank_journals_pre[0].get("suspense_account_id"):
    existing_susp = search("account.account", [("code", "=", "1015")], limit=1)
    if existing_susp:
        susp_id = existing_susp[0]
    else:
        susp_id = create("account.account", {
            "code": "1015",
            "name": "Bank Suspense Account",
            "account_type": "asset_current",
            "reconcile": True,
        })
    write("account.journal", [bank_journals_pre[0]["id"]], {"suspense_account_id": susp_id})

    profit_acct = search("account.account", [("code", "=", "4900")], limit=1)
    loss_acct = search("account.account", [("code", "=", "7100")], limit=1)
    updates = {}
    if profit_acct:
        updates["profit_account_id"] = profit_acct[0]
    if loss_acct:
        updates["loss_account_id"] = loss_acct[0]
    if updates:
        write("account.journal", [bank_journals_pre[0]["id"]], updates)
    print("  Configured suspense/profit/loss accounts on Bank journal")
else:
    print("  Bank journal already configured")


# ── Helpers ───────────────────────────────────────────────────────────────────

def safe_action(model, method, ids, label=""):
    """Call an Odoo action method, swallow already-done errors."""
    if not ids:
        return
    try:
        result = x(model, method, ids)
        if isinstance(result, dict) and result.get("res_model") == "confirm.stock.sms":
            # SMS confirmation wizard — skip SMS, validate by setting state directly
            write("stock.picking", ids, {"state": "done"})
            print(f"  {label} OK (SMS wizard bypassed)")
            return
        print(f"  {label} OK (ids={ids})")
    except Exception as e:
        msg = str(e)[:120]
        if "already" in msg.lower() or "nothing to" in msg.lower() or "posted" in msg.lower():
            print(f"  {label} — already done (ids={ids})")
        else:
            print(f"  {label} FAILED: {msg}")


# ═══════════════════════════════════════════════════════════════════════════════
# 1. POST SOME INVOICES (leave others as draft = stale drafts)
# ═══════════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 60)
print("  STEP 1: Post selected invoices & bills")
print("=" * 60)

all_invoices = search_read(
    "account.move",
    [("move_type", "=", "out_invoice"), ("state", "=", "draft")],
    fields=["id", "name", "ref", "partner_id", "amount_total"],
)
print(f"\n  Found {len(all_invoices)} draft customer invoices")

# Post the first batch, leave others as stale drafts for month-end scan
invoices_to_post = []
invoices_to_keep_draft = []
for inv in all_invoices:
    ref = inv.get("ref") or ""
    if ref in ("INV-GIG-2026-001", "INV-EQ-2026-001", "INV-AGI-2026-001", "INV-NBK-2026-001"):
        invoices_to_post.append(inv)
    else:
        invoices_to_keep_draft.append(inv)

for inv in invoices_to_post:
    safe_action("account.move", "action_post", [inv["id"]],
                f"Post invoice {inv.get('ref', inv['name'])}")

if invoices_to_keep_draft:
    print(f"\n  Keeping {len(invoices_to_keep_draft)} invoices as DRAFT (stale drafts for month-end scan):")
    for inv in invoices_to_keep_draft:
        partner = inv.get("partner_id", [0, "?"])
        pname = partner[1] if isinstance(partner, (list, tuple)) else partner
        print(f"    - {inv.get('ref', inv['name'])} | {pname} | ${inv.get('amount_total', 0):,.2f}")

all_bills = search_read(
    "account.move",
    [("move_type", "=", "in_invoice"), ("state", "=", "draft")],
    fields=["id", "name", "ref", "partner_id", "amount_total"],
)
print(f"\n  Found {len(all_bills)} draft vendor bills")

bills_to_post = []
bills_to_keep_draft = []
for bill in all_bills:
    ref = bill.get("ref") or ""
    if ref in ("BILL-DELL-2026-001", "BILL-SAM-2026-001", "BILL-CIS-2026-001"):
        bills_to_post.append(bill)
    else:
        bills_to_keep_draft.append(bill)

for bill in bills_to_post:
    safe_action("account.move", "action_post", [bill["id"]],
                f"Post bill {bill.get('ref', bill['name'])}")

if bills_to_keep_draft:
    print(f"\n  Keeping {len(bills_to_keep_draft)} bills as DRAFT:")
    for bill in bills_to_keep_draft:
        print(f"    - {bill.get('ref', bill['name'])} | ${bill.get('amount_total', 0):,.2f}")

# ═══════════════════════════════════════════════════════════════════════════════
# 2. VALIDATE STOCK PICKINGS (deliveries + receipts)
# ═══════════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 60)
print("  STEP 2: Validate deliveries and receipts")
print("=" * 60)

outgoing_pickings = search_read(
    "stock.picking",
    [("picking_type_code", "=", "outgoing"), ("state", "in", ["confirmed", "assigned", "waiting"])],
    fields=["id", "name", "partner_id", "origin", "state"],
)
print(f"\n  Found {len(outgoing_pickings)} pending outgoing deliveries")

# Validate first 3 deliveries (leave the rest as uninvoiced for month-end scan)
for pick in outgoing_pickings[:3]:
    try:
        move_lines = search_read(
            "stock.move",
            [("picking_id", "=", pick["id"]), ("state", "!=", "done")],
            fields=["id", "product_uom_qty"],
        )
        for ml in move_lines:
            write("stock.move", [ml["id"]], {"quantity": ml["product_uom_qty"]})

        result = x("stock.picking", "button_validate", [pick["id"]])

        if isinstance(result, dict) and result.get("res_model") == "confirm.stock.sms":
            write("stock.picking", [pick["id"]], {"state": "done"})
            for ml in move_lines:
                write("stock.move", [ml["id"]], {"state": "done"})
            print(f"  Validated delivery {pick['name']} (SMS wizard bypassed)")
        else:
            print(f"  Validated delivery {pick['name']}")
    except Exception as e:
        print(f"  Could not validate {pick['name']}: {str(e)[:100]}")

if len(outgoing_pickings) > 3:
    print(f"\n  Left {len(outgoing_pickings) - 3} deliveries unvalidated (unbilled deliveries for month-end)")

incoming_pickings = search_read(
    "stock.picking",
    [("picking_type_code", "=", "incoming"), ("state", "in", ["confirmed", "assigned", "waiting"])],
    fields=["id", "name", "partner_id", "origin", "state"],
)
print(f"\n  Found {len(incoming_pickings)} pending incoming receipts")

for pick in incoming_pickings[:3]:
    try:
        move_lines = search_read(
            "stock.move",
            [("picking_id", "=", pick["id"]), ("state", "!=", "done")],
            fields=["id", "product_uom_qty"],
        )
        for ml in move_lines:
            write("stock.move", [ml["id"]], {"quantity": ml["product_uom_qty"]})

        result = x("stock.picking", "button_validate", [pick["id"]])

        if isinstance(result, dict) and result.get("res_model") == "confirm.stock.sms":
            write("stock.picking", [pick["id"]], {"state": "done"})
            for ml in move_lines:
                write("stock.move", [ml["id"]], {"state": "done"})
            print(f"  Validated receipt {pick['name']} (SMS wizard bypassed)")
        else:
            print(f"  Validated receipt {pick['name']}")
    except Exception as e:
        print(f"  Could not validate {pick['name']}: {str(e)[:100]}")

if len(incoming_pickings) > 3:
    print(f"\n  Left {len(incoming_pickings) - 3} receipts unvalidated (missing vendor bills for month-end)")


# ═══════════════════════════════════════════════════════════════════════════════
# 3. CREATE BANK STATEMENT LINES (for reconciliation testing)
# ═══════════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 60)
print("  STEP 3: Create bank statement lines for reconciliation")
print("=" * 60)

# Find the bank journal
bank_journals = search_read(
    "account.journal",
    [("type", "=", "bank")],
    fields=["id", "name", "code"],
)
if not bank_journals:
    print("\n  ERROR: No bank journal found! Run setup_chart_of_accounts.py first.")
    sys.exit(1)

bank_journal = bank_journals[0]
BANK_JOURNAL_ID = bank_journal["id"]
print(f"\n  Using bank journal: {bank_journal['name']} [{bank_journal['code']}] (id={BANK_JOURNAL_ID})")

# Reload posted invoices and bills to get their amounts
posted_invoices = search_read(
    "account.move",
    [("move_type", "=", "out_invoice"), ("state", "=", "posted")],
    fields=["id", "name", "ref", "partner_id", "amount_total", "amount_residual"],
)
posted_bills = search_read(
    "account.move",
    [("move_type", "=", "in_invoice"), ("state", "=", "posted")],
    fields=["id", "name", "ref", "partner_id", "amount_total", "amount_residual"],
)

inv_map = {inv.get("ref", ""): inv for inv in posted_invoices if inv.get("ref")}
bill_map = {b.get("ref", ""): b for b in posted_bills if b.get("ref")}

print(f"  Posted invoices: {len(posted_invoices)}")
print(f"  Posted bills: {len(posted_bills)}")

# Check if bank statement lines already exist for this journal
existing_bsl = search_count(
    "account.bank.statement.line",
    [("journal_id", "=", BANK_JOURNAL_ID)],
)
if existing_bsl > 0:
    print(f"\n  {existing_bsl} bank statement lines already exist — skipping creation")
    print("  (Delete existing lines manually if you want to re-create them)")
else:
    # Build bank statement lines with varied matching quality
    bank_lines = []

    # --- 1. EXACT MATCH: ref matches INV-GIG-2026-001, exact amount ---
    gig_inv = inv_map.get("INV-GIG-2026-001")
    if gig_inv:
        partner_id = gig_inv["partner_id"][0] if isinstance(gig_inv["partner_id"], (list, tuple)) else gig_inv["partner_id"]
        bank_lines.append({
            "label": "Exact match — GIG payment",
            "vals": {
                "date": today_str(-5),
                "payment_ref": "INV-GIG-2026-001",
                "amount": gig_inv["amount_total"],
                "journal_id": BANK_JOURNAL_ID,
                "partner_id": partner_id,
            },
        })

    # --- 2. FUZZY MATCH: ref is close but not exact (EQUATE) ---
    eq_inv = inv_map.get("INV-EQ-2026-001")
    if eq_inv:
        partner_id = eq_inv["partner_id"][0] if isinstance(eq_inv["partner_id"], (list, tuple)) else eq_inv["partner_id"]
        bank_lines.append({
            "label": "Fuzzy ref match — EQUATE wire",
            "vals": {
                "date": today_str(-3),
                "payment_ref": "EQUATE PMT REF EQ-2026-001",
                "amount": eq_inv["amount_total"],
                "journal_id": BANK_JOURNAL_ID,
                "partner_id": partner_id,
            },
        })

    # --- 3. ROUNDING DIFFERENCE: amount off by $0.30 (Agility) ---
    agi_inv = inv_map.get("INV-AGI-2026-001")
    if agi_inv:
        partner_id = agi_inv["partner_id"][0] if isinstance(agi_inv["partner_id"], (list, tuple)) else agi_inv["partner_id"]
        bank_lines.append({
            "label": "Rounding difference — Agility payment",
            "vals": {
                "date": today_str(-7),
                "payment_ref": "INV-AGI-2026-001",
                "amount": agi_inv["amount_total"] - 0.30,
                "journal_id": BANK_JOURNAL_ID,
                "partner_id": partner_id,
            },
        })

    # --- 4. PARTNER ONLY: correct partner, no useful ref (NBK) ---
    nbk_inv = inv_map.get("INV-NBK-2026-001")
    if nbk_inv:
        partner_id = nbk_inv["partner_id"][0] if isinstance(nbk_inv["partner_id"], (list, tuple)) else nbk_inv["partner_id"]
        bank_lines.append({
            "label": "Partner match only — NBK wire transfer",
            "vals": {
                "date": today_str(-2),
                "payment_ref": "WIRE TRF 2026-02-24 NBK SHARQ",
                "amount": nbk_inv["amount_total"],
                "journal_id": BANK_JOURNAL_ID,
                "partner_id": partner_id,
            },
        })

    # --- 5. VENDOR PAYMENT: negative amount matching Dell bill ---
    dell_bill = bill_map.get("BILL-DELL-2026-001")
    if dell_bill:
        partner_id = dell_bill["partner_id"][0] if isinstance(dell_bill["partner_id"], (list, tuple)) else dell_bill["partner_id"]
        bank_lines.append({
            "label": "Vendor payment — Dell (outgoing)",
            "vals": {
                "date": today_str(-4),
                "payment_ref": "BILL-DELL-2026-001 PAYMENT",
                "amount": -dell_bill["amount_total"],
                "journal_id": BANK_JOURNAL_ID,
                "partner_id": partner_id,
            },
        })

    # --- 6. PARTIAL REF: Samsung bill, ref truncated ---
    sam_bill = bill_map.get("BILL-SAM-2026-001")
    if sam_bill:
        partner_id = sam_bill["partner_id"][0] if isinstance(sam_bill["partner_id"], (list, tuple)) else sam_bill["partner_id"]
        bank_lines.append({
            "label": "Partial ref — Samsung payment",
            "vals": {
                "date": today_str(-6),
                "payment_ref": "SAM-2026-001",
                "amount": -sam_bill["amount_total"],
                "journal_id": BANK_JOURNAL_ID,
                "partner_id": partner_id,
            },
        })

    # --- 7. NO MATCH: mystery incoming wire ---
    bank_lines.append({
        "label": "No match — mystery deposit",
        "vals": {
            "date": today_str(-8),
            "payment_ref": "INTL WIRE TRF 7743892 UNKNOWN SENDER",
            "amount": 4250.00,
            "journal_id": BANK_JOURNAL_ID,
        },
    })

    # --- 8. NO MATCH: ATM / cash withdrawal ---
    bank_lines.append({
        "label": "No match — ATM withdrawal",
        "vals": {
            "date": today_str(-1),
            "payment_ref": "ATM WITHDRAWAL SHUWAIKH BRANCH",
            "amount": -500.00,
            "journal_id": BANK_JOURNAL_ID,
        },
    })

    # --- 9. AMOUNT TOLERANCE: Cisco bill with 1.5% difference ---
    cis_bill = bill_map.get("BILL-CIS-2026-001")
    if cis_bill:
        partner_id = cis_bill["partner_id"][0] if isinstance(cis_bill["partner_id"], (list, tuple)) else cis_bill["partner_id"]
        adjusted = cis_bill["amount_total"] * 1.015  # 1.5% more (bank fees?)
        bank_lines.append({
            "label": "Amount tolerance — Cisco payment with bank fees",
            "vals": {
                "date": today_str(-3),
                "payment_ref": "BILL-CIS-2026-001",
                "amount": -adjusted,
                "journal_id": BANK_JOURNAL_ID,
                "partner_id": partner_id,
            },
        })

    # --- 10. SPLIT PAYMENT: partial payment of GIG invoice ---
    if gig_inv:
        partner_id = gig_inv["partner_id"][0] if isinstance(gig_inv["partner_id"], (list, tuple)) else gig_inv["partner_id"]
        bank_lines.append({
            "label": "Split payment — GIG partial (50%)",
            "vals": {
                "date": today_str(-10),
                "payment_ref": "GIG PARTIAL PMT 1 OF 2",
                "amount": round(gig_inv["amount_total"] / 2, 2),
                "journal_id": BANK_JOURNAL_ID,
                "partner_id": partner_id,
            },
        })

    print(f"\n  Creating {len(bank_lines)} bank statement lines:")
    for bl in bank_lines:
        try:
            bsl_id = create("account.bank.statement.line", bl["vals"])
            ref = bl["vals"].get("payment_ref", "")
            amt = bl["vals"].get("amount", 0)
            print(f"    [{bsl_id:>4}] {bl['label']}")
            print(f"           ref=\"{ref}\"  amount={amt:>12,.2f}")
        except Exception as e:
            print(f"    FAILED: {bl['label']} — {str(e)[:120]}")


# ═══════════════════════════════════════════════════════════════════════════════
# 4. CREATE DEPRECIATION ENTRY (draft — for month-end scan)
# ═══════════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 60)
print("  STEP 4: Create depreciation journal entry (draft)")
print("=" * 60)

misc_journals = search_read(
    "account.journal",
    [("type", "=", "general")],
    fields=["id", "name", "code"],
    limit=1,
)

depr_acct = search_read("account.account", [("code", "=", "6900")], fields=["id", "name"], limit=1)
fixed_acct = search_read("account.account", [("code", "=", "1600")], fields=["id", "name"], limit=1)

if misc_journals and depr_acct and fixed_acct:
    existing_depr = search(
        "account.move",
        [("ref", "=", "DEPRECIATION-2026-02"), ("state", "=", "draft")],
        limit=1,
    )
    if existing_depr:
        print(f"  Depreciation entry already exists (id={existing_depr[0]})")
    else:
        try:
            depr_id = create("account.move", {
                "journal_id": misc_journals[0]["id"],
                "date": today_str(-5),
                "ref": "DEPRECIATION-2026-02",
                "move_type": "entry",
                "line_ids": [
                    (0, 0, {
                        "name": "Monthly depreciation — Computer Equipment",
                        "account_id": depr_acct[0]["id"],
                        "debit": 3500.00,
                        "credit": 0,
                    }),
                    (0, 0, {
                        "name": "Monthly depreciation — Computer Equipment",
                        "account_id": fixed_acct[0]["id"],
                        "debit": 0,
                        "credit": 3500.00,
                    }),
                ],
            })
            print(f"  Created depreciation entry (DRAFT) id={depr_id} — $3,500.00")
        except Exception as e:
            print(f"  Failed to create depreciation entry: {str(e)[:120]}")
else:
    print("  Skipping — missing journal or accounts (run setup_chart_of_accounts.py first)")


# ═══════════════════════════════════════════════════════════════════════════════
# 5. CREATE MANUAL ADJUSTMENT ENTRY (posted — for month-end scan)
# ═══════════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 60)
print("  STEP 5: Create manual adjustment journal entry (posted)")
print("=" * 60)

accrual_acct = search_read("account.account", [("code", "=", "2100")], fields=["id", "name"], limit=1)
expense_acct = search_read("account.account", [("code", "=", "7100")], fields=["id", "name"], limit=1)

if misc_journals and accrual_acct and expense_acct:
    existing_adj = search(
        "account.move",
        [("ref", "=", "ADJ-2026-02-ACCRUAL")],
        limit=1,
    )
    if existing_adj:
        print(f"  Adjustment entry already exists (id={existing_adj[0]})")
    else:
        try:
            adj_id = create("account.move", {
                "journal_id": misc_journals[0]["id"],
                "date": today_str(-2),
                "ref": "ADJ-2026-02-ACCRUAL",
                "move_type": "entry",
                "line_ids": [
                    (0, 0, {
                        "name": "Accrued utilities — February estimate",
                        "account_id": expense_acct[0]["id"],
                        "debit": 2800.00,
                        "credit": 0,
                    }),
                    (0, 0, {
                        "name": "Accrued utilities — February estimate",
                        "account_id": accrual_acct[0]["id"],
                        "debit": 0,
                        "credit": 2800.00,
                    }),
                ],
            })
            print(f"  Created adjustment entry id={adj_id} — $2,800.00")

            safe_action("account.move", "action_post", [adj_id],
                        f"Posted adjustment ADJ-2026-02-ACCRUAL")
        except Exception as e:
            print(f"  Failed to create adjustment entry: {str(e)[:120]}")
else:
    print("  Skipping — missing journal or accounts")


# ═══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 60)
print("  SUMMARY")
print("=" * 60)

posted_inv_count = search_count("account.move", [("move_type", "=", "out_invoice"), ("state", "=", "posted")])
draft_inv_count = search_count("account.move", [("move_type", "=", "out_invoice"), ("state", "=", "draft")])
posted_bill_count = search_count("account.move", [("move_type", "=", "in_invoice"), ("state", "=", "posted")])
draft_bill_count = search_count("account.move", [("move_type", "=", "in_invoice"), ("state", "=", "draft")])
bsl_count = search_count("account.bank.statement.line", [("journal_id", "=", BANK_JOURNAL_ID)])
unrec_bsl = search_count("account.bank.statement.line", [("journal_id", "=", BANK_JOURNAL_ID), ("is_reconciled", "=", False)])
done_out = search_count("stock.picking", [("picking_type_code", "=", "outgoing"), ("state", "=", "done")])
done_in = search_count("stock.picking", [("picking_type_code", "=", "incoming"), ("state", "=", "done")])
depr_count = search_count("account.move", [("ref", "like", "DEPRECIATION"), ("state", "=", "draft")])
adj_count = search_count("account.move", [("move_type", "=", "entry"), ("state", "=", "posted")])

current_month = datetime.now().strftime("%Y-%m")

print(f"""
  Customer Invoices (posted):     {posted_inv_count}
  Customer Invoices (draft/stale): {draft_inv_count}
  Vendor Bills (posted):          {posted_bill_count}
  Vendor Bills (draft):           {draft_bill_count}
  Bank Statement Lines:           {bsl_count}
  Bank Lines (unreconciled):      {unrec_bsl}
  Deliveries validated (done):    {done_out}
  Receipts validated (done):      {done_in}
  Depreciation entries (draft):   {depr_count}
  Journal adjustments (posted):   {adj_count}

  Bank Journal ID: {BANK_JOURNAL_ID}
  Current period:  {current_month}
""")

print("=" * 60)
print("  TEST COMMANDS")
print("=" * 60)
print(f"""
  1. Month-End Closing:
     curl -X POST https://odoo-ai-api-65-21-62-16.traefik.me/api/close/start \\
       -H "Content-Type: application/json" \\
       -H "X-API-Key: <your-api-key>" \\
       -d '{{"period": "{current_month}"}}'

  2. Bank Reconciliation:
     curl -X POST https://odoo-ai-api-65-21-62-16.traefik.me/api/reconciliation/start \\
       -H "Content-Type: application/json" \\
       -H "X-API-Key: <your-api-key>" \\
       -d '{{"journal_id": {BANK_JOURNAL_ID}}}'

  3. Check closing status:
     curl https://odoo-ai-api-65-21-62-16.traefik.me/api/close/{current_month}/status \\
       -H "X-API-Key: <your-api-key>"
""")

print("Done! Your Odoo instance now has realistic accounting data")
print("for testing Month-End Closing and Bank Reconciliation.\n")
