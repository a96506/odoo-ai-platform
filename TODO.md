# Smart Odoo -- Project TODO List

**The complete task list for the entire project, ordered by execution sequence.**
**Status key:** `[x]` done | `[ ]` not started | `[~]` in progress

---

## Phase 0: Foundation -- COMPLETE

- [x] 0.1 Fix docker-compose.yml port mappings for ai-service and dashboard
- [x] 0.2 Fix odoo_ai_bridge controller JSON handling (type="http")
- [x] 0.3 Deploy 6 Docker services to Hetzner (ai-service, celery-worker, celery-beat, redis, ai-db, dashboard)
- [x] 0.4 Install odoo_ai_bridge module on live Odoo 18
- [x] 0.5 Seed 24 automation rules, test chat endpoint, verify dashboard
- [x] 0.6 Progressive activation: read-only (week 1), approval-gated (week 2), full auto (week 3)

---

## Phase 1: Core AI Expansion -- COMPLETE

> Goal: Add the automations and capabilities that save the most time immediately.
> Detail docs: [ODOO_PAIN_POINTS.md](ODOO_PAIN_POINTS.md), [FINANCE_INTELLIGENCE.md](FINANCE_INTELLIGENCE.md), [COMMUNICATION_AND_PORTALS.md](COMMUNICATION_AND_PORTALS.md)

### Sprint 0: Foundation -- COMPLETE

- [x] 1.S0a **Testing framework** -- pytest + pytest-asyncio + pytest-cov + pytest-mock; pyproject.toml config; requirements-dev.txt; in-memory SQLite test DB with StaticPool
- [x] 1.S0b **Webhook payload fixtures** -- 13 fixtures for all 11 Odoo models (account.move, crm.lead, sale.order, purchase.order, stock.picking, hr.leave, hr.expense, project.task, helpdesk.ticket, mrp.production, mailing.mailing)
- [x] 1.S0c **API key authentication** -- X-API-Key header required on all /api/ endpoints; health endpoint remains public; app/auth.py dependency
- [x] 1.S0d **Mandatory webhook signature** -- HMAC-SHA256 signature required on all webhook requests (single + batch); unsigned requests rejected with 401
- [x] 1.S0e **CORS restriction** -- restricted to known origins (dashboard, Odoo, localhost); configurable via CORS_ORIGINS env var
- [x] 1.S0f **Phase 1 database models** -- 13 new SQLAlchemy models added to audit.py (month_end_closings, closing_steps, reconciliation_sessions, document_processing_jobs, extraction_corrections, deduplication_scans, duplicate_groups, credit_scores, report_jobs, cash_forecasts, forecast_scenarios, forecast_accuracy_log, daily_digests)
- [x] 1.S0g **Alembic migration 002** -- creates all 13 Phase 1 tables with indexes; full downgrade support
- [x] 1.S0h **Baseline unit tests** -- 75 tests covering schemas, config, auth, webhook signatures, BaseAutomation, all Phase 1 models, webhook fixtures; 60%+ coverage

### New Automations (Pillar 1B)

- [x] 1.1 **Month-End Closing Assistant** -- AI-powered closing checklist tracking all 10 steps; auto-detect unreconciled bank items, stale drafts, missing bills, uninvoiced deliveries, unposted depreciation, tax validation, inter-company balances; closing status dashboard; pre-close validation report; AI-generated summary with risk assessment
- [x] 1.3 **Enhanced Bank Reconciliation** -- fuzzy matching (rapidfuzz) for partial references and rounding differences (< $0.50 / 2%); session memory across reconciliation sessions; learn from manual matches with per-journal rule persistence; pre-reconciliation report ("auto-matchable vs needs review"); multi-signal scoring (reference + amount + partner + learned rules)
- [x] 1.4 **Smart Invoice Processing (IDP)** -- vision-LLM document extraction pipeline (preprocessing -> classification -> VLM extraction -> validation); fuzzy vendor matching; line-item cross-check against PO; multi-invoice batch processing; auto-categorize non-PO expenses; 99%+ accuracy target
- [x] 1.5 **Cross-Entity Deduplication** -- scan contacts, leads, products, vendors for duplicates using fuzzy matching (name, email, phone, address); suggest merges with master record selection; block duplicates at creation time; weekly scheduled scan with dashboard report
- [x] 1.6 **Customer Credit Management** -- monitor AR aging in real-time; auto-enforce credit limits on SO creation; AI credit scoring (payment history + order volume + industry risk); alert sales rep on credit hold; auto-release holds when payment received
- [x] 1.7 **Natural Language Report Builder** -- chat command generates formatted reports from plain English; scheduled delivery ("send me this every Monday"); PDF/Excel export; period comparison ("this month vs same month last year")

