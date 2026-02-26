# Communication & Portals -- Pillar 4 Detail Document

**Research date:** February 2026
**Sources:** WhatsApp Business API docs, Meta for Developers, Frappe WhatsApp, SAP B2B Portal, Acumatica Portal, CommerceBuild, Manhattan, Chakra Chat, n8n integrations
**Referenced by:** [MASTER_PLAN.md](MASTER_PLAN.md) -- Pillar 4

---

## Why This Pillar Exists

Odoo communicates with the outside world almost exclusively through email. This is a problem:

- Email has a 20% open rate. WhatsApp has 98%.
- Approval requests sit in email inboxes for days. A WhatsApp message gets read in minutes.
- Payment reminder emails are ignored. WhatsApp payment reminders get 5x higher response rates.
- Customers call or email to ask "where's my order?" because there's no self-service portal.
- Vendors email delivery updates that someone must manually enter into Odoo.
- Odoo's built-in Discuss module is underpowered -- teams use Slack/Teams anyway.

This pillar adds three capabilities: multi-channel messaging, customer self-service portal, and vendor self-service portal.

---

## 4A. Messaging Channel Integration

### The Problem

Every notification, approval request, collection message, and status update in Odoo goes through email. Email is slow, noisy, and increasingly ignored for operational messages. Meanwhile:

- WhatsApp Business API supports interactive messages, payment reminders, and order management
- Slack/Teams are where internal teams already collaborate
- SMS remains the most reliable channel for critical alerts
- ERPNext already has a native WhatsApp integration (Frappe WhatsApp)

### What We Build

A multi-channel messaging layer that routes notifications through the right channel based on urgency, recipient preference, and message type.

**Channel Routing Logic:**

| Message Type | Primary Channel | Fallback | Why |
|-------------|----------------|----------|-----|
| Payment reminders / collection | WhatsApp | Email | 98% open rate, interactive payment links |
| Approval requests (internal) | Slack / Teams | Email | Where teams already work, one-click approve |
| Order confirmations (customer) | WhatsApp | Email | Instant delivery, read receipts |
| Delivery updates | WhatsApp + SMS | Email | Time-sensitive, mobile-first |
| Daily AI digest (internal) | Slack / Email | In-app | Morning briefing for each role |
| Critical alerts (stock-out, fraud) | SMS + Slack | WhatsApp + Email | Must not be missed |
| Follow-up reminders (sales) | WhatsApp | Email | Personal touch, high engagement |
| Invoice delivery | WhatsApp + Email | Email only | Document delivery with payment link |

### WhatsApp Business API Integration

**Capabilities we implement:**

| Feature | Description |
|---------|------------|
| Template messages | Pre-approved message templates for invoices, reminders, confirmations |
| Interactive messages | Buttons for "Pay Now", "Approve", "Reject", "View Details" |
| Order status messages | Real-time order/delivery status updates |
| Payment reminders | Payment links embedded in WhatsApp messages |
| Two-way messaging | Customer replies routed back to Odoo chatter/helpdesk |
| Media messages | Send PDF invoices, delivery photos, product catalogs |
| Read receipts | Track message delivery and read status for collection follow-up |

**Implementation:**
- WhatsApp Business API via Meta Cloud API (hosted by Meta, no server setup)
- Message templates submitted for Meta approval (required for outbound business messages)
- Webhook receiver for inbound customer replies
- Phone number verification and business profile setup

**Template Examples:**

```
[Invoice Reminder]
Hi {{customer_name}}, invoice {{invoice_number}} for {{amount}} {{currency}}
is due on {{due_date}}. 

[Pay Now] [View Invoice] [Contact Us]
```

```
[Approval Request]
{{approver_name}}, a {{document_type}} from {{requester}} needs your approval:
{{description}} -- Amount: {{amount}} {{currency}}

[Approve] [Reject] [View Details]
```

### Slack / Microsoft Teams Integration

**Capabilities:**
- Approval notifications with inline Approve/Reject buttons
- AI alert channels (anomaly detection, risk alerts, daily digest)
- Slash commands: `/odoo search customer Acme`, `/odoo pipeline summary`
- Thread-based discussions linked to Odoo records
- Interactive messages for quick actions without leaving Slack/Teams

