# Deployment & Operations

**Referenced by:** [MASTER_PLAN.md](MASTER_PLAN.md) -- Engineering Scaffolding
**Applies to:** All phases

---

## Environments

| Environment | Purpose | Odoo Instance | Data |
|-------------|---------|---------------|------|
| **Local dev** | Development and unit tests | None (mocked) | Test fixtures |
| **Staging** | Integration testing, E2E tests, demos | Staging Odoo with synthetic data | Generated via `populate_odoo_data.py` |
| **Production** | Live system | `odoo-odoo18-*.traefik.me` | Real business data |

### Environment-Specific Config

```bash
# .env.local (development)
ODOO_URL=http://localhost:8069
AI_DATABASE_URL=postgresql://odoo_ai:dev@localhost:5432/odoo_ai_dev
LOG_LEVEL=DEBUG

# .env.staging (staging)
ODOO_URL=https://odoo-staging.example.com
AI_DATABASE_URL=postgresql://odoo_ai:staging-pass@ai-db:5432/odoo_ai_staging
LOG_LEVEL=INFO

# .env (production)
ODOO_URL=https://odoo-odoo18-7de73a-65-21-62-16.traefik.me
AI_DATABASE_URL=postgresql://odoo_ai:prod-pass@ai-db:5432/odoo_ai
LOG_LEVEL=INFO
```

---

## Current Deployment Status

| Component | Version | Status | Last Deployed |
|-----------|---------|--------|---------------|
| AI Service (FastAPI) | Phase 1 complete | healthy | 2026-02-26 |
| Celery Worker | Phase 1 complete | running | 2026-02-26 |
| Celery Beat | Phase 1 complete | running | 2026-02-26 |
| Dashboard (Next.js) | Phase 1 complete | running | 2026-02-26 |
| PostgreSQL | 15 | healthy | stable |
| Redis | 7 (256MB) | healthy | stable |

**Deployed features:** 10 original automations + 6 Phase 1 automations (dedup, credit, IDP, digest, cash flow, reports) + role-based dashboards + WebSocket + 15 API routers + 362 tests.

---

## Dokploy / Traefik Deployment (Current)

The platform is deployed as a **Docker Compose stack** managed by **Dokploy** on a Hetzner VPS (`65.21.62.16`). Traefik handles external routing — containers do NOT bind host ports.

### Key Infrastructure Facts

| Item | Value |
|------|-------|
| Server | Hetzner VPS `65.21.62.16` |
| Orchestrator | Dokploy v0.27.1 (`dokploy.atmatasolutions.com`) |
| Reverse Proxy | Traefik (auto-configured by Dokploy + manual dynamic config) |
| Git Source | `https://github.com/a96506/odoo-ai-platform.git` (branch: `main`) |
| Compose ID | `MFFNIydB-V76TrLCXo4x0` |
| Compose Project Name | `compose-navigate-haptic-matrix-2qe6ph` |
| AI API Domain | `odoo-ai-api-65-21-62-16.traefik.me` → ai-service:8000 |
| Dashboard Domain | `odoo-ai-dash-65-21-62-16.traefik.me` → dashboard:3000 |
| SSH Access | `ssh -i ~/.ssh/dokploy_ed25519 root@65.21.62.16` |
| Code on Server | `/etc/dokploy/compose/compose-navigate-haptic-matrix-2qe6ph/code/` |
| Traefik Config | `/etc/dokploy/traefik/dynamic/odoo-ai-platform.yml` |

### Critical: No Host Port Bindings

The `docker-compose.yml` uses `expose:` (internal) NOT `ports:` (host-bound). Traefik routes external traffic to containers via the Docker network. **Never use `ports:` in the compose file** — the host ports are occupied by other services (N8N on 8000, Dokploy on 3000).

```yaml
# CORRECT — internal only, Traefik routes to it
expose:
  - "8000"

# WRONG — will fail with "port is already allocated"
ports:
  - "8000:8000"
```

### Deployment Steps (SSH — Primary Method)

