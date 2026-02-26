#!/usr/bin/env python3
"""
Populate Odoo with realistic business data for Al Rawabi Group —
a diversified trading & distribution conglomerate based in Kuwait.

Covers: Company, Contacts, Products, CRM, Sales, Purchase, Inventory,
        Accounting, HR, Projects, Helpdesk, Manufacturing, Marketing.
"""

import ssl
import sys
import xmlrpc.client
from datetime import datetime, timedelta
import random
import os

# ── Connection ────────────────────────────────────────────────────────────────

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


def find_or_create(model, domain, vals):
    ids = search(model, domain, limit=1)
    if ids:
        return ids[0]
    return create(model, vals)


def today_str(offset_days=0):
    return (datetime.now() + timedelta(days=offset_days)).strftime("%Y-%m-%d")


def datetime_str(offset_days=0, hour=9, minute=0):
    dt = datetime.now() + timedelta(days=offset_days)
    dt = dt.replace(hour=hour, minute=minute, second=0)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def model_exists(model_name):
    try:
        search(model_name, [], limit=1)
        return True
    except Exception:
        return False


# ── 1. COMPANY ────────────────────────────────────────────────────────────────

print("\n=== 1. Updating Company Info ===")

company_ids = search("res.company", [], limit=1)
if company_ids:
    write("res.company", company_ids, {
        "name": "Al Rawabi Group",
        "street": "Al Soor Street, Block 3, Building 15",
        "street2": "Sharq Business District",
        "city": "Kuwait City",
        "zip": "13001",
        "phone": "+965 2224 8800",
        "email": "info@alrawabigroup.com",
        "website": "https://www.alrawabigroup.com",
        "vat": "KW-1234567890",
        "currency_id": search("res.currency", [("name", "=", "USD")], limit=1)[0],
    })
    print(f"  Company updated to 'Al Rawabi Group'")

    partner_ids = search("res.partner", [("id", "=", company_ids[0])], limit=1)
    if not partner_ids:
        partner_ids = search("res.partner", [("is_company", "=", True), ("name", "like", "Al Rawabi")], limit=1)

COMPANY_ID = company_ids[0] if company_ids else 1

# ── 2. PRODUCT CATEGORIES ────────────────────────────────────────────────────

print("\n=== 2. Creating Product Categories ===")

categories = {}
cat_data = {
    "Electronics": None,
    "Laptops & Computers": "Electronics",
    "Smartphones & Tablets": "Electronics",
    "Networking Equipment": "Electronics",
    "Home Appliances": None,
    "Kitchen Appliances": "Home Appliances",
    "Laundry & Cleaning": "Home Appliances",
    "Air Conditioning & HVAC": "Home Appliances",
    "Office Supplies": None,
    "Furniture": "Office Supplies",
    "Stationery": "Office Supplies",
    "Construction Materials": None,
    "Electrical Supplies": "Construction Materials",
    "Plumbing": "Construction Materials",
    "Services": None,
}

for cat_name, parent_name in cat_data.items():
    parent_id = categories.get(parent_name, False)
    vals = {"name": cat_name}
    if parent_id:
        vals["parent_id"] = parent_id
    cat_id = find_or_create("product.category", [("name", "=", cat_name)], vals)
    categories[cat_name] = cat_id
    print(f"  Category: {cat_name} (id={cat_id})")

# ── 3. PRODUCTS ───────────────────────────────────────────────────────────────

print("\n=== 3. Creating Products ===")

products = {}
product_data = [
    # (name, category, type, list_price, standard_price, barcode_suffix)
    ("Dell Latitude 5540 Laptop", "Laptops & Computers", "consu", 1249.00, 890.00, "1001"),
    ("HP ProBook 450 G10", "Laptops & Computers", "consu", 1099.00, 780.00, "1002"),
    ("Lenovo ThinkPad X1 Carbon Gen 11", "Laptops & Computers", "consu", 1649.00, 1180.00, "1003"),
    ("Apple MacBook Air M3", "Laptops & Computers", "consu", 1299.00, 1050.00, "1004"),
    ("Samsung Galaxy S24 Ultra", "Smartphones & Tablets", "consu", 1199.00, 850.00, "2001"),
    ("Apple iPhone 15 Pro Max", "Smartphones & Tablets", "consu", 1499.00, 1100.00, "2002"),
    ("iPad Pro 12.9\" M2", "Smartphones & Tablets", "consu", 1099.00, 820.00, "2003"),
    ("Samsung Galaxy Tab S9", "Smartphones & Tablets", "consu", 849.00, 610.00, "2004"),
    ("Cisco Catalyst 9200 Switch", "Networking Equipment", "consu", 3200.00, 2400.00, "3001"),
    ("Ubiquiti UniFi Dream Machine Pro", "Networking Equipment", "consu", 499.00, 350.00, "3002"),
    ("TP-Link Omada EAP670 AP", "Networking Equipment", "consu", 189.00, 120.00, "3003"),
    ("Fortinet FortiGate 60F Firewall", "Networking Equipment", "consu", 895.00, 650.00, "3004"),
    ("Samsung Side-by-Side Refrigerator", "Kitchen Appliances", "consu", 1899.00, 1350.00, "4001"),
    ("LG NeoChef Microwave Oven", "Kitchen Appliances", "consu", 249.00, 160.00, "4002"),
    ("Bosch Dishwasher Serie 6", "Kitchen Appliances", "consu", 799.00, 550.00, "4003"),
    ("Samsung EcoBubble Washing Machine", "Laundry & Cleaning", "consu", 699.00, 480.00, "5001"),
    ("Dyson V15 Detect Vacuum", "Laundry & Cleaning", "consu", 749.00, 520.00, "5002"),
    ("Daikin Split AC 2.0 Ton Inverter", "Air Conditioning & HVAC", "consu", 1450.00, 980.00, "6001"),
    ("Carrier Ducted AC System 5 Ton", "Air Conditioning & HVAC", "consu", 4500.00, 3200.00, "6002"),
    ("Midea Portable AC 1.5 Ton", "Air Conditioning & HVAC", "consu", 549.00, 380.00, "6003"),
    ("Herman Miller Aeron Chair", "Furniture", "consu", 1395.00, 950.00, "7001"),
    ("IKEA BEKANT Standing Desk", "Furniture", "consu", 549.00, 350.00, "7002"),
    ("Steelcase Series 2 Office Chair", "Furniture", "consu", 449.00, 280.00, "7003"),
    ("Conference Table 12-Seater", "Furniture", "consu", 2200.00, 1500.00, "7004"),
    ("HP LaserJet Pro MFP M428fdn", "Stationery", "consu", 449.00, 310.00, "8001"),
    ("A4 Paper Box (5 Reams)", "Stationery", "consu", 18.00, 11.00, "8002"),
    ("IT Infrastructure Setup", "Services", "service", 5000.00, 0.00, "9001"),
    ("Annual Maintenance Contract", "Services", "service", 2400.00, 0.00, "9002"),
    ("Network Installation Service", "Services", "service", 3500.00, 0.00, "9003"),
    ("AC Installation & Commissioning", "Services", "service", 800.00, 0.00, "9004"),
    ("Schneider MCB 32A", "Electrical Supplies", "consu", 12.50, 7.00, "C001"),
    ("Legrand 13A Socket Outlet", "Electrical Supplies", "consu", 8.00, 4.50, "C002"),
    ("Grundfos CR Pump 2HP", "Plumbing", "consu", 1250.00, 850.00, "C003"),
]

