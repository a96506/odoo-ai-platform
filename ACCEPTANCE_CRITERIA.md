# Acceptance Criteria

**Referenced by:** [MASTER_PLAN.md](MASTER_PLAN.md) -- Engineering Scaffolding
**Applies to:** Phase 1 deliverables

---

## How to Use This Document

Each Phase 1 deliverable has:
1. **User Journey** -- step-by-step walkthrough from the user's perspective
2. **Acceptance Criteria** -- specific, testable conditions that must pass before the feature is "done"
3. **Out of Scope** -- what this deliverable explicitly does NOT include (to prevent scope creep)

---

## 1.1 Month-End Closing Assistant

### User Journey

**Actor:** Controller / Accounting Manager

1. Controller opens the dashboard and clicks "Start Month-End Close" for February 2026
2. System runs an automated scan of Odoo accounting data
3. Within 60 seconds, a checklist appears with 10 steps, each showing:
   - Step name (e.g., "Reconcile Bank Transactions")
   - Status (complete / in progress / needs attention)
   - Count (e.g., "12 unreconciled items")
   - AI recommendation (e.g., "3 can be auto-matched, 9 need review")
4. Controller works through each step, marking items as resolved
5. When all steps show green, controller clicks "Complete Close"
6. System sets lock dates in Odoo and generates a closing summary

### Acceptance Criteria

- [ ] `POST /api/close/start` creates a closing record and triggers scan
- [ ] Scan detects: unreconciled bank items, stale drafts (>30 days), unbilled deliveries, missing recurring bills, unposted depreciation
- [ ] Each step shows item count and status
- [ ] Steps can be individually marked as complete
- [ ] Overall progress percentage is calculated correctly
- [ ] Closing summary includes all issues found and resolutions
- [ ] Cannot start a second closing for the same period
- [ ] Audit log records all closing activity

### Out of Scope

- Auto-fixing issues (this version only identifies and reports)
- Lock date management in Odoo (manual for Phase 1)
- Multi-company closing coordination

---

## 1.3 Enhanced Bank Reconciliation

### User Journey

**Actor:** Accountant

1. Accountant starts a reconciliation session for the bank journal
2. System loads unreconciled bank statement lines and Odoo journal entries
3. AI generates match suggestions with confidence scores and match type (exact, fuzzy, partial)
4. Accountant sees a pre-reconciliation summary: "85 of 120 lines can be auto-matched"
5. Accountant reviews auto-match suggestions, approves batch
6. For remaining lines, AI provides best-guess matches with reasoning
7. Accountant matches manually; system learns from manual matches
8. Session state persists across browser sessions (come back tomorrow, pick up where you left off)

### Acceptance Criteria

- [ ] Fuzzy matching handles: partial reference numbers, rounding differences (<$0.50), split payments
- [ ] Session state persists in database (not lost on page refresh or next-day return)
- [ ] Learned match rules are stored per journal and applied to future sessions
- [ ] Pre-reconciliation summary shows auto-matchable count and review count
- [ ] Match suggestions include confidence score and explanation
- [ ] Manual matches create learned rules for similar future transactions
- [ ] Performance: processes 200 bank lines in <30 seconds

### Out of Scope

- Intermediate account cleanup (Phase 2 continuous close)
- Multi-currency reconciliation enhancements
- Bank feed auto-import (Phase 3 integration hub)

---

## 1.4 Smart Invoice Processing (IDP)

### User Journey

**Actor:** AP Clerk

1. AP Clerk uploads a vendor invoice PDF via the dashboard
2. System classifies document type (invoice, credit note, delivery note)
3. Claude Vision extracts: vendor name, invoice number, date, line items, totals, tax, PO reference
4. System fuzzy-matches vendor to Odoo partners
5. If PO reference found: cross-validates line items (quantities, prices) against PO
6. If confidence >= 0.95: auto-creates draft bill in Odoo
7. If confidence 0.85-0.95: creates draft with "needs review" flag
8. If confidence < 0.85: shows extraction results for manual review
9. AP Clerk can correct any extracted field; corrections are stored for learning

### Acceptance Criteria

