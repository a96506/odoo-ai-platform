# Platform Capabilities -- Pillar 5 Detail Document

**Research date:** February 2026
**Sources:** Novacura Flow, Joget DX, Corteza, ProcessMaker, MCP specification (Anthropic), NetSuite MCP Connector, IEEE/arXiv IDP research, V7 Labs, Klippa IDP Survey
**Referenced by:** [MASTER_PLAN.md](MASTER_PLAN.md) -- Pillar 5

---

## Why This Pillar Exists

Our platform currently has a fixed set of AI automations. Users cannot create their own rules, cannot connect external systems, and cannot process documents beyond what Odoo's basic OCR offers. Meanwhile:

- NetSuite shipped an MCP AI Connector Service in 2026.1 -- any AI tool can query NetSuite data
- Low-code platforms like Novacura and Joget let business users build ERP applications without code
- Vision-LLM document processing achieves 99%+ accuracy vs. Odoo OCR at 60-80%
- 85% of enterprise AI failures stem from AI lacking business context, not model failures
- 28% of Fortune 500 companies implemented MCP servers as of Q1 2025

This pillar adds five capabilities: low-code automation builder, integration hub, intelligent document processing, MCP protocol server, and digital twins.

---

## 5A. Low-Code/No-Code Automation Builder

### The Problem

Every automation in our platform is hardcoded in Python. If a business wants:
- "When a quotation exceeds $10K, notify the CFO on Slack" -- they need a developer
- "When a product drops below 50 units, create a PO with Vendor X" -- they need a developer
- "When a support ticket is marked urgent, assign to Agent Y" -- they need a developer

Odoo has "Automated Actions" in Settings, but they require technical knowledge (Python code, domain filters) and can only trigger basic actions. There's no visual builder.

### What We Build

A visual rule builder in the dashboard where business users create custom automations using drag-and-drop:

**Components:**

| Component | Examples |
|-----------|---------|
| **Triggers** | Record created, record updated, field changed, date reached, threshold crossed, scheduled time |
| **Conditions** | Field equals/contains/greater than, AND/OR logic, current user role, time of day, day of week |
| **Actions** | Send notification (Slack/email), create record, update field, assign user, call AI analysis, approve/reject, create task, add note |
| **Templates** | Pre-built common automations users can enable with one click |

**User Interface:**

```
WHEN [trigger dropdown]
  a [model: Sales Order] is [event: created]
AND [condition builder]
  [field: Amount Total] [operator: is greater than] [value: 10000]
  AND [field: Customer Credit] [operator: is less than] [value: 5000]
THEN [action list]
  1. [Send Slack] to [CFO] with message [template: High Value Order Alert]
  2. [Create Task] assigned to [Credit Manager] with title "Review credit for {customer}"
  3. [Update Field] set [Sales Order.Tag] to "High Value - Credit Review"
```

**Template Library (pre-built, one-click enable):**

| Template | Trigger | Action |
|----------|---------|--------|
| Large order alert | SO > threshold | Notify manager |
| Low stock reorder | Product qty < reorder point | Create PO draft |
| Overdue invoice escalation | Invoice past due > 30 days | Notify account manager + email customer |
| New lead notification | Lead created from website | Slack to sales rep + AI lead scoring |
| Expense policy check | Expense > limit | Route to department head instead of direct manager |
| Delivery delay alert | Picking past scheduled date | Notify warehouse manager + customer |

**Technical Implementation:**

- Rules stored as JSON in AI database (`automation_rule_v2` table)
- Rule engine evaluates conditions on webhook events (already received from Odoo)
- Actions executed through existing infrastructure (Slack API, SMTP email, Odoo XML-RPC)
- React-based visual builder using `react-flow` or similar for drag-and-drop
- Test mode: simulates rule execution against recent events without taking action

### How It Differs from Odoo Automated Actions