```bash
# 1. Push to main
git push origin main

# 2. SSH into server, pull, build, and recreate
ssh -i ~/.ssh/dokploy_ed25519 root@65.21.62.16

cd /etc/dokploy/compose/compose-navigate-haptic-matrix-2qe6ph/code

git pull origin main

# CRITICAL: always use -p with the Dokploy project name (not the default "code")
docker compose -p compose-navigate-haptic-matrix-2qe6ph build --no-cache ai-service dashboard
docker compose -p compose-navigate-haptic-matrix-2qe6ph up -d --force-recreate ai-service celery-worker celery-beat dashboard

# 3. Reconnect to Traefik overlay network (required after recreate)
docker network connect dokploy-network compose-navigate-haptic-matrix-2qe6ph-ai-service-1
docker network connect dokploy-network compose-navigate-haptic-matrix-2qe6ph-dashboard-1

# 4. Verify endpoints
curl -s http://odoo-ai-api-65-21-62-16.traefik.me/health
curl -s -o /dev/null -w "%{http_code}" http://odoo-ai-dash-65-21-62-16.traefik.me/
```

### Deployment Steps (Dokploy API — Alternative)

```bash
# If you have a Dokploy API key:
curl -sk -X POST "https://dokploy.atmatasolutions.com/api/compose.deploy" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $DOKPLOY_API_KEY" \
  -d '{"composeId": "MFFNIydB-V76TrLCXo4x0"}'
```

Note: Dokploy API deploy handles Traefik labels and network automatically. The SSH method requires manual `docker network connect` (see Traefik Routing below).

### Post-Deploy: Run Alembic Migrations

Migrations do NOT run automatically. After deploying new DB schema changes:

```bash
ssh -i ~/.ssh/dokploy_ed25519 root@65.21.62.16 \
  "docker exec compose-navigate-haptic-matrix-2qe6ph-ai-service-1 alembic upgrade head"
```

If tables already exist (created by `Base.metadata.create_all()`), stamp instead:

```bash
ssh -i ~/.ssh/dokploy_ed25519 root@65.21.62.16 \
  "docker exec compose-navigate-haptic-matrix-2qe6ph-ai-service-1 alembic stamp head"
```

### Updating Environment Variables

```bash
curl -sk -X POST "https://dokploy.atmatasolutions.com/api/compose.update" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $DOKPLOY_API_KEY" \
  -d '{"composeId": "MFFNIydB-V76TrLCXo4x0", "env": "KEY=value\nKEY2=value2"}'

# Then redeploy to pick up changes
```

### Traefik Routing (Critical)

Traefik uses the `dokploy-network` (Docker Swarm overlay, attachable) for service discovery. When deploying via SSH (not Dokploy API), containers are only on the compose default network. **You must manually connect them to `dokploy-network`** or Traefik returns 404.

Routing is configured via a file-based dynamic config at `/etc/dokploy/traefik/dynamic/odoo-ai-platform.yml`:

```yaml
http:
  routers:
    odoo-ai-api:
      rule: Host(`odoo-ai-api-65-21-62-16.traefik.me`)
      service: odoo-ai-api-service
      entryPoints:
        - web
    odoo-ai-api-secure:
      rule: Host(`odoo-ai-api-65-21-62-16.traefik.me`)
      service: odoo-ai-api-service
      entryPoints:
        - websecure
      tls:
        certResolver: letsencrypt
    odoo-ai-dash:
      rule: Host(`odoo-ai-dash-65-21-62-16.traefik.me`)
      service: odoo-ai-dash-service
      entryPoints:
        - web
    odoo-ai-dash-secure:
      rule: Host(`odoo-ai-dash-65-21-62-16.traefik.me`)
      service: odoo-ai-dash-service
      entryPoints:
        - websecure
      tls:
        certResolver: letsencrypt
  services:
    odoo-ai-api-service:
      loadBalancer:
        servers:
          - url: http://compose-navigate-haptic-matrix-2qe6ph-ai-service-1:8000
        passHostHeader: true
    odoo-ai-dash-service:
      loadBalancer:
        servers:
          - url: http://compose-navigate-haptic-matrix-2qe6ph-dashboard-1:3000
        passHostHeader: true
```

Traefik watches this directory and picks up changes automatically (no restart needed).

**Verifying Traefik routing:**