for name, cat, ptype, lprice, sprice, barcode in product_data:
    cat_id = categories.get(cat, False)
    vals = {
        "name": name,
        "categ_id": cat_id,
        "type": ptype,
        "list_price": lprice,
        "standard_price": sprice,
        "default_code": f"ARG-{barcode}",
        "sale_ok": True,
        "purchase_ok": ptype != "service",
    }
    pid = find_or_create("product.template", [("default_code", "=", f"ARG-{barcode}")], vals)
    products[name] = pid
    print(f"  Product: {name} (id={pid})")

# ── 4. CONTACTS — Customers ──────────────────────────────────────────────────

print("\n=== 4. Creating Customers ===")

customers = {}
customer_data = [
    {"name": "Kuwait National Petroleum Corp", "street": "Shuaiba Industrial Area", "city": "Al Ahmadi", "phone": "+965 2398 5000", "email": "procurement@knpc.com.kw", "vat": "KW-9000001001"},
    {"name": "Zain Telecommunications", "street": "Zain Tower, Shuwaikh", "city": "Kuwait City", "phone": "+965 2464 4444", "email": "it-purchasing@zain.com", "vat": "KW-9000001002"},
    {"name": "National Bank of Kuwait", "street": "NBK Tower, Shuhada St", "city": "Kuwait City", "phone": "+965 2224 2011", "email": "facilities@nbk.com", "vat": "KW-9000001003"},
    {"name": "Alghanim Industries", "street": "Olympic Tower, Fahad Al Salem St", "city": "Kuwait City", "phone": "+965 2229 3000", "email": "purchasing@alghanim.com", "vat": "KW-9000001004"},
    {"name": "Agility Logistics", "street": "Sulaibiya Free Trade Zone", "city": "Sulaibiya", "phone": "+965 2228 0228", "email": "admin@agility.com", "vat": "KW-9000001005"},
    {"name": "Gulf Insurance Group", "street": "Al Tijaria Tower, Floor 31", "city": "Kuwait City", "phone": "+965 2296 2000", "email": "operations@gig.com.kw", "vat": "KW-9000001006"},
    {"name": "Boubyan Bank", "street": "Ahmad Al Jaber St, Sharq", "city": "Kuwait City", "phone": "+965 2232 8328", "email": "it-dept@bankboubyan.com", "vat": "KW-9000001007"},
    {"name": "Ooredoo Kuwait", "street": "Ooredoo Tower, Soor St", "city": "Kuwait City", "phone": "+965 2202 1111", "email": "enterprise@ooredoo.com.kw", "vat": "KW-9000001008"},
    {"name": "Kuwait University", "street": "Khaldiya Campus", "city": "Khaldiya", "phone": "+965 2484 0011", "email": "procurement@ku.edu.kw", "vat": "KW-9000001009"},
    {"name": "EQUATE Petrochemical", "street": "Shuaiba Area, Plot 1", "city": "Al Ahmadi", "phone": "+965 2398 6000", "email": "supplies@equate.com", "vat": "KW-9000001010"},
    {"name": "KIPCO Group", "street": "KIPCO Tower, Sharq", "city": "Kuwait City", "phone": "+965 2294 3000", "email": "admin@kipco.com", "vat": "KW-9000001011"},
    {"name": "Al Sayer Group", "street": "Free Trade Zone, Shuwaikh", "city": "Kuwait City", "phone": "+965 1804 700", "email": "fleet@alsayer.com", "vat": "KW-9000001012"},
    {"name": "Ministry of Education Kuwait", "street": "South Surra, Block 3", "city": "Kuwait City", "phone": "+965 2483 7504", "email": "tenders@moe.gov.kw", "vat": "KW-9000001013"},
    {"name": "Burgan Bank", "street": "Burgan Tower, Al Sharq", "city": "Kuwait City", "phone": "+965 2298 8000", "email": "procurement@burgan.com", "vat": "KW-9000001014"},
    {"name": "Jazeera Airways", "street": "Kuwait International Airport, T5", "city": "Farwaniya", "phone": "+965 177", "email": "ops@jazeeraairways.com", "vat": "KW-9000001015"},
]

for c in customer_data:
    vals = {**c, "is_company": True, "customer_rank": 1, "country_id": search("res.country", [("code", "=", "KW")], limit=1)[0]}
    cid = find_or_create("res.partner", [("name", "=", c["name"])], vals)
    customers[c["name"]] = cid
    print(f"  Customer: {c['name']} (id={cid})")

# ── 5. CONTACTS — Vendors ────────────────────────────────────────────────────

print("\n=== 5. Creating Vendors ===")

