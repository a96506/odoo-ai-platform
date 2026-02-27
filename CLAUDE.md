# Odoo AI Automation Platform

AI-powered automation layer for Odoo Enterprise ERP on Hetzner/Dokploy.

## Project Plan

The **[MASTER_PLAN.md](MASTER_PLAN.md)** is the single source of truth for all project end goals. It covers 6 pillars, 4 delivery phases, and 40+ features that transform standard Odoo into "Smart Odoo."

**[TODO.md](TODO.md)** is the project-wide task list with all 66 deliverables ordered by execution sequence. Check it before starting any work and update it when completing tasks. Status: `[x]` done, `[ ]` not started, `[~]` in progress.

### Document Index

| Document | Purpose |
|----------|---------|
| [TODO.md](TODO.md) | **Project-wide task list** -- all 66 deliverables ordered by execution sequence, update on completion |
| [MASTER_PLAN.md](MASTER_PLAN.md) | Definitive roadmap -- all end goals, 6 pillars, 4 phases, architecture, competitive benchmark |
| [WHAT_WE_AUTOMATE.md](WHAT_WE_AUTOMATE.md) | Detailed descriptions of the 10 deployed automation modules (Pillar 1A) |
| [ODOO_PAIN_POINTS.md](ODOO_PAIN_POINTS.md) | 25 ranked user pain points, coverage gaps, 7 proposed new automations (Pillars 1B, 6B) |
| [ODOO_UX_PAIN_POINTS.md](ODOO_UX_PAIN_POINTS.md) | 20 UX/UI issues, design principles, competitive UX benchmark (Pillar 2) |
| [AGENTIC_AI_ARCHITECTURE.md](AGENTIC_AI_ARCHITECTURE.md) | Agentic AI upgrade: LangGraph, agent design patterns, 7 planned agents, guardrails (Pillar 1C) |
| [FINANCE_INTELLIGENCE.md](FINANCE_INTELLIGENCE.md) | Cash flow forecasting, continuous close, compliance monitoring, ESG reporting (Pillar 3) |
| [COMMUNICATION_AND_PORTALS.md](COMMUNICATION_AND_PORTALS.md) | Slack/Teams integration, customer portal, vendor portal (Pillar 4) |
| [PLATFORM_CAPABILITIES.md](PLATFORM_CAPABILITIES.md) | Low-code builder, integration hub, IDP, MCP protocol, digital twins (Pillar 5) |
| [SUPPLY_CHAIN_INTELLIGENCE.md](SUPPLY_CHAIN_INTELLIGENCE.md) | Supplier risk scoring, disruption prediction, alternative supplier intelligence (Pillar 6A) |
| [TESTING_STRATEGY.md](TESTING_STRATEGY.md) | Test layers, mock strategy, CI/CD pipeline, coverage targets |
| [PHASE1_DATABASE_SCHEMA.md](PHASE1_DATABASE_SCHEMA.md) | 13 new Phase 1 table definitions, migration sequence, indexing |
| [SECURITY.md](SECURITY.md) | Authentication, secrets management, data privacy, CORS, input validation |
| [PHASE1_SPRINT_PLAN.md](PHASE1_SPRINT_PLAN.md) | Dependency graph, 6 sprints with effort estimates, definition of done |
| [PROMPT_ENGINEERING.md](PROMPT_ENGINEERING.md) | Prompt catalog, model selection, cost estimation, versioning, fallback behavior |
| [API_CONTRACTS.md](API_CONTRACTS.md) | Phase 1 endpoint specs, request/response schemas, WebSocket events, rate limits |
| [OBSERVABILITY.md](OBSERVABILITY.md) | Structured logging, health checks, metrics, alerting, distributed tracing |
| [DEPLOYMENT_OPS.md](DEPLOYMENT_OPS.md) | Environments, deployment, rollback, feature flags, backups, disaster recovery |
| [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md) | User journeys and acceptance criteria for all 11 Phase 1 deliverables |
| [README.md](README.md) | Architecture overview, deployment guide, API endpoints |
| [LOGBOOK.md](LOGBOOK.md) | Chronological development log -- sessions, deployments, decisions |
| [LESSONS_LEARNED.md](LESSONS_LEARNED.md) | Error loops, root causes, and fixes discovered during development |

### Document Reading Order & Dependencies

Files are grouped into tiers. Read all files in a tier before moving to the next.

**Tier 0 -- Standalone (no prerequisites)**

| File | Why It's Safe to Read First |
|------|-----------------------------|
| [WHAT_WE_AUTOMATE.md](WHAT_WE_AUTOMATE.md) | Describes the 10 deployed Phase 0 automations, no external references |
| [ODOO_UX_PAIN_POINTS.md](ODOO_UX_PAIN_POINTS.md) | Standalone UX research, no dependencies |
| [README.md](README.md) | Quick-start guide, self-contained |

