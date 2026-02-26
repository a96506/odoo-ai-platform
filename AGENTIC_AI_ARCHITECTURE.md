# Agentic AI Architecture -- Pillar 1C Detail Document

**Research date:** February 2026
**Sources:** LangGraph documentation, AutoGen, CrewAI, SAP Joule architecture, Microsoft Dynamics 365 AI agents, McKinsey AI-ERP analysis, Towards AI, BIX Tech
**Referenced by:** [MASTER_PLAN.md](MASTER_PLAN.md) -- Pillar 1C

---

## Why This Upgrade Is Needed

Our current architecture handles each automation as a single-action handler:

```
Event -> Analyze with Claude -> Take one action -> Log result
```

This works for simple decisions (score a lead, categorize a transaction) but fails for complex, multi-step business workflows that require state, branching, and cross-module coordination. Real-world ERP operations are multi-step:

**Example: A vendor invoice arrives**
1. Extract data from document (IDP)
2. Match to purchase order
3. Validate quantities and prices against PO
4. Check if goods were received (stock.picking)
5. If discrepancy: notify purchasing + vendor portal
6. If match: create draft bill
7. If amount > threshold: route for approval
8. On approval: post bill, schedule payment
9. Update vendor performance score

Our current system would need 9 separate automations coordinated manually. An agentic system handles this as one autonomous workflow.

**Market context:**
- 67% of large enterprises run autonomous AI agents in production (Jan 2026)
- SAP Joule has 1,300+ skills with multi-step agent orchestration
- Microsoft Dynamics 365 shipped Account Reconciliation Agent (autonomous)
- Gartner predicts 40% of agent projects will be canceled by 2027 due to inadequate controls -- we must build with guardrails from day 1

---

## Current Architecture (Phase 0)

```
Odoo Webhook Event
  |
  v
FastAPI endpoint (handlers.py)
  |
  v
Celery task dispatched (celery_tasks.py)
  |
  v
BaseAutomation subclass (e.g., accounting.py)
  |-- Reads data from Odoo (XML-RPC)
  |-- Sends to Claude (tool-use, single turn)
  |-- Claude returns decision + confidence
  |
  v
Confidence gating:
  >= 0.95: auto-execute via XML-RPC
  0.85-0.95: queue for approval
  < 0.85: log only
  |
  v
AuditLog entry
```

**Limitations:**
- Single-turn Claude calls (no multi-step reasoning)
- No state persistence across steps
- No branching logic (if condition A, do X; if condition B, do Y)
- No cross-module coordination within a single workflow
- No retry/recovery if a step fails mid-workflow
- Cannot wait for external events (approval, vendor response, payment confirmation)

---

## Target Architecture (Phase 2)

### Core Concept: Agent Orchestrator

A new layer between the Celery worker and the automation logic that manages multi-step, stateful workflows.

```
Odoo Webhook Event
  |
  v
FastAPI endpoint
  |
  v
Celery task
  |
  v
Agent Orchestrator (NEW)
  |-- Selects appropriate agent for this event type
  |-- Creates agent instance with initial state
  |-- Manages execution graph (steps, branches, waits)
  |
  v
Agent (graph-based execution)
  |-- Step 1: Gather data (Odoo read)
  |-- Step 2: Analyze (Claude call)
  |-- Step 3: Branch based on analysis result
  |   |-- Branch A: Auto-execute (high confidence)
  |   |-- Branch B: Request approval (medium confidence)
  |   |-- Branch C: Escalate (low confidence or complex case)
  |-- Step 4: Execute action(s) in Odoo
  |-- Step 5: Notify stakeholders (WhatsApp/Slack/email)
  |-- Step 6: Schedule follow-up if needed
  |
  v
Agent State persisted (Redis + PostgreSQL)
  |-- Can resume after approval/external event
  |-- Can be inspected for debugging
  |-- Full audit trail of every step
```

### Framework Decision: LangGraph

After evaluating the three leading frameworks, LangGraph is the recommended choice:

| Criteria | LangGraph | AutoGen | CrewAI |
|----------|-----------|---------|--------|
| **Architecture** | Graph-based state machine | Event-driven async | Role-based team |
| **Control flow** | Explicit, deterministic edges | Emergent from agent interaction | Predefined team roles |
| **State management** | Built-in checkpoints | Custom implementation | Limited |
| **Debugging** | Execution replay, step inspection | Difficult (async events) | Moderate |
| **Human-in-the-loop** | Native support (interrupt nodes) | Supported but complex | Supported |
| **Fault tolerance** | Checkpoint-based recovery | Custom | Limited |
| **EU AI Act compliance** | Audit trail + timestamped decisions | Requires custom logging | Requires custom logging |
| **Production readiness** | Highest (used by 67% of enterprises) | Growing | Early stage |
| **Python ecosystem** | Excellent (LangChain ecosystem) | Good | Good |
| **Overhead** | Low (graph execution only) | Higher (async event loop) | Higher (role delegation) |