**Implementation:**
- Slack: `slack-sdk` Python package + Slack app with bot token
- Teams: Microsoft Graph API + Teams bot framework
- Both: webhook-based event delivery from AI service

### SMS Integration

For critical alerts only (cost-conscious):
- Twilio or equivalent SMS gateway
- Used for: stock-out alerts, fraud detection, system failures, approval escalation (after 24h no response on other channels)

### Architecture

```
Odoo Event -> AI Service -> Channel Router -> {
  WhatsApp Business API (external customers/vendors)
  Slack API (internal team - Slack orgs)
  Teams API (internal team - Teams orgs)  
  Twilio SMS (critical alerts)
  SMTP Email (fallback, document delivery)
}

Inbound replies:
  WhatsApp webhook -> AI Service -> route to Odoo chatter/helpdesk
  Slack interaction -> AI Service -> process approval/command
```

**New DB tables:** `message_channel_preference` (per user/contact), `message_log` (delivery tracking), `message_template` (templates per type)

---

## 4B. Customer Self-Service Portal

### The Problem

When a customer wants to:
- Check order status -- they call or email, someone looks it up manually
- Pay an invoice -- they receive a PDF, transfer money, someone reconciles manually
- Reorder products -- they email a list, someone creates a quotation manually
- Submit an RFQ -- they email specs, someone enters it into Odoo manually
- Check stock availability -- they call, someone checks and calls back
- Submit a support ticket -- they email, someone creates a ticket manually

Every interaction requires a human intermediary. This doesn't scale.

### What We Build

A branded web portal where B2B customers can self-serve 24/7, with every action syncing directly to Odoo.

**Portal Features:**

| Feature | Description | Odoo Integration |
|---------|------------|-----------------|
| Order dashboard | All orders with real-time status (quoted, confirmed, shipped, delivered, invoiced) | `sale.order`, `stock.picking` |
| Invoice center | View all invoices, download PDFs, see payment status | `account.move` |
| Online payment | Pay invoices via credit card, bank transfer, or local payment methods | Payment gateway + `account.payment` |
| Reorder | One-click reorder from order history with pre-filled cart | `sale.order` creation |
| RFQ submission | Submit requests for quotation with product specs and quantities | `sale.order` (draft) or custom model |
| Product catalog | Browse available products with account-specific pricing | `product.product`, `product.pricelist` |
| Stock visibility | Real-time inventory availability by product | `stock.quant` |
| Support tickets | Submit and track support tickets | `helpdesk.ticket` |
| Document center | Access contracts, certificates, technical datasheets | `ir.attachment` |
| Account management | Update contact info, manage users, view credit status | `res.partner` |

**Account-Specific Features:**
- Pricing based on customer's pricelist (not public prices)
- Credit limit visibility ("You have $15,000 of $25,000 credit available")
- Order history with export to CSV/Excel
- Saved carts and favorites for repeat purchasing

### Architecture Decision

Two viable approaches:

| Approach | Pros | Cons |
|----------|------|------|
| **Extend Odoo's built-in portal** | Faster to ship, native Odoo integration, uses existing auth | Limited UX customization, tied to Odoo's frontend stack |
| **New Next.js portal app** | Modern UX, full control, mobile-optimized, can serve as PWA | Separate auth layer, API integration work, more code to maintain |
| **Hybrid** | Odoo portal for basic features, custom app for advanced UX | Two systems to maintain |

**Recommended:** Start with Odoo's built-in portal for Phase 3 MVP (order tracking, invoices, support tickets), then evaluate Next.js rebuild for Phase 4 if UX requirements exceed what Odoo portal can deliver.

### Expected Impact

| Metric | Before | After |
|--------|--------|-------|
| "Where's my order?" calls/emails | 10-20/day | Near zero (self-service) |
| Invoice payment time | Net 30-45 average | Net 15-20 (online payment) |
| Reorder process | 15 min email chain | 2 min self-service |
| Support ticket creation | Email (unstructured) | Form (structured, auto-categorized by AI) |

---

