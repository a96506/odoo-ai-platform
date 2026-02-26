# Security

**Referenced by:** [MASTER_PLAN.md](MASTER_PLAN.md) -- Engineering Scaffolding
**Applies to:** All phases

---

## Threat Model

The AI platform handles financial data, customer information, and employee records. It has write access to a live ERP system. The attack surface includes:

| Vector | Risk | Severity |
|--------|------|----------|
| Unauthenticated API access | Anyone can query/modify ERP data via chat or trigger automations | Critical |
| Secrets in source control | `.env` with API keys, DB passwords committed to git | Critical |
| Claude API data leakage | Customer PII sent to Anthropic's API for analysis | High |
| Webhook spoofing | Fake webhooks trigger unauthorized automations | High |
| SQL injection via JSONB | Malicious data in webhook payloads stored as JSONB | Medium |
| CORS wildcard | `allow_origins=["*"]` permits any frontend to call the API | Medium |
| Unencrypted internal traffic | Services communicate over Docker network without TLS | Low (internal) |

---

## Authentication & Authorization

### Current State (Phase 0)

- API has **no authentication** -- all endpoints are public
- CORS allows all origins (`*`)
- Webhook signature verification exists but is optional (only when `X-Webhook-Signature` header is present)
- Dashboard has no login

### Required Changes

#### API Key Authentication

All API endpoints (except `/health`) require an API key in the `Authorization` header.

```
Authorization: Bearer <AI_SECRET_KEY>
```

**Implementation:**

```python
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> str:
    if credentials.credentials != get_settings().ai_secret_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return credentials.credentials
```

Apply to all routers: `router = APIRouter(dependencies=[Depends(verify_api_key)])`.

Exceptions: `/health` (no auth), `/webhooks/odoo` (uses webhook signature instead).

#### Webhook Signature Verification

Make HMAC-SHA256 signature verification **mandatory** (not optional). Reject webhooks without valid signature.

```python
import hmac, hashlib

def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
```

#### Dashboard Authentication

Phase 0: API key passed as query parameter or stored in `localStorage` (simple but functional).

Phase 1+: Replace with proper session-based auth or integrate with Odoo's auth system.

---

## Secrets Management

### Current State

- `.env` file with plaintext secrets
- `.env` is in `.gitignore` (good)
- `.env.example` has placeholder values (good)

### Required Practices

| Secret | Storage | Rotation |
|--------|---------|----------|
| `ANTHROPIC_API_KEY` | `.env` on server, never in git | When compromised |
| `AI_SECRET_KEY` | `.env` on server | Every 90 days |
| `WEBHOOK_SECRET` | `.env` on server + Odoo `ai.config` | Every 90 days |
| `POSTGRES_PASSWORD` | `.env` on server | Every 90 days |
| `WHATSAPP_API_TOKEN` | `.env` on server | Per Meta's policy |
| `SLACK_BOT_TOKEN` | `.env` on server | When compromised |
| `SMTP_PASSWORD` | `.env` on server | Every 90 days |

**Rules:**
- Never commit `.env` to git (verified: `.gitignore` includes it)
- Never log secret values (structlog must not include API keys in output)
- Never include secrets in error messages returned to clients
- Use Dokploy's environment variable management for server-side secrets

---

## Data Privacy & Claude API

### What Gets Sent to Anthropic

Every automation sends business data to Claude for analysis. This includes:

| Data Type | Examples | Sensitivity |
|-----------|---------|-------------|
| Invoice data | Amounts, vendor names, dates | Medium |
| Customer info | Names, emails, company names | High (PII) |
| Employee data | Leave requests, expense details | High (PII) |
| Financial data | Bank transactions, P&L items | High |
| Sales data | Lead details, quotation amounts | Medium |

### Anthropic Data Handling

Per Anthropic's API terms (as of 2026):
- API inputs/outputs are **not used for training** by default
- Data is processed and discarded (not stored long-term)
- SOC 2 Type II compliant

### Minimization Practices

- Send only the fields needed for analysis, not entire Odoo records
- Strip unnecessary PII when possible (e.g., use customer ID instead of full address for lead scoring)
- Never send passwords, API keys, or authentication tokens to Claude
- Log the prompt structure but not the full content in audit trails

---

## CORS Configuration

### Current State (Insecure)

```python
allow_origins=["*"]  # Allows any website to call our API
```

### Required Change

Restrict to known origins:

```python
allow_origins=[
    "https://odoo-ai-dash-65-21-62-16.traefik.me",
    "http://localhost:3000",
    "http://localhost:3001",
]
```

---

## Network Security

### Docker Network

All services communicate over the `dokploy-network` Docker network. Internal traffic is unencrypted but isolated.

| Service | Needs Public Access | Port |
|---------|-------------------|------|
| `ai-service` | Yes (Traefik routes) | 8000 |
| `dashboard` | Yes (Traefik routes) | 3000 |
| `redis` | No (internal only) | 6379 |
| `ai-db` | No (internal only) | 5432 |
| `celery-worker` | No (internal only) | -- |
| `celery-beat` | No (internal only) | -- |

**Rules:**
- Redis must NOT be exposed externally (no `ports:` mapping in docker-compose)
- PostgreSQL must NOT be exposed externally
- Traefik handles TLS termination for public-facing services

---

## Input Validation

### Webhook Payloads

All incoming webhook data is validated by Pydantic schema (`WebhookPayload`). Additional safeguards:

- `record_id` must be a positive integer
- `model` must be a recognized Odoo model name (whitelist, not blacklist)
- `values` dict is stored as JSONB -- SQLAlchemy handles escaping
- Maximum payload size enforced at FastAPI level (default 1MB)

### Chat Input

User messages to `/api/chat` should be:
- Limited to 10,000 characters
- Rate-limited (10 requests/minute per client)
- Sanitized before passing to Claude (no prompt injection via user input)

### Prompt Injection Defense

The chat interface passes user input to Claude. Defense layers:

1. System prompt clearly separates user input from instructions
2. Claude's tool-use constrains output to defined schemas
3. Write operations require explicit confirmation regardless of what the user types
4. Audit trail logs every chat interaction for review

---

## Encryption

| Layer | Current | Target |
|-------|---------|--------|
| Data in transit (external) | TLS via Traefik | TLS via Traefik (no change) |
| Data in transit (internal) | Plaintext on Docker network | Acceptable for single-host deployment |
| Data at rest (PostgreSQL) | Unencrypted | Enable `pgcrypto` for sensitive columns (Phase 3) |
| Data at rest (Redis) | Unencrypted | Acceptable (transient cache data only) |
| Backups | Not encrypted | Encrypt with `gpg` before offsite transfer |

---

## Checklist Before Phase 1 Launch

- [ ] Add API key authentication to all non-health endpoints
- [ ] Make webhook signature verification mandatory
- [ ] Restrict CORS to known origins
- [ ] Verify `.env` is in `.gitignore` and not committed
- [ ] Verify Redis and PostgreSQL are not exposed externally
- [ ] Add rate limiting to chat endpoint
- [ ] Add input length limits to chat endpoint
- [ ] Review structlog output for accidental secret logging
- [ ] Document which Odoo fields are sent to Claude per automation
- [ ] Set up API key rotation schedule