| Feature | Odoo Automated Actions | Our Low-Code Builder |
|---------|----------------------|---------------------|
| Interface | Form with Python code | Visual drag-and-drop |
| Conditions | Odoo domain syntax | Human-readable condition builder |
| Actions | Limited (set field, create activity, send email) | Full action library (Slack, email, AI analysis, multi-step) |
| AI integration | None | Can invoke AI analysis as an action |
| Cross-module | Per-model only | Can chain across models |
| Testing | No test mode | Simulate against recent events |
| Templates | None | Pre-built library |

---

## 5B. Integration Hub / Pre-Built Connectors

### The Problem

Our AI platform only talks to Odoo. In reality, businesses need data flowing between Odoo and:
- Banks (statement imports, balance checks, payment confirmations)
- Shipping carriers (tracking, label generation, delivery confirmation)
- Payment gateways (online payments from portals and invoices)
- Government portals (VAT filing, e-invoicing submission, customs)
- Communication platforms (Slack, Teams -- covered in Pillar 4)

Currently, all of this is manual: download bank statement CSV, import into Odoo; check tracking on carrier website, update Odoo manually; file taxes in government portal, no connection to Odoo.

### What We Build

A connector framework with pre-built integrations for the most common external systems.

**Connector Architecture:**

```
AI Service
  -> Integration Hub (new module)
    -> Connector Registry (pluggable connectors)
      -> Banking Connector (Open Banking / file import)
      -> Shipping Connector (DHL, FedEx, Aramex APIs)
      -> Payment Connector (Stripe, PayPal, Tap)
      -> Government Connector (VAT portals, e-invoicing)
    -> Sync Engine (scheduled + event-driven)
    -> Credential Vault (encrypted storage for API keys)
    -> Sync Log (audit trail of all external data exchanges)
```

**Phase 3 Connectors:**

| Connector | Functions | Data Flow |
|-----------|----------|-----------|
| **Open Banking** | Fetch bank statements, check balances, verify payments | Bank -> Odoo (auto-import statements) |
| **Bank File Import** | Parse MT940, CAMT.053, OFX, CSV formats | File -> Odoo (structured bank lines) |
| **Stripe** | Process payments, create payment intents, handle webhooks | Portal -> Stripe -> Odoo (payment records) |
| **PayPal** | Process payments, handle IPN notifications | Portal -> PayPal -> Odoo |
| **Tap (GCC)** | Process payments for Middle East (KNET, Benefit, mada) | Portal -> Tap -> Odoo |
| **DHL** | Create shipments, generate labels, track deliveries | Odoo -> DHL (ship), DHL -> Odoo (tracking) |
| **Aramex** | Create shipments, track deliveries (GCC primary carrier) | Odoo -> Aramex (ship), Aramex -> Odoo (tracking) |
| **FedEx / UPS** | Create shipments, generate labels, track deliveries | Odoo -> Carrier (ship), Carrier -> Odoo (tracking) |

**Sync Modes:**
- **Scheduled:** Pull data at intervals (bank statements every 4 hours, tracking every 2 hours)
- **Event-driven:** Push data on Odoo events (create shipment when DO validated, send payment notification on invoice creation)
- **On-demand:** User triggers sync ("Import latest bank statement now")

---

## 5C. Intelligent Document Processing (IDP)

### The Problem

Odoo's built-in OCR (IAP) achieves 60-80% accuracy on invoices, requiring manual verification of most fields. It cannot handle:
- Delivery notes, contracts, customs declarations, receipts
- Handwritten annotations on documents
- Multi-page documents with complex layouts
- Arabic text (critical for GCC market)
- Documents from vendors with non-standard formats

### What We Build

A vision-LLM-powered document processing pipeline that achieves 99%+ field extraction accuracy and processes documents in 20-30 seconds.

**Multi-Stage Pipeline:**

