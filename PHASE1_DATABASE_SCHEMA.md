# Phase 1 Database Schema

**Referenced by:** [MASTER_PLAN.md](MASTER_PLAN.md) -- Engineering Scaffolding
**Applies to:** Phase 1 deliverables

---

## Current Schema (Phase 0)

Three tables exist in the AI database:

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `audit_logs` | Every AI decision | id, timestamp, automation_type, action_name, odoo_model, odoo_record_id, status, confidence, ai_reasoning, input_data, output_data, tokens_used |
| `automation_rules` | Enable/disable rules per automation | id, name, automation_type, action_name, enabled, confidence_threshold, auto_approve, config |
| `webhook_events` | Raw webhook event log | id, received_at, event_type, odoo_model, odoo_record_id, payload, processed |

---

## Phase 1 New Tables

### 1. `cash_forecasts` (Deliverable 1.8)

Stores daily cash flow forecast snapshots.

```sql
CREATE TABLE cash_forecasts (
    id              SERIAL PRIMARY KEY,
    forecast_date   DATE NOT NULL,
    target_date     DATE NOT NULL,
    predicted_balance DECIMAL(15,2) NOT NULL,
    confidence_low  DECIMAL(15,2),
    confidence_high DECIMAL(15,2),
    ar_expected     DECIMAL(15,2) DEFAULT 0,
    ap_expected     DECIMAL(15,2) DEFAULT 0,
    pipeline_expected DECIMAL(15,2) DEFAULT 0,
    recurring_expected DECIMAL(15,2) DEFAULT 0,
    model_version   VARCHAR(50),
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_cash_forecasts_dates ON cash_forecasts(forecast_date, target_date);
```

### 2. `forecast_scenarios` (Deliverable 1.8)

User-defined what-if scenarios for cash flow.

```sql
CREATE TABLE forecast_scenarios (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    adjustments     JSONB NOT NULL DEFAULT '{}',
    base_forecast_id INTEGER REFERENCES cash_forecasts(id),
    result_data     JSONB,
    created_by      VARCHAR(255),
    created_at      TIMESTAMP DEFAULT NOW()
);
```

### 3. `forecast_accuracy_log` (Deliverable 1.8)

Tracks forecast vs. actual for model improvement.

```sql
CREATE TABLE forecast_accuracy_log (
    id              SERIAL PRIMARY KEY,
    forecast_id     INTEGER REFERENCES cash_forecasts(id),
    target_date     DATE NOT NULL,
    predicted_balance DECIMAL(15,2),
    actual_balance  DECIMAL(15,2),
    error_pct       DECIMAL(8,4),
    logged_at       TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_forecast_accuracy_date ON forecast_accuracy_log(target_date);
```

### 4. `credit_scores` (Deliverable 1.6)

AI-calculated customer credit scores.

```sql
CREATE TABLE credit_scores (
    id              SERIAL PRIMARY KEY,
    customer_id     INTEGER NOT NULL UNIQUE,
    customer_name   VARCHAR(255),
    credit_score    DECIMAL(5,2),
    credit_limit    DECIMAL(15,2),
    current_exposure DECIMAL(15,2) DEFAULT 0,
    overdue_amount  DECIMAL(15,2) DEFAULT 0,
    payment_history_score DECIMAL(5,2),
    order_volume_score DECIMAL(5,2),
    risk_level      VARCHAR(20) DEFAULT 'normal',
    hold_active     BOOLEAN DEFAULT FALSE,
    hold_reason     TEXT,
    last_calculated TIMESTAMP DEFAULT NOW(),
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_credit_scores_customer ON credit_scores(customer_id);
CREATE INDEX idx_credit_scores_hold ON credit_scores(hold_active);
```

### 7. `month_end_closings` (Deliverable 1.1)

Tracks month-end closing progress.

```sql
CREATE TABLE month_end_closings (
    id              SERIAL PRIMARY KEY,
    period          VARCHAR(7) NOT NULL,
    status          VARCHAR(20) DEFAULT 'in_progress',
    started_at      TIMESTAMP DEFAULT NOW(),
    completed_at    TIMESTAMP,
    started_by      VARCHAR(255),
    checklist       JSONB DEFAULT '{}',
    issues_found    JSONB DEFAULT '[]',
    summary         TEXT,
    lock_date_set   BOOLEAN DEFAULT FALSE
);

CREATE UNIQUE INDEX idx_month_end_period ON month_end_closings(period);
```

