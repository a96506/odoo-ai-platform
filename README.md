# Odoo AI Automation Platform

AI-powered automation layer for Odoo Enterprise ERP. Replaces repetitive tasks across all essential modules so humans become advisors, not workers.

## Architecture

- **AI Service** (FastAPI + Celery) — receives Odoo events, analyzes with Claude, executes actions back
- **Odoo Bridge Module** — custom Odoo module that fires webhooks on record events
- **Monitoring Dashboard** (Next.js) — approval queue, audit trail, chat, metrics

## Services (Docker Compose)

| Service | Container | Description |
|---------|-----------|-------------|
| `ai-service` | FastAPI on port 8000 | AI brain — REST API + webhook receiver |
| `celery-worker` | Celery worker (4 threads) | Async task processing (webhooks, automations, scheduled) |
| `celery-beat` | Celery beat scheduler | Periodic scans (lead scoring, demand forecast, etc.) |
| `redis` | Redis 7 Alpine | Message broker + result backend |
| `ai-db` | PostgreSQL 16 Alpine | AI state database (audit logs, rules, webhook events) |
| `dashboard` | Next.js on port 3000 | Monitoring UI (stats, approvals, rules, chat, insights) |

All services connect to your existing Odoo instance via the `dokploy-network` Docker network.

## Quick Start

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env — set at minimum:
#   ANTHROPIC_API_KEY  (your Claude API key)
#   ODOO_URL           (your Odoo instance URL)
#   POSTGRES_PASSWORD   (strong random password)
#   AI_SECRET_KEY       (random 32+ char secret)
#   WEBHOOK_SECRET      (random 32+ char secret)
# Update AI_DATABASE_URL to match your POSTGRES_PASSWORD

# 2. Deploy everything
./scripts/deploy.sh

# 3. Install the Odoo bridge module
# Copy odoo_ai_bridge/ into your Odoo addons path, then:
#   Settings → Apps → Update Apps List → Install "AI Bridge"

# 4. Configure webhooks
python3 scripts/setup_odoo_webhooks.py

# 5. (Optional) Seed automation rules via API
python3 scripts/seed_automation_rules.py

# 6. Verify
curl http://localhost:8000/health
open http://localhost:8000/docs    # Swagger UI
open http://localhost:3000         # Dashboard
```

## Useful Commands

```bash
# View AI service logs
docker compose logs -f ai-service

# View Celery worker logs
docker compose logs -f celery-worker

# Restart a single service
docker compose restart ai-service

# Stop everything
docker compose down

# Rebuild and restart
docker compose up -d --build
```

## Automated Modules

| Module | Automations |
|--------|------------|
| Accounting | Transaction categorization, bank reconciliation, anomaly detection |
| CRM | Lead scoring, auto-assignment, follow-up generation, duplicate detection |
| Sales | Quotation generation, pricing optimization, pipeline forecasting |
| Purchase | Auto-PO creation, vendor selection, bill matching |
| Inventory | Demand forecasting, auto-reorder, product categorization |
| HR | Leave approval, expense processing |
| Project | Task assignment, duration estimation |
| Helpdesk | Ticket categorization, auto-assignment |
| Manufacturing | Production scheduling |
| Marketing | Contact segmentation |

## API Endpoints

| Endpoint | Description |
|----------|------------|
| `GET /health` | Service health check |
| `POST /webhooks/odoo` | Receive Odoo webhook events |
| `GET /api/stats` | Dashboard statistics |
| `GET /api/audit-logs` | Audit trail |
| `POST /api/approve` | Approve/reject pending actions |
| `GET /api/rules` | List automation rules |
| `POST /api/chat` | Natural language ERP chat |
| `GET /api/insights` | Cross-app intelligence analysis |
| `POST /api/trigger/{type}/{action}` | Manually trigger automation |

## Confidence Thresholds

- **>= 0.95** — Auto-executed (no human needed)
- **0.85 - 0.95** — Queued for human approval
- **< 0.85** — Logged but not acted upon
