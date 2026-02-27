# Phase 1 Sprint Plan

**Referenced by:** [MASTER_PLAN.md](MASTER_PLAN.md) -- Engineering Scaffolding
**Applies to:** Phase 1 deliverables

---

## Dependency Graph

Phase 1 deliverables are not independent. Some must be built before others.

```
                    ┌──────────────────┐
                    │  Sprint 0        │
                    │  Testing + Auth  │
                    │  + DB Schema     │
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
     ┌────────▼───────┐  ┌──▼──────────┐  ┌▼───────────────┐
     │  Sprint 1      │  │  Sprint 1   │  │  Sprint 1      │
     │  1.9 Slack     │  │  1.1 Month  │  │  1.3 Enhanced  │
     │  notify        │  │  End Close  │  │  Bank Recon    │
     └────────┬───────┘  └──┬──────────┘  └┬───────────────┘
              │              │              │
     ┌────────▼───────┐  ┌──▼──────────┐  ┌▼───────────────┐
     │  Sprint 2      │  │  Sprint 2   │  │  Sprint 2      │
     │  1.6 Credit    │  │  1.5 Dedup  │  │  1.11 Daily    │
     │  Management    │  │             │  │  Digest        │
     └────────────────┘  └─────────────┘  └────────────────┘

     ┌────────────────┐     ┌──────────────┐
     │  Sprint 3      │     │  Sprint 3    │
     │  1.11 Daily    │     │  1.4 IDP     │
     │  Digest        │     │  Smart Inv.  │
     │  (needs notify)│     │              │
     └────────────────┘     └──────────────┘

     ┌────────────────┐     ┌──────────────┐
     │  Sprint 4      │     │  Sprint 4    │
     │  1.8 Cash Flow │     │  1.7 NL      │
     │  Forecast      │     │  Report      │
     └────────────────┘     └──────────────┘

     ┌────────────────┐
     │  Sprint 5      │
     │  1.10 Role     │
     │  Dashboards    │
     └────────────────┘
```

### Key Dependencies

| Deliverable | Depends On | Why |
|-------------|-----------|-----|
| 1.11 Daily Digest | 1.9 Slack | Delivers digest via channels |
| 1.6 Credit Management | 1.1 Month-End (partial) | Shares AR aging analysis logic |
| 1.10 Role Dashboards | 1.8 Forecast + 1.1 Close | Dashboards display data from other features |
| 1.4 IDP | None (standalone) | Can be built independently |
| 1.5 Deduplication | None (standalone) | Can be built independently |
| 1.7 Report Builder | None (standalone) | Can be built independently |

---

## Sprint Breakdown

### Sprint 0: Foundation (1 week)

Before building any Phase 1 feature, set up the engineering scaffolding.

| Task | Effort | Output |
|------|--------|--------|
| Set up `pytest` + test structure + `conftest.py` | 4h | Testing framework ready |
| Create webhook payload fixtures (all 11 models) | 4h | `tests/fixtures/` populated |
| Add API key authentication to all endpoints | 3h | Secure API |
| Make webhook signature mandatory | 1h | No unsigned webhooks |
| Restrict CORS to known origins | 0.5h | Hardened CORS |
| Add `requirements-dev.txt` with test deps | 0.5h | Dev dependencies separated |
| Write unit tests for existing `BaseAutomation`, schemas, config | 8h | Baseline coverage |
| Create Alembic migrations for first batch of Phase 1 tables | 4h | DB ready |

**Exit criteria:** `pytest` passes, API requires auth, webhook signatures mandatory, 60%+ coverage on existing code.

---

### Sprint 1: Notifications + Month-End + Bank Recon (2 weeks)

Three independent features that can be developed in parallel.

#### 1.9 Slack Notification Integration

| Task | Effort |
|------|--------|
| Implement Slack interactive messages (approve/reject buttons) | 6h |
| Channel routing logic (message type -> preferred channel -> fallback) | 4h |
| Message template storage and management | 4h |
| Unit tests for notification routing | 4h |

**MVP definition:** Can send a Slack message to a channel with buttons. Fallback to email if Slack not configured.

#### 1.1 Month-End Closing Assistant