vendors = {}
vendor_data = [
    {"name": "Dell Technologies EMEA", "street": "One Dell Way, Round Rock", "city": "Dubai (MENA HQ)", "country_code": "AE", "phone": "+971 4 365 5000", "email": "orders-mena@dell.com"},
    {"name": "HP Inc. Middle East", "street": "Dubai Internet City, Building 17", "city": "Dubai", "country_code": "AE", "phone": "+971 4 369 6500", "email": "enterprise-mea@hp.com"},
    {"name": "Samsung Gulf Electronics", "street": "Samsung Building, DAFZA", "city": "Dubai", "country_code": "AE", "phone": "+971 800 726 7864", "email": "b2b@samsung-gulf.com"},
    {"name": "Apple MEA Distribution", "street": "Gate District, DIFC", "city": "Dubai", "country_code": "AE", "phone": "+971 4 709 6600", "email": "enterprise@apple-mea.com"},
    {"name": "Cisco Systems Kuwait", "street": "Hamra Tower, Floor 22", "city": "Kuwait City", "country_code": "KW", "phone": "+965 2295 7000", "email": "partners-kw@cisco.com"},
    {"name": "Daikin Middle East & Africa", "street": "JAFZA South, Plot S20303", "city": "Jebel Ali", "country_code": "AE", "phone": "+971 4 880 9000", "email": "sales@daikin-mea.com"},
    {"name": "Schneider Electric Kuwait", "street": "Shuwaikh Industrial, Block 1", "city": "Kuwait City", "country_code": "KW", "phone": "+965 2461 6300", "email": "orders@se-kuwait.com"},
    {"name": "LG Electronics Gulf", "street": "Al Quoz Industrial Area 3", "city": "Dubai", "country_code": "AE", "phone": "+971 4 340 8989", "email": "b2b@lg-gulf.com"},
    {"name": "Bosch Home Appliances ME", "street": "Jebel Ali Free Zone", "city": "Dubai", "country_code": "AE", "phone": "+971 4 881 7222", "email": "pro-sales@bosch-me.com"},
    {"name": "Lenovo MECA", "street": "Emaar Business Park, Bldg 3", "city": "Dubai", "country_code": "AE", "phone": "+971 4 510 1600", "email": "partners@lenovo-meca.com"},
]

kw_country = search("res.country", [("code", "=", "KW")], limit=1)[0]
ae_country = search("res.country", [("code", "=", "AE")], limit=1)[0]
country_map = {"KW": kw_country, "AE": ae_country}

for v in vendor_data:
    cc = v.pop("country_code")
    vals = {**v, "is_company": True, "supplier_rank": 1, "country_id": country_map.get(cc, kw_country)}
    vid = find_or_create("res.partner", [("name", "=", v["name"])], vals)
    vendors[v["name"]] = vid
    print(f"  Vendor: {v['name']} (id={vid})")

# ── 6. CUSTOMER CONTACT PERSONS ──────────────────────────────────────────────

print("\n=== 6. Creating Contact Persons ===")

contact_persons = [
    ("Ahmed Al-Mutairi", "IT Manager", "Kuwait National Petroleum Corp"),
    ("Fatima Al-Sabah", "Head of Procurement", "Zain Telecommunications"),
    ("Mohammad Al-Shatti", "VP Facilities", "National Bank of Kuwait"),
    ("Sarah Al-Kandari", "Purchasing Director", "Alghanim Industries"),
    ("Yousef Al-Rashidi", "Admin Manager", "Agility Logistics"),
    ("Nour Al-Dosari", "Operations Lead", "Gulf Insurance Group"),
    ("Khalid Al-Enezi", "IT Director", "Boubyan Bank"),
    ("Hessa Al-Ghanim", "Enterprise Sales", "Ooredoo Kuwait"),
    ("Dr. Bader Al-Otaibi", "IT Department Head", "Kuwait University"),
    ("Layla Al-Hajri", "Supply Chain Manager", "EQUATE Petrochemical"),
]

for name, title, parent_name in contact_persons:
    parent_id = customers.get(parent_name)
    if not parent_id:
        continue
    vals = {
        "name": name,
        "function": title,
        "parent_id": parent_id,
        "type": "contact",
        "email": f"{name.split()[0].lower()}@{parent_name.split()[0].lower()}.com",
        "phone": f"+965 {random.randint(5000,9999)} {random.randint(1000,9999)}",
    }
    find_or_create("res.partner", [("name", "=", name), ("parent_id", "=", parent_id)], vals)
    print(f"  Contact: {name} at {parent_name}")

# ── 7. HR — Departments & Employees ──────────────────────────────────────────

print("\n=== 7. Creating Departments & Employees ===")

departments = {}
dept_names = [
    "Executive Management", "Sales & Business Development", "Procurement & Supply Chain",
    "Information Technology", "Finance & Accounting", "Human Resources",
    "Warehouse & Logistics", "Technical Services", "Marketing & Communications",
    "Customer Support",
]

for dname in dept_names:
    did = find_or_create("hr.department", [("name", "=", dname)], {"name": dname, "company_id": COMPANY_ID})
    departments[dname] = did
    print(f"  Department: {dname} (id={did})")