```bash
# Check routers are loaded
docker exec dokploy-traefik wget -qO- http://localhost:8080/api/http/routers | \
  python3 -c "import sys,json; [print(r['name'], r['status']) for r in json.load(sys.stdin) if 'odoo-ai' in r['name']]"

# Check backends are UP
docker exec dokploy-traefik wget -qO- http://localhost:8080/api/http/services | \
  python3 -c "import sys,json; [print(s['name'], s.get('serverStatus',{})) for s in json.load(sys.stdin) if 'odoo-ai' in s['name']]"
```

---

## Troubleshooting

### Traefik returns 404 after SSH deploy

**Symptom:** Containers are running and healthy, but `curl https://odoo-ai-api-*.traefik.me/health` returns `404 page not found`.

**Cause:** When deploying via SSH (not Dokploy API), containers are only on the compose default network. Traefik discovers services on `dokploy-network` (overlay).

**Fix:**

```bash
docker network connect dokploy-network compose-navigate-haptic-matrix-2qe6ph-ai-service-1
docker network connect dokploy-network compose-navigate-haptic-matrix-2qe6ph-dashboard-1
```

Also verify the Traefik dynamic config file exists at `/etc/dokploy/traefik/dynamic/odoo-ai-platform.yml` (see "Traefik Routing" section above).

### Duplicate containers (wrong docker compose project name)

**Symptom:** `docker ps` shows two sets of containers — old `compose-navigate-haptic-matrix-2qe6ph-*` AND new `code-*` containers.

**Cause:** Running `docker compose up` from the code directory without `-p` uses the directory name (`code`) as the project name instead of Dokploy's project name.

**Fix:**

```bash
# Remove the duplicate set
docker compose -p code down

# Always use the Dokploy project name
docker compose -p compose-navigate-haptic-matrix-2qe6ph up -d --force-recreate
```

### Dashboard 502 Bad Gateway

**Symptom:** AI API works fine but dashboard returns 502.

**Cause:** Next.js standalone binds to `localhost` by default, making it unreachable from Traefik's overlay network. The `HOSTNAME=0.0.0.0` env var is required.

**Fix:** Already fixed in `dashboard/Dockerfile` with `ENV HOSTNAME=0.0.0.0`. If the problem recurs, verify:

```bash
docker exec <dashboard-container> env | grep HOSTNAME
# Should show: HOSTNAME=0.0.0.0 (NOT a container ID)
```

### Container stuck in "Created" state

**Symptom:** `docker ps -a` shows a container with status `Created` (never starts).

**Cause:** Almost always a **port conflict**. Check with:

```bash
docker inspect <container-name> --format '{{.State.Status}} {{.State.Error}}'
```

If the error says `Bind for 0.0.0.0:XXXX failed: port is already allocated`, find what's using the port:

```bash
lsof -i :8000   # or ss -tlnp | grep 8000
```

**Fix:** Use `expose:` instead of `ports:` in `docker-compose.yml` (see "Critical: No Host Port Bindings" above).

### Old containers still serving traffic

**Symptom:** Health check returns healthy but new endpoints return 404.

**Cause:** A previous deployment left old containers running. Dokploy created new containers but they couldn't start (port conflict), so the old ones kept serving.

**Fix:**

```bash
# Stop and remove old containers
docker stop <old-container> && docker rm <old-container>

# Remove stale new containers
docker rm -f <stuck-container>

# Redeploy
curl -sk -X POST ".../api/compose.deploy" ...
```

### "Access Denied" from Odoo XML-RPC

**Symptom:** Month-end scans return `<Fault 3: 'Access Denied'>` for every step.

**Cause:** Wrong `ODOO_USERNAME` in the Dokploy env vars. Must be `alfailakawi1000@gmail.com`, NOT `admin`.

**Fix:** Update env vars via Dokploy API (see "Updating Environment Variables" above), then redeploy.

### "Invalid input value for enum automationtype"

**Symptom:** 500 error when creating audit logs for new automation types.

**Cause:** Alembic migration 001 (enum extension) wasn't run, or was rolled back when migration 002 failed.

**Fix:** Add missing values directly:

