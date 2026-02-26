# Prompt Engineering

**Referenced by:** [MASTER_PLAN.md](MASTER_PLAN.md) -- Engineering Scaffolding
**Applies to:** All phases

---

## Overview

Every automation sends data to Claude via the `ClaudeClient.analyze()` method with a system prompt, user message, and tool definitions. This document centralizes the prompt architecture, versioning strategy, and cost management approach.

---

## Prompt Architecture

Each Claude call follows this structure:

```
┌─────────────────────────────────┐
│  System Prompt                  │  Role, constraints, output format
├─────────────────────────────────┤
│  User Message                   │  Actual data to analyze (Odoo record fields)
├─────────────────────────────────┤
│  Tools                          │  Structured output schema (tool-use)
└─────────────────────────────────┘
```

### System Prompt Pattern

All automation system prompts follow this template:

```
You are an AI assistant for {module_name} automation in an Odoo ERP system.

Your task: {specific_task_description}

Context:
- Company industry: {industry}
- Currency: {currency}
- Timezone: {timezone}

Rules:
1. Return your analysis using the provided tool.
2. Your confidence score must be between 0.0 and 1.0.
3. Confidence >= 0.95 means you are certain and the action can be auto-executed.
4. Confidence 0.85-0.95 means you are fairly sure but a human should confirm.
5. Confidence < 0.85 means you are unsure and the result should be logged only.
6. Always provide reasoning for your decision.
7. {module_specific_rules}
```

### Tool-Use Schema Pattern

Every automation returns its decision via a tool call (not free text). This ensures structured, parseable output.

```python
tools = [
    {
        "name": "automation_decision",
        "description": "Return the automation decision with confidence and reasoning",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "Action to take"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "reasoning": {"type": "string"},
                # ... module-specific fields
            },
            "required": ["action", "confidence", "reasoning"],
        },
    }
]
```

---

## Prompt Catalog

### Phase 0 Prompts (Deployed)

#### Accounting: Transaction Categorization

```
System: You are an AI accountant assistant. Categorize this bank transaction
into the correct chart of accounts category.

Tool output: account_id, account_name, confidence, reasoning
Temperature: 0.0
Avg tokens: ~800 in, ~200 out
Cost per call: ~$0.003
```

#### Accounting: Bank Reconciliation Matching

```
System: You are an AI bank reconciliation assistant. Match this bank
statement line to the most likely Odoo journal entry.

Tool output: matched_entry_id, match_type (exact/partial/none), confidence, reasoning
Temperature: 0.0
Avg tokens: ~1200 in, ~300 out
Cost per call: ~$0.005
```

#### Accounting: Anomaly Detection

```
System: You are an AI fraud/anomaly detection assistant. Analyze this
transaction for unusual patterns.

Tool output: is_anomaly, anomaly_type, severity, confidence, reasoning
Temperature: 0.0
Avg tokens: ~600 in, ~200 out
Cost per call: ~$0.002
```

#### CRM: Lead Scoring

```
System: You are an AI sales intelligence assistant. Score this lead
based on likelihood to convert.

Tool output: score (0-100), priority (hot/warm/cold), reasoning,
             suggested_salesperson
Temperature: 0.0
Avg tokens: ~500 in, ~200 out
Cost per call: ~$0.002
```

#### CRM: Follow-Up Generation

```
System: You are an AI sales assistant. Draft a follow-up email for this
lead based on the current stage and context.

Tool output: subject, body, suggested_send_time, confidence
Temperature: 0.3 (slight creativity for email content)
Avg tokens: ~800 in, ~400 out
Cost per call: ~$0.004
```

#### Sales: Pricing Optimization

```
System: You are an AI pricing analyst. Recommend optimal pricing for
this quotation based on customer history, margin targets, and market data.

Tool output: recommended_price, discount_pct, margin_impact, confidence, reasoning
Temperature: 0.0
Avg tokens: ~1000 in, ~300 out
Cost per call: ~$0.004
```

### Phase 1 Prompts (New)

#### Month-End Closing Analysis

```
System: You are an AI controller assistant for month-end closing. Analyze
the current state of the accounting period and identify issues blocking close.

Tool output: step_status[], issues[], recommendations[], overall_readiness_pct
Temperature: 0.0
Avg tokens: ~3000 in, ~800 out (large context: full period data)
Cost per call: ~$0.012
```

#### IDP Document Extraction

```
System: You are an AI document processing specialist. Extract structured
data from this document image/PDF.

Uses: Claude Vision API (multi-modal)
Tool output: vendor_name, invoice_number, date, line_items[], totals,
             tax_amount, po_reference, confidence_per_field
Temperature: 0.0
Avg tokens: ~500 text + image, ~600 out
Cost per call: ~$0.01-0.03 (vision is more expensive)
```

#### Credit Scoring

