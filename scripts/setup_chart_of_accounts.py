#!/usr/bin/env python3
"""
Set up a full chart of accounts for Al Rawabi Group via XML-RPC,
then create invoices and vendor bills.
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
    print("ERROR: Authentication failed"); sys.exit(1)
models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object", allow_none=True, context=ctx)
print(f"Authenticated uid={uid}")


def x(model, method, *args, **kw):
    return models.execute_kw(ODOO_DB, uid, AUTH, model, method, list(args), kw)

def search(model, domain, **kw):
    return x(model, "search", domain, **kw)

def search_read(model, domain, fields=None, **kw):
    kw2 = {**kw}
    if fields: kw2["fields"] = fields
    return x(model, "search_read", domain, **kw2)

def create(model, vals):
    return x(model, "create", vals)

def write(model, ids, vals):
    return x(model, "write", ids, vals)

def find_or_create(model, domain, vals):
    ids = search(model, domain, limit=1)
    if ids: return ids[0]
    return create(model, vals)

def today_str(offset_days=0):
    return (datetime.now() + timedelta(days=offset_days)).strftime("%Y-%m-%d")


company = search_read("res.company", [], fields=["id", "name", "currency_id"], limit=1)[0]
COMPANY_ID = company["id"]
CURRENCY_ID = company["currency_id"][0] if company.get("currency_id") else False
print(f"Company: {company['name']} (id={COMPANY_ID})")

# ── 1. Create Chart of Accounts ──────────────────────────────────────────────

print("\n=== Creating Chart of Accounts ===")

# Odoo 18 account types (account_type field values):
# asset_receivable, asset_cash, asset_current, asset_non_current, asset_prepayments, asset_fixed
# liability_payable, liability_credit_card, liability_current, liability_non_current
# equity, equity_unaffected
# income, income_other
# expense, expense_depreciation, expense_direct_cost
# off_balance

accounts_spec = [
    # Assets
    ("1000", "Cash", "asset_cash"),
    ("1010", "Bank – Main Account", "asset_cash"),
    ("1020", "Bank – Payroll Account", "asset_cash"),
    ("1100", "Accounts Receivable", "asset_receivable"),
    ("1200", "Inventory", "asset_current"),
    ("1210", "Goods in Transit", "asset_current"),
    ("1300", "Prepaid Expenses", "asset_prepayments"),
    ("1400", "VAT Receivable", "asset_current"),
    ("1500", "Office Equipment", "asset_fixed"),
    ("1510", "Vehicles", "asset_fixed"),
    ("1520", "Computer Equipment", "asset_fixed"),
    ("1600", "Accumulated Depreciation", "asset_fixed"),
    # Liabilities
    ("2000", "Accounts Payable", "liability_payable"),
    ("2100", "Accrued Expenses", "liability_current"),
    ("2200", "VAT Payable", "liability_current"),
    ("2300", "Employee Benefits Payable", "liability_current"),
    ("2400", "Short-term Loans", "liability_current"),
    ("2500", "Long-term Loans", "liability_non_current"),
    # Equity
    ("3000", "Share Capital", "equity"),
    ("3100", "Retained Earnings", "equity"),
    ("3200", "Current Year Earnings", "equity_unaffected"),
    # Income
    ("4000", "Product Sales Revenue", "income"),
    ("4100", "Service Revenue", "income"),
    ("4200", "Installation Revenue", "income"),
    ("4300", "Maintenance Contract Revenue", "income"),
    ("4900", "Other Income", "income_other"),
    # Expenses
    ("5000", "Cost of Goods Sold", "expense_direct_cost"),
    ("5100", "Freight & Shipping", "expense_direct_cost"),
    ("5200", "Installation Costs", "expense_direct_cost"),
    ("6000", "Salaries & Wages", "expense"),
    ("6100", "Employee Benefits", "expense"),
    ("6200", "Rent Expense", "expense"),
    ("6300", "Utilities", "expense"),
    ("6400", "Office Supplies", "expense"),
    ("6500", "Marketing & Advertising", "expense"),
    ("6600", "Travel & Entertainment", "expense"),
    ("6700", "Insurance", "expense"),
    ("6800", "Professional Fees", "expense"),
    ("6900", "Depreciation Expense", "expense_depreciation"),
    ("7000", "Bank Charges", "expense"),
    ("7100", "Miscellaneous Expense", "expense"),
]

acct_ids = {}
for code, name, acct_type in accounts_spec:
    vals = {
        "code": code,
        "name": name,
        "account_type": acct_type,
        "reconcile": acct_type in ("asset_receivable", "liability_payable"),
    }
    aid = find_or_create("account.account", [("code", "=", code)], vals)
    acct_ids[code] = aid
    print(f"  [{code}] {name} ({acct_type}) -> id={aid}")

# ── 2. Configure Journals ────────────────────────────────────────────────────

print("\n=== Configuring Journals ===")

# Delete and recreate journals with proper accounts
existing_journals = search_read("account.journal", [], fields=["id", "name", "type", "code"])
for ej in existing_journals:
    try:
        x("account.journal", "unlink", [ej["id"]])
        print(f"  Removed old journal: {ej['name']}")
    except Exception as e:
        print(f"  Could not remove {ej['name']}: {str(e)[:80]}")

journal_specs = [
    ("Customer Invoices", "sale", "INV", "4000", None),
    ("Vendor Bills", "purchase", "BILL", None, "5000"),
    ("Bank", "bank", "BNK", "1010", None),
    ("Cash", "cash", "CSH", "1000", None),
    ("Miscellaneous", "general", "MISC", None, None),
    ("Exchange Difference", "general", "EXCH", None, None),
]

journal_ids = {}
for jname, jtype, jcode, debit_acct, credit_acct in journal_specs:
    vals = {
        "name": jname,
        "type": jtype,
        "code": jcode,
    }
    if debit_acct and acct_ids.get(debit_acct):
        vals["default_account_id"] = acct_ids[debit_acct]
    if credit_acct and acct_ids.get(credit_acct):
        vals["default_account_id"] = acct_ids[credit_acct]
    
    jid = find_or_create("account.journal", [("code", "=", jcode)], vals)
    journal_ids[jtype] = jid
    print(f"  Journal: {jname} [{jcode}] (type={jtype}, id={jid})")

# ── 3. Set default accounts on product categories ────────────────────────────

print("\n=== Setting Product Category Accounts ===")

income_acct = acct_ids.get("4000")
expense_acct = acct_ids.get("5000")

all_cats = search_read("product.category", [], fields=["id", "name"])
for cat in all_cats:
    try:
        write("product.category", [cat["id"]], {
            "property_account_income_categ_id": income_acct,
            "property_account_expense_categ_id": expense_acct,
        })
        print(f"  Category '{cat['name']}' -> income={income_acct}, expense={expense_acct}")
    except Exception as e:
        print(f"  Could not update '{cat['name']}': {str(e)[:80]}")

# ── 4. Set company default accounts ──────────────────────────────────────────

print("\n=== Setting Company Defaults ===")

try:
    write("res.company", [COMPANY_ID], {
        "account_journal_payment_debit_account_id": acct_ids.get("1010"),
        "account_journal_payment_credit_account_id": acct_ids.get("1010"),
    })
    print("  Company payment accounts set")
except Exception as e:
    print(f"  Company defaults: {str(e)[:100]}")

# Set default receivable/payable on partner
try:
    partners = search("res.partner", [], limit=50)
    write("res.partner", partners, {
        "property_account_receivable_id": acct_ids.get("1100"),
        "property_account_payable_id": acct_ids.get("2000"),
    })
    print(f"  Set default AR/AP accounts on {len(partners)} partners")
except Exception as e:
    print(f"  Partner defaults: {str(e)[:100]}")

# ── 5. Create Customer Invoices ──────────────────────────────────────────────

print("\n=== Creating Customer Invoices ===")

product_variants = search_read("product.product", [("default_code", "like", "ARG-")], fields=["id", "name", "default_code"])
pv_map = {p["default_code"]: p for p in product_variants}

customers = {p["name"]: p["id"] for p in search_read("res.partner", [("customer_rank", ">", 0), ("is_company", "=", True)], fields=["id", "name"])}
vendors = {p["name"]: p["id"] for p in search_read("res.partner", [("supplier_rank", ">", 0), ("is_company", "=", True)], fields=["id", "name"])}

sale_journal = journal_ids.get("sale")

invoice_data = [
    {"partner": "Gulf Insurance Group", "lines": [("ARG-1001", 120, 1249.00), ("ARG-8001", 10, 449.00)], "ref": "INV-GIG-2026-001"},
    {"partner": "EQUATE Petrochemical", "lines": [("ARG-9002", 2, 2400.00), ("ARG-9001", 1, 5000.00)], "ref": "INV-EQ-2026-001"},
    {"partner": "Alghanim Industries", "lines": [("ARG-7001", 20, 1395.00), ("ARG-7002", 15, 549.00)], "ref": "INV-ALG-2026-001"},
    {"partner": "KIPCO Group", "lines": [("ARG-7001", 10, 1395.00), ("ARG-7003", 30, 449.00), ("ARG-7004", 2, 2200.00)], "ref": "INV-KIP-2026-001"},
    {"partner": "Agility Logistics", "lines": [("ARG-3001", 4, 3200.00), ("ARG-3003", 20, 189.00)], "ref": "INV-AGI-2026-001"},
    {"partner": "National Bank of Kuwait", "lines": [("ARG-6001", 48, 1450.00), ("ARG-9004", 48, 800.00)], "ref": "INV-NBK-2026-001"},
]

for inv in invoice_data:
    partner_id = customers.get(inv["partner"])
    if not partner_id:
        continue
    existing = search("account.move", [("ref", "=", inv["ref"])], limit=1)
    if existing:
        print(f"  {inv['ref']} exists (id={existing[0]})")
        continue

    inv_lines = []
    for code, qty, price in inv["lines"]:
        pv = pv_map.get(code)
        if not pv:
            continue
        inv_lines.append((0, 0, {
            "product_id": pv["id"],
            "quantity": qty,
            "price_unit": price,
            "account_id": income_acct,
        }))

    vals = {
        "partner_id": partner_id,
        "move_type": "out_invoice",
        "invoice_line_ids": inv_lines,
        "ref": inv["ref"],
        "invoice_date": today_str(random.randint(-20, -1)),
    }
    if sale_journal:
        vals["journal_id"] = sale_journal

    try:
        inv_id = create("account.move", vals)
        print(f"  Invoice: {inv['ref']} for {inv['partner']} (id={inv_id})")
    except Exception as e:
        print(f"  Error {inv['ref']}: {str(e)[:120]}")

# ── 6. Create Vendor Bills ───────────────────────────────────────────────────

print("\n=== Creating Vendor Bills ===")

purchase_journal = journal_ids.get("purchase")

bill_data = [
    {"vendor": "Dell Technologies EMEA", "lines": [("ARG-1001", 150, 890.00)], "ref": "BILL-DELL-2026-001"},
    {"vendor": "Daikin Middle East & Africa", "lines": [("ARG-6001", 60, 980.00), ("ARG-6002", 10, 3200.00)], "ref": "BILL-DAI-2026-001"},
    {"vendor": "Samsung Gulf Electronics", "lines": [("ARG-2001", 100, 850.00), ("ARG-2004", 60, 610.00)], "ref": "BILL-SAM-2026-001"},
    {"vendor": "Cisco Systems Kuwait", "lines": [("ARG-3001", 15, 2400.00), ("ARG-3004", 10, 650.00)], "ref": "BILL-CIS-2026-001"},
    {"vendor": "Apple MEA Distribution", "lines": [("ARG-1004", 40, 1050.00), ("ARG-2002", 50, 1100.00)], "ref": "BILL-APL-2026-001"},
]

for bill in bill_data:
    vendor_id = vendors.get(bill["vendor"])
    if not vendor_id:
        continue
    existing = search("account.move", [("ref", "=", bill["ref"])], limit=1)
    if existing:
        print(f"  {bill['ref']} exists (id={existing[0]})")
        continue

    bill_lines = []
    for code, qty, price in bill["lines"]:
        pv = pv_map.get(code)
        if not pv:
            continue
        bill_lines.append((0, 0, {
            "product_id": pv["id"],
            "quantity": qty,
            "price_unit": price,
            "account_id": expense_acct,
        }))

    vals = {
        "partner_id": vendor_id,
        "move_type": "in_invoice",
        "invoice_line_ids": bill_lines,
        "ref": bill["ref"],
        "invoice_date": today_str(random.randint(-30, -5)),
    }
    if purchase_journal:
        vals["journal_id"] = purchase_journal

    try:
        bill_id = create("account.move", vals)
        print(f"  Bill: {bill['ref']} from {bill['vendor']} (id={bill_id})")
    except Exception as e:
        print(f"  Error {bill['ref']}: {str(e)[:120]}")

# ── Final Summary ────────────────────────────────────────────────────────────

print("\n=== Final Summary ===")
print(f"  Accounts:          {len(search('account.account', []))}")
print(f"  Journals:          {len(search('account.journal', []))}")
print(f"  Customer Invoices: {len(search('account.move', [('move_type', '=', 'out_invoice')]))}")
print(f"  Vendor Bills:      {len(search('account.move', [('move_type', '=', 'in_invoice')]))}")
print("\nDone!")