### 8. `closing_steps` (Deliverable 1.1)

Individual steps within a month-end closing.

```sql
CREATE TABLE closing_steps (
    id              SERIAL PRIMARY KEY,
    closing_id      INTEGER REFERENCES month_end_closings(id) ON DELETE CASCADE,
    step_name       VARCHAR(100) NOT NULL,
    step_order      INTEGER NOT NULL,
    status          VARCHAR(20) DEFAULT 'pending',
    auto_check_result JSONB,
    items_found     INTEGER DEFAULT 0,
    items_resolved  INTEGER DEFAULT 0,
    started_at      TIMESTAMP,
    completed_at    TIMESTAMP,
    completed_by    VARCHAR(255),
    notes           TEXT
);

CREATE INDEX idx_closing_steps_closing ON closing_steps(closing_id);
```

### 9. `deduplication_scans` (Deliverable 1.5)

Tracks deduplication scan runs and results.

```sql
CREATE TABLE deduplication_scans (
    id              SERIAL PRIMARY KEY,
    scan_type       VARCHAR(50) NOT NULL,
    status          VARCHAR(20) DEFAULT 'running',
    total_records   INTEGER DEFAULT 0,
    duplicates_found INTEGER DEFAULT 0,
    auto_merged     INTEGER DEFAULT 0,
    pending_review  INTEGER DEFAULT 0,
    started_at      TIMESTAMP DEFAULT NOW(),
    completed_at    TIMESTAMP
);

CREATE INDEX idx_dedup_scans_type ON deduplication_scans(scan_type);
```

### 10. `duplicate_groups` (Deliverable 1.5)

Groups of duplicate records found by a scan.

```sql
CREATE TABLE duplicate_groups (
    id              SERIAL PRIMARY KEY,
    scan_id         INTEGER REFERENCES deduplication_scans(id) ON DELETE CASCADE,
    odoo_model      VARCHAR(255) NOT NULL,
    record_ids      JSONB NOT NULL,
    master_record_id INTEGER,
    similarity_score DECIMAL(5,4),
    match_fields    JSONB DEFAULT '[]',
    status          VARCHAR(20) DEFAULT 'pending',
    resolved_at     TIMESTAMP,
    resolved_by     VARCHAR(255),
    resolution      VARCHAR(20)
);

CREATE INDEX idx_duplicate_groups_scan ON duplicate_groups(scan_id);
CREATE INDEX idx_duplicate_groups_status ON duplicate_groups(status);
```

### 11. `document_processing_jobs` (Deliverable 1.4)

IDP document processing pipeline.

```sql
CREATE TABLE document_processing_jobs (
    id              SERIAL PRIMARY KEY,
    file_name       VARCHAR(500),
    file_type       VARCHAR(20),
    document_type   VARCHAR(50),
    status          VARCHAR(20) DEFAULT 'queued',
    source          VARCHAR(50) DEFAULT 'upload',
    uploaded_by     VARCHAR(255),
    extraction_result JSONB,
    matched_po_id   INTEGER,
    matched_vendor_id INTEGER,
    overall_confidence DECIMAL(5,4),
    field_confidences JSONB DEFAULT '{}',
    odoo_record_created INTEGER,
    odoo_model_created VARCHAR(255),
    error_message   TEXT,
    processing_time_ms INTEGER,
    created_at      TIMESTAMP DEFAULT NOW(),
    completed_at    TIMESTAMP
);

CREATE INDEX idx_doc_jobs_status ON document_processing_jobs(status);
CREATE INDEX idx_doc_jobs_type ON document_processing_jobs(document_type);
```

### 12. `extraction_corrections` (Deliverable 1.4)

Human corrections to IDP extractions for learning loop.

```sql
CREATE TABLE extraction_corrections (
    id              SERIAL PRIMARY KEY,
    job_id          INTEGER REFERENCES document_processing_jobs(id) ON DELETE CASCADE,
    field_name      VARCHAR(100) NOT NULL,
    original_value  TEXT,
    corrected_value TEXT,
    corrected_by    VARCHAR(255),
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_corrections_job ON extraction_corrections(job_id);
```

### 13. `reconciliation_sessions` (Deliverable 1.3)

Bank reconciliation session state with memory.