**Why LangGraph wins for our use case:**
1. Explicit control flow matches ERP requirements (compliance, auditability)
2. Built-in checkpoint/recovery matches our confidence gating pattern
3. Human-in-the-loop interrupts map directly to our approval queue
4. Deterministic execution makes debugging straightforward
5. Can be used without LLM for purely logic-driven steps (reduces cost)

### Agent Design Pattern

Each agent is defined as a graph with:

```python
# Conceptual structure -- not final implementation code

class ProcureToPayAgent:
    """
    Handles the full procure-to-pay workflow:
    invoice received -> match to PO -> validate -> create bill -> approve -> pay
    """
    
    # State schema: what data flows through the agent
    state = {
        "document_id": str,          # IDP processing result
        "extracted_data": dict,      # Fields from document
        "matched_po": dict | None,   # Matched purchase order
        "discrepancies": list,       # Price/qty differences
        "confidence": float,         # Overall confidence
        "bill_id": str | None,       # Created bill in Odoo
        "approval_status": str,      # pending/approved/rejected
        "notifications_sent": list,  # Tracking sent messages
    }
    
    # Graph nodes (processing steps)
    nodes = [
        "extract_document",     # IDP extraction
        "match_purchase_order", # Find matching PO
        "validate_amounts",     # Check prices and quantities
        "check_goods_receipt",  # Verify goods were received
        "create_draft_bill",    # Create bill in Odoo
        "route_for_approval",   # Confidence-based routing
        "wait_for_approval",    # Human-in-the-loop interrupt
        "post_bill",            # Finalize bill
        "notify_stakeholders",  # Send notifications
        "update_vendor_score",  # Update vendor performance
    ]
    
    # Graph edges (routing logic)
    edges = {
        "extract_document": "match_purchase_order",
        "match_purchase_order": {
            "found": "validate_amounts",
            "not_found": "notify_stakeholders",  # Alert: no PO match
        },
        "validate_amounts": {
            "match": "check_goods_receipt",
            "discrepancy": "notify_stakeholders",  # Alert: price/qty mismatch
        },
        "check_goods_receipt": {
            "received": "create_draft_bill",
            "not_received": "wait_for_receipt",
        },
        "create_draft_bill": "route_for_approval",
        "route_for_approval": {
            "auto_approve": "post_bill",       # confidence >= 0.95
            "needs_approval": "wait_for_approval",  # 0.85-0.95
            "escalate": "notify_stakeholders",     # < 0.85
        },
        "wait_for_approval": {
            "approved": "post_bill",
            "rejected": "notify_stakeholders",
        },
        "post_bill": "update_vendor_score",
        "update_vendor_score": "notify_stakeholders",
    }
```

### Planned Agents (Phase 2)

| Agent | Trigger | Steps | Cross-Module? |
|-------|---------|-------|---------------|
| **ProcureToPayAgent** | Invoice upload / vendor bill webhook | Extract -> Match PO -> Validate -> Create bill -> Approve -> Pay -> Score vendor | Purchase + Accounting + Inventory |
| **OrderToDeliveryAgent** | Sales order confirmed | Check stock -> Reserve -> Create picking -> Track -> Confirm delivery -> Create invoice | Sales + Inventory + Accounting |
| **LeadToOpportunityAgent** | New lead created | Score -> Deduplicate -> Assign -> Draft follow-up -> Monitor engagement -> Convert or archive | CRM + Sales |
| **ReorderAgent** | Stock below reorder point | Forecast demand -> Evaluate suppliers -> Select vendor -> Create PO -> Get approval -> Track delivery | Inventory + Purchase + Supply Chain |
| **CollectionAgent** | Invoice overdue | Assess customer -> Select strategy -> Draft message -> Send via WhatsApp -> Track response -> Escalate if needed -> Update credit score | Accounting + CRM + Communication |
| **MonthEndCloseAgent** | Scheduled (monthly) | Scan unreconciled -> Find stale drafts -> Check unbilled deliveries -> Validate taxes -> Generate report -> Guide controller | Accounting + Inventory + Sales |
| **EmployeeExpenseAgent** | Expense submitted | Validate policy -> Check duplicates -> Categorize -> Route approval -> Process payment | HR + Accounting |

### State Persistence

Agent state must survive service restarts, approval wait times, and external event delays:

| Storage | Purpose | Data |
|---------|---------|------|
| **Redis** | Active agent state (fast access) | Current step, in-flight data, timeout tracking |
| **PostgreSQL** | Completed agent runs (audit) | Full execution history, decisions, timestamps, outcomes |
| **PostgreSQL** | Suspended agents (waiting for approval/event) | Frozen state, resume conditions, expiry |

**New DB Tables:**

| Table | Purpose |
|-------|---------|
| `agent_run` | One row per agent execution (ID, type, trigger, status, started_at, completed_at) |
| `agent_step` | One row per step executed (agent_run_id, step_name, input, output, duration, status) |
| `agent_decision` | Claude analysis results (step_id, prompt, response, confidence, tools_used) |
| `agent_suspension` | Suspended agents waiting for external events (agent_run_id, resume_condition, timeout) |