employee_data = [
    ("Faisal Al Rawabi", "CEO", "Executive Management", "faisal@alrawabigroup.com", "CEO"),
    ("Maha Al-Khaled", "CFO", "Finance & Accounting", "maha@alrawabigroup.com", "CFO"),
    ("Omar Hassan", "VP Sales", "Sales & Business Development", "omar@alrawabigroup.com", "VP Sales"),
    ("Rania Mahmoud", "Sales Manager – Enterprise", "Sales & Business Development", "rania@alrawabigroup.com", "Sales Mgr"),
    ("Tariq Al-Sayed", "Account Executive", "Sales & Business Development", "tariq@alrawabigroup.com", "Account Exec"),
    ("Nadia Farooq", "Account Executive", "Sales & Business Development", "nadia@alrawabigroup.com", "Account Exec"),
    ("Hassan Abdel-Rahman", "Procurement Director", "Procurement & Supply Chain", "hassan@alrawabigroup.com", "Procurement Dir"),
    ("Lina Barakat", "Procurement Specialist", "Procurement & Supply Chain", "lina@alrawabigroup.com", "Proc Specialist"),
    ("Dr. Salim Nasser", "IT Director", "Information Technology", "salim@alrawabigroup.com", "IT Dir"),
    ("Yara Qasim", "Systems Engineer", "Information Technology", "yara@alrawabigroup.com", "Sys Engineer"),
    ("Ahmad Jaber", "Network Engineer", "Information Technology", "ahmad.j@alrawabigroup.com", "Net Engineer"),
    ("Fatima Al-Zahra", "Financial Controller", "Finance & Accounting", "fatima@alrawabigroup.com", "Fin Controller"),
    ("Khaled Ibrahim", "Accountant", "Finance & Accounting", "khaled@alrawabigroup.com", "Accountant"),
    ("Dina Rashid", "HR Manager", "Human Resources", "dina@alrawabigroup.com", "HR Mgr"),
    ("Waleed Mansour", "Warehouse Manager", "Warehouse & Logistics", "waleed@alrawabigroup.com", "Warehouse Mgr"),
    ("Samira Haddad", "Logistics Coordinator", "Warehouse & Logistics", "samira@alrawabigroup.com", "Logistics Coord"),
    ("Ali Mostafa", "Field Service Engineer", "Technical Services", "ali@alrawabigroup.com", "Field Eng"),
    ("Bassem Tayeh", "HVAC Technician", "Technical Services", "bassem@alrawabigroup.com", "HVAC Tech"),
    ("Jana Al-Turki", "Marketing Manager", "Marketing & Communications", "jana@alrawabigroup.com", "Mktg Mgr"),
    ("Rami Khoury", "Support Team Lead", "Customer Support", "rami@alrawabigroup.com", "Support Lead"),
    ("Ghada Saleh", "Support Agent", "Customer Support", "ghada@alrawabigroup.com", "Support Agent"),
]

employees = {}
for ename, job_title, dept, email, short in employee_data:
    dept_id = departments.get(dept)
    vals = {
        "name": ename,
        "job_title": job_title,
        "department_id": dept_id,
        "work_email": email,
        "company_id": COMPANY_ID,
    }
    eid = find_or_create("hr.employee", [("name", "=", ename)], vals)
    employees[short] = eid
    employees[ename] = eid
    print(f"  Employee: {ename} – {job_title} (id={eid})")

# ── 8. CRM — Leads & Opportunities ───────────────────────────────────────────

print("\n=== 8. Creating CRM Leads & Opportunities ===")

# Get CRM stages
crm_stages = search_read("crm.stage", [], fields=["id", "name"])
stage_map = {s["name"]: s["id"] for s in crm_stages}
print(f"  Available stages: {list(stage_map.keys())}")

# Pick stage IDs (Odoo 18 default stage names)
stage_new = stage_map.get("New", crm_stages[0]["id"] if crm_stages else False)
stage_qualified = stage_map.get("Qualified", crm_stages[1]["id"] if len(crm_stages) > 1 else stage_new)
stage_proposition = stage_map.get("Proposition", crm_stages[2]["id"] if len(crm_stages) > 2 else stage_qualified)
stage_won = stage_map.get("Won", crm_stages[-1]["id"] if crm_stages else False)

# Get sales team
sales_teams = search_read("crm.team", [], fields=["id", "name"], limit=5)
default_team = sales_teams[0]["id"] if sales_teams else False

leads = [
    {"name": "KNPC — IT Infrastructure Refresh 2026", "partner_id": customers.get("Kuwait National Petroleum Corp"), "expected_revenue": 185000, "stage_id": stage_proposition, "probability": 65, "priority": "3"},
    {"name": "Zain — 500x Samsung Galaxy S24 Fleet", "partner_id": customers.get("Zain Telecommunications"), "expected_revenue": 420000, "stage_id": stage_qualified, "probability": 45, "priority": "2"},
    {"name": "NBK — Branch AC Replacement (12 branches)", "partner_id": customers.get("National Bank of Kuwait"), "expected_revenue": 156000, "stage_id": stage_proposition, "probability": 75, "priority": "3"},
    {"name": "Alghanim — HQ Office Furniture Fitout", "partner_id": customers.get("Alghanim Industries"), "expected_revenue": 89000, "stage_id": stage_new, "probability": 20, "priority": "1"},
    {"name": "Agility — Warehouse Network Overhaul", "partner_id": customers.get("Agility Logistics"), "expected_revenue": 72000, "stage_id": stage_qualified, "probability": 50, "priority": "2"},
    {"name": "GIG — 200x Dell Laptops for Staff", "partner_id": customers.get("Gulf Insurance Group"), "expected_revenue": 249800, "stage_id": stage_won, "probability": 100, "priority": "3"},
    {"name": "Boubyan Bank — Cisco Network Upgrade", "partner_id": customers.get("Boubyan Bank"), "expected_revenue": 128000, "stage_id": stage_proposition, "probability": 60, "priority": "2"},
    {"name": "Ooredoo — Data Center Cooling", "partner_id": customers.get("Ooredoo Kuwait"), "expected_revenue": 340000, "stage_id": stage_qualified, "probability": 35, "priority": "3"},
    {"name": "KU — Smart Classroom Equipment", "partner_id": customers.get("Kuwait University"), "expected_revenue": 95000, "stage_id": stage_new, "probability": 15, "priority": "1"},
    {"name": "EQUATE — Annual Maintenance Renewal", "partner_id": customers.get("EQUATE Petrochemical"), "expected_revenue": 48000, "stage_id": stage_won, "probability": 100, "priority": "2"},
    {"name": "KIPCO — Executive Office Renovation", "partner_id": customers.get("KIPCO Group"), "expected_revenue": 67000, "stage_id": stage_qualified, "probability": 40, "priority": "1"},
    {"name": "Al Sayer — Fleet Tablet Deployment", "partner_id": customers.get("Al Sayer Group"), "expected_revenue": 112000, "stage_id": stage_proposition, "probability": 70, "priority": "2"},
    {"name": "MOE — School IT Lab Setup (Phase 1)", "partner_id": customers.get("Ministry of Education Kuwait"), "expected_revenue": 520000, "stage_id": stage_new, "probability": 10, "priority": "3"},
    {"name": "Burgan Bank — IP Phone System", "partner_id": customers.get("Burgan Bank"), "expected_revenue": 85000, "stage_id": stage_qualified, "probability": 55, "priority": "2"},
    {"name": "Jazeera Airways — Check-in Kiosk Hardware", "partner_id": customers.get("Jazeera Airways"), "expected_revenue": 210000, "stage_id": stage_proposition, "probability": 60, "priority": "3"},
]

