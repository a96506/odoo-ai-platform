# Smart Odoo — Full Architecture Map

## 1. System Overview — 3 Tiers

```mermaid
flowchart LR
    subgraph odoo [Odoo 18 Enterprise]
        Bridge[ai_webhook_mixin\n11 models hooked]
        Callback[ai_callback.py\nHTTP controller]
        OdooDB[(Odoo DB)]
    end

    subgraph platform [AI Platform — Docker Compose]
        subgraph tier1 [Tier 1 — Frontend]
            Dash[Next.js 14 Dashboard\nReact 18 + Tailwind]
        end

        subgraph tier2 [Tier 2 — Backend]
            API[FastAPI ai-service\nUvicorn · Port 8000]
            Worker[Celery Worker\n4 threads · 512MB]
            Beat[Celery Beat\nScheduler · 128MB]
        end

        subgraph tier3 [Tier 3 — Data]
            PG[(PostgreSQL 16\n18 tables · 256MB)]
            Redis[(Redis 7\nBroker + Cache · 256MB)]
        end
    end

    subgraph external [External APIs]
        Claude[Claude Sonnet 4\nAnthropic API]
        SlackAPI[Slack API]
        EmailAPI[SMTP Server]
    end

    User((User)) --> Dash
    User --> odoo

    Bridge -->|"webhook POST\nHMAC-SHA256"| API
    Dash -->|"REST + WebSocket"| API
    API --> Redis
    Beat -->|"cron triggers"| Redis
    Redis --> Worker

    Worker -->|"analyze"| Claude
    Worker -->|"XML-RPC read/write"| Callback
    Callback --> OdooDB

    API --> PG
    Worker --> PG

    Worker -.-> SlackAPI
    Worker -.-> EmailAPI
```

## 2. Backend — Routers (Controllers)

```mermaid
flowchart LR
    subgraph routers [FastAPI Routers — 15 files]
        R1["health.py\nGET /health"]
        R2["dashboard.py\nGET /api/stats\nGET /api/audit-logs\nPOST /api/approve"]
        R3["rules.py\nCRUD /api/rules"]
        R4["chat.py\nPOST /api/chat\nPOST /api/chat/confirm"]
        R5["insights.py\nGET /api/insights\nPOST /api/trigger"]
        R6["closing.py\nMonth-end close"]
        R7["reconciliation.py\nBank recon"]
        R8["deduplication.py\nDedup scan + merge"]
        R9["credit.py\nCredit score + hold"]
        R10["documents.py\nIDP upload + process"]
        R11["digest.py\nDaily digest"]
        R12["forecast.py\nCash flow forecast"]
        R13["reports.py\nNL report builder"]
        R14["role_dashboard.py\nRole-specific data"]
        R15["websocket.py\nWS /ws/dashboard"]
    end

    API[FastAPI main.py\napp factory + lifespan] --> R1 & R2 & R3 & R4 & R5 & R6 & R7 & R8 & R9 & R10 & R11 & R12 & R13 & R14 & R15
```

## 3. Backend — Automation Modules

```mermaid
flowchart TB
    Base[BaseAutomation\nhandle_event · handle_batch\nnotify · confidence gating]

    subgraph automations [11 Automation Modules]
        A1[accounting.py\ncategorize · reconcile\nanomaly detect]
        A2[crm.py\nscore · assign\nfollow-up · dedup]
        A3[sales.py\nquotation · pricing\nforecast]
        A4[purchase.py\nauto-PO · vendor\nbill match]
        A5[inventory.py\ndemand · reorder\ncategorize]
        A6[hr.py\nleave · expense]
        A7[project.py\nassign · estimate · risk]
        A8[helpdesk.py\ncategorize · assign]
        A9[manufacturing.py\nschedule · QC]
        A10[marketing.py\nsegment · optimize]
        A11[cross_app.py\ncross-module intelligence]
    end

    Base --> A1 & A2 & A3 & A4 & A5
    Base --> A6 & A7 & A8 & A9 & A10 & A11
```

## 4. Database — 18 Tables

```mermaid
flowchart TB
    subgraph phase0 [Phase 0 — Core Tables]
        T1[audit_logs\nevery AI decision]
        T2[automation_rules\non/off + thresholds]
        T3[webhook_events\nincoming Odoo events]
    end

    subgraph phase1a [Phase 1 — Finance]
        T4[month_end_closings]
        T5[closing_steps]
        T6[dunning_campaigns]
        T7[dunning_actions]
        T8[credit_scores]
        T9[reconciliation_sessions]
    end

    subgraph phase1b [Phase 1 — Intelligence]
        T10[deduplication_scans]
        T11[duplicate_groups]
        T12[document_processing_jobs]
        T13[extraction_corrections]
        T14[daily_digests]
        T15[report_jobs]
    end

    subgraph phase1c [Phase 1 — Forecasting]
        T16[cash_forecasts]
        T17[forecast_scenarios]
        T18[forecast_accuracy_log]
    end

    T4 --> T5
    T6 --> T7
    T10 --> T11
    T12 --> T13
    T16 --> T17
    T16 --> T18
```

## 5. Webhook Lifecycle — Data Flow