```
1. Document Upload (portal, email, API, or manual)
   |
2. Image Preprocessing
   - Orientation detection and correction
   - Size normalization
   - Quality enhancement for degraded scans
   |
3. Document Classification
   - Invoice, credit note, delivery note, receipt, contract, customs form
   - ML classifier (logistic regression or lightweight CNN)
   |
4. Field Extraction (Vision-Language Model)
   - Send document image + extraction prompt to Claude Vision API
   - Extract structured fields: vendor, date, amounts, line items, references
   - Multi-language: Arabic + English in same document
   |
5. Validation & Matching
   - Match extracted vendor to Odoo partners (fuzzy matching)
   - Match PO reference to existing purchase orders
   - Validate amounts, quantities, tax calculations
   - Confidence scoring per field
   |
6. Output
   - Confidence >= 0.95: Auto-create Odoo record (draft bill, receipt, etc.)
   - Confidence 0.85-0.95: Create record, flag for human review
   - Confidence < 0.85: Queue for manual entry with pre-filled suggestions
   |
7. Learning Loop
   - Track human corrections
   - Use corrections to improve extraction prompts and matching rules
```

**Supported Document Types:**

| Document | Extracted Fields | Odoo Record Created |
|----------|-----------------|-------------------|
| Vendor invoice | Vendor, date, amounts, line items, PO ref, tax | `account.move` (bill) |
| Credit note | Vendor, date, amounts, original invoice ref | `account.move` (credit note) |
| Delivery note | Vendor, products, quantities, lot/serial numbers | `stock.picking` validation data |
| Receipt | Vendor, date, amount, category | `hr.expense` or `account.move` |
| Contract | Parties, dates, terms, renewal date | Custom model or `ir.attachment` with metadata |
| Customs declaration | HS codes, country of origin, declared values | Procurement/logistics metadata |

**Performance Targets:**

| Metric | Odoo OCR (Current) | Our IDP (Target) |
|--------|-------------------|-----------------|
| Field extraction accuracy | 60-80% | 95-99% |
| Processing time per document | Manual verification required | 20-30 seconds, auto |
| Document types supported | Invoices only | 6+ types |
| Language support | European languages | Arabic + English + European |
| Learning from corrections | No | Yes (prompt tuning) |

**Implementation:**
- Claude Vision API (Anthropic multi-modal) for extraction
- `pdfplumber` or `PyMuPDF` for PDF text/table extraction
- `rapidfuzz` for vendor name fuzzy matching
- New Celery task: `process_document` with priority queue
- New API endpoints: `POST /api/documents/process`, `GET /api/documents/{id}/status`
- New DB tables: `document_processing_job`, `document_extraction_result`, `extraction_correction_log`

---

## 5D. MCP Protocol for Odoo

### The Problem

NetSuite shipped an MCP AI Connector Service in August 2025, allowing any MCP-compatible AI tool (Claude Desktop, GitHub Copilot, ChatGPT) to query NetSuite data securely. Our Odoo platform has no equivalent.

72% of CFOs say inability to integrate ERP with external AI tools is their primary bottleneck. 85% of enterprise AI failures stem from AI lacking business context.

### What We Build

A standards-compliant Model Context Protocol server that exposes Odoo data to any MCP-compatible AI client.

**MCP Server Capabilities:**

| MCP Primitive | Odoo Implementation |
|--------------|-------------------|
| **Resources** | Odoo models exposed as browsable resources (contacts, invoices, orders, products, etc.) |
| **Tools** | Read records, search records, create records, update records, execute actions |
| **Prompts** | Pre-built query templates ("Show overdue invoices", "Summarize customer", "List low stock") |

**Access Control:**
- Role-based: MCP queries respect Odoo's access rights (user making the query only sees what their Odoo role allows)
- Read vs. Write: read operations allowed freely, write operations require approval gating (same confidence threshold system)
- Audit trail: every MCP query logged with user, query, results, timestamp

**Example MCP Interactions:**

```
User in Claude Desktop: "What are the top 10 overdue invoices?"
  -> MCP Client sends tool call to Odoo MCP Server
  -> Server queries account.move with filters (state=posted, payment_state=not_paid, date < today)
  -> Returns structured results with customer names, amounts, days overdue
  -> Claude formats and presents to user

User in Claude Desktop: "Create a quotation for Acme Corp with 100 units of Widget Pro"
  -> MCP Client sends tool call
  -> Server checks user permissions (can this user create sale.order?)
  -> Server creates draft quotation
  -> Returns confirmation with SO number and link
```

