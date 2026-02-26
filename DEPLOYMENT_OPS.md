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

## Deployment Process

### Standard Deployment (Phase 0 -- Current)

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
| Redis (128MB) | ~50K queued tasks | Memory limit hit with forecast caching |
| PostgreSQL | ~10K queries/s | Not a bottleneck for Phase 1 |
| Claude API | ~60 req/min (rate limit) | >60 automations/minute sustained |

### Phase 1 Scaling Actions

| Action | When | How |
|--------|------|-----|
| Increase Redis memory | Forecast caching, recon session memory | Set `maxmemory 512mb` in docker-compose |
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