**Tier 1 -- Core Planning (read Tier 0 first)**

| File | Read These First | Why |
|------|-----------------|-----|
| [ODOO_PAIN_POINTS.md](ODOO_PAIN_POINTS.md) | WHAT_WE_AUTOMATE, ODOO_UX_PAIN_POINTS | References coverage gaps vs existing automations, links to UX doc |
| [MASTER_PLAN.md](MASTER_PLAN.md) | All Tier 0 + ODOO_PAIN_POINTS | Root document -- defines all 6 pillars, 4 phases, 40+ features; references every other file |
| [TODO.md](TODO.md) | MASTER_PLAN | Task list tracks all 66 deliverables defined in the master plan |

**Tier 2 -- Pillar Detail Docs (read MASTER_PLAN first)**

Each deep-dives into one pillar. Only need MASTER_PLAN + the pillar-specific pain point doc.

| File | Read First | Pillar |
|------|-----------|--------|
| [AGENTIC_AI_ARCHITECTURE.md](AGENTIC_AI_ARCHITECTURE.md) | MASTER_PLAN (Pillar 1C) | Multi-step autonomous agents, LangGraph, guardrails |
| [FINANCE_INTELLIGENCE.md](FINANCE_INTELLIGENCE.md) | MASTER_PLAN (Pillar 3), ODOO_PAIN_POINTS (#3 month-end) | Cash flow forecasting, continuous close, compliance |
| [COMMUNICATION_AND_PORTALS.md](COMMUNICATION_AND_PORTALS.md) | MASTER_PLAN (Pillar 4) | Slack, customer portal, vendor portal |
| [PLATFORM_CAPABILITIES.md](PLATFORM_CAPABILITIES.md) | MASTER_PLAN (Pillar 5) | IDP, low-code builder, MCP protocol, digital twins |
| [SUPPLY_CHAIN_INTELLIGENCE.md](SUPPLY_CHAIN_INTELLIGENCE.md) | MASTER_PLAN (Pillar 6A) | Supplier risk scoring, disruption prediction |

**Tier 3 -- Engineering Scaffolding (read MASTER_PLAN + relevant pillar docs)**

These define **how** to build. Each needs the master plan plus the pillar docs for the features it covers.

| File | Read First | Needed Before |
|------|-----------|---------------|
| [PHASE1_DATABASE_SCHEMA.md](PHASE1_DATABASE_SCHEMA.md) | MASTER_PLAN, FINANCE_INTELLIGENCE, ODOO_PAIN_POINTS, COMMUNICATION_AND_PORTALS | Any Phase 1 DB migration (13 new tables) |
| [API_CONTRACTS.md](API_CONTRACTS.md) | MASTER_PLAN, PHASE1_DATABASE_SCHEMA | Any new API endpoint development |
| [PHASE1_SPRINT_PLAN.md](PHASE1_SPRINT_PLAN.md) | MASTER_PLAN, all Phase 1 pillar docs | Planning sprint work (dependency graph, effort estimates) |
| [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md) | MASTER_PLAN, API_CONTRACTS | Knowing when any Phase 1 feature is "done" |
| [PROMPT_ENGINEERING.md](PROMPT_ENGINEERING.md) | MASTER_PLAN, TESTING_STRATEGY | Any AI prompt changes or new automations |
| [TESTING_STRATEGY.md](TESTING_STRATEGY.md) | MASTER_PLAN, this file (CLAUDE.md) | Setting up tests, writing test suites |
| [SECURITY.md](SECURITY.md) | MASTER_PLAN | Any auth, CORS, or secrets work |
| [OBSERVABILITY.md](OBSERVABILITY.md) | MASTER_PLAN | Logging, health checks, alerting |
| [DEPLOYMENT_OPS.md](DEPLOYMENT_OPS.md) | MASTER_PLAN | Any deployment, rollback, or infra work |

**Phase 1 Kickoff -- Read in This Exact Order**

1. `MASTER_PLAN.md` -- understand everything
2. `TODO.md` -- see what's done (Phase 0) and what's next (Phase 1)
3. `PHASE1_SPRINT_PLAN.md` -- dependency graph tells you build order
4. `SECURITY.md` + `TESTING_STRATEGY.md` -- Sprint 0 requires auth + test scaffolding first
5. `PHASE1_DATABASE_SCHEMA.md` -- 13 new tables to migrate
6. `API_CONTRACTS.md` -- endpoint specs for whatever you're building
7. `ACCEPTANCE_CRITERIA.md` -- definition of "done" for each deliverable
8. The pillar doc for the feature you're building (e.g., `FINANCE_INTELLIGENCE.md` for cash flow)
9. `PROMPT_ENGINEERING.md` -- when writing Claude prompts for new automations

## Structure

```
odoo-ai-platform/
├── docker-compose.yml           # 6 services: AI, Celery worker, Celery beat, Redis, PostgreSQL, Dashboard
├── .env.example                 # Environment variables template
├── .gitignore                   # Git ignore rules
├── README.md                    # Quick start guide
├── CLAUDE.md                    # This file
│
├── ai_service/                  # FastAPI AI brain (Python 3.12)
│   ├── Dockerfile
│   ├── .dockerignore
│   ├── requirements.txt
│   ├── requirements-dev.txt     # Dev/test deps (extends requirements.txt)
│   ├── pyproject.toml           # pytest + coverage config
│   ├── alembic.ini              # Alembic migration config
│   ├── alembic/                 # Database migrations
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/
│   │       ├── 001_extend_automation_type_enum.py
│   │       ├── 002_phase1_tables.py  # 13 new Phase 1 tables
│   │       └── 003_phase2_tables.py  # 9 new Phase 2 tables (agents + supply chain)
│   ├── tests/                   # pytest suite (443 tests)
│   │   ├── conftest.py          # In-memory SQLite DB, TestClient, mocks
│   │   ├── fixtures/
│   │   │   └── webhook_payloads.py  # 13 fixtures for all 11 Odoo models
│   │   ├── test_auth.py         # API key + webhook signature tests
│   │   ├── test_base_automation.py  # BaseAutomation routing/gating tests
│   │   ├── test_month_end_closing.py  # Month-end closing automation + API tests (22 tests)
│   │   ├── test_bank_reconciliation.py  # Fuzzy matching engine + API tests (19 tests)
│   │   ├── test_deduplication.py # Dedup matching engine + API tests (29 tests)
│   │   ├── test_credit_management.py # Credit scoring engine + API tests (42 tests)
│   │   ├── test_document_processing.py # IDP extraction + vendor match + API tests (28 tests)
│   │   ├── test_daily_digest.py  # Daily digest generation + delivery + API tests (24 tests)
│   │   ├── test_cash_flow.py     # Cash flow forecasting engine + scenarios + API tests (39 tests)
│   │   ├── test_report_builder.py # NL report builder + exports + API tests (50 tests)
│   │   ├── test_role_dashboard.py # Role-based dashboards + WebSocket + schemas (35 tests)
│   │   ├── test_slack.py        # Slack integration: channel, Block Kit, interactions, digest (29 tests)
│   │   ├── test_agents.py       # BaseAgent, Orchestrator, concrete agents + API tests (28 tests)
│   │   ├── test_supply_chain.py # Anomaly detector, risk scoring, supply chain API tests (26 tests)
│   │   ├── test_config.py       # Settings property tests
│   │   ├── test_fixtures.py     # Fixture validation tests
│   │   ├── test_models.py       # All 18 model CRUD tests
│   │   └── test_schemas.py      # Pydantic schema tests
│   └── app/
│       ├── __init__.py          # Package init
│       ├── main.py              # FastAPI app factory (lean: lifespan + router includes)
│       ├── auth.py              # API key auth dependency (X-API-Key header)
│       ├── config.py            # pydantic-settings configuration (incl. Phase 1+2 fields)
│       ├── odoo_client.py       # Odoo XML-RPC client wrapper
│       ├── claude_client.py     # Anthropic Claude API wrapper (tool-use)
│       ├── chat.py              # Natural language ERP chat interface
│       ├── onboarding.py        # AI onboarding assistant (role tips, contextual suggestions)
│       ├── models/
│       │   ├── __init__.py      # Package init
│       │   ├── audit.py         # SQLAlchemy models (25 tables) + get_db helpers
│       │   └── schemas.py       # Pydantic request/response schemas
│       ├── agents/              # Phase 2 Agentic AI (LangGraph-based multi-step agents)
│       │   ├── __init__.py      # Agent registry + init_agents()
│       │   ├── base_agent.py    # BaseAgent ABC (state, guardrails, persistence, suspend/resume)
│       │   ├── orchestrator.py  # AgentOrchestrator singleton (select, run, resume, list agents)
│       │   ├── procure_to_pay.py # ProcureToPayAgent (invoice → PO match → bill → post)
│       │   ├── collection.py    # CollectionAgent (overdue invoice → strategy → message → escalate)
│       │   └── month_end_close.py # MonthEndCloseAgent (scan → anomaly → auto-resolve → report)
│       ├── routers/
│       │   ├── __init__.py      # Package init
│       │   ├── health.py        # GET /health
│       │   ├── dashboard.py     # GET /api/stats, /api/audit-logs, POST /api/approve
│       │   ├── rules.py         # CRUD /api/rules
│       │   ├── chat.py          # POST /api/chat, /api/chat/confirm, GET /api/chat/onboarding, GET /api/chat/suggestions
│       │   ├── insights.py      # GET /api/insights, POST /api/trigger
│       │   ├── closing.py       # POST /api/close/start, GET /api/close/{period}/status, POST step/complete, POST rescan
│       │   ├── reconciliation.py # POST /api/reconciliation/start, GET suggestions, POST match/skip
│       │   ├── deduplication.py # POST /api/dedup/scan, GET scans, POST merge/dismiss, POST check
│       │   ├── credit.py       # GET /api/credit/{id}, POST check, POST recalculate, POST releases
│       │   ├── documents.py    # POST /api/documents/process, GET /{id}, POST /{id}/correct
│       │   ├── digest.py       # GET /api/digest/latest, POST send, PUT config, GET history, GET preview
│       │   ├── forecast.py     # GET /api/forecast/cashflow, POST scenario, GET accuracy, GET/GET scenarios
│       │   ├── reports.py      # POST /api/reports/generate, GET /{id}, GET /{id}/download, POST schedule
│       │   ├── role_dashboard.py # GET /api/dashboard/{cfo,sales,warehouse} — role-specific aggregated views
│       │   ├── websocket.py    # WS /ws/dashboard — real-time updates via Redis pub/sub
│       │   ├── slack.py        # POST /api/slack/interactions — Slack interactive button callbacks
│       │   ├── agents.py       # POST /api/agents/run, GET /api/agents/runs, GET types, POST resume
│       │   └── supply_chain.py # GET /api/supply-chain/risk-scores, alerts, predictions, POST scan
│       ├── automations/
│       │   ├── __init__.py      # Automation registry
│       │   ├── base.py          # BaseAutomation class (+ handle_batch, notify)
│       │   ├── accounting.py    # Transaction categorization, reconciliation, anomaly
│       │   ├── month_end.py     # Month-end closing assistant (10-step scan engine + AI summary)
│       │   ├── reconciliation.py # Enhanced bank reconciliation (fuzzy matching + learned rules)
│       │   ├── crm.py           # Lead scoring, assignment, follow-ups, duplicates
│       │   ├── sales.py         # Quotation generation, pricing, pipeline forecast
│       │   ├── purchase.py      # Auto-PO, vendor selection, bill matching
│       │   ├── inventory.py     # Demand forecast, auto-reorder, product categorization
│       │   ├── hr.py            # Leave approval, expense processing
│       │   ├── project.py       # Task assignment, duration estimation, risk detection
│       │   ├── helpdesk.py      # Ticket categorization, assignment, solution suggestion
│       │   ├── manufacturing.py # Production scheduling, quality control
│       │   ├── marketing.py     # Contact segmentation, campaign optimization
│       │   ├── cross_app.py     # Cross-module intelligence engine
│       │   ├── deduplication.py # Cross-entity dedup (fuzzy name/email/phone/VAT matching)
│       │   ├── credit.py        # Customer credit scoring + limit enforcement
│       │   ├── document_processing.py # Vision-LLM invoice extraction + fuzzy vendor matching
│       │   ├── daily_digest.py  # Role-based daily briefing (CFO/Sales/Warehouse)
│       │   ├── cash_flow.py     # 30/60/90-day cash flow forecasting + scenarios
│       │   ├── report_builder.py # NL query → Odoo data → table/Excel/PDF export
│       │   ├── anomaly_detection.py # Benford's Law + Z-score statistical anomaly detection
│       │   └── supply_chain.py  # Supplier risk scoring, disruption prediction, single-source detection
│       ├── notifications/
│       │   ├── __init__.py      # Package init
│       │   ├── base.py          # NotificationChannel abstract base
│       │   ├── email.py         # SMTP email channel
│       │   ├── slack.py         # Slack SDK channel (Block Kit, interactive buttons, digest)
│       │   └── service.py       # NotificationService (unified router)
│       ├── webhooks/
│       │   ├── __init__.py      # Package init
│       │   └── handlers.py      # Webhook endpoints (receives Odoo events)
│       └── tasks/
│           ├── __init__.py      # Package init
│           ├── celery_app.py    # Celery config + beat schedules
│           └── celery_tasks.py  # Async task definitions
│
├── odoo_ai_bridge/              # Custom Odoo module (installed in Odoo)
│   ├── __manifest__.py          # Module manifest (depends on all ERP modules)
│   ├── models/
│   │   ├── ai_config.py         # AI configuration model (URL, secret, toggles)
│   │   ├── ai_webhook_mixin.py  # Abstract mixin: fires webhooks on CRUD
│   │   ├── account_move.py      # Accounting webhook hooks
│   │   ├── crm_lead.py          # CRM webhook hooks
│   │   ├── sale_order.py        # Sales webhook hooks
│   │   ├── purchase_order.py    # Purchase webhook hooks
│   │   ├── stock_picking.py     # Inventory webhook hooks
│   │   ├── hr_leave.py          # HR Leave webhook hooks
│   │   ├── hr_expense.py        # HR Expense webhook hooks
│   │   ├── project_task.py      # Project webhook hooks
│   │   ├── helpdesk_ticket.py   # Helpdesk webhook hooks
│   │   ├── mrp_production.py    # Manufacturing webhook hooks
│   │   └── mailing_mailing.py   # Marketing webhook hooks
│   ├── controllers/
│   │   └── ai_callback.py       # HTTP endpoints AI calls back to (read/write/action)
│   ├── security/
│   │   └── ir.model.access.csv  # Access rights
│   ├── data/
│   │   └── ai_config_data.xml   # Default configuration record
│   ├── static/
│   │   └── description/
│   │       └── icon.svg         # Module icon
│   └── views/
│       └── ai_config_views.xml  # Configuration form + menu
│
├── dashboard/                   # Next.js + Tailwind monitoring UI
│   ├── Dockerfile
│   ├── .dockerignore
│   ├── package.json             # next 14, react 18, tailwindcss, recharts
│   ├── public/                  # Static assets (favicon etc.)
│   └── src/
│       ├── app/
│       │   ├── layout.js
│       │   ├── page.js          # Main dashboard (role switching + 6 tabs)
│       │   └── globals.css
│       ├── lib/
│       │   └── api.js           # Centralized API helper with X-API-Key auth
│       ├── hooks/
│       │   └── useWebSocket.js  # WebSocket hook with auto-reconnect
│       └── components/
│           ├── StatsCards.js     # KPI cards (total, success rate, approvals, time saved)
│           ├── AuditLog.js      # Automation audit trail
│           ├── ApprovalQueue.js # Human-in-the-loop approval UI
│           ├── RulesPanel.js    # Enable/disable automation rules
│           ├── ChatInterface.js # Natural language ERP chat
│           ├── InsightsPanel.js # Cross-app intelligence results
│           ├── RoleSwitcher.js  # Role selection dropdown (CFO/Sales/Warehouse/Overview)
│           ├── CFODashboard.js  # Cash forecast AreaChart, AR/AP aging, P&L, close status
│           ├── SalesDashboard.js # Pipeline BarChart, conversion funnel, at-risk deals
│           ├── WarehouseDashboard.js # Stock levels chart, reorder alerts, shipments
│           ├── AgentDashboard.js # AI agent runs table, type filter, step detail view
│           └── SupplyChainDashboard.js # Vendor risk scores, alerts, predictions, scan trigger
│
└── scripts/
    ├── deploy.sh                # Docker deployment script
    ├── setup_odoo_webhooks.py   # Verify/configure Odoo AI Bridge module
    └── seed_automation_rules.py # Seed default automation rules
```

## Key Commands

```bash
# Deploy everything (validates .env, builds, starts, health-checks)
./scripts/deploy.sh

# Or manually
docker compose up -d --build

# Check health
curl http://localhost:8000/health

# API docs
open http://localhost:8000/docs

# Dashboard
open http://localhost:3000

# Setup Odoo module + configure webhook URL
python3 scripts/setup_odoo_webhooks.py

# Seed all 24 automation rules via API
python3 scripts/seed_automation_rules.py

# View logs
docker compose logs -f ai-service
docker compose logs -f celery-worker

# Run Celery worker locally (dev)
celery -A app.tasks.celery_app:celery_app worker --loglevel=info

# Database migrations (from ai_service/ directory)
alembic revision --autogenerate -m "description"
alembic upgrade head

# Run tests (from ai_service/ directory)
python -m pytest tests/ -v
python -m pytest tests/ --cov=app --cov-report=term-missing
```

## Dependencies

### AI Service (Python)
- fastapi, uvicorn, pydantic, pydantic-settings
- anthropic (Claude API with tool-use)
- celery, redis (async task queue)
- sqlalchemy, psycopg2-binary, alembic (DB)
- httpx, structlog, tenacity
- rapidfuzz (fuzzy string matching for bank recon + dedup)
- pandas, numpy (data processing and forecasting)
- openpyxl (Excel report generation)
- pdfplumber (PDF parsing for IDP)
- slack-sdk (Slack Block Kit messaging, interactive buttons, approval workflow)
- aiosmtplib (async email sending)
- langgraph, langgraph-checkpoint-postgres (Phase 2 agentic AI graph execution)

### Dashboard (Node.js)
- next 14, react 18, tailwindcss 3
- recharts (charts and data visualization)
- date-fns (date utilities)

## Architecture

- **Odoo** fires webhooks on record CRUD via `ai_webhook_mixin`
- **AI Service** receives webhooks, dispatches to Celery, analyzes with Claude
- **Claude tool-use** returns structured decisions with confidence scores
- **Confidence gating**: >=0.95 auto-execute, 0.85-0.95 needs approval, <0.85 logged only
- **Dashboard** shows audit trail, approval queue, rules config, chat, insights

## Mandatory Workflow

**Before writing ANY code that uses an external library, you MUST:**

1. Call `resolve-library-id` to get the Context7 library ID
2. Call `get-library-docs` with a focused query about the API you're about to use
3. Use the returned docs as source of truth — not training data

This applies to: FastAPI, SQLAlchemy, Alembic, Pydantic, Celery, Anthropic SDK, React, Next.js, Tailwind, pytest, httpx, structlog, redis, slack-sdk, pandas, and any other dependency.

**No exceptions.** If Context7 returns nothing, say so and proceed with best knowledge. Never fabricate an API.

## Design Rules

- All automations inherit from `BaseAutomation` in `base.py`
- Every AI decision is logged in `AuditLog` with confidence + reasoning
- Write/destructive actions from chat require explicit user confirmation
- Odoo module uses abstract mixin pattern for minimal code per model
- ai.config has per-module toggles: enable_accounting, enable_crm, enable_sales, enable_purchase, enable_inventory, enable_hr, enable_project, enable_helpdesk, enable_manufacturing, enable_marketing
- `AutomationType` enum includes: accounting, crm, sales, purchase, inventory, hr, project, helpdesk, manufacturing, marketing, cross_app, month_end, deduplication, credit_management, forecasting, reporting, document_processing
- Celery tasks check `AutomationRule.enabled` before executing any automation
- Webhook signature (HMAC-SHA256) is **mandatory** on all incoming Odoo webhooks; unsigned requests are rejected with 401
- DB engine and session factory are cached as module-level singletons for connection pooling
- FastAPI endpoints use `Depends(get_db)` for session lifecycle; Celery tasks use `with get_db_session()` context manager
- API routes are split into routers: health, dashboard, rules, chat, insights, closing, reconciliation, deduplication, credit, documents, digest, forecast, reports, role_dashboard, websocket, slack (main.py is a lean app factory)
- `BaseAutomation` provides `handle_batch()` for multi-record processing and `notify()` for sending messages via channels
- `NotificationService` routes messages to email/slack channels; channels are auto-registered and checked via `is_configured()`
- Settings includes optional Phase 1 config fields (Slack, SMTP, forecasting, IDP) -- all disabled by default
- Cross-app intelligence runs every 6 hours via Celery beat
- Docker services use health-check-based `depends_on` for proper startup ordering
- PostgreSQL credentials are sourced from env vars (POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB)
- AI DB hostname is `ai-db` (must match in AI_DATABASE_URL)
- deploy.sh validates .env placeholders before building
- Odoo MCP server configured via `ODOO_MCP_URL` and `ODOO_MCP_TRANSPORT` env vars; API key stored in `ODOO_API_KEY`
- Celery worker initializes automations and DB via `worker_init` signal (not just FastAPI lifespan)
- Celery task discovery uses explicit `include=["app.tasks.celery_tasks"]` in `conf.update()` (not `autodiscover_tasks`)
- `odoo_ai_bridge` callbacks use `type="http"` (not `type="json"`) for raw JSON POST compatibility
- `helpdesk` module is optional: conditionally imported only if `odoo.addons.helpdesk` is installed
- Deployed services are routed via Traefik (no direct port mappings in Dokploy environment)
- Live endpoints: AI API at `odoo-ai-api-65-21-62-16.traefik.me`, Dashboard at `odoo-ai-dash-65-21-62-16.traefik.me`
- Odoo admin login is `alfailakawi1000@gmail.com` (not `admin`)
- All `/api/` endpoints require `X-API-Key` header (validated by `app/auth.py`); health endpoint is public
- CORS restricted to known origins (dashboard, Odoo, localhost); configurable via `CORS_ORIGINS` env var
- Phase 1 adds 13 new SQLAlchemy models to `audit.py` (sharing same `Base`) + Alembic migration `002_phase1_tables`
- Tests use in-memory SQLite with `StaticPool` for cross-thread compatibility with FastAPI TestClient
- Test DB fixtures in `tests/conftest.py`; webhook payload fixtures in `tests/fixtures/webhook_payloads.py`
- Sprint 0 exit criteria: pytest passes, API requires auth, webhook sigs mandatory, 60%+ coverage
- Month-end closing uses a 10-step scan engine; each step queries Odoo for specific issues (unreconciled bank, stale drafts, unbilled deliveries, missing vendor bills, uninvoiced revenue, depreciation, tax validation, inter-company, adjustments, final review)
- Month-end closing generates an AI summary with risk level, priority actions, and estimated completion hours
- Enhanced bank reconciliation uses multi-signal scoring: reference similarity (rapidfuzz, 0-0.4), amount proximity (0-0.35), partner match (0-0.15), learned rule bonus (0-0.10)
- Reconciliation sessions persist in DB; learned match rules are stored per journal and carried across sessions
- Fuzzy matching tolerances: amount ±$0.50 or ±2%; reference fuzzy threshold 70% (token_sort_ratio)
- Candidates are consumed once matched — no duplicate matching within a session
- Cross-entity deduplication uses two-tier matching: strong signal (exact email/phone/VAT/barcode = instant duplicate) + weighted composite (name/email/phone/VAT with per-entity weights)
- Dedup similarity normalizes by matched-field weight only — missing fields don't penalize score; name threshold 70%, email threshold 90%
- Dedup uses union-find clustering to group multi-way duplicates transitively; heuristic master selection picks most complete record
- Dedup scans support 3 entities: res.partner (contacts), crm.lead, product.template; configurable via ENTITY_CONFIGS
- Weekly dedup scan via Celery beat; real-time duplicate check on record creation via webhook
- Credit scoring uses 4 weighted factors: payment history (40%), overdue ratio (25%), order volume (20%), relationship age (15%); composite 0-100
- 5-tier risk classification: low (>=80), normal (>=60), elevated (>=40), high (>=20), critical (<20)
- Credit check on SO creation: blocks if exposure > limit or customer on hold; auto-releases hold when payment reduces exposure below limit
- Daily credit score batch recalculation + hourly hold-release check via Celery beat
- Credit scores persist in `credit_scores` table; hold_active flag enforced on SO creation webhook
- IDP uses a 5-stage pipeline: content prep (pdfplumber text + Vision image) → Claude extraction (tool-use) → fuzzy vendor matching (rapidfuzz token_sort_ratio, 70% threshold) → PO cross-validation (line items, amounts ±2%) → confidence-gated bill creation
- IDP sends images to Claude Vision API as base64 content blocks; falls back to text extraction for text-based PDFs
- IDP learning loop: corrections stored in `extraction_corrections` table; past corrections for same vendor auto-applied when count >= 2
- IDP confidence scoring: weighted average of per-field confidences (vendor 25%, total 25%, line_items 20%, invoice_number 15%, date 10%, po_reference 5%)
- IDP accepts PDF, JPEG, PNG, WebP via multipart/form-data file upload; processing results stored in `document_processing_jobs` table
- Daily digest generates per-role briefings: CFO (AR/AP aging, cash, overdue, approvals, anomalies), Sales Manager (pipeline, at-risk deals, follow-ups, win/loss), Warehouse Manager (low stock, deliveries, receipts)
- Digest uses Claude tool-use for AI narrative; falls back to structured fallback digest when Claude unavailable
- Digest delivery via email (HTML + plain text); in-DB storage for dashboard access; daily Celery beat schedule
- Digest roles: cfo, sales_manager, warehouse_manager; configurable channels, send time, and enable/disable per role via PUT /api/digest/config
- Cash flow forecasting uses a hybrid statistical model: AR aging (due date distribution), AP commitments (bill due dates), pipeline (expected_revenue * probability), recurring expenses (auto-detected from vendor bill patterns with CV < 0.3)
- Forecast confidence bands widen linearly with horizon: uncertainty = 15% * |balance| * (day_offset / horizon)
- Scenario planning supports: delay_customer_{id} (delay days), remove_deal_{id} (remove from pipeline), reduce_ar_by (%), increase_ap_by (%), adjust_expense_{category} (multiplier)
- Forecast accuracy tracked via ForecastAccuracyLog: MAE and MAPE computed for 30/60/90-day windows; daily actual balance recording
- Daily forecast regeneration + persistence via Celery beat; accuracy check runs daily
- NL Report Builder uses Claude tool-use to parse queries into structured Odoo domain/fields/group_by; keyword-based fallback when Claude unavailable
- Report Builder supports 8 Odoo models: sale.order, account.move, crm.lead, product.template, product.product, res.partner, purchase.order, hr.expense
- Excel export via openpyxl with styled headers; PDF export as formatted text; scheduled reports via cron + hourly Celery beat check
- Reports stored in ReportJob table with status lifecycle: pending -> generating -> completed/error/scheduled
- Role-based AI dashboards provide 3 views: CFO (cash forecast AreaChart, AR/AP aging BarChart, P&L summary, close status, anomalies), Sales Manager (pipeline BarChart, conversion funnel, at-risk deals table, win rate, quota), Warehouse Manager (stock levels vs reorder BarChart, alerts list, shipment counts)
- Dashboard endpoints: GET /api/dashboard/{cfo,sales,warehouse} aggregate data from DB models + Odoo XML-RPC; gracefully degrade when Odoo unavailable
- WebSocket endpoint WS /ws/dashboard supports optional `?role=` query param for role-filtered events; ConnectionManager broadcasts via Redis pub/sub
- Redis pub/sub channel `dashboard_events` carries events: automation_completed, approval_needed, forecast_updated, alert
- Celery tasks publish events to Redis pub/sub after task completion for real-time dashboard updates
- Dashboard frontend uses recharts (AreaChart, BarChart, LineChart) for all chart components; recharts ^2.12.0 already in package.json
- RoleSwitcher component in header persists selected role to localStorage; switches between Overview, CFO, Sales, Warehouse views
- useWebSocket custom hook manages WebSocket lifecycle with exponential backoff reconnect (1s, 2s, 4s, 8s, 16s, 30s)
- Centralized API helper (dashboard/src/lib/api.js) adds X-API-Key header to all requests; WS URL derived from API URL
- Redis maxmemory increased from 128mb to 256mb; NEXT_PUBLIC_WS_URL and NEXT_PUBLIC_API_KEY env vars added to dashboard service
- 19 automation handlers registered: 10 original + month_end + deduplication + credit + document_processing + daily_digest + cash_flow + report_builder + role_dashboard + websocket
- 389 tests total (29 new for Slack integration); full test suite passes
- Slack integration uses Block Kit for rich messages with approve/reject buttons; interaction endpoint at POST /api/slack/interactions
- Slack interaction endpoint is public (no API key) — protected by Slack signing secret verification (HMAC-SHA256 with X-Slack-Signature header)
- Approval actions from Slack route to existing AuditLog PENDING -> APPROVED/REJECTED workflow; original message replaced with status update
- Celery webhook processing auto-sends Slack approval notification when action has PENDING status and Slack is configured
- Daily digest supports Slack delivery via Block Kit (key metrics as fields, attention items with severity emojis, anomalies in context blocks)
- WhatsApp removed entirely from project — notification channels are email + Slack only
- Dashboard Dockerfile requires `ENV HOSTNAME=0.0.0.0` — Next.js standalone binds to localhost by default, which is unreachable from Traefik's Docker overlay network
- SSH deploys must use `-p compose-navigate-haptic-matrix-2qe6ph` with docker compose — omitting `-p` creates duplicate containers under project name `code`
- After SSH deploy, containers must be manually connected to `dokploy-network`: `docker network connect dokploy-network <container>`
- Traefik routing for the AI platform is defined in `/etc/dokploy/traefik/dynamic/odoo-ai-platform.yml` (file-based, not container labels)
- Code on server lives at `/etc/dokploy/compose/compose-navigate-haptic-matrix-2qe6ph/code/`
- Phase 1 fully deployed to production on 2026-02-26; all 6 services healthy; Slack integration added 2026-02-27 (item 1.9, 17/17 complete)
- Phase 2 adds 9 new SQLAlchemy models: AgentRun, AgentStep, AgentDecision, AgentSuspension, SupplierRiskScore, SupplierRiskFactor, DisruptionPrediction, SupplyChainAlert, AlternativeSupplierMap
- Phase 2 Alembic migration `003_phase2_tables` creates 9 tables + extends AutomationType enum with `supply_chain`, `agent`
- `AutomationType` enum extended with: supply_chain, agent
- Multi-step agents inherit from `BaseAgent` (not `BaseAutomation`); `BaseAgent` provides LangGraph StateGraph, guardrails, persistence, suspend/resume
- Agent guardrails: step limit (`agent_max_steps`, default 30), token budget (`agent_max_tokens`, default 50000), loop detection (`agent_loop_threshold`, default 3 visits per node)
- Suspended agents timeout after `agent_suspension_timeout_hours` (default 48h); resume via `POST /api/agents/runs/{id}/resume`
- `AgentOrchestrator` singleton coordinates agent selection, execution, and status retrieval
- 3 concrete agents registered: `procure_to_pay`, `collection`, `month_end_close`
- `ProcureToPayAgent`: document extraction → PO matching → validation → goods receipt check → draft bill → approval routing → posting → vendor score update
- `CollectionAgent`: customer assessment → strategy determination (gentle/firm/escalate) → message drafting → sending → credit score update
- `MonthEndCloseAgent`: issue scanning → anomaly detection (Benford + Z-score) → severity classification → auto-resolution → readiness calculation → report generation
- Anomaly detection uses Benford's Law (leading digit distribution, chi-squared test) and Z-score analysis (per-journal outliers, threshold 3.0)
- Supply chain intelligence: vendor risk scoring (7 weighted factors), delivery degradation detection (trend analysis), single-source risk detection
- Supplier risk scoring factors: delivery performance (25%), quality metrics (20%), financial stability (15%), dependency concentration (15%), geographic risk (10%), compliance (10%), communication (5%)
- Risk classification: low (>=80), watch (>=60), elevated (>=40), critical (<40)
- Supply chain Celery beat schedules: daily risk scoring, twice-daily delivery degradation check, weekly single-source scan
- 20 automation handlers registered: 10 original + month_end + deduplication + credit + document_processing + daily_digest + cash_flow + report_builder + role_dashboard + websocket + supply_chain
- 443 tests total (28 agent + 26 supply chain); full test suite passes
- Celery worker initializes agents via `init_agents()` alongside automations on startup
- AI onboarding assistant provides role-based tips and contextual suggestions via GET /api/chat/onboarding and GET /api/chat/suggestions
- Dashboard frontend includes AI Agents tab (agent run table, type filter, step detail) and Supply Chain tab (risk scores, alerts, predictions, scan trigger)