**Implementation:**
- Python `mcp` package (official MCP SDK)
- Runs as a separate service or embedded in AI service
- Connects to Odoo via XML-RPC (same client we already have)
- Configuration: which models to expose, field-level access control, rate limits

---

## 5E. Digital Twins & Scenario Simulation

### The Problem

Business decisions are made on gut feel because there's no way to simulate outcomes:
- "Should we open a second warehouse?" -- no way to model the impact
- "What if demand increases 20%?" -- manual spreadsheet scenario
- "What if we raise prices 5%?" -- guess at volume impact
- "What if our main supplier fails?" -- panic when it actually happens

### What We Build

A simulation engine that creates virtual models of business operations using historical Odoo data, then runs what-if scenarios.

**Simulation Domains:**

| Domain | Simulates | Example Questions |
|--------|----------|-------------------|
| **Inventory** | Stock levels, reorder cycles, warehouse utilization | "What if demand increases 20%?", "Should we add a warehouse?" |
| **Finance** | Cash flow, AR/AP, working capital | "What if our largest customer goes bankrupt?", "What if we extend payment terms?" |
| **Supply Chain** | Supplier disruption, lead time changes, cost fluctuations | "What if Supplier X can't deliver?", "What if shipping costs increase 15%?" |
| **Sales** | Pipeline conversion, pricing impact, seasonal patterns | "What if we offer a 10% discount?", "What revenue if we add 2 sales reps?" |
| **Capacity** | Production throughput, resource utilization, bottlenecks | "Can we fulfill a 30% order increase?", "Which machine is the bottleneck?" |

**Technical Approach:**
- Monte Carlo simulation for probabilistic outcomes (random sampling from historical distributions)
- `simpy` library for discrete event simulation (warehouse operations, production lines)
- Historical Odoo data as input parameters (sales velocity, lead times, payment patterns)
- AI-generated narrative summaries of simulation results

**Implementation Priority:** Phase 4 (long-term). Requires mature data from other pillars (cash flow forecasting, supply chain risk, demand forecasting) to produce meaningful simulations.

---

## Implementation Priority

| Deliverable | Phase | Key Dependency |
|------------|-------|---------------|
| IDP document processing | Phase 1 | Claude Vision API access |
| Low-code automation builder | Phase 3 | React-flow or similar for visual builder |
| Integration hub (banking, shipping) | Phase 3 | API accounts with providers |
| MCP protocol server | Phase 3 | `mcp` Python SDK |
| Digital twins | Phase 4 | Mature historical data from other pillars |

---

## Research Sources

- Novacura Flow: Low-code platform for ERP extension (process-based app designer, BPM)
- Joget DX: Open-source no-code/low-code with AI (drag-and-drop, plugin architecture)
- Corteza: Open-source low-code platform (Salesforce-comparable, vendor lock-in free)
- ProcessMaker: Low-code BPA with AI (process automation, generative AI for screen/process creation)
- MCP Specification: Anthropic's Model Context Protocol (client-host-server architecture)
- NetSuite AI Connector Service: MCP implementation for ERP (launched August 2025)
- ERP Software Blog: "Why MCP and AI Context Define the Next Decade of ERP" (72% CFO bottleneck stat)
- arXiv 2601.01897: "Hybrid Architecture for Multi-Stage Claim Document Understanding" (VLM + ML pipeline)
- arXiv 2510.23066: "Multi-Stage Field Extraction with OCR and Compact VLMs" (8.8x accuracy at 0.7% GPU cost)
- Towards AI: "How We Built a 99% Accurate Invoice Processing System Using OCR and LLMs"
- V7 Labs: "Automated Document Processing for Enterprises 2026 Guide"
- Klippa: "IDP Survey 2025: Trends, Challenges & AI Adoption Insights"
