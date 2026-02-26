# API Contracts

**Referenced by:** [MASTER_PLAN.md](MASTER_PLAN.md) -- Engineering Scaffolding
**Applies to:** Phase 1 deliverables

---

## Current Endpoints (Phase 0)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/health` | None | Service health check |
| POST | `/webhooks/odoo` | Webhook signature | Receive Odoo webhook events |
| GET | `/api/stats` | API key | Dashboard statistics |
| GET | `/api/audit-logs` | API key | Audit trail (paginated) |
| POST | `/api/approve` | API key | Approve/reject pending actions |
| GET | `/api/rules` | API key | List automation rules |
| POST | `/api/rules` | API key | Create automation rule |
| PUT | `/api/rules/{id}` | API key | Update automation rule |
| DELETE | `/api/rules/{id}` | API key | Delete automation rule |
| POST | `/api/chat` | API key | Natural language ERP query |
| POST | `/api/chat/confirm` | API key | Confirm chat write action |
| GET | `/api/insights` | API key | Cross-app intelligence |
| POST | `/api/trigger/{type}/{action}` | API key | Manually trigger automation |

---

## Phase 1 New Endpoints

### Month-End Closing (1.1)

```
POST /api/close/start
  Body: { "period": "2026-02" }
  Response: { "closing_id": 1, "period": "2026-02", "status": "scanning", "steps": [...] }

GET /api/close/{period}/status
  Response: { "closing_id": 1, "period": "2026-02", "status": "in_progress",
              "steps": [{"name": "reconcile_bank", "status": "complete", "items_found": 12, "items_resolved": 12}, ...],
              "overall_progress_pct": 70, "issues": [...] }

POST /api/close/{period}/step/{step_name}/complete
  Body: { "completed_by": "admin", "notes": "Reviewed manually" }
  Response: { "step_name": "reconcile_bank", "status": "complete" }

POST /api/close/{period}/rescan
  Response: { "status": "scanning", "message": "Re-scanning period..." }
```

### Bank Reconciliation (1.3)

```
POST /api/reconciliation/start
  Body: { "journal_id": 1 }
  Response: { "session_id": 1, "total_lines": 120, "auto_matchable": 85, "needs_review": 35 }

GET /api/reconciliation/{session_id}/suggestions
  Query: ?page=1&limit=20
  Response: { "suggestions": [{"bank_line_id": 1, "matched_entry_id": 42,
              "confidence": 0.92, "match_type": "fuzzy", "reasoning": "..."}, ...] }

POST /api/reconciliation/{session_id}/match
  Body: { "bank_line_id": 1, "entry_id": 42 }
  Response: { "matched": true, "session_progress": {"matched": 86, "remaining": 34} }

POST /api/reconciliation/{session_id}/skip
  Body: { "bank_line_id": 1, "reason": "Need more info" }
  Response: { "skipped": true }
```

### Document Processing / IDP (1.4)

```
POST /api/documents/process
  Content-Type: multipart/form-data
  Body: file (PDF/image), document_type (optional)
  Response: { "job_id": 1, "status": "processing" }

GET /api/documents/{job_id}
  Response: { "job_id": 1, "status": "completed", "document_type": "invoice",
              "extraction": {"vendor": "Acme Corp", "date": "2026-02-15", "total": 5400.00,
                            "line_items": [...], "po_reference": "PO-0042"},
              "confidence": 0.96, "field_confidences": {"vendor": 0.99, "total": 0.98, ...},
              "matched_po_id": 42, "odoo_record_created": 1234 }

POST /api/documents/{job_id}/correct
  Body: { "field_name": "vendor", "corrected_value": "Acme Corporation Ltd" }
  Response: { "correction_saved": true }
```

### Deduplication (1.5)

```
POST /api/dedup/scan
  Body: { "scan_type": "contacts" }
  Response: { "scan_id": 1, "status": "running" }

GET /api/dedup/scans
  Query: ?status=completed&page=1
  Response: { "scans": [...], "total": 10 }

GET /api/dedup/scans/{scan_id}/groups
  Response: { "groups": [{"id": 1, "odoo_model": "res.partner",
              "records": [{"id": 42, "name": "Acme Corp"}, {"id": 67, "name": "ACME Corporation"}],
              "similarity": 0.94, "match_fields": ["name", "email"]}, ...] }

POST /api/dedup/groups/{group_id}/merge
  Body: { "master_record_id": 42, "merged_by": "admin" }
  Response: { "merged": true, "records_merged": 1 }

POST /api/dedup/groups/{group_id}/dismiss
  Response: { "dismissed": true }
```