```mermaid
flowchart LR
    A[User creates/edits\nrecord in Odoo] --> B[ai_webhook_mixin\nfires POST]
    B -->|"HMAC signed"| C[FastAPI\n/webhooks/odoo]
    C --> D[Redis\nwebhooks queue]
    D --> E[Celery Worker\npicks up task]
    E --> F[Claude API\nanalyze + tool-use]
    F --> G{Confidence?}
    G -->|">= 0.95"| H[Auto-execute\nXML-RPC write to Odoo]
    G -->|"0.85 - 0.95"| I[Approval Queue\nDashboard notification]
    G -->|"< 0.85"| J[Log only\nAudit trail]
    H --> K[(PostgreSQL\naudit_logs)]
    I --> K
    J --> K
    K --> L[Dashboard\nreal-time via WebSocket]
```

## 6. Celery Beat — 15 Scheduled Tasks

```mermaid
flowchart TB
    Beat[Celery Beat Scheduler]

    subgraph every30 [Every 30 min]
        S1[Lead scoring]
    end

    subgraph every1h [Every 1 hour]
        S2[Bank reconciliation]
        S3[Credit hold release]
        S4[Scheduled reports]
    end

    subgraph every2h [Every 2 hours]
        S5[Reorder points check]
        S6[Production scheduling]
    end

    subgraph every4h [Every 4 hours]
        S7[Demand forecast]
    end

    subgraph every6h [Every 6 hours]
        S8[Cross-app intelligence]
    end

    subgraph daily [Every 24 hours]
        S9[Month-end preclose]
        S10[Credit scoring]
        S11[Daily digest]
        S12[Cash flow forecast]
        S13[Forecast accuracy]
        S14[Contact segmentation]
    end

    subgraph weekly [Every 7 days]
        S15[Deduplication scan]
    end

    Beat --> every30 & every1h & every2h & every4h & every6h & daily & weekly
```

## 7. Docker Services — Startup Order

```mermaid
flowchart BT
    Redis[(Redis 7\nhealthcheck: redis-cli ping)] --> AI
    Redis --> Worker
    Redis --> Beat[Celery Beat\n128MB]
    DB[(PostgreSQL 16\nhealthcheck: pg_isready)] --> AI
    DB --> Worker
    AI[FastAPI ai-service\nhealthcheck: /health\n512MB] --> Dash[Dashboard\nNext.js 14\nPort 3000]
    Worker[Celery Worker\n4 threads\n512MB]
```

## 8. Frontend — Dashboard Components

```mermaid
flowchart TB
    App[page.js\nMain Dashboard]

    subgraph views [10 Components]
        C1[StatsCards.js\nKPI cards]
        C2[AuditLog.js\nDecision trail]
        C3[ApprovalQueue.js\nApprove / Reject]
        C4[RulesPanel.js\nToggle rules]
        C5[ChatInterface.js\nNL chat with ERP]
        C6[InsightsPanel.js\nCross-module insights]
        C7[CFODashboard.js\nCash flow · P&L · AR/AP]
        C8[SalesDashboard.js\nPipeline · Leads · Quotas]
        C9[WarehouseDashboard.js\nStock · Reorder alerts]
        C10[RoleSwitcher.js\nSwitch role views]
    end

    App --> C10
    C10 --> C7 & C8 & C9
    App --> C1 & C2 & C3 & C4 & C5 & C6
```

## 9. Odoo Bridge — Hooked Models

```mermaid
flowchart LR
    Mixin[ai_webhook_mixin\nAbstract model]

    subgraph models [11 Odoo Models]
        M1[account.move\nAccounting]
        M2[crm.lead\nCRM]
        M3[sale.order\nSales]
        M4[purchase.order\nPurchase]
        M5[stock.picking\nInventory]
        M6[hr.leave\nHR Leave]
        M7[hr.expense\nHR Expense]
        M8[project.task\nProject]
        M9[helpdesk.ticket\nHelpdesk]
        M10[mrp.production\nManufacturing]
        M11[mailing.mailing\nMarketing]
    end

    Mixin --> M1 & M2 & M3 & M4 & M5 & M6 & M7 & M8 & M9 & M10 & M11
    M1 & M2 & M3 & M4 & M5 & M6 & M7 & M8 & M9 & M10 & M11 -->|"POST on create/write/unlink"| WH[FastAPI\n/webhooks/odoo]
```

## 10. Tech Stack Summary

```mermaid
flowchart TB
    subgraph frontend [Frontend Stack]
        F1[Next.js 14]
        F2[React 18]
        F3[Tailwind CSS 3]
        F4[recharts]
        F5[date-fns]
    end

    subgraph backend [Backend Stack]
        B1[FastAPI 0.115]
        B2[Uvicorn 0.34]
        B3[Celery 5.4]
        B4[SQLAlchemy 2.0]
        B5[Alembic 1.14]
        B6[Anthropic SDK 0.44]
        B7[httpx 0.28]
        B8[structlog 24.4]
        B9[Pydantic 2.10]
        B10[tenacity 9.0]
    end

    subgraph datatools [Data & AI Libraries]
        D1[pandas + numpy]
        D2[rapidfuzz]
        D3[pdfplumber]
        D4[openpyxl]
    end

    subgraph notifications [Notification SDKs]
        N1[slack-sdk 3.33]
        N2[aiosmtplib 3.0]
    end

    subgraph infra [Infrastructure]
        I1[Docker Compose]
        I2[PostgreSQL 16]
        I3[Redis 7]
        I4[Traefik]
        I5[Dokploy]
        I6[Hetzner VPS]
    end
```