- [ ] Accepts PDF and image files (JPG, PNG)
- [ ] Extracts vendor name with 95%+ accuracy
- [ ] Extracts line items (product, qty, unit price) with 90%+ accuracy
- [ ] Fuzzy-matches vendor name to Odoo `res.partner` (handles spelling variations)
- [ ] Cross-validates amounts against matched PO (flags discrepancies > 2%)
- [ ] Creates `account.move` (bill) in Odoo with correct fields
- [ ] Processing time: < 30 seconds per single-page document
- [ ] Corrections stored in `extraction_corrections` table
- [ ] Supports Arabic text (critical for GCC market)

### Out of Scope

- Batch upload of multiple documents (Phase 2)
- Multi-page invoice handling (Phase 2)
- Non-invoice document types (delivery notes, contracts -- Phase 2)

---

## 1.5 Cross-Entity Deduplication

### User Journey

**Actor:** System Admin / Data Manager

1. Admin triggers a deduplication scan for contacts (or it runs weekly via schedule)
2. System scans all `res.partner` records, comparing name, email, phone, address
3. Duplicate groups are presented with similarity scores and matched fields
4. Admin reviews each group: selects master record and approves merge, or dismisses as "not duplicate"
5. On merge: AI updates all references (invoices, orders, tickets) to point to master record
6. Real-time: when a new contact is created via webhook, system checks for existing duplicates and warns

### Acceptance Criteria

- [ ] Scans contacts (`res.partner`), leads (`crm.lead`), products (`product.product`)
- [ ] Fuzzy matching on: name (similarity > 0.85), email domain, phone number (normalized), address
- [ ] Groups presented with similarity score and which fields matched
- [ ] Master record selection preserves the record with more data / more relationships
- [ ] Merge updates all foreign key references in Odoo
- [ ] Real-time duplicate warning on new record creation (webhook-triggered)
- [ ] Weekly scheduled scan via Celery beat
- [ ] Dashboard shows: scan history, pending groups, merge history

### Out of Scope

- Automatic merge without human approval
- Product variant deduplication
- Cross-company deduplication

---

## 1.6 Customer Credit Management

### User Journey

**Actor:** Sales Rep / Credit Manager

1. System calculates credit scores for all customers daily
2. When a sales rep creates a quotation for a customer over their credit limit, the system flags it
3. Sales rep sees alert: "Customer Acme Corp exceeded credit limit. $12K overdue. Quote on hold."
4. Credit Manager reviews the hold on the dashboard
5. Credit Manager can override (release hold) or confirm hold
6. When customer pays overdue invoices, hold auto-releases and sales rep is notified

### Acceptance Criteria

- [ ] Credit score calculated from: payment history (40%), order volume (20%), overdue ratio (30%), account age (10%)
- [ ] Score range: 0-100 with risk levels: excellent (80+), good (60-79), watch (40-59), critical (<40)
- [ ] SO creation for over-limit customers triggers hold alert via webhook
- [ ] Hold auto-releases when customer's overdue amount drops below threshold
- [ ] Sales rep notified via configured channel when hold applied or released
- [ ] Dashboard shows: at-risk customers, hold status, credit utilization

### Out of Scope

- External credit bureau integration
- Automated credit limit adjustment
- Customer-facing credit portal

---

## 1.7 Natural Language Report Builder

### User Journey

**Actor:** Any Manager

1. Manager types in chat: "Show me sales by product category for Q4 2025"
2. AI parses the request into an Odoo data query (model, fields, filters, grouping)
3. System executes query against Odoo and returns a formatted table
4. Manager can refine: "Compare to Q3 2025"
5. Manager exports to Excel or PDF
6. Manager schedules: "Send me this report every Monday at 8 AM"

### Acceptance Criteria

- [ ] Parses natural language into structured Odoo query (model, domain, fields, group_by)
- [ ] Returns formatted table with column headers and row data
- [ ] Handles time periods: "last quarter", "this month", "YTD", specific dates
- [ ] Handles comparisons: "compare to last year", "vs. previous quarter"
- [ ] Excel export via `openpyxl` with formatted headers
- [ ] PDF export with company branding
- [ ] Scheduled reports delivered via email at configured times
- [ ] Error handling: graceful message if query can't be parsed or data not found