### Finance Intelligence (Pillar 3A)

- [x] 1.8 **Cash Flow Forecasting** -- AI predicts cash positions 30/60/90 days out using AR/AP aging, sales pipeline, recurring expenses, seasonal patterns; hybrid model (Prophet/statsforecast + LSTM); scenario planning via natural language ("what if Customer X pays late?"); working capital optimization; daily Celery beat task

### Communication (Pillar 4A)

- [ ] 1.9 **WhatsApp/Slack notification integration** -- WhatsApp Business API for payment reminders, order confirmations, approval requests, delivery updates (98% open rate); Slack integration for internal approvals, AI alerts, daily digest; channel routing logic (urgency + recipient preference + message type); template message system

### Dashboard & UX (Pillars 2B, 2C)

- [x] 1.10 **Role-based AI dashboards** -- personalized views per role (CFO: cash flow + P&L + AR/AP + close status; Sales: pipeline + conversion + at-risk deals + quota; Warehouse: stock levels + reorder alerts + shipments); real-time WebSocket updates via Redis pub/sub; recharts integration; role switching with localStorage persistence
- [x] 1.11 **Proactive AI daily digest** -- AI-curated morning briefing per user; what needs attention today (overdue items, pending approvals, at-risk deals); key metrics vs yesterday; anomalies detected overnight; delivery via preferred channel (email/WhatsApp/Slack/in-app)

### Phase 1 Infrastructure

- [x] 1.12 **Add Python dependencies** -- rapidfuzz, pandas, numpy, pdfplumber, openpyxl, slack-sdk, aiosmtplib (all already in requirements.txt)
- [x] 1.13 **Expand database schema** -- new tables for cash_forecast, forecast_scenario, credit_score, reconciliation_session, dedup_result, document_processing_job, message_log, message_template
- [x] 1.14 **Upgrade Redis** -- increased maxmemory from 128mb to 256mb; pub/sub for real-time dashboard events
- [x] 1.15 **Dashboard upgrade** -- recharts charts (AreaChart, BarChart, LineChart); WebSocket support with auto-reconnect; role-based routing (CFO/Sales/Warehouse); centralized API helper with auth headers
- [x] 1.16 **New Celery beat tasks** -- forecast_cash_flow (daily), scan_duplicates (weekly), generate_daily_digest (daily 7 AM)
- [x] 1.17 **New API endpoints** -- /api/forecast/cashflow, /api/forecast/scenario, /api/documents/process, /api/reports/generate, /api/credit/check, /api/digest/preview, /api/dashboard/{cfo,sales,warehouse}, WS /ws/dashboard

---

## Phase 2: Intelligence & UX -- NOT STARTED

> Goal: Upgrade AI architecture, fix the biggest UX pain points, add supply chain intelligence.
> Detail docs: [AGENTIC_AI_ARCHITECTURE.md](AGENTIC_AI_ARCHITECTURE.md), [ODOO_UX_PAIN_POINTS.md](ODOO_UX_PAIN_POINTS.md), [SUPPLY_CHAIN_INTELLIGENCE.md](SUPPLY_CHAIN_INTELLIGENCE.md)

