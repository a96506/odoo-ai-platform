# Testing Strategy

**Referenced by:** [MASTER_PLAN.md](MASTER_PLAN.md) -- Engineering Scaffolding
**Applies to:** All phases

---

## Philosophy

Every automation makes decisions about real business data (money, customers, inventory). A single bug in confidence gating could auto-approve a $50K payment or silently drop invoices. Testing is not optional -- it is the primary guardrail alongside the confidence system.

---

## Test Layers

### Layer 1: Unit Tests

Test individual functions and classes in isolation. Mock all external dependencies (Odoo, Claude, Redis, PostgreSQL).

**Framework:** `pytest` + `pytest-asyncio`

**What to test:**

| Component | Test Focus | Mock Strategy |
|-----------|-----------|---------------|
| `BaseAutomation` subclasses | Event routing, handler dispatch, confidence gating logic | Mock `odoo_client`, `claude_client` |
| `ClaudeClient` | Response parsing, tool call extraction, error handling | Mock `anthropic.Anthropic` |
| `OdooClient` | XML-RPC call construction, response parsing, error handling | Mock `xmlrpc.client.ServerProxy` |
| `NotificationService` | Channel routing, fallback logic, `is_configured()` checks | Mock channel implementations |
| Pydantic schemas | Validation, serialization, edge cases (missing fields, wrong types) | None needed |
| Confidence gating | `should_auto_execute()`, `needs_approval()` at boundary values | None needed |
| Config / Settings | Default values, env var parsing, property methods | Env var fixtures |

**Naming convention:** `tests/unit/test_{module}.py`

**Example structure:**

```
ai_service/tests/
├── conftest.py                  # Shared fixtures (mock Odoo, mock Claude, test DB)
├── unit/
│   ├── test_base_automation.py
│   ├── test_claude_client.py
│   ├── test_odoo_client.py
│   ├── test_confidence_gating.py
│   ├── test_notification_service.py
│   ├── test_schemas.py
│   ├── automations/
│   │   ├── test_accounting.py
│   │   ├── test_crm.py
│   │   ├── test_sales.py
│   │   ├── test_purchase.py
│   │   ├── test_inventory.py
│   │   ├── test_hr.py
│   │   ├── test_project.py
│   │   ├── test_helpdesk.py
│   │   ├── test_manufacturing.py
│   │   ├── test_marketing.py
│   │   └── test_cross_app.py
│   └── phase1/
│       ├── test_month_end.py
│       ├── test_deduplication.py
│       ├── test_credit_management.py
│       ├── test_forecasting.py
│       ├── test_reporting.py
│       └── test_document_processing.py
├── integration/
│   ├── test_webhook_to_celery.py
│   ├── test_celery_to_automation.py
│   ├── test_api_endpoints.py
│   └── test_db_operations.py
└── fixtures/
    ├── webhook_payloads/
    │   ├── crm_lead_create.json
    │   ├── account_move_write.json
    │   ├── sale_order_create.json
    │   ├── purchase_order_write.json
    │   ├── stock_picking_write.json
    │   ├── hr_leave_create.json
    │   ├── hr_expense_create.json
    │   ├── project_task_create.json
    │   ├── helpdesk_ticket_create.json
    │   ├── mrp_production_create.json
    │   └── mailing_mailing_write.json
    ├── claude_responses/
    │   ├── lead_scoring.json
    │   ├── transaction_categorization.json
    │   ├── reconciliation_match.json
    │   └── anomaly_detection.json
    └── odoo_records/
        ├── sample_invoice.json
        ├── sample_lead.json
        ├── sample_product.json
        └── sample_partner.json
```

---

### Layer 2: Integration Tests

Test component interactions with real (but isolated) infrastructure.

**Database:** Use a separate PostgreSQL instance (or `testcontainers-python` to spin one up). Run Alembic migrations before each test suite, rollback after.

**Redis:** Use a separate Redis instance or `fakeredis` for Celery broker simulation.

**Odoo:** NOT required for integration tests. Mock the XML-RPC layer with recorded responses.

**Claude API:** NOT called in integration tests. Use recorded responses from `fixtures/claude_responses/`.

| Test | What It Validates |
|------|------------------|
| Webhook -> Celery dispatch | FastAPI receives webhook, validates signature, dispatches correct Celery task |
| Celery task -> Automation | Task loads correct automation class, passes data, handles result |
| Automation -> AuditLog | Result is written to DB with correct fields, confidence, status |
| Approval flow | Pending audit log -> approve API call -> status change -> execute handler |
| Rule enable/disable | Disabled rule prevents automation execution |
| API endpoint auth | Endpoints return 401/403 when auth is missing or invalid |

---

### Layer 3: Claude Response Tests (Prompt Regression)

Claude's responses are non-deterministic. These tests validate that our prompt + tool schema produces parseable, actionable output.

**How it works:**
1. Record real Claude responses for each automation type (golden responses)
2. Parse them through the same code path as production
3. Assert the parsed result has required fields, valid confidence ranges, and sensible actions

**When to re-record:** When prompts change, when Claude model version changes, when tool schemas change.