```
System: You are an AI credit risk analyst. Calculate a credit risk score
for this customer based on payment history, order volume, and overdue exposure.

Tool output: credit_score (0-100), risk_level, recommended_limit,
             hold_recommendation, reasoning
Temperature: 0.0
Avg tokens: ~800 in, ~300 out
Cost per call: ~$0.003
```

#### Report Query Parsing

```
System: You are an AI report builder. Parse this natural language report
request into a structured Odoo data query.

Tool output: odoo_model, domain_filter, fields, group_by, order_by,
             date_range, format
Temperature: 0.0
Avg tokens: ~300 in, ~200 out
Cost per call: ~$0.001
```

#### Daily Digest Generation

```
System: You are an AI executive briefing assistant. Generate a morning
digest for this role based on the provided ERP data summary.

Tool output: headline, key_metrics[], attention_items[], anomalies[],
             recommendations[]
Temperature: 0.2 (readable narrative)
Avg tokens: ~2000 in, ~600 out
Cost per call: ~$0.008
```

---

## Model Selection Strategy

| Task Type | Model | Why |
|-----------|-------|-----|
| Structured decisions (scoring, categorization, matching) | Claude Sonnet | Best price/performance for tool-use |
| Creative content (email drafts, digest narratives) | Claude Sonnet | Good enough, much cheaper than Opus |
| Complex analysis (month-end, multi-factor credit) | Claude Sonnet | Sufficient for structured analysis |
| Document vision (IDP) | Claude Sonnet (vision) | Multi-modal support required |
| Simple parsing (report query NL->structured) | Claude Haiku | Cheapest for simple transformations |

**Default model in config:** `claude-sonnet-4-20250514`

**Override per task:** Add `claude_model` field to `AutomationRule.config` JSONB to allow per-rule model selection.

---

## Cost Estimation

### Phase 0 (Current)

| Automation | Calls/Day | Cost/Call | Daily Cost |
|-----------|-----------|----------|------------|
| Transaction categorization | 50 | $0.003 | $0.15 |
| Bank reconciliation | 30 | $0.005 | $0.15 |
| Lead scoring | 20 | $0.002 | $0.04 |
| Follow-up generation | 10 | $0.004 | $0.04 |
| Other automations | 40 | $0.003 | $0.12 |
| Cross-app intelligence | 4 | $0.015 | $0.06 |
| Chat queries | 20 | $0.005 | $0.10 |
| **Total** | **~174** | | **~$0.66/day ($20/month)** |

### Phase 1 (Projected)

| New Automation | Calls/Day | Cost/Call | Daily Cost |
|---------------|-----------|----------|------------|
| Month-end closing (monthly burst) | 2 | $0.012 | $0.024 |
| IDP document processing | 15 | $0.02 | $0.30 |
| Credit scoring (daily batch) | 5 | $0.003 | $0.015 |
| Report generation | 10 | $0.001 | $0.01 |
| Daily digest | 7 | $0.008 | $0.056 |
| Cash flow forecast | 1 | $0.012 | $0.012 |
| Dedup scans (weekly) | 1 | $0.01 | $0.01 |
| **Phase 1 Addition** | **~51** | | **~$0.48/day ($14/month)** |
| **Grand Total** | **~225** | | **~$1.14/day ($34/month)** |

---

## Prompt Versioning

### Strategy

Prompts are embedded in automation code (not in a separate config). Version them by:

1. **Comment header** in each prompt with version and date
2. **Audit log** records the prompt version used for each decision
3. **A/B testing** via `AutomationRule.config`: store `prompt_version` field to route between versions

### Prompt Change Process

1. Write new prompt version
2. Test against recorded golden responses (see [TESTING_STRATEGY.md](TESTING_STRATEGY.md))
3. Deploy with feature flag routing 10% of traffic to new prompt
4. Compare confidence distribution and accuracy between versions
5. If new prompt is better, promote to 100%

---

## Fallback Behavior

| Failure Mode | Handling |
|-------------|---------|
| Claude API timeout (>30s) | Retry once with `tenacity`, then log as failed |
| Claude returns no tool call | Parse text response, log warning, set confidence=0.0 |
| Claude returns malformed tool input | Validate against Pydantic schema, log error, skip action |
| Claude API rate limited (429) | Exponential backoff via `tenacity` (max 3 retries) |
| Claude API down (500/503) | Log error, set automation to deferred, retry via Celery |
| Unexpected confidence value | Clamp to 0.0-1.0 range, log warning |

---

## Token Budget Controls

| Control | Value | Action When Exceeded |
|---------|-------|---------------------|
| Max tokens per single call | 8,192 output | Claude enforced |
| Max input context per call | 50,000 tokens | Truncate oldest data, log warning |
| Max cost per automation run | $0.10 | Abort and log error |
| Max daily spend (all automations) | $5.00 | Pause non-critical automations, alert admin |
| Max monthly spend | $100.00 | Alert admin, require manual override to continue |