### Agentic AI (Pillar 1C)

- [ ] 2.1 **Agentic AI architecture upgrade** -- install LangGraph; build BaseAgent class alongside BaseAutomation; implement agent state persistence (Redis + PostgreSQL); agent_run/agent_step/agent_decision DB tables; build first 3 agents: CollectionAgent, ProcureToPayAgent, MonthEndCloseAgent; dashboard agent run visualization; guardrails (token budget, step limit, loop detection, EU AI Act audit trail)

### UX Day-1 Fixes (Pillar 2A)

- [ ] 2.2 **Global Search across all modules** -- single search bar searching contacts, invoices, products, orders, tasks, settings simultaneously; instant results grouped by type; Odoo OWL/JS custom widget
- [ ] 2.3 **Dark mode (native)** -- Odoo SCSS theme module with CSS variable overrides; dark/light/auto toggle in user preferences; consistent across all views including reports, wizards, popups
- [ ] 2.4 **Customer 360 view** -- single screen showing a contact's invoices, orders, tickets, projects, activities, communications, credit status; Odoo OWL component pulling cross-module data
- [ ] 2.5 **Unified Activity Center ("My Day")** -- all activities due today across CRM, tasks, invoices, tickets in one view; smart prioritization; calendar integration; Eisenhower matrix option; "what should I do next?" AI suggestion

### Finance Intelligence (Pillar 3B)