**Budget:** Set a monthly test budget for Claude API calls (~$20/month). Run prompt regression tests weekly, not on every CI push.

---

### Layer 4: End-to-End Tests (Staging Only)

Full pipeline test against a staging Odoo instance with test data.

**Frequency:** Before each deployment to production. Not in CI (too slow, requires live Odoo).

**Setup:**
1. Staging Odoo with synthetic test data (use `scripts/populate_odoo_data.py`)
2. AI service pointing at staging Odoo
3. Create a test record in Odoo -> verify webhook fires -> verify automation runs -> verify Odoo record updated

**E2E test scenarios:**

| Scenario | Steps | Expected Result |
|----------|-------|----------------|
| Lead scoring | Create CRM lead -> AI scores it -> lead gets priority tag | Lead has score, priority, assignment |
| Transaction categorization | Create bank statement line -> AI categorizes | Journal entry with correct account |
| Invoice matching | Create vendor bill -> AI matches to PO | Bill linked to PO, discrepancies flagged |
| Leave approval | Create leave request -> AI checks policy | Auto-approved or routed to manager |
| Anomaly detection | Create unusual transaction -> AI flags it | Audit log with anomaly flag |

---

## Mock Strategy for Claude API

**Problem:** Claude API calls cost money and are non-deterministic. Running 500 tests with real API calls is expensive and flaky.

**Solution:** Three-tier mock strategy.

| Tier | When | How |
|------|------|-----|
| **Unit tests** | Always | `unittest.mock.patch` on `ClaudeClient.analyze` returning fixture data |
| **Integration tests** | Always | Same mock, but verify the mock is called with correct prompt structure |
| **Prompt regression** | Weekly scheduled | Real Claude API call with `temperature=0.0`, compare output structure to golden response |

**Recording golden responses:**

```python
# Run once to record, then use fixture in tests
response = claude.analyze(system_prompt=PROMPT, user_message=DATA, tools=TOOLS)
with open("fixtures/claude_responses/lead_scoring.json", "w") as f:
    json.dump(response, f, indent=2)
```

---

## Test Data Strategy

### Webhook Payloads

Each automation needs realistic webhook payloads. Store in `tests/fixtures/webhook_payloads/`.

**Requirements per fixture:**
- Valid `event_type` (create/write/unlink)
- Realistic `values` dict matching Odoo model fields
- Edge cases: empty values, missing optional fields, Unicode characters (Arabic names)

### Odoo Records

Simulated responses from `odoo_client.get_record()` and `odoo_client.search_read()`.

**Generate from live Odoo:** Use `scripts/populate_odoo_data.py` to create test data, then record XML-RPC responses as JSON fixtures.

---

## CI/CD Pipeline

```
┌─────────────────┐
│  Git Push/PR     │
└────────┬────────┘
         │
    ┌────▼────┐
    │  Lint   │  ruff check, ruff format --check, mypy
    └────┬────┘
         │
    ┌────▼──────────┐
    │  Unit Tests   │  pytest tests/unit/ --cov (target: 80%+)
    └────┬──────────┘
         │
    ┌────▼────────────────┐
    │  Integration Tests  │  pytest tests/integration/ (needs test DB + Redis)
    └────┬────────────────┘
         │
    ┌────▼───────────────┐
    │  Build Docker      │  docker compose build (verify images build)
    └────┬───────────────┘
         │
    ┌────▼────────────┐
    │  Deploy Staging  │  (only on main branch merge)
    └────┬────────────┘
         │
    ┌────▼──────────┐
    │  E2E Tests    │  Against staging Odoo (only on main branch)
    └────┬──────────┘
         │
    ┌────▼────────────┐
    │  Deploy Prod    │  Manual approval gate
    └─────────────────┘
```

**CI tool:** GitHub Actions (`.github/workflows/ci.yml`)

---

## Coverage Targets

| Area | Target | Notes |
|------|--------|-------|
| Confidence gating logic | 100% | Safety-critical: every boundary condition tested |
| Schema validation | 100% | Input validation prevents garbage data |
| Automation handlers | 80% | Core logic paths, not every error branch |
| API endpoints | 90% | All happy paths + auth failures + validation errors |
| Notification channels | 70% | Basic send/fail, not every API edge case |
| Overall | 80% | Measured by `pytest-cov` |

---

## Test Dependencies to Add

```
# Add to ai_service/requirements-dev.txt
pytest>=8.0.0
pytest-asyncio>=0.23.0
pytest-cov>=4.1.0
httpx>=0.28.0              # Already in main deps, used for TestClient
fakeredis>=2.21.0           # In-memory Redis for tests
factory-boy>=3.3.0          # Test data factories for SQLAlchemy models
```

---

## Running Tests

```bash
# All unit tests
cd ai_service && pytest tests/unit/ -v

# With coverage
pytest tests/unit/ --cov=app --cov-report=html

# Integration tests (needs running test DB)
pytest tests/integration/ -v

# Single automation module
pytest tests/unit/automations/test_accounting.py -v

# Prompt regression (uses real Claude API -- costs money)
CLAUDE_TEST_MODE=live pytest tests/prompt_regression/ -v
```