lead_ids = {}
for l in leads:
    l["type"] = "opportunity"
    if default_team:
        l["team_id"] = default_team
    lid = find_or_create("crm.lead", [("name", "=", l["name"])], l)
    lead_ids[l["name"]] = lid
    print(f"  Opportunity: {l['name']} — ${l['expected_revenue']:,.0f} (id={lid})")

# ── 9. SALES ORDERS ──────────────────────────────────────────────────────────

print("\n=== 9. Creating Sales Orders ===")

product_variants = search_read("product.product", [("default_code", "like", "ARG-")], fields=["id", "name", "default_code", "list_price"])
pv_map = {p["default_code"]: p for p in product_variants}

so_data = [
    {
        "partner": "Gulf Insurance Group",
        "lines": [("ARG-1001", 120, 1249.00), ("ARG-8001", 10, 449.00), ("ARG-8002", 50, 18.00)],
        "note": "GIG Laptop rollout — 120 Dell Latitude + printers + paper",
    },
    {
        "partner": "EQUATE Petrochemical",
        "lines": [("ARG-9002", 2, 2400.00), ("ARG-9001", 1, 5000.00)],
        "note": "EQUATE Annual Maintenance + IT Setup",
    },
    {
        "partner": "National Bank of Kuwait",
        "lines": [("ARG-6001", 48, 1450.00), ("ARG-9004", 48, 800.00)],
        "note": "NBK Branch AC Replacement — 12 branches x 4 units",
    },
    {
        "partner": "Agility Logistics",
        "lines": [("ARG-3001", 4, 3200.00), ("ARG-3002", 2, 499.00), ("ARG-3003", 20, 189.00), ("ARG-9003", 1, 3500.00)],
        "note": "Agility Warehouse Network Infrastructure",
    },
    {
        "partner": "Al Sayer Group",
        "lines": [("ARG-2003", 80, 1099.00), ("ARG-2004", 40, 849.00)],
        "note": "Al Sayer Fleet Tablet Deployment — iPad Pro + Galaxy Tab",
    },
    {
        "partner": "Boubyan Bank",
        "lines": [("ARG-3001", 8, 3200.00), ("ARG-3004", 4, 895.00), ("ARG-3003", 30, 189.00)],
        "note": "Boubyan Bank Core Network Upgrade — Cisco + FortiGate + APs",
    },
    {
        "partner": "Jazeera Airways",
        "lines": [("ARG-2003", 30, 1099.00), ("ARG-1003", 15, 1649.00)],
        "note": "Jazeera check-in hardware — iPads + ThinkPads for counters",
    },
    {
        "partner": "Kuwait University",
        "lines": [("ARG-1002", 60, 1099.00), ("ARG-1001", 40, 1249.00), ("ARG-3003", 50, 189.00)],
        "note": "KU Smart Classroom Phase 1 — HP + Dell laptops + WiFi APs",
    },
]

so_ids = []
for so in so_data:
    partner_id = customers.get(so["partner"])
    if not partner_id:
        continue
    order_lines = []
    for code, qty, price in so["lines"]:
        pv = pv_map.get(code)
        if not pv:
            continue
        order_lines.append((0, 0, {
            "product_id": pv["id"],
            "product_uom_qty": qty,
            "price_unit": price,
        }))

    if not order_lines:
        continue

    vals = {
        "partner_id": partner_id,
        "order_line": order_lines,
        "note": so["note"],
        "date_order": today_str(random.randint(-30, -1)),
    }
    sid = find_or_create("sale.order", [("partner_id", "=", partner_id), ("note", "=", so["note"])], vals)
    so_ids.append(sid)
    print(f"  Sale Order: {so['partner']} (id={sid})")

# Confirm the first 4 sales orders
for sid in so_ids[:4]:
    try:
        x("sale.order", "action_confirm", [sid])
        print(f"  Confirmed SO id={sid}")
    except Exception as e:
        print(f"  (SO {sid} may already be confirmed: {str(e)[:80]})")

# ── 10. PURCHASE ORDERS ──────────────────────────────────────────────────────

print("\n=== 10. Creating Purchase Orders ===")

po_data = [
    {
        "vendor": "Dell Technologies EMEA",
        "lines": [("ARG-1001", 150, 890.00), ("ARG-1001", 50, 890.00)],
        "note": "Q1 2026 Dell Latitude 5540 bulk procurement",
    },
    {
        "vendor": "HP Inc. Middle East",
        "lines": [("ARG-1002", 80, 780.00), ("ARG-8001", 20, 310.00)],
        "note": "HP ProBook + LaserJet for resale stock",
    },
    {
        "vendor": "Samsung Gulf Electronics",
        "lines": [("ARG-2001", 100, 850.00), ("ARG-2004", 60, 610.00), ("ARG-4001", 20, 1350.00), ("ARG-5001", 30, 480.00)],
        "note": "Samsung mixed order — phones, tablets, appliances",
    },
    {
        "vendor": "Cisco Systems Kuwait",
        "lines": [("ARG-3001", 15, 2400.00), ("ARG-3004", 10, 650.00)],
        "note": "Cisco switches + FortiGate firewalls for projects",
    },
    {
        "vendor": "Daikin Middle East & Africa",
        "lines": [("ARG-6001", 60, 980.00), ("ARG-6002", 10, 3200.00), ("ARG-6003", 25, 380.00)],
        "note": "Daikin AC units — split, ducted, portable",
    },
    {
        "vendor": "Apple MEA Distribution",
        "lines": [("ARG-1004", 40, 1050.00), ("ARG-2002", 50, 1100.00), ("ARG-2003", 60, 820.00)],
        "note": "Apple MacBook Air + iPhone 15 Pro + iPad Pro",
    },
    {
        "vendor": "Schneider Electric Kuwait",
        "lines": [("ARG-C001", 500, 7.00), ("ARG-C002", 300, 4.50)],
        "note": "Schneider electrical supplies — MCBs + sockets",
    },
    {
        "vendor": "LG Electronics Gulf",
        "lines": [("ARG-4002", 40, 160.00)],
        "note": "LG Microwave ovens for hospitality project resale",
    },
]