| Task | Effort |
|------|--------|
| Month-end closing data model (SQLAlchemy) + migration | 3h |
| Scan engine: query Odoo for unreconciled items, stale drafts, unbilled deliveries | 8h |
| Scan engine: missing recurring bills, tax validation, depreciation check | 6h |
| AI analysis: generate closing summary with recommendations | 4h |
| API endpoints: `POST /api/close/start`, `GET /api/close/{period}/status`, `POST /api/close/{period}/step/{step}/complete` | 6h |
| Celery task for automated pre-close scan | 3h |
| Unit tests | 6h |

**MVP definition:** User starts a closing for a period. AI scans Odoo and returns a checklist with counts (12 unreconciled, 3 stale drafts, etc.). User marks steps complete manually. Status dashboard shows progress.

#### 1.3 Enhanced Bank Reconciliation

| Task | Effort |
|------|--------|
| Reconciliation session model + migration | 2h |
| Fuzzy matching engine (partial refs, rounding, split payments) using `rapidfuzz` | 8h |
| Session memory (learned match rules persisted per journal) | 4h |
| Pre-reconciliation report (auto-matchable vs. needs review) | 4h |
| API endpoints: `POST /api/reconciliation/start`, `GET /api/reconciliation/{id}/suggestions` | 4h |
| Unit tests for fuzzy matching at various thresholds | 6h |

**MVP definition:** User starts a reconciliation session. AI returns match suggestions with confidence scores. Session remembers skipped items. Learned rules from manual matches.

---

### Sprint 2: Credit + Dedup (2 weeks)

#### 1.6 Customer Credit Management

| Task | Effort |
|------|--------|
| Credit score model + migration | 2h |
| AI credit scoring (payment history, volume, overdue analysis) | 6h |
| Credit limit enforcement on SO creation (webhook intercept) | 4h |
| Auto-hold and auto-release on payment | 3h |
| Sales rep alerts when customer near/over limit | 2h |
| API endpoint: `GET /api/credit/{customer_id}` | 2h |
| Unit tests | 4h |

**MVP definition:** Credit scores calculated daily. SO creation for over-limit customers is flagged. Auto-release when payment received.

#### 1.5 Cross-Entity Deduplication

| Task | Effort |
|------|--------|
| Dedup scan model + migration | 2h |
| Fuzzy matching engine for contacts, leads, products, vendors | 8h |
| Merge suggestion with master record selection | 4h |
| Real-time duplicate detection on record creation (webhook) | 4h |
| Weekly scheduled scan via Celery beat | 2h |
| API endpoints: `GET /api/dedup/scans`, `POST /api/dedup/{group_id}/merge` | 4h |
| Unit tests | 4h |

**MVP definition:** Weekly scan identifies duplicate contacts/leads. Dashboard shows duplicate groups with similarity scores. User can approve merge.

---

### Sprint 3: Daily Digest + IDP (2 weeks)

#### 1.11 Proactive AI Daily Digest

| Task | Effort |
|------|--------|
| Daily digest model + migration | 2h |
| Data aggregation per role (overdue items, approvals, metrics, anomalies) | 8h |
| AI-generated narrative summary per role | 4h |
| Delivery via configured channels (email, Slack) | 3h |
| Celery beat task (daily at 7 AM per timezone) | 2h |
| Role configuration (which roles get which data) | 3h |
| Unit tests | 4h |

**MVP definition:** CFO gets a morning digest with AR/AP summary, cash position, anomalies. Sales Manager gets pipeline summary and at-risk deals. Delivered via email or Slack.

#### 1.4 Smart Invoice Processing (IDP)

| Task | Effort |
|------|--------|
| Document processing model + migration | 3h |
| PDF/image preprocessing pipeline (orientation, quality) | 4h |
| Claude Vision API integration for field extraction | 8h |
| Vendor fuzzy matching (`rapidfuzz` against Odoo partners) | 4h |
| PO matching and line-item cross-validation | 6h |
| Confidence scoring per field | 3h |
| Learning loop (store corrections, adjust prompts) | 4h |
| API endpoints: `POST /api/documents/process`, `GET /api/documents/{id}` | 4h |
| Unit tests | 6h |

