# Supply Chain Intelligence -- Pillar 6A Detail Document

**Research date:** February 2026
**Sources:** SR Analytics, Sphera AI Supplier Risk Survey, Exiger TPRM Report, APPIT Software, Supply Chain Connect, Digital Applied, GrowExx, Bezos.ai
**Referenced by:** [MASTER_PLAN.md](MASTER_PLAN.md) -- Pillar 6A

---

## Why This Pillar Exists

Our platform does demand forecasting (predicting what customers will buy) but has zero supply-side intelligence. This is a critical blind spot:

- 89% of enterprises cannot see tier-2/tier-3 supplier disruptions
- 74% of mid-market companies rely on manual supplier updates with 24-72 hour delays
- 68% of SMBs lack shipment tracking between origin and destination
- Only 25% of organizations maintain steady supply chain risk reporting
- A single supplier disruption can cascade into weeks of production delays and emergency procurement at 40-60% cost premiums

Meanwhile, AI can now predict supplier failures 90-180 days in advance and delivery delays 2-6 weeks ahead.

---

## What We Build

### 6A.1 Supplier Risk Scoring

A continuous, automated risk assessment for every vendor in Odoo, replacing periodic manual reviews.

**Risk Score Components:**

| Factor | Weight | Data Source | Update Frequency |
|--------|--------|------------|-----------------|
| **Delivery performance** | 30% | Odoo `stock.picking` (on-time vs. late deliveries) | Real-time (every delivery) |
| **Quality acceptance rate** | 20% | Odoo `stock.picking` (accepted vs. returned quantities) | Real-time |
| **Price stability** | 10% | Odoo `purchase.order` (price changes over time) | Monthly |
| **Financial health signals** | 15% | External APIs (credit ratings, news, filings) | Weekly |
| **Geographic risk** | 10% | Static + news monitoring (conflict zones, natural disasters, sanctions) | Daily |
| **Dependency concentration** | 10% | Odoo `purchase.order` (% of total spend with this vendor) | Monthly |
| **Communication responsiveness** | 5% | PO acknowledgment times, delivery update frequency | Real-time |

**Risk Score Output:**

| Score Range | Classification | Action |
|------------|---------------|--------|
| 80-100 | Low Risk (Green) | Standard monitoring |
| 60-79 | Watch (Yellow) | Increased monitoring frequency, review alternatives |
| 40-59 | Elevated Risk (Orange) | Activate backup supplier search, reduce dependency, alert procurement |
| 0-39 | Critical Risk (Red) | Immediate action: secure alternative supply, halt new POs pending review |

**Scoring Engine:**
- Runs as Celery beat task (daily for all vendors, real-time update on delivery events)
- Stores history for trend analysis ("Vendor X risk has increased from 72 to 58 over 3 months")
- AI generates natural language risk summaries for procurement team

### 6A.2 Disruption Prediction

ML models that forecast supply chain disruptions before they happen.

**Prediction Types:**

| Prediction | Lead Time | Method | Data Sources |
|-----------|-----------|--------|-------------|
| Supplier delivery delay | 2-6 weeks ahead | Pattern recognition on PO-to-delivery timelines | Odoo historical data + vendor risk score |
| Supplier failure risk | 90-180 days ahead | Anomaly detection on delivery degradation patterns | Odoo delivery trends + external signals |
| Stock-out probability | 30-90 days ahead | Demand forecast vs. supply pipeline analysis | Demand model + open PO delivery dates |
| Price increase likelihood | 30-60 days ahead | Historical price patterns + market signals | Odoo price history + commodity data |

**How Disruption Prediction Works:**

```
1. Monitor vendor delivery performance over rolling windows (30/60/90 days)
2. Detect degradation patterns (increasing delays, declining acceptance rates)
3. Cross-reference with external signals (if available):
   - News mentions (factory fire, labor dispute, bankruptcy filing)
   - Geographic events (port congestion, weather, sanctions)
   - Industry trends (raw material shortages, demand spikes)
4. Calculate disruption probability and estimated impact
5. If probability > threshold:
   - Alert procurement team with specific vendor and risk
   - Auto-search for alternative suppliers from Odoo vendor database
   - Recommend pre-emptive PO to secure inventory
```

**Example Alert:**

```
SUPPLY CHAIN ALERT -- Elevated Risk

Vendor: Acme Electronics (VEN-0042)
Risk Score: 47/100 (was 71 three months ago)
Issue: Delivery delays increased from avg 2 days to avg 8 days over last 60 days
        Quality rejection rate up from 1.2% to 4.7%
Impact: 3 products depend on this vendor, 2 have no alternative supplier
        Current stock covers 18 days at current sales velocity

Recommended Actions:
1. Contact vendor for root cause assessment
2. Request quotes from alternative vendors: TechParts Ltd, GlobalSupply Co
3. Consider safety stock increase for dependent products
4. Review open POs (2 POs worth $34,500 in pipeline)
```

### 6A.3 Alternative Supplier Intelligence