po_ids = []
for po in po_data:
    vendor_id = vendors.get(po["vendor"])
    if not vendor_id:
        continue
    order_lines = []
    for code, qty, price in po["lines"]:
        pv = pv_map.get(code)
        if not pv:
            continue
        order_lines.append((0, 0, {
            "product_id": pv["id"],
            "product_qty": qty,
            "price_unit": price,
        }))

    if not order_lines:
        continue

    vals = {
        "partner_id": vendor_id,
        "order_line": order_lines,
        "notes": po["note"],
        "date_order": today_str(random.randint(-45, -5)),
    }
    pid = find_or_create("purchase.order", [("partner_id", "=", vendor_id), ("notes", "=", po["note"])], vals)
    po_ids.append(pid)
    print(f"  Purchase Order: {po['vendor']} (id={pid})")

# Confirm the first 5 purchase orders
for pid in po_ids[:5]:
    try:
        x("purchase.order", "button_confirm", [pid])
        print(f"  Confirmed PO id={pid}")
    except Exception as e:
        print(f"  (PO {pid} may already be confirmed: {str(e)[:80]})")

# ── 11. PROJECTS & TASKS ─────────────────────────────────────────────────────

print("\n=== 11. Creating Projects & Tasks ===")

project_data = [
    {
        "name": "KNPC IT Infrastructure Refresh",
        "tasks": [
            ("Site survey & network assessment", today_str(-15), today_str(-8), "1_done"),
            ("Hardware specification & vendor quotes", today_str(-10), today_str(-3), "1_done"),
            ("Procurement of servers & switches", today_str(-3), today_str(10), "02_progress"),
            ("Physical installation & cabling", today_str(10), today_str(25), "03_approved"),
            ("Network configuration & testing", today_str(25), today_str(35), "03_approved"),
            ("Security hardening & documentation", today_str(35), today_str(42), "04_waiting_normal"),
            ("Go-live & handover", today_str(42), today_str(45), "04_waiting_normal"),
        ],
    },
    {
        "name": "NBK Branch AC Replacement Program",
        "tasks": [
            ("Audit existing AC units — 12 branches", today_str(-20), today_str(-12), "1_done"),
            ("Daikin procurement — 48 split units", today_str(-5), today_str(5), "02_progress"),
            ("Branch 1-3 installation", today_str(5), today_str(12), "03_approved"),
            ("Branch 4-6 installation", today_str(12), today_str(19), "04_waiting_normal"),
            ("Branch 7-9 installation", today_str(19), today_str(26), "04_waiting_normal"),
            ("Branch 10-12 installation", today_str(26), today_str(33), "04_waiting_normal"),
            ("Final inspection & handover", today_str(33), today_str(36), "04_waiting_normal"),
        ],
    },
    {
        "name": "Agility Warehouse Network Upgrade",
        "tasks": [
            ("Current network architecture review", today_str(-10), today_str(-5), "1_done"),
            ("New network design & topology", today_str(-5), today_str(0), "02_progress"),
            ("Cisco switch & AP procurement", today_str(0), today_str(8), "02_progress"),
            ("Core switch installation", today_str(8), today_str(12), "03_approved"),
            ("Access point deployment", today_str(12), today_str(18), "04_waiting_normal"),
            ("WMS integration testing", today_str(18), today_str(22), "04_waiting_normal"),
            ("Performance tuning & sign-off", today_str(22), today_str(25), "04_waiting_normal"),
        ],
    },
    {
        "name": "Al Rawabi Internal ERP Optimization",
        "tasks": [
            ("Odoo workflow analysis & gap assessment", today_str(-25), today_str(-18), "1_done"),
            ("AI automation module development", today_str(-18), today_str(-5), "1_done"),
            ("Webhook integration setup", today_str(-5), today_str(2), "02_progress"),
            ("Dashboard build & deployment", today_str(2), today_str(10), "02_progress"),
            ("UAT with department heads", today_str(10), today_str(15), "03_approved"),
            ("Production rollout", today_str(15), today_str(18), "04_waiting_normal"),
        ],
    },
    {
        "name": "KU Smart Classroom — Phase 1",
        "tasks": [
            ("Classroom survey — 20 rooms", today_str(-8), today_str(-2), "1_done"),
            ("Equipment specification (laptops, APs)", today_str(-2), today_str(3), "02_progress"),
            ("Procurement & receiving", today_str(3), today_str(15), "03_approved"),
            ("Room 1-5 installation", today_str(15), today_str(22), "04_waiting_normal"),
            ("Room 6-10 installation", today_str(22), today_str(29), "04_waiting_normal"),
            ("Room 11-15 installation", today_str(29), today_str(36), "04_waiting_normal"),
            ("Room 16-20 installation", today_str(36), today_str(43), "04_waiting_normal"),
            ("Teacher training & handover", today_str(43), today_str(47), "04_waiting_normal"),
        ],
    },
]

# Get project stages
proj_stages = search_read("project.task.type", [], fields=["id", "name"])
pstage_map = {s["name"]: s["id"] for s in proj_stages}

for proj in project_data:
    proj_id = find_or_create("project.project", [("name", "=", proj["name"])], {
        "name": proj["name"],
        "company_id": COMPANY_ID,
    })
    print(f"  Project: {proj['name']} (id={proj_id})")

    for task_name, date_start, date_end, stage_key in proj["tasks"]:
        stage_id = False
        for sname, sid in pstage_map.items():
            if stage_key.lower() in sname.lower():
                stage_id = sid
                break
        if not stage_id and proj_stages:
            stage_id = proj_stages[0]["id"]

        task_vals = {
            "name": task_name,
            "project_id": proj_id,
            "date_deadline": date_end,
        }
        if stage_id:
            task_vals["stage_id"] = stage_id

        find_or_create("project.task", [("name", "=", task_name), ("project_id", "=", proj_id)], task_vals)
        print(f"    Task: {task_name}")

# ── 12. ACCOUNTING — Invoices ─────────────────────────────────────────────────

print("\n=== 12. Creating Customer Invoices ===")