```bash
docker exec <ai-db-container> psql -U odoo_ai -d odoo_ai -c "
  ALTER TYPE automationtype ADD VALUE IF NOT EXISTS 'MONTH_END';
  ALTER TYPE automationtype ADD VALUE IF NOT EXISTS 'DEDUPLICATION';
  ALTER TYPE automationtype ADD VALUE IF NOT EXISTS 'CREDIT_MANAGEMENT';
  ALTER TYPE automationtype ADD VALUE IF NOT EXISTS 'FORECASTING';
  ALTER TYPE automationtype ADD VALUE IF NOT EXISTS 'REPORTING';
  ALTER TYPE automationtype ADD VALUE IF NOT EXISTS 'DOCUMENT_PROCESSING';
"
```

### Bank Statement Line creation fails ("not allowed to create")

**Symptom:** `populate_accounting_test_data.py` fails creating BSL records.

**Cause:** User needs `Show Full Accounting Features` group (id=29). Also, the Bank journal needs a `suspense_account_id` configured.

**Fix:** The script handles both automatically (adds group + creates suspense account if missing).

### Docker build makes server unresponsive

**Symptom:** All services (Dokploy UI, Traefik, even SSH) become slow or timeout during deployment.

**Cause:** The VPS has limited RAM/CPU. Building multiple Docker images concurrently exhausts resources.

**Mitigation:**
- Create a Hetzner snapshot before deploying
- Deploy during low-traffic hours
- Consider increasing VPS size for production

---

## Legacy Deployment (deploy.sh)

For local or non-Dokploy environments:

```bash
# 1. SSH to server
ssh root@65.21.62.16

# 2. Pull latest code
cd /path/to/project && git pull

# 3. Run deploy script
./scripts/deploy.sh
```

`deploy.sh` validates `.env`, builds Docker images, starts services, and runs health checks.

### Phase 1+ Deployment Process

```
1. Push to main branch
   │
2. CI runs (lint, unit tests, integration tests, build)
   │
3. CI passes → Manual approval to deploy staging
   │
4. Deploy to staging environment
   │
5. Run E2E tests against staging
   │
6. E2E passes → Manual approval to deploy production
   │
7. Deploy to production (rolling update)
   │
8. Health check (automated, 2 min)
   │
9. If unhealthy → Automatic rollback
   │
10. Post-deploy smoke test (manual, 5 min)
```

### Rolling Update Strategy

Docker Compose doesn't support true rolling updates. Our approach:

```bash
# Build new images without stopping current services
docker compose build

# Restart services one at a time (order matters)
docker compose up -d --no-deps ai-db       # DB first (stateful)
docker compose up -d --no-deps redis        # Broker second
docker compose up -d --no-deps ai-service   # API third
docker compose up -d --no-deps celery-worker # Worker fourth
docker compose up -d --no-deps celery-beat   # Beat fifth
docker compose up -d --no-deps dashboard     # Dashboard last

# Health check after each critical service
curl -sf http://localhost:8000/health || echo "UNHEALTHY"
```

---

## Rollback Procedures

### Application Rollback

```bash
# Find the previous working image
docker images | grep ai-service

# Or use git to revert
git log --oneline -5
git checkout <previous-commit>

# Rebuild and restart
docker compose build
docker compose up -d
```

### Database Rollback

```bash
# Check current migration
cd ai_service && alembic current

# Rollback one migration
alembic downgrade -1

# Rollback to specific revision
alembic downgrade <revision_id>

# Verify
alembic current
```

**Before every migration in production:**

```bash
# Create DB backup FIRST
docker exec ai-db pg_dump -U odoo_ai odoo_ai > backup_$(date +%Y%m%d_%H%M%S).sql
```

### Feature Rollback (Without Full Rollback)

Each Phase 1 feature can be disabled independently via automation rules:

```bash
# Disable a specific feature via API
curl -X PUT http://localhost:8000/api/rules/42 \
  -H "Authorization: Bearer $API_KEY" \
  -d '{"enabled": false}'
```

Or via Odoo's AI Platform configuration (per-module toggles).

---

## Feature Flags

### Current System

Automation rules in the `automation_rules` table serve as feature flags. Each rule has:
- `enabled` (boolean) -- master on/off switch
- `automation_type` -- which module
- `config` (JSONB) -- per-feature configuration

### Phase 1 Feature Flag Pattern

For each Phase 1 deliverable, add automation rules at startup:

```python
# Example: Month-End Closing Assistant
{
    "name": "Month-End Closing Assistant",
    "automation_type": "month_end",
    "action_name": "close_period",
    "enabled": False,  # Disabled by default until tested
    "config": {
        "auto_scan_on_1st": True,
        "scan_lookback_months": 3,
        "notify_controller": True,
    }
}
```

### Enabling Features

1. Deploy code with feature disabled (`enabled=False`)
2. Test manually via API (`POST /api/trigger/month_end/close_period`)
3. Enable for one client/period as pilot
4. Monitor audit logs and error rates
5. Enable globally

---

## Backup Strategy

### Database Backups

```bash
# Manual backup
docker exec ai-db pg_dump -U odoo_ai odoo_ai > backup.sql

# Automated daily backup (add to cron)
0 3 * * * docker exec ai-db pg_dump -U odoo_ai odoo_ai | gzip > /backups/ai_db_$(date +\%Y\%m\%d).sql.gz

# Retention: keep last 30 daily backups
find /backups/ -name "ai_db_*.sql.gz" -mtime +30 -delete
```

### Backup Verification

Weekly: restore backup to a test database, verify table counts match production.

```bash
# Restore to test database
docker exec -i ai-db psql -U odoo_ai -d odoo_ai_test < backup.sql

# Verify row counts
docker exec ai-db psql -U odoo_ai -d odoo_ai_test -c "
SELECT 'audit_logs' as tbl, count(*) FROM audit_logs
UNION ALL SELECT 'automation_rules', count(*) FROM automation_rules
UNION ALL SELECT 'webhook_events', count(*) FROM webhook_events;
"
```

### Redis Backups

Redis is used as a transient broker. Data loss is acceptable (tasks will be re-queued). No backup needed.

---

## Scaling Considerations

### Current Capacity

| Service | Capacity | Bottleneck At |
|---------|----------|---------------|
| FastAPI (ai-service) | ~500 req/s | Not a bottleneck |
| Celery Worker (4 threads) | ~4 concurrent tasks | >100 webhooks/min sustained |
| Redis (256MB) | ~100K queued tasks | Memory limit hit with heavy pub/sub + forecast caching |
| PostgreSQL | ~10K queries/s | Not a bottleneck for Phase 1 |
| Claude API | ~60 req/min (rate limit) | >60 automations/minute sustained |

### Phase 1 Scaling Actions

| Action | When | How |
|--------|------|-----|
| Increase Redis memory | Heavy pub/sub + forecast + recon caching | Set `maxmemory 512mb` in docker-compose (currently 256mb) |
| Add Celery worker | >100 webhooks/min or >4 concurrent Claude calls | Scale worker replicas: `docker compose up -d --scale celery-worker=2` |
| Increase DB connections | >20 concurrent API requests | Adjust `pool_size` in SQLAlchemy engine |

---

## Disaster Recovery

### Scenarios

| Scenario | Recovery Time | Procedure |
|----------|--------------|-----------|
| Server crash (Hetzner) | 1-4 hours | Restore from Hetzner snapshot + latest DB backup |
| Database corruption | 30 min | Restore from daily backup |
| Accidental data deletion | 30 min | Restore specific tables from backup |
| Claude API outage | 0 min (graceful) | Automations queue and retry when API returns |
| Odoo instance down | 0 min (graceful) | Webhooks queue in Celery, process on recovery |
| Redis crash | 5 min | Restart container, in-flight tasks lost (re-queued) |

### Server Snapshots

Configure Hetzner automated snapshots:
- Daily snapshots, keep last 7
- Before any major deployment, create manual snapshot

---

## Maintenance Windows

| Task | Frequency | Downtime | Schedule |
|------|-----------|----------|----------|
| Database backup | Daily | None (pg_dump is non-blocking) | 3:00 AM UTC |
| Alembic migrations | Per deployment | <1 min (additive migrations) | During deployment |
| Docker image cleanup | Weekly | None | Sunday 4:00 AM UTC |
| Log rotation | Daily | None | Handled by Docker |
| SSL cert renewal | Auto (Traefik) | None | Automatic |

### Docker Cleanup

```bash
# Remove unused images and volumes (weekly cron)
docker system prune -f --volumes
docker image prune -a --filter "until=168h" -f
```