### Coexistence with Current System

The agentic architecture does not replace the current system -- it extends it:

- **Simple automations** (single-step: score a lead, categorize a transaction) continue using `BaseAutomation` subclasses via Celery tasks. No change needed.
- **Complex workflows** (multi-step: procure-to-pay, order-to-cash) use the new `BaseAgent` class with graph-based execution.
- Both share the same Celery worker pool, Claude client, Odoo client, and audit logging.
- Migration path: existing automations can be progressively upgraded to agents when multi-step behavior is needed.

```
BaseAutomation (existing)     BaseAgent (new, Phase 2)
  |-- Single Celery task        |-- Agent orchestrator
  |-- One Claude call           |-- Multiple Claude calls
  |-- One action                |-- Graph of steps
  |-- Stateless                 |-- Stateful (persistent)
  |-- Synchronous               |-- Can suspend/resume
```

---

## Guardrails and Safety

Given Gartner's prediction that 40% of agent projects fail due to inadequate controls, safety is built into the architecture:

### Cost Controls
- **Token budget per agent run:** maximum Claude API spend per workflow execution
- **Step limit:** maximum number of steps an agent can take before requiring human review
- **Loop detection:** if an agent revisits the same step 3 times, pause and alert

### Audit and Compliance
- **Every step logged:** input, output, duration, Claude usage, confidence score
- **Every decision traceable:** which data was read, what Claude was asked, what it decided
- **Execution replay:** any agent run can be replayed step-by-step for debugging
- **EU AI Act Article 14:** human oversight built-in via approval interrupts and step inspection

### Failure Handling
- **Step retry:** failed steps retry with exponential backoff (max 3 retries)
- **Graceful degradation:** if Claude API is down, agent suspends and resumes when available
- **Timeout escalation:** if an agent waits for approval > 48 hours, escalate to next approver
- **Dead letter queue:** permanently failed agent runs flagged for manual investigation

### Permission Boundaries
- **Agents inherit user permissions:** an agent triggered by User X can only access what User X can access
- **Write operations require explicit tool calls:** agents declare their intended write actions, which go through confidence gating
- **Destructive actions always require human approval:** delete, cancel, reverse operations never auto-execute regardless of confidence

---

## Implementation Plan

**Prerequisites (Phase 1):**
- No agent framework needed yet
- Current single-action automations handle Phase 1 deliverables
- Redis state storage patterns established (for cash flow forecast caching, reconciliation session memory)

**Phase 2 Deliverables:**
1. Install and integrate LangGraph (or chosen framework)
2. Build `BaseAgent` class alongside existing `BaseAutomation`
3. Implement agent state persistence (Redis + PostgreSQL)
4. Build first agent: `ProcureToPayAgent` (builds on Phase 1 IDP work)
5. Build second agent: `MonthEndCloseAgent` (upgrades Phase 1 closing assistant to continuous close)
7. Dashboard updates: agent run visualization, step-by-step execution view
8. Monitoring: agent run duration, Claude token usage, failure rates

**Phase 3+:**
- Remaining agents (OrderToDelivery, LeadToOpportunity, Reorder, EmployeeExpense)
- Low-code builder creates custom agents (visual graph builder)
- Agent-to-agent communication (CollectionAgent triggers CreditManagement)

---

## Technology Stack Addition

| Package | Purpose | Version |
|---------|---------|---------|
| `langgraph` | Graph-based agent orchestration | Latest stable |
| `langgraph-checkpoint-postgres` | PostgreSQL checkpoint persistence | Latest stable |
| `langgraph-checkpoint-redis` | Redis checkpoint for active agents | Latest stable |

LangGraph can be used without LangChain -- it operates as a standalone graph execution engine, which keeps our dependency surface small.

---

## Research Sources

- LangGraph Documentation: Graph-based state machine framework for agentic AI
- BIX Tech: "AI Agents Orchestration with LangGraph: Architectures, Patterns, and Advanced Implementation"
- Towards AI: "Building an Agentic Workflow in LangGraph (No LLM Required)"
- Medium (Ali Topuz): "Advanced LangGraph Orchestration: Enterprise-Ready AI Workflow Management"
- Likhon's Gen AI Blog: "Building Production Agentic AI Systems in 2026: LangGraph vs AutoGen vs CrewAI"
- Likhon's Gen AI Blog: "Multi-Agent Orchestration: LangGraph vs CrewAI vs AutoGen for Enterprise Workflows"
- SAP: Joule Agents (1,300+ skills, Knowledge Graph, Business Data Cloud)
- Microsoft: Dynamics 365 AI agents (Account Reconciliation Agent)
- McKinsey: "Bridging the Great AI Agent and ERP Divide" (27% higher ROI with bold AI adoption; 95% AI pilots fail to scale)
- Gartner: Predicts 40% of agent projects canceled by 2027 due to cost overruns and inadequate controls