invoice_data = [
    {
        "partner": "Gulf Insurance Group",
        "lines": [("ARG-1001", 120, 1249.00), ("ARG-8001", 10, 449.00)],
        "ref": "INV-GIG-2026-001",
    },
    {
        "partner": "EQUATE Petrochemical",
        "lines": [("ARG-9002", 2, 2400.00)],
        "ref": "INV-EQ-2026-001",
    },
    {
        "partner": "Alghanim Industries",
        "lines": [("ARG-7001", 20, 1395.00), ("ARG-7002", 15, 549.00)],
        "ref": "INV-ALG-2026-001",
    },
    {
        "partner": "KIPCO Group",
        "lines": [("ARG-7001", 10, 1395.00), ("ARG-7003", 30, 449.00), ("ARG-7004", 2, 2200.00)],
        "ref": "INV-KIP-2026-001",
    },
]

for inv in invoice_data:
    partner_id = customers.get(inv["partner"])
    if not partner_id:
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
        }))

    if not inv_lines:
        continue

    existing = search("account.move", [("ref", "=", inv["ref"]), ("move_type", "=", "out_invoice")], limit=1)
    if existing:
        print(f"  Invoice {inv['ref']} already exists (id={existing[0]})")
        continue

    vals = {
        "partner_id": partner_id,
        "move_type": "out_invoice",
        "invoice_line_ids": inv_lines,
        "ref": inv["ref"],
        "invoice_date": today_str(random.randint(-20, -1)),
    }
    try:
        inv_id = create("account.move", vals)
        print(f"  Invoice: {inv['ref']} for {inv['partner']} (id={inv_id})")
    except Exception as e:
        print(f"  (Invoice {inv['ref']} error: {str(e)[:100]})")

# ── 13. VENDOR BILLS ──────────────────────────────────────────────────────────

print("\n=== 13. Creating Vendor Bills ===")

bill_data = [
    {
        "vendor": "Dell Technologies EMEA",
        "lines": [("ARG-1001", 150, 890.00)],
        "ref": "BILL-DELL-2026-001",
    },
    {
        "vendor": "Daikin Middle East & Africa",
        "lines": [("ARG-6001", 60, 980.00), ("ARG-6002", 10, 3200.00)],
        "ref": "BILL-DAI-2026-001",
    },
    {
        "vendor": "Samsung Gulf Electronics",
        "lines": [("ARG-2001", 100, 850.00), ("ARG-2004", 60, 610.00)],
        "ref": "BILL-SAM-2026-001",
    },
]

for bill in bill_data:
    vendor_id = vendors.get(bill["vendor"])
    if not vendor_id:
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
        }))

    if not bill_lines:
        continue

    existing = search("account.move", [("ref", "=", bill["ref"]), ("move_type", "=", "in_invoice")], limit=1)
    if existing:
        print(f"  Bill {bill['ref']} already exists (id={existing[0]})")
        continue

    vals = {
        "partner_id": vendor_id,
        "move_type": "in_invoice",
        "invoice_line_ids": bill_lines,
        "ref": bill["ref"],
        "invoice_date": today_str(random.randint(-30, -5)),
    }
    try:
        bill_id = create("account.move", vals)
        print(f"  Bill: {bill['ref']} from {bill['vendor']} (id={bill_id})")
    except Exception as e:
        print(f"  (Bill {bill['ref']} error: {str(e)[:100]})")

# ── 14. HELPDESK TICKETS ─────────────────────────────────────────────────────

print("\n=== 14. Creating Helpdesk Tickets ===")

if model_exists("helpdesk.ticket"):
    helpdesk_teams = search_read("helpdesk.team", [], fields=["id", "name"], limit=5)
    hd_team = helpdesk_teams[0]["id"] if helpdesk_teams else False

    ticket_data = [
        {"name": "Dell Latitude — screen flickering on 5 units", "partner": "Gulf Insurance Group", "priority": "2", "description": "5 laptops from batch GIG-2026-001 showing screen flicker after 2 weeks of use. Units S/N: DL5540-0012 to DL5540-0016."},
        {"name": "Daikin AC unit error code E3 — Branch 2", "partner": "National Bank of Kuwait", "priority": "3", "description": "NBK Hawalli branch — 2nd floor Daikin split unit showing E3 error. AC not cooling. Ambient temp 45°C. Urgent."},
        {"name": "Cisco switch stack link failure", "partner": "Agility Logistics", "priority": "3", "description": "Stack link between Catalyst 9200 units in warehouse rack A failed at 3 AM. Redundancy lost. Need on-site ASAP."},
        {"name": "Samsung Galaxy Tab S9 — charging port issue (3 units)", "partner": "Al Sayer Group", "priority": "1", "description": "3 Galaxy Tab S9 units not charging via USB-C. Under warranty. Need RMA process."},
        {"name": "FortiGate firewall firmware update assistance", "partner": "Boubyan Bank", "priority": "2", "description": "Boubyan IT team requesting remote assistance for FortiGate 60F firmware upgrade from v7.2 to v7.4. Scheduled for weekend."},
        {"name": "HP Printer paper jam — recurring issue", "partner": "EQUATE Petrochemical", "priority": "1", "description": "HP LaserJet M428fdn at EQUATE admin building getting paper jams every 50 pages. Fuser may need replacement."},
        {"name": "WiFi dead zones in new warehouse section", "partner": "Agility Logistics", "priority": "2", "description": "New mezzanine level in Sulaibiya warehouse has no WiFi coverage. Need 4 additional Omada APs. Quote + install requested."},
        {"name": "MacBook Air M3 — keyboard issue", "partner": "Jazeera Airways", "priority": "1", "description": "MacBook Air M3 unit at check-in counter 7 — spacebar sticky. Under AppleCare. Coordinate with Apple for replacement."},
    ]

    for t in ticket_data:
        partner_id = customers.get(t.pop("partner", ""), False)
        vals = {
            "name": t["name"],
            "priority": t["priority"],
            "description": t.get("description", ""),
        }
        if partner_id:
            vals["partner_id"] = partner_id
        if hd_team:
            vals["team_id"] = hd_team
        try:
            tid = find_or_create("helpdesk.ticket", [("name", "=", t["name"])], vals)
            print(f"  Ticket: {t['name']} (id={tid})")
        except Exception as e:
            print(f"  (Ticket error: {str(e)[:80]})")
