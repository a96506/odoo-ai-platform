# Observability

**Referenced by:** [MASTER_PLAN.md](MASTER_PLAN.md) -- Engineering Scaffolding
**Applies to:** All phases

---

## Overview

The platform has 6 Docker services, external API calls (Claude, Odoo), and async task processing. When something breaks at 2 AM, we need to know what, where, and why -- fast.

---

## Structured Logging

### Current State

Using `structlog` with basic `logger.info()` / `logger.error()` calls. No consistent conventions.

### Logging Conventions

#### Log Levels

| Level | When | Example |
|-------|------|---------|
| `ERROR` | Something failed and needs attention | Claude API call failed, Odoo unreachable, DB write error |
| `WARNING` | Unexpected but handled | Notification channel not configured, confidence below threshold, retry triggered |
| `INFO` | Normal operation milestones | Webhook received, automation completed, rule evaluated, forecast generated |
| `DEBUG` | Detailed for troubleshooting | Odoo record fields fetched, Claude prompt constructed, fuzzy match scores |

#### Structured Fields

Every log entry should include these fields when applicable:

```python
logger.info(
    "event_name",                    # snake_case event identifier
    automation_type="accounting",    # which module
    action="categorize_transaction", # which action
    odoo_model="account.move",       # Odoo model involved
    odoo_record_id=42,              # Odoo record ID
    confidence=0.92,                # AI confidence (if applicable)
    duration_ms=340,                # Processing time
    tokens_used=450,                # Claude tokens consumed
    trace_id="abc-123",            # Request trace ID
)
```

#### Sensitive Data Rules

**NEVER log:**
- API keys, passwords, tokens
- Full customer email addresses (use masked: `a***@example.com`)
- Full credit card or bank account numbers
- Claude prompt content at INFO level (only at DEBUG, and never in production)

---

## Health Checks

### Current `/health` Endpoint

Returns basic status. Needs expansion.

### Enhanced Health Check

```python
{
    "status": "healthy",           # healthy | degraded | unhealthy
    "version": "1.1.0",
    "uptime_seconds": 86400,
    "checks": {
        "database": {
            "status": "up",
            "latency_ms": 5,
            "connection_pool": {"active": 2, "idle": 8, "max": 10}
        },
        "redis": {
            "status": "up",
            "latency_ms": 1,
            "memory_used_mb": 45
        },
        "odoo": {
            "status": "up",
            "latency_ms": 120,
            "last_successful_call": "2026-02-26T10:30:00Z"
        },
        "claude_api": {
            "status": "up",
            "last_successful_call": "2026-02-26T10:29:45Z",
            "daily_spend": 0.85
        },
        "celery_workers": {
            "status": "up",
            "active_workers": 4,
            "queued_tasks": 3,
            "failed_tasks_24h": 0
        }
    }
}
```

**Status logic:**
- `healthy`: all checks pass
- `degraded`: non-critical check failing (e.g., Claude API slow but reachable)
- `unhealthy`: critical check failing (DB down, Redis down, no Celery workers)

---

## Metrics

### Key Metrics to Track

| Metric | Type | Description |
|--------|------|-------------|
| `automation_total` | Counter | Total automations executed (by type, action, status) |
| `automation_duration_seconds` | Histogram | Processing time per automation |
| `automation_confidence` | Histogram | Confidence distribution per automation type |
| `claude_api_calls_total` | Counter | Claude API calls (by model, success/failure) |
| `claude_api_latency_seconds` | Histogram | Claude response time |
| `claude_tokens_total` | Counter | Tokens consumed (input, output) |
| `claude_cost_dollars` | Counter | Estimated API cost |
| `webhook_received_total` | Counter | Webhooks received (by model, event_type) |
| `webhook_processing_seconds` | Histogram | Time from receive to completion |
| `odoo_rpc_calls_total` | Counter | Odoo XML-RPC calls (by method) |
| `odoo_rpc_latency_seconds` | Histogram | Odoo response time |
| `approval_queue_size` | Gauge | Current pending approvals |
| `celery_tasks_active` | Gauge | Currently executing tasks |
| `celery_tasks_queued` | Gauge | Tasks waiting in queue |
| `celery_tasks_failed_total` | Counter | Failed task count |
| `notification_sent_total` | Counter | Notifications sent (by channel, success/failure) |

### Implementation: Lightweight Approach

For Phase 1, avoid adding Prometheus/Grafana overhead. Instead:

1. **Dashboard stats API** already aggregates key metrics from the DB
2. **Add a `/metrics` endpoint** that returns current counters as JSON
3. **Log-based metrics** via structlog + a log aggregator (if needed later)

Phase 2+: Add Prometheus client library and Grafana dashboard if operational complexity warrants it.

---

## Alerting

### What Triggers Alerts

| Alert | Severity | Channel | Condition |
|-------|----------|---------|-----------|
| AI service down | Critical | Slack + SMS | `/health` returns unhealthy or unreachable for 2 min |
| Database unreachable | Critical | Slack + SMS | DB health check fails for 1 min |
| Claude API errors | High | Slack | >5 failed Claude calls in 10 min |
| Claude daily spend exceeded | High | Slack | Daily cost > $5.00 |
| Celery worker down | High | Slack | No active workers for 5 min |
| Celery task backlog | Medium | Slack | >50 tasks queued for >10 min |
| Odoo unreachable | High | Slack | Odoo health check fails for 5 min |
| Automation failure rate | Medium | Slack | >10% failure rate in last hour |
| Webhook processing lag | Medium | Slack | Avg processing time >60s |
| Approval queue stale | Low | Email | Approvals pending >48h |

### Implementation: Simple Alerting

Phase 1: Celery beat task that runs every 5 minutes, checks conditions, sends alerts via Slack/email.

```python
# In celery_app.py beat_schedule:
"health-check-alerting": {
    "task": "app.tasks.celery_tasks.run_health_alerts",
    "schedule": 300.0,  # Every 5 minutes
}
```

Phase 2+: Consider Uptime Kuma or Grafana Alerting for more sophisticated monitoring.

---

## Distributed Tracing

### The Problem

A single user action flows across multiple services:

```
Odoo (webhook) -> FastAPI -> Redis -> Celery Worker -> Claude API -> Odoo (XML-RPC) -> DB (audit log)
```

When something fails, we need to trace the full request path.

### Solution: Trace ID Propagation

Generate a `trace_id` at webhook receipt and propagate through all steps:

1. FastAPI generates `trace_id = uuid4()` on webhook receipt
2. Pass `trace_id` to Celery task via task kwargs
3. Include `trace_id` in all structlog calls within the task
4. Store `trace_id` in `audit_logs` and `webhook_events` tables
5. Dashboard can search by `trace_id` to see full request journey

```python
# In webhook handler:
trace_id = str(uuid4())
logger.info("webhook_received", trace_id=trace_id, model=payload.model)

# Pass to Celery:
process_webhook_event.delay(payload.dict(), trace_id=trace_id)

# In Celery task:
logger.info("task_started", trace_id=trace_id)
```

### Adding trace_id to DB

Add `trace_id` column to `audit_logs` and `webhook_events`:

```sql
ALTER TABLE audit_logs ADD COLUMN trace_id VARCHAR(36);
ALTER TABLE webhook_events ADD COLUMN trace_id VARCHAR(36);
CREATE INDEX idx_audit_logs_trace ON audit_logs(trace_id);
```

---

## Log Aggregation

### Phase 1: Docker Logs

```bash
# View all service logs
docker compose logs -f

# View specific service
docker compose logs -f ai-service

# Search for errors
docker compose logs ai-service 2>&1 | grep ERROR

# Search by trace ID
docker compose logs ai-service 2>&1 | grep "trace_id=abc-123"
```

### Phase 2+: Centralized Logging

If log volume grows, add a lightweight log aggregator:
- **Option A:** Loki + Grafana (lightweight, Docker-native)
- **Option B:** Seq (structured log viewer, free for single user)

---

## Runbook: Common Issues

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Automations not running | Celery worker crashed | `docker compose restart celery-worker` |
| High webhook latency | Redis memory full | `docker compose restart redis`, check `maxmemory` |
| Claude API 429 errors | Rate limit exceeded | Reduce Celery concurrency, check beat schedules |
| "Database connection refused" | ai-db container down | `docker compose up -d ai-db`, wait for health check |
| Dashboard shows stale data | API unreachable from dashboard | Check Traefik routing, CORS config |
| Webhook signature failures | Secret mismatch | Verify `WEBHOOK_SECRET` matches in `.env` and Odoo `ai.config` |
| Automations completing but not writing to Odoo | XML-RPC auth failure | Check `ODOO_API_KEY` in `.env`, verify key in Odoo |