When a risk is detected, the system automatically identifies and evaluates alternatives.

**Alternative Supplier Search:**
- Scan all vendors in Odoo who supply the same or similar products
- Rank by: price competitiveness, delivery reliability, available capacity, existing relationship
- Highlight gaps: "No alternative supplier exists for Product X -- single-source risk"
- Suggest action: "Vendor B can supply Product X at +8% cost with 5-day lead time"

**Single-Source Risk Detection:**
- Scan all products and identify those with only one supplier
- Calculate business impact if that supplier fails (revenue at risk, production impact)
- Prioritize finding alternatives for highest-impact single-source products

### 6A.4 Supply Chain Dashboard

A dedicated dashboard view for procurement and operations:

| Section | Shows |
|---------|-------|
| Vendor risk heat map | All vendors color-coded by risk score |
| Risk trend chart | Risk score changes over time for watched vendors |
| Active alerts | Current disruption predictions requiring action |
| Single-source risks | Products with only one supplier, ranked by revenue impact |
| Delivery performance | On-time delivery rates by vendor (trending) |
| Open PO pipeline | Expected deliveries timeline with delay probability |
| Cost impact | Emergency procurement costs vs. planned procurement |

---

## Data Architecture

**New Database Tables:**

| Table | Purpose |
|-------|---------|
| `supplier_risk_score` | Current and historical risk scores per vendor |
| `supplier_risk_factor` | Individual factor scores (delivery, quality, financial, etc.) |
| `disruption_prediction` | Active predictions with probability, impact, recommended actions |
| `supply_chain_alert` | Alerts generated and their resolution status |
| `alternative_supplier_map` | Product-to-vendor alternatives with comparative metrics |

**Odoo Models Queried:**

| Model | Fields Used |
|-------|-----------|
| `res.partner` (vendors) | Name, country, supplier rank, categories |
| `purchase.order` | Vendor, products, quantities, prices, dates, state |
| `purchase.order.line` | Product, quantity, price, date planned |
| `stock.picking` | Vendor, scheduled date, effective date, state |
| `stock.move` | Product, quantity done, quantity demanded |
| `product.supplierinfo` | Vendor-product mapping, price, min qty, delay |

**New Celery Beat Tasks:**

| Task | Frequency | Purpose |
|------|-----------|---------|
| `calculate_supplier_risk_scores` | Daily at 5 AM | Recalculate all vendor risk scores |
| `detect_delivery_degradation` | Every 6 hours | Check for worsening delivery patterns |
| `single_source_risk_scan` | Weekly | Identify products with single suppliers |
| `generate_supply_chain_digest` | Daily at 7 AM | Summary for procurement team |

---

## Implementation Phases

**Phase 1 (with Core AI Expansion):**
- None -- supply chain intelligence starts in Phase 2

**Phase 2 (Intelligence & UX):**
- Supplier risk scoring using Odoo internal data only (delivery performance, quality, price)
- Delivery delay prediction based on historical patterns
- Single-source risk detection
- Supply chain alerts
- Basic dashboard

**Phase 3 (Platform & Portals):**
- External data integration via Integration Hub (financial health APIs, news monitoring)
- Alternative supplier intelligence
- Vendor portal integration (vendors self-report delays, improving prediction data)

**Phase 4 (Scale & Polish):**
- Digital twin simulation for supply chain scenarios
- Tier-2/tier-3 visibility (requires vendor cooperation or external data providers)
- Market data integration (commodity prices, exchange rates)

---

## Expected Impact

| Metric | Before | After |
|--------|--------|-------|
| Supplier disruption warning | 0 days (reactive) | 90-180 days (predictive) |
| Emergency procurement frequency | Multiple times/quarter | Rare (proactive reordering) |
| Emergency procurement cost premium | 40-60% above normal | Minimal (planned alternatives) |
| Single-source risk awareness | Unknown | Complete visibility |
| Vendor performance visibility | Manual spreadsheet review | Real-time dashboard |
| Delivery delay prediction | After it happens | 2-6 weeks advance warning |

---

## Research Sources

- SR Analytics: "Supply Chain Risk Management: Complete Guide 2026" (predictive analytics 90-180 days, 40-60% cost reduction)
- Sphera: "AI-Powered Supplier Risk Management Survey 2025"
- Exiger: "From Reactive to Predictive: How AI Is Redefining Third-Party Risk Management in 2026" (pharmaceutical case study: AI detected Tier 2 fire in hours vs. 10 days traditional)
- APPIT Software: "Solving Supply Chain Visibility: AI-Powered Supplier Risk Monitoring"
- Supply Chain Connect: "How AI-Powered Risk Intelligence Is Transforming Supplier Management"
- Digital Applied: "Supply Chain Digital Visibility: Tracking Guide 2026" (89% can't see tier-2/3, IoT costs down 70%)
- GrowExx: "Real-Time Supply Chain Visibility: Complete 2026 Guide"
- Bezos.ai: "Supply Chain Visibility Solutions: Why Real-Time Data Matters"
