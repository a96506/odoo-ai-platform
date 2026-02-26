# Odoo AI Automation Platform

AI-powered automation layer for Odoo Enterprise ERP on Hetzner/Dokploy.

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
│   ├── alembic.ini              # Alembic migration config
│   ├── alembic/                 # Database migrations
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/
│   └── app/
│       ├── __init__.py          # Package init
│       ├── main.py              # FastAPI entry + REST API endpoints
│       ├── config.py            # pydantic-settings configuration
│       ├── odoo_client.py       # Odoo XML-RPC client wrapper
│       ├── claude_client.py     # Anthropic Claude API wrapper (tool-use)
│       ├── chat.py              # Natural language ERP chat interface
│       ├── models/
│       │   ├── __init__.py      # Package init
│       │   ├── audit.py         # SQLAlchemy: AuditLog, AutomationRule, WebhookEvent
│       │   └── schemas.py       # Pydantic request/response schemas
│       ├── automations/
│       │   ├── __init__.py      # Automation registry
│       │   ├── base.py          # BaseAutomation class (all handlers inherit)
│       │   ├── accounting.py    # Transaction categorization, reconciliation, anomaly
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
```

## Dependencies

### AI Service (Python)
- fastapi, uvicorn, pydantic, pydantic-settings
- anthropic (Claude API with tool-use)
- celery, redis (async task queue)
- sqlalchemy, psycopg2-binary, alembic (DB)
- httpx, structlog, tenacity

### Dashboard (Node.js)
- next 14, react 18, tailwindcss 3

## Architecture

- **Odoo** fires webhooks on record CRUD via `ai_webhook_mixin`
- **AI Service** receives webhooks, dispatches to Celery, analyzes with Claude
- **Claude tool-use** returns structured decisions with confidence scores
- **Confidence gating**: >=0.95 auto-execute, 0.85-0.95 needs approval, <0.85 logged only
- **Dashboard** shows audit trail, approval queue, rules config, chat, insights

## Design Rules

- All automations inherit from `BaseAutomation` in `base.py`
- Every AI decision is logged in `AuditLog` with confidence + reasoning
- Write/destructive actions from chat require explicit user confirmation
- Odoo module uses abstract mixin pattern for minimal code per model
- ai.config has per-module toggles: enable_accounting, enable_crm, enable_sales, enable_purchase, enable_inventory, enable_hr, enable_project, enable_helpdesk, enable_manufacturing, enable_marketing
- `AutomationType` enum includes: accounting, crm, sales, purchase, inventory, hr, project, helpdesk, manufacturing, marketing, cross_app
- Celery tasks check `AutomationRule.enabled` before executing any automation
- Webhook signature (HMAC-SHA256) is verified on incoming Odoo webhooks when X-Webhook-Signature header is present
- DB engine and session factory are cached as module-level singletons for connection pooling
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
