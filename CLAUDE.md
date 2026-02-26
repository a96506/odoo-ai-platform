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
| [COMMUNICATION_AND_PORTALS.md](COMMUNICATION_AND_PORTALS.md) | WhatsApp/Slack/Teams integration, customer portal, vendor portal (Pillar 4) |
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
| [COMMUNICATION_AND_PORTALS.md](COMMUNICATION_AND_PORTALS.md) | MASTER_PLAN (Pillar 4) | WhatsApp/Slack, customer portal, vendor portal |
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
│   │       └── 002_phase1_tables.py  # 13 new Phase 1 tables
│   ├── tests/                   # pytest suite (115 tests, 67%+ coverage)
│   │   ├── conftest.py          # In-memory SQLite DB, TestClient, mocks
│   │   ├── fixtures/
│   │   │   └── webhook_payloads.py  # 13 fixtures for all 11 Odoo models
│   │   ├── test_auth.py         # API key + webhook signature tests
│   │   ├── test_base_automation.py  # BaseAutomation routing/gating tests
│   │   ├── test_month_end_closing.py  # Month-end closing automation + API tests (22 tests)
│   │   ├── test_bank_reconciliation.py  # Fuzzy matching engine + API tests (19 tests)
│   │   ├── test_config.py       # Settings property tests
│   │   ├── test_fixtures.py     # Fixture validation tests
│   │   ├── test_models.py       # All 18 model CRUD tests
│   │   └── test_schemas.py      # Pydantic schema tests
│   └── app/
│       ├── __init__.py          # Package init
│       ├── main.py              # FastAPI app factory (lean: lifespan + router includes)
│       ├── auth.py              # API key auth dependency (X-API-Key header)
│       ├── config.py            # pydantic-settings configuration (incl. Phase 1 fields)
│       ├── odoo_client.py       # Odoo XML-RPC client wrapper
│       ├── claude_client.py     # Anthropic Claude API wrapper (tool-use)
│       ├── chat.py              # Natural language ERP chat interface
│       ├── models/
│       │   ├── __init__.py      # Package init
│       │   ├── audit.py         # SQLAlchemy models (16 tables) + get_db helpers
│       │   └── schemas.py       # Pydantic request/response schemas
│       ├── routers/
│       │   ├── __init__.py      # Package init
│       │   ├── health.py        # GET /health
│       │   ├── dashboard.py     # GET /api/stats, /api/audit-logs, POST /api/approve
│       │   ├── rules.py         # CRUD /api/rules
│       │   ├── chat.py          # POST /api/chat, /api/chat/confirm
│       │   ├── insights.py      # GET /api/insights, POST /api/trigger
│       │   ├── closing.py       # POST /api/close/start, GET /api/close/{period}/status, POST step/complete, POST rescan
│       │   └── reconciliation.py # POST /api/reconciliation/start, GET suggestions, POST match/skip
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
│       │   └── cross_app.py     # Cross-module intelligence engine
│       ├── notifications/
│       │   ├── __init__.py      # Package init
│       │   ├── base.py          # NotificationChannel abstract base
│       │   ├── email.py         # SMTP email channel
│       │   ├── slack.py         # Slack SDK channel
│       │   ├── whatsapp.py      # WhatsApp Business API channel
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
│   ├── package.json             # next 14, react 18, tailwindcss
│   ├── public/                  # Static assets (favicon etc.)
│   └── src/
│       ├── app/
│       │   ├── layout.js
│       │   ├── page.js          # Main dashboard (6 tabs)
│       │   └── globals.css
│       └── components/
│           ├── StatsCards.js     # KPI cards (total, success rate, approvals, time saved)
│           ├── AuditLog.js      # Automation audit trail
│           ├── ApprovalQueue.js # Human-in-the-loop approval UI
│           ├── RulesPanel.js    # Enable/disable automation rules
│           ├── ChatInterface.js # Natural language ERP chat
│           └── InsightsPanel.js # Cross-app intelligence results
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
- slack-sdk (Slack notifications)
- aiosmtplib (async email sending)

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
- API routes are split into routers: health, dashboard, rules, chat, insights, closing, reconciliation (main.py is a lean app factory)
- `BaseAutomation` provides `handle_batch()` for multi-record processing and `notify()` for sending messages via channels
- `NotificationService` routes messages to email/slack/whatsapp channels; channels are auto-registered and checked via `is_configured()`
- Settings includes optional Phase 1 config fields (WhatsApp, Slack, SMTP, forecasting, IDP) -- all disabled by default
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