### Credit Management (1.6)

```
GET /api/credit/{customer_id}
  Response: { "customer_id": 42, "credit_score": 78.5, "credit_limit": 25000.00,
              "current_exposure": 18000.00, "overdue_amount": 3500.00,
              "risk_level": "watch", "hold_active": false }

GET /api/credit/at-risk
  Query: ?risk_level=watch,critical&page=1
  Response: { "customers": [...], "total": 12 }

POST /api/credit/{customer_id}/hold
  Body: { "reason": "Exceeded credit limit", "held_by": "admin" }
  Response: { "hold_active": true }

POST /api/credit/{customer_id}/release
  Response: { "hold_active": false }
```

### Report Builder (1.7)

```
POST /api/reports/generate
  Body: { "query": "Sales by product category for Q4 2025", "format": "table" }
  Response: { "job_id": 1, "status": "generating" }

GET /api/reports/{job_id}
  Response: { "job_id": 1, "status": "completed", "format": "table",
              "data": {"columns": [...], "rows": [...]}, "query_parsed": {...} }

GET /api/reports/{job_id}/download
  Query: ?format=excel|pdf
  Response: File download

POST /api/reports/schedule
  Body: { "query": "Weekly sales summary", "cron": "0 8 * * MON", "format": "pdf",
          "deliver_via": "email", "recipient": "cfo@company.com" }
  Response: { "job_id": 1, "schedule": "Every Monday at 8 AM" }
```

### Cash Flow Forecast (1.8)

```
GET /api/forecast/cashflow
  Query: ?horizon=90
  Response: { "generated_at": "2026-02-26T06:00:00Z",
              "forecasts": [{"date": "2026-03-01", "balance": 125000.00,
                            "low": 110000.00, "high": 140000.00}, ...],
              "ar_summary": {...}, "ap_summary": {...} }

POST /api/forecast/scenario
  Body: { "name": "Customer X pays late", "adjustments": {"delay_customer_42": 30} }
  Response: { "scenario_id": 1, "forecasts": [...], "impact": {"cash_gap_date": "2026-04-15"} }

GET /api/forecast/accuracy
  Response: { "last_30_days": {"mae": 2500.00, "mape": 3.2} }
```

### Daily Digest (1.11)

```
GET /api/digest/latest
  Query: ?role=cfo
  Response: { "digest_date": "2026-02-26", "role": "cfo",
              "content": {"headline": "...", "key_metrics": [...],
                         "attention_items": [...], "anomalies": [...]} }

POST /api/digest/send
  Body: { "role": "cfo", "channel": "slack" }
  Response: { "sent": true, "channel": "slack" }

PUT /api/digest/config
  Body: { "role": "cfo", "channels": ["email", "slack"], "send_time": "07:00" }
  Response: { "updated": true }
```

---

## Common Response Patterns

### Pagination

All list endpoints support:

```
?page=1&limit=20

Response includes: { "items": [...], "total": 100, "page": 1, "limit": 20 }
```

### Error Responses

```json
{
    "detail": "Human-readable error message",
    "error_code": "MACHINE_READABLE_CODE",
    "context": {}
}
```

| Status Code | When |
|-------------|------|
| 400 | Invalid request body or query parameters |
| 401 | Missing or invalid API key |
| 404 | Resource not found |
| 409 | Conflict (e.g., closing already in progress for period) |
| 422 | Pydantic validation failure |
| 429 | Rate limit exceeded |
| 500 | Internal server error |

### Versioning

API is unversioned for now (all endpoints under `/api/`). When breaking changes are needed (Phase 2+), prefix with `/api/v2/` and maintain `/api/v1/` for backward compatibility for 6 months.

---

## WebSocket Events (Phase 1.10)

Real-time push updates for the dashboard:

```
WS /ws/dashboard

Events:
  { "type": "automation_completed", "data": { "audit_log_id": 1, ... } }
  { "type": "approval_needed", "data": { "audit_log_id": 2, ... } }
  { "type": "forecast_updated", "data": { "date": "2026-02-26" } }
  { "type": "alert", "data": { "severity": "high", "message": "..." } }
```

---

## Rate Limits

| Endpoint Group | Limit | Window |
|---------------|-------|--------|
| `/api/chat` | 30 requests | per minute |
| `/api/reports/generate` | 10 requests | per minute |
| `/api/documents/process` | 20 requests | per minute |
| `/webhooks/odoo` | 100 requests | per minute |
| All other endpoints | 60 requests | per minute |