else:
    print("  Helpdesk module not installed — skipping")

# ── 15. MANUFACTURING ORDERS ─────────────────────────────────────────────────

print("\n=== 15. Creating Manufacturing Orders ===")

if model_exists("mrp.production"):
    print("  Manufacturing module found — creating sample MO data")
    # MRP requires BOM setup which is complex; log availability
    bom_count = search_count("mrp.bom", [])
    print(f"  Existing BOMs: {bom_count}")
    if bom_count == 0:
        print("  No BOMs configured — skipping MO creation (needs BOM setup first)")
    else:
        print("  BOMs exist — MOs can be created from sales orders")
else:
    print("  Manufacturing module not installed — skipping")

# ── 16. MARKETING ─────────────────────────────────────────────────────────────

print("\n=== 16. Creating Marketing Campaigns ===")

if model_exists("mailing.mailing"):
    mailing_data = [
        {
            "subject": "Al Rawabi Q1 2026 — New Arrivals: Dell, HP & Lenovo Laptops",
            "body_html": "<h2>New Stock Alert — Enterprise Laptops</h2><p>Dear valued customer,</p><p>We're excited to announce our latest shipment of business-grade laptops:</p><ul><li>Dell Latitude 5540 — from KD 375</li><li>HP ProBook 450 G10 — from KD 330</li><li>Lenovo ThinkPad X1 Carbon Gen 11 — from KD 495</li></ul><p>Volume discounts available for orders of 50+ units. Contact your account manager today.</p><p>Best regards,<br>Al Rawabi Group Sales Team</p>",
        },
        {
            "subject": "Beat the Heat — Daikin AC Systems Special Offer",
            "body_html": "<h2>Summer 2026 AC Deals</h2><p>Prepare for summer with our exclusive Daikin partnership offers:</p><ul><li>Split AC 2.0 Ton Inverter — KD 435 (was KD 480)</li><li>Free installation on orders of 10+ units</li><li>Extended 5-year warranty program</li></ul><p>Offer valid until June 30, 2026.</p><p>Al Rawabi Group — Your Climate Partner</p>",
        },
        {
            "subject": "Network Security Alert — FortiGate Firewall Solutions",
            "body_html": "<h2>Protect Your Business</h2><p>Cyber threats are on the rise. Secure your network with Fortinet solutions from Al Rawabi:</p><ul><li>FortiGate 60F — Perfect for SMBs</li><li>Free security assessment for existing customers</li><li>Managed firewall service available</li></ul><p>Schedule a consultation with our security team today.</p>",
        },
    ]

    for m in mailing_data:
        vals = {
            "subject": m["subject"],
            "body_html": m["body_html"],
            "mailing_type": "mail",
        }
        try:
            mid = find_or_create("mailing.mailing", [("subject", "=", m["subject"])], vals)
            print(f"  Mailing: {m['subject'][:60]}... (id={mid})")
        except Exception as e:
            print(f"  (Mailing error: {str(e)[:80]})")
else:
    print("  Marketing module not installed — skipping")

# ── 17. CALENDAR EVENTS ──────────────────────────────────────────────────────

print("\n=== 17. Creating Calendar Events ===")

events = [
    {"name": "KNPC — Final Proposal Presentation", "start": datetime_str(3, 10, 0), "stop": datetime_str(3, 11, 30), "location": "KNPC HQ, Shuaiba"},
    {"name": "Zain — Samsung Fleet Demo", "start": datetime_str(5, 14, 0), "stop": datetime_str(5, 15, 0), "location": "Zain Tower, Shuwaikh"},
    {"name": "NBK — AC Installation Kickoff", "start": datetime_str(7, 9, 0), "stop": datetime_str(7, 10, 0), "location": "NBK Sharq Branch"},
    {"name": "Monthly Sales Review Meeting", "start": datetime_str(10, 9, 0), "stop": datetime_str(10, 10, 30), "location": "Al Rawabi HQ, Boardroom"},
    {"name": "Cisco Partner Certification Training", "start": datetime_str(14, 8, 0), "stop": datetime_str(14, 17, 0), "location": "Cisco Kuwait Office"},
    {"name": "Boubyan — Network Upgrade Progress Review", "start": datetime_str(8, 11, 0), "stop": datetime_str(8, 12, 0), "location": "Boubyan Bank HQ"},
    {"name": "Ooredoo — Data Center Cooling RFP Discussion", "start": datetime_str(12, 13, 0), "stop": datetime_str(12, 14, 30), "location": "Ooredoo Tower, Soor St"},
    {"name": "Al Rawabi — Q1 Budget Review", "start": datetime_str(15, 10, 0), "stop": datetime_str(15, 12, 0), "location": "Al Rawabi HQ, Finance Room"},
]

for ev in events:
    find_or_create("calendar.event", [("name", "=", ev["name"])], ev)
    print(f"  Event: {ev['name']}")

# ── 18. NOTES / ACTIVITIES ───────────────────────────────────────────────────

print("\n=== 18. Summary ===")

# Count totals
totals = {
    "Products": search_count("product.template", [("default_code", "like", "ARG-")]),
    "Customers": search_count("res.partner", [("customer_rank", ">", 0)]),
    "Vendors": search_count("res.partner", [("supplier_rank", ">", 0)]),
    "Employees": search_count("hr.employee", []),
    "CRM Opportunities": search_count("crm.lead", [("type", "=", "opportunity")]),
    "Sales Orders": search_count("sale.order", []),
    "Purchase Orders": search_count("purchase.order", []),
    "Projects": search_count("project.project", []),
    "Tasks": search_count("project.task", []),
    "Invoices": search_count("account.move", [("move_type", "=", "out_invoice")]),
    "Vendor Bills": search_count("account.move", [("move_type", "=", "in_invoice")]),
    "Calendar Events": search_count("calendar.event", []),
}

print("\n" + "=" * 55)
print("  AL RAWABI GROUP — Odoo Data Population Complete!")
print("=" * 55)
for label, count in totals.items():
    print(f"  {label:.<35} {count:>5}")
print("=" * 55)
print("\nDone! Your Odoo instance is now populated with realistic")
print("business data for Al Rawabi Group, a Kuwaiti trading &")
print("distribution conglomerate.\n")