### Out of Scope

- Chart/graph generation in reports (Phase 2 dashboards)
- Cross-database queries (only queries Odoo)
- Report template designer (visual builder is Phase 3)

---

## 1.8 Cash Flow Forecasting

### User Journey

**Actor:** CFO / Finance Manager

1. CFO opens the finance dashboard and sees cash flow forecast chart
2. Chart shows predicted cash balance for next 30, 60, 90 days with confidence bands
3. Below the chart: upcoming cash gaps flagged in red
4. CFO clicks "What-if" and types: "What if Customer X pays 30 days late?"
5. System adjusts the forecast and shows the impact
6. CFO can compare multiple scenarios side by side

### Acceptance Criteria

- [ ] Forecast uses: AR aging, AP commitments, sales pipeline (weighted by probability), recurring expenses
- [ ] Generates 30/60/90-day predictions updated daily
- [ ] Confidence bands (high/low) shown for each prediction
- [ ] Cash gaps (days where balance < 0 or < threshold) highlighted
- [ ] Scenario planning accepts natural language adjustments
- [ ] Forecast accuracy tracked: predicted vs. actual (target: 90%+ within 30 days)
- [ ] Dashboard chart with interactive date range selection

### Out of Scope

- LSTM deep learning model (Phase 2 continuous close)
- Multi-currency forecasting
- Investment/financing recommendations

---

## 1.9 Slack Notification Integration

### User Journey

**Actor:** Any user receiving notifications

1. Admin configures Slack bot token in settings
2. System sends approval requests via Slack to internal team with approve/reject buttons
3. Team member clicks "Approve" in Slack; action is executed in Odoo
4. Email notifications sent for external-facing messages (payment reminders, order confirmations)

### Acceptance Criteria

- [ ] Slack: messages with interactive buttons for approvals
- [ ] Slack: button click triggers approval in AI platform
- [ ] Email fallback when Slack not configured
- [ ] Channel routing logic: message type determines primary/fallback channel
- [ ] All notifications logged in `audit_logs`

### Out of Scope

- Microsoft Teams integration (Phase 2)

---

## 1.10 Role-Based AI Dashboards

### User Journey

**Actor:** Any user with a defined role

1. User logs into the dashboard
2. System detects user role (CFO, Sales Manager, Warehouse Manager, etc.)
3. Dashboard shows role-specific view with relevant KPIs, charts, and alerts
4. Data updates in real-time via WebSocket
5. User can drill down into any metric for detail

### Acceptance Criteria

- [ ] At least 3 role views: CFO, Sales Manager, Warehouse Manager
- [ ] CFO view: cash forecast chart, P&L summary, AR/AP aging, close status, anomaly alerts
- [ ] Sales view: pipeline by stage, conversion rates, at-risk deals, quota progress
- [ ] Warehouse view: stock levels with forecast, reorder alerts, incoming shipments
- [ ] Real-time updates via WebSocket (new automation result, new approval, alert)
- [ ] Charts rendered with recharts
- [ ] Mobile-responsive layout
- [ ] Role switching available for admins

### Out of Scope

- HR Manager and Project Manager views (Phase 2)
- Custom dashboard builder (Phase 3 low-code)
- Drill-through to Odoo records (Phase 2)

---

## 1.11 Proactive AI Daily Digest

### User Journey

**Actor:** Any user subscribed to digest

1. Every morning at 7 AM, AI compiles data relevant to each role
2. AI generates a natural language summary with key metrics, attention items, and anomalies
3. Digest is delivered via user's preferred channel (email or Slack)
4. User reads digest and knows exactly what needs their attention today

### Acceptance Criteria

- [ ] Generates per-role digest with: headline, key metrics vs. yesterday, attention items, anomalies
- [ ] Delivered at configured time (default 7 AM, per-role timezone support)
- [ ] Delivered via at least 2 channels (email + Slack)
- [ ] Content is concise (< 500 words) and actionable
- [ ] Includes direct links to relevant Odoo records or dashboard sections
- [ ] Can be disabled per role
- [ ] Audit log tracks generation and delivery

### Out of Scope

- Real-time alerts (separate from digest)
- User-customizable digest content
- In-app notification center (Phase 2)