## 4C. Vendor Self-Service Portal

### The Problem

Vendor communication is a manual bottleneck:
- POs are emailed as PDFs, vendors confirm via reply email, someone updates Odoo
- Delivery status: "Where's my shipment?" requires calling the vendor
- Invoice submission: vendors email PDFs, AP staff manually enters them
- Performance feedback: vendors never know how they're performing
- Onboarding: new vendor setup takes days of back-and-forth for documents and certifications

### What We Build

A portal where vendors manage their relationship with our business directly, reducing communication overhead by 20-35%.

**Portal Features:**

| Feature | Description | Odoo Integration |
|---------|------------|-----------------|
| PO management | View, acknowledge, and confirm purchase orders | `purchase.order` |
| Delivery updates | Update shipment status, expected delivery date, tracking numbers | `stock.picking` |
| Invoice submission | Upload invoices digitally (processed by IDP) | `account.move` creation via IDP |
| Performance scorecard | View delivery compliance, quality metrics, price competitiveness | Custom analytics |
| Document management | Upload/maintain certifications, insurance, compliance docs | `ir.attachment` |
| RFQ responses | Respond to requests for quotation with pricing and availability | `purchase.order` (draft) |
| Payment status | View payment history and upcoming payment dates | `account.payment` |
| Communication | Threaded messaging linked to specific POs/deliveries | Odoo chatter |

**Vendor Performance Scorecard (visible to vendor):**

| Metric | Calculation | Target |
|--------|------------|--------|
| On-time delivery rate | Deliveries on/before promised date / total deliveries | >= 95% |
| Quality acceptance rate | Accepted quantities / delivered quantities | >= 98% |
| Price competitiveness | Vendor price vs. average market price | Within 10% |
| Response time | Average time to acknowledge POs | < 24 hours |
| Invoice accuracy | Invoices matching PO on first submission | >= 90% |

### IDP Integration

When a vendor uploads an invoice through the portal:
1. IDP extracts fields (vendor, amount, line items, PO reference)
2. Auto-matches to corresponding PO
3. Validates quantities and prices against PO
4. If match confidence >= 0.95: auto-creates draft bill in Odoo
5. If discrepancy detected: flags for AP review with specific differences highlighted
6. Vendor sees real-time status: "Processing", "Matched", "Awaiting Review", "Approved"

### Expected Impact

| Metric | Before | After |
|--------|--------|-------|
| PO acknowledgment time | 1-3 days (email) | < 4 hours (portal) |
| Delivery status visibility | Call/email vendor | Real-time portal updates |
| Invoice processing time | 8-10 min/invoice (manual entry) | 20-30 sec (IDP + auto-match) |
| Vendor onboarding time | 1-2 weeks | 1-2 days (digital doc submission) |
| Supplier lead time variability | High (no shared KPIs) | 20-35% reduction (shared targets) |

---

## Implementation Priority

| Deliverable | Phase | Dependencies |
|------------|-------|-------------|
| WhatsApp notification integration | Phase 1 | WhatsApp Business API account, Meta template approval |
| Slack integration | Phase 1 | Slack app creation, bot token |
| Customer portal (MVP on Odoo portal) | Phase 3 | Payment gateway integration |
| Vendor portal (MVP on Odoo portal) | Phase 3 | IDP (Pillar 5C) for invoice upload |
| SMS critical alerts | Phase 3 | Twilio or equivalent account |
| Portal UX upgrade (Next.js) | Phase 4 | If Odoo portal UX is insufficient |

---

## Research Sources

- WhatsApp Business API: Meta Cloud API documentation, order_details/order_status messages
- Frappe WhatsApp: Native ERPNext integration (two-way messaging, WhatsApp Flows, webhook support)
- Chakra Chat: ERP-WhatsApp integration for automated invoices and payment reminders
- SAP B2B Self-Service Portal: Order, invoice, payment, claims management features
- Acumatica Customer Self-Service Portal: ERP-integrated portal architecture
- CommerceBuild: B2B Customer Portal for real-time self-service
- Manhattan: B2B order management architecture for ERP augmentation
- n8n: Visual workflow builder for ERPNext-WhatsApp integration