- [ ] 2.6 **Continuous close capabilities** -- upgrade month-end closing assistant to event-driven continuous reconciliation; real-time transaction matching as subledger movements occur; anomaly detection (Benford's Law, isolation forests, Z-score); instant financial statement regeneration; soft close any day

### AI Capabilities (Pillar 1D)

- [ ] 2.7 **AI onboarding assistant** -- contextual help ("How do I set up fiscal positions?" -> step-by-step guide with direct links); proactive tips based on user behavior; interactive setup wizards for first-time module configuration; feature discovery suggestions

### Supply Chain (Pillar 6A)

- [ ] 2.8 **Supply chain risk intelligence** -- supplier risk scoring (7 weighted factors: delivery, quality, price, financial health, geographic, dependency, responsiveness); delivery delay prediction (2-6 weeks ahead); single-source risk detection; supply chain alerts; alternative supplier auto-suggestion; procurement dashboard

### UX Improvements (Pillar 2A, 2D)

- [ ] 2.9 **Auto-save feedback + edit mode clarity** -- clear visual distinction between view and edit mode; "unsaved changes" indicator; Ctrl+Z undo; confirmation before auto-saving unintended changes; Odoo OWL widget
- [ ] 2.10 **Notification intelligence** -- priority levels for notifications; daily/weekly digest option; separate streams for system changes vs human messages; smart filtering; @mention with channel-based organization

### Phase 2 Infrastructure

- [ ] 2.11 **Add LangGraph dependencies** -- langgraph, langgraph-checkpoint-postgres, langgraph-checkpoint-redis
- [ ] 2.12 **Odoo frontend modules** -- create separate installable Odoo modules for: global search widget, dark mode theme, Customer 360 view, activity center, auto-save feedback, notification intelligence
- [ ] 2.13 **Expand database schema** -- agent_run, agent_step, agent_decision, agent_suspension, supplier_risk_score, supplier_risk_factor, disruption_prediction, supply_chain_alert, alternative_supplier_map
- [ ] 2.14 **New Celery beat tasks** -- calculate_supplier_risk_scores (daily), detect_delivery_degradation (every 6 hours), single_source_risk_scan (weekly)

---

## Phase 3: Platform & Portals -- NOT STARTED

> Goal: Build the platform layer enabling self-service, external integration, and user empowerment.
> Detail docs: [COMMUNICATION_AND_PORTALS.md](COMMUNICATION_AND_PORTALS.md), [PLATFORM_CAPABILITIES.md](PLATFORM_CAPABILITIES.md), [FINANCE_INTELLIGENCE.md](FINANCE_INTELLIGENCE.md)

### Portals (Pillar 4B, 4C)

- [ ] 3.1 **Customer self-service portal** -- order dashboard with real-time status; invoice center with online payment; one-click reorder from history; RFQ submission; product catalog with account-specific pricing; stock visibility; support ticket submission; document center; start with Odoo built-in portal, evaluate Next.js rebuild
- [ ] 3.2 **Vendor self-service portal** -- PO management (view, acknowledge, confirm); delivery status updates; invoice submission with IDP auto-processing; performance scorecard (on-time delivery, quality, price, response time); payment status; communication threads linked to POs

### Platform Capabilities (Pillar 5A, 5B, 5D)

- [ ] 3.3 **Integration hub** -- connector framework with credential vault and sync log; Open Banking API for bank statement sync; Stripe/PayPal/Tap payment gateway connectors; DHL/Aramex/FedEx shipping connectors (auto-tracking, label generation); bank file import (MT940, CAMT, OFX, CSV); scheduled + event-driven + on-demand sync modes
- [ ] 3.4 **Low-code automation builder** -- visual "if X happens, do Y" rule builder in dashboard; trigger library (record events, field changes, dates, thresholds); action library (notifications, record operations, AI analysis); condition builder with AND/OR logic; test mode; template library of common automations; React-based UI with react-flow
- [ ] 3.5 **MCP protocol server for Odoo** -- standards-compliant Model Context Protocol server; expose Odoo models as resources; tools for read/search/create/update; pre-built prompt templates; role-based access control; read operations free, write operations through approval gating; audit trail; Python mcp package

### Compliance (Pillar 3C)

- [ ] 3.6 **Real-time compliance monitoring** -- always-on tax rule checker scanning every transaction; fiscal position validation; regulatory change detection (VAT rate changes, e-invoicing mandates); automated remediation suggestions; country-specific modules (EU ViDA, GCC VAT/ZATCA, US sales tax nexus, UK MTD)

### UX (Pillar 2D)

- [ ] 3.7 **Central approval inbox with badges** -- dedicated approval center with count badges on menu; push notifications for "your approval is needed"; automatic escalation when approval sits too long; approval history on record header; mobile-optimized approval flow
- [ ] 3.8 **Data import wizard redesign** -- drag-and-drop CSV/Excel upload; automatic column detection and mapping; preview with validation warnings before committing; background processing with progress bar; clear error messages with fix suggestions; no more "import-compatible export" confusion

### Phase 3 Infrastructure

- [ ] 3.9 **Portal authentication** -- JWT or nextauth layer for portal users; Odoo portal user integration; role-based access (customer vs vendor); secure API gateway
- [ ] 3.10 **Payment gateway integration** -- Stripe SDK, PayPal SDK, Tap SDK (GCC); webhook receivers for payment confirmations; auto-reconciliation with Odoo payments
- [ ] 3.11 **Shipping carrier SDKs** -- DHL, Aramex, FedEx API integrations; label generation; tracking webhook receivers
- [ ] 3.12 **New database tables** -- automation_rule_v2 (low-code rules as JSON), connector_config, sync_log, portal_user, mcp_query_log, compliance_check, compliance_alert

---

## Phase 4: Scale & Polish -- NOT STARTED

> Goal: Advanced capabilities, full UX overhaul, and platform maturity.
> Detail docs: [PLATFORM_CAPABILITIES.md](PLATFORM_CAPABILITIES.md), [ODOO_UX_PAIN_POINTS.md](ODOO_UX_PAIN_POINTS.md)

### Advanced Capabilities (Pillar 5E, 3C)

- [ ] 4.1 **Digital twins & scenario simulation** -- virtual models of business operations using historical Odoo data; Monte Carlo simulation (simpy); inventory scenarios ("what if demand +20%?"); finance scenarios ("what if largest customer goes bankrupt?"); supply chain scenarios ("what if Supplier X fails?"); pricing scenarios ("impact of 5% price increase"); AI-generated narrative summaries
- [ ] 4.5 **ESG / sustainability reporting** -- collect ESG metrics from Odoo operations data (energy from bills, travel from expenses, procurement from POs); map to frameworks (CSRD, IFRS S1/S2, GRI); generate compliance-ready reports with audit trail; track progress toward targets

### UX Improvements (Pillar 2D, 2E, 2F)

- [ ] 4.2 **Offline / PWA mode** -- Service Worker + IndexedDB for offline action queuing; background sync when connectivity restored; optimized for warehouse workers, field sales, delivery drivers; low-bandwidth mode
- [ ] 4.3 **PDF report engine upgrade** -- replace wkhtmltopdf with WeasyPrint or Playwright-based renderer; reliable header/footer rendering; WYSIWYG report designer; beautiful default templates; multi-page layout stability
- [ ] 4.4 **Form view progressive disclosure** -- essential fields visible by default; advanced fields in collapsible sections; smart defaults pre-filling common values; visual hierarchy guiding the eye; reduce Studio-induced clutter
- [ ] 4.8 **One-page checkout for eCommerce** -- single-page checkout replacing multi-step flow; guest checkout by default; express payment (Apple Pay, Google Pay); trust badges; cart persistence across sessions
- [ ] 4.9 **Backend theme editor / white-label** -- backend theme editor with color palette, font choices, logo placement; white-label mode for partners; customer-facing document template builder with live preview
- [ ] 4.10 **Keyboard navigation + macros** -- full keyboard navigation with customizable shortcuts; logical tab order in forms; command palette for every action; macro recorder for repetitive operations
- [ ] 4.11 **Headless commerce API** -- REST/GraphQL API layer for custom storefronts; decoupled frontend architecture; Shopify-level theme capability

### Gap Features (Pillar 6B, 6C)

- [ ] 4.6 **Cross-system data unification** -- unified data layer connecting Odoo with external sources; real-time bank feed sync; shipping carrier tracking status; government portal data (tax filing, registration); market data (commodity prices, exchange rates)
- [ ] 4.7 **Multi-company orchestration** -- inter-company SO/PO auto-creation; inter-company bank transfer journal entries; per-company route/warehouse configuration; consolidated reporting; prevent wrong-company context errors
- [ ] 4.12 **Vendor performance tracking** -- delivery compliance scoring dashboard; quality issue aggregation by vendor; price trend analysis over time; vendor comparison reports; automated scorecarding
- [ ] 4.13 **Order lifecycle tracking** -- unified view from quote -> SO -> delivery -> invoice -> payment with status at each step; "where's my order?" one-screen answer; customer-facing tracking page

### Phase 4 Infrastructure

- [ ] 4.14 **Add simulation dependencies** -- simpy (discrete event simulation), Monte Carlo engine
- [ ] 4.15 **Service Worker + IndexedDB** -- PWA infrastructure for offline mode
- [ ] 4.16 **PDF engine replacement** -- WeasyPrint or Playwright integration; remove wkhtmltopdf dependency
- [ ] 4.17 **Headless API layer** -- GraphQL or REST gateway for custom storefronts

---

## Summary

| Phase | Items | Status |
|-------|-------|--------|
| Phase 0: Foundation | 6 | COMPLETE |
| Phase 1: Sprint 0 Foundation | 8 | COMPLETE |
| Phase 1: Core AI Expansion | 17 | COMPLETE (16/17 done, 1.9 deferred) |
| Phase 2: Intelligence & UX | 14 | Not started |
| Phase 3: Platform & Portals | 12 | Not started |
| Phase 4: Scale & Polish | 17 | Not started |
| **TOTAL** | **74** | **30 done, 44 remaining** |