```sql
CREATE TABLE reconciliation_sessions (
    id              SERIAL PRIMARY KEY,
    user_id         VARCHAR(255),
    journal_id      INTEGER,
    status          VARCHAR(20) DEFAULT 'active',
    total_lines     INTEGER DEFAULT 0,
    auto_matched    INTEGER DEFAULT 0,
    manually_matched INTEGER DEFAULT 0,
    skipped         INTEGER DEFAULT 0,
    remaining       INTEGER DEFAULT 0,
    learned_rules   JSONB DEFAULT '[]',
    started_at      TIMESTAMP DEFAULT NOW(),
    last_activity   TIMESTAMP DEFAULT NOW(),
    completed_at    TIMESTAMP
);

CREATE INDEX idx_recon_sessions_status ON reconciliation_sessions(status);
CREATE INDEX idx_recon_sessions_user ON reconciliation_sessions(user_id);
```

### 14. `daily_digests` (Deliverable 1.11)

Tracks daily digest generation and delivery.

```sql
CREATE TABLE daily_digests (
    id              SERIAL PRIMARY KEY,
    user_role       VARCHAR(100) NOT NULL,
    digest_date     DATE NOT NULL,
    content         JSONB NOT NULL,
    channels_sent   JSONB DEFAULT '[]',
    delivered       BOOLEAN DEFAULT FALSE,
    generated_at    TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_digest_date_role ON daily_digests(digest_date, user_role);
```

### 15. `report_jobs` (Deliverable 1.7)

Natural language report requests and outputs.

```sql
CREATE TABLE report_jobs (
    id              SERIAL PRIMARY KEY,
    request_text    TEXT NOT NULL,
    parsed_query    JSONB,
    result_data     JSONB,
    format          VARCHAR(20) DEFAULT 'table',
    file_path       VARCHAR(500),
    schedule_cron   VARCHAR(100),
    requested_by    VARCHAR(255),
    status          VARCHAR(20) DEFAULT 'pending',
    error_message   TEXT,
    created_at      TIMESTAMP DEFAULT NOW(),
    completed_at    TIMESTAMP
);

CREATE INDEX idx_report_jobs_status ON report_jobs(status);
CREATE INDEX idx_report_jobs_schedule ON report_jobs(schedule_cron) WHERE schedule_cron IS NOT NULL;
```

---

## Migration Plan

### Sequence

All tables are independent (no cross-table foreign keys except within feature pairs). Create migrations in this order:

| Migration | Tables | Deliverable |
|-----------|--------|-------------|
| `002_month_end_closing.py` | `month_end_closings`, `closing_steps` | 1.1 |
| `003_reconciliation_sessions.py` | `reconciliation_sessions` | 1.3 |
| `005_document_processing.py` | `document_processing_jobs`, `extraction_corrections` | 1.4 |
| `006_deduplication.py` | `deduplication_scans`, `duplicate_groups` | 1.5 |
| `007_credit_management.py` | `credit_scores` | 1.6 |
| `008_reporting.py` | `report_jobs` | 1.7 |
| `009_cash_forecasting.py` | `cash_forecasts`, `forecast_scenarios`, `forecast_accuracy_log` | 1.8 |
| `010_daily_digests.py` | `daily_digests` | 1.11 |

### Commands

```bash
cd ai_service

# Generate migration from model changes
alembic revision --autogenerate -m "add month end closing tables"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Check current state
alembic current
```

### Indexing Strategy

Every table includes indexes on:
- **Status columns** -- queries filter by status constantly
- **Date columns** -- dashboards query by date range
- **Foreign keys** -- joins between parent/child tables
- **Customer/user IDs** -- lookups by entity

### Data Retention

| Table | Retention | Cleanup |
|-------|-----------|---------|
| `audit_logs` | 12 months | Archive to cold storage, delete after 24 months |
| `webhook_events` | 3 months | Delete after processing confirmation |
| `cash_forecasts` | 24 months | Keep for accuracy tracking |
| `document_processing_jobs` | 6 months | Keep extraction results, delete raw file references |
| `reconciliation_sessions` | 6 months | Delete completed sessions |
| `report_jobs` | 3 months | Delete generated files after 30 days |

---

## SQLAlchemy Models Location

New models added to `ai_service/app/models/audit.py` (sharing the existing `Base = declarative_base()` instance so Alembic autogenerate detects all tables).

Phase 0 total: 3 tables. Phase 1 total: 18 tables (+15).