**MVP definition:** User uploads a PDF invoice. AI extracts vendor, date, amounts, line items. Matches to PO. Creates draft bill in Odoo if confidence > 0.95. Queues for review otherwise.

---

### Sprint 4: Forecasting + Reporting (2 weeks)

#### 1.8 Cash Flow Forecasting

| Task | Effort |
|------|--------|
| Forecast model + migration | 3h |
| Data collection from Odoo (AR, AP, pipeline, recurring expenses) | 8h |
| Prophet/statsforecast model for seasonal baseline | 8h |
| Event calendar overlay (known irregular payments) | 3h |
| Scenario planning engine (what-if adjustments) | 6h |
| Accuracy tracking (predicted vs. actual) | 3h |
| API endpoints: `GET /api/forecast/cashflow`, `POST /api/forecast/scenario` | 4h |
| Celery beat task (daily forecast regeneration) | 2h |
| Unit tests | 6h |

**MVP definition:** Daily forecast generates 30/60/90-day cash position. Dashboard shows line chart with confidence bands. User can ask what-if questions via chat.

#### 1.7 Natural Language Report Builder

| Task | Effort |
|------|--------|
| Report jobs model + migration | 2h |
| NL query parsing (Claude extracts model, fields, filters, grouping) | 6h |
| Odoo data query execution | 4h |
| Table formatting (terminal-friendly) | 3h |
| Excel export (`openpyxl`) | 4h |
| PDF export (`weasyprint` or `reportlab`) | 4h |
| Scheduled reports (Celery beat with cron expression) | 3h |
| API endpoints: `POST /api/reports/generate`, `GET /api/reports/{id}` | 3h |
| Unit tests | 4h |

**MVP definition:** User types "Sales by product category for Q4 2025" in chat. AI queries Odoo, returns formatted table. User can export to Excel.

---

### Sprint 5: Role-Based Dashboards (2 weeks)

#### 1.10 Role-Based AI Dashboards

| Task | Effort |
|------|--------|
| Dashboard API: role-specific data endpoints | 8h |
| CFO dashboard (cash forecast, P&L, AR/AP, close status) | 6h |
| Sales Manager dashboard (pipeline, conversion, rep performance) | 6h |
| Warehouse Manager dashboard (stock levels, reorder alerts, forecasts) | 4h |
| WebSocket support for real-time updates | 6h |
| Chart components (recharts integration) | 8h |
| Role detection and view switching | 4h |
| Integration tests | 6h |

**MVP definition:** Dashboard detects user role and shows relevant KPIs with charts. Real-time updates via WebSocket. At least 3 role views (CFO, Sales, Warehouse).

---

## Timeline Summary

| Sprint | Duration | Deliverables | Parallel Tracks |
|--------|----------|-------------|-----------------|
| Sprint 0 | 1 week | Foundation (tests, auth, schema) | 1 |
| Sprint 1 | 2 weeks | 1.9 Notifications, 1.1 Month-End, 1.3 Bank Recon | 3 |
| Sprint 2 | 2 weeks | 1.6 Credit, 1.5 Dedup | 2 |
| Sprint 3 | 2 weeks | 1.11 Daily Digest, 1.4 IDP | 2 |
| Sprint 4 | 2 weeks | 1.8 Cash Flow Forecast, 1.7 Report Builder | 2 |
| Sprint 5 | 2 weeks | 1.10 Role-Based Dashboards | 1 |
| **Total** | **11 weeks** | **All 11 Phase 1 deliverables** | |

**Solo developer realistic estimate:** 14-16 weeks (add 30-45% buffer for debugging, integration issues, and scope discovery).

---

## Definition of Done (per deliverable)

- [ ] Feature code complete
- [ ] Unit tests passing (80%+ coverage for feature code)
- [ ] Integration test with mock Odoo data
- [ ] API endpoints documented in FastAPI Swagger
- [ ] Alembic migration created and tested (up + down)
- [ ] Celery beat schedule configured (if applicable)
- [ ] Dashboard component or section added (if applicable)
- [ ] Audit logging for all AI decisions
- [ ] Error handling and structured logging
- [ ] Feature flag / automation rule to enable/disable
