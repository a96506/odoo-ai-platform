"""Role-based dashboard endpoints: CFO, Sales Manager, Warehouse Manager."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
import structlog

from app.auth import require_api_key
from app.models.audit import (
    AuditLog,
    ActionStatus,
    MonthEndClosing,
    ClosingStep,
    CashForecast,
    CreditScore,
    DailyDigest,
    get_db,
)
from app.models.schemas import (
    CFODashboardResponse,
    SalesDashboardResponse,
    WarehouseDashboardResponse,
    AgingBucket,
    PLSummary,
    CloseStatusSummary,
    ForecastDataPoint,
    DigestAnomaly,
    PipelineStage,
    AtRiskDeal,
    StockAlert,
    ShipmentSummary,
)

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/dashboard",
    tags=["role-dashboard"],
    dependencies=[Depends(require_api_key)],
)


def _safe_odoo_client():
    """Return OdooClient or None if connection fails."""
    try:
        from app.odoo_client import get_odoo_client
        return get_odoo_client()
    except Exception:
        logger.warning("odoo_client_unavailable")
        return None


def _get_aging_buckets(odoo, move_type: str) -> list[AgingBucket]:
    """Compute AR or AP aging from Odoo account.move records."""
    if not odoo:
        return _default_aging()

    try:
        domain = [
            ("move_type", "=", move_type),
            ("payment_state", "in", ["not_paid", "partial"]),
            ("state", "=", "posted"),
        ]
        invoices = odoo.search_read(
            "account.move",
            domain,
            fields=["amount_residual", "invoice_date_due"],
            limit=500,
        )

        today = datetime.utcnow().date()
        buckets = {"0-30": 0.0, "31-60": 0.0, "61-90": 0.0, "90+": 0.0}
        counts = {"0-30": 0, "31-60": 0, "61-90": 0, "90+": 0}

        for inv in invoices:
            due = inv.get("invoice_date_due")
            if not due:
                continue
            if isinstance(due, str):
                try:
                    due = datetime.strptime(due, "%Y-%m-%d").date()
                except ValueError:
                    continue

            days_overdue = (today - due).days
            amount = abs(inv.get("amount_residual", 0))
            if days_overdue <= 30:
                buckets["0-30"] += amount
                counts["0-30"] += 1
            elif days_overdue <= 60:
                buckets["31-60"] += amount
                counts["31-60"] += 1
            elif days_overdue <= 90:
                buckets["61-90"] += amount
                counts["61-90"] += 1
            else:
                buckets["90+"] += amount
                counts["90+"] += 1

        return [
            AgingBucket(bucket=k, amount=round(v, 2), count=counts[k])
            for k, v in buckets.items()
        ]
    except Exception as exc:
        logger.warning("aging_fetch_failed", error=str(exc))
        return _default_aging()


def _default_aging() -> list[AgingBucket]:
    return [
        AgingBucket(bucket="0-30"),
        AgingBucket(bucket="31-60"),
        AgingBucket(bucket="61-90"),
        AgingBucket(bucket="90+"),
    ]


@router.get("/cfo", response_model=CFODashboardResponse)
async def get_cfo_dashboard(session: Session = Depends(get_db)):
    now = datetime.utcnow()
    odoo = _safe_odoo_client()

    ar_aging = _get_aging_buckets(odoo, "out_invoice")
    ap_aging = _get_aging_buckets(odoo, "in_invoice")
    total_ar = sum(b.amount for b in ar_aging)
    total_ap = sum(b.amount for b in ap_aging)

    # Cash forecast from DB (scenarios are stored in ForecastScenario table)
    forecast_rows = (
        session.query(CashForecast)
        .order_by(CashForecast.forecast_date.desc(), CashForecast.target_date.asc())
        .limit(90)
        .all()
    )
    cash_forecast = [
        ForecastDataPoint(
            date=str(f.target_date),
            balance=float(f.predicted_balance or 0),
            low=float(f.confidence_low or 0),
            high=float(f.confidence_high or 0),
            ar_expected=float(f.ar_expected or 0),
            ap_expected=float(f.ap_expected or 0),
        )
        for f in forecast_rows
    ]

    current_balance = float(forecast_rows[0].predicted_balance) if forecast_rows else 0.0

    # P&L summary from Odoo
    pl = PLSummary(period=now.strftime("%Y-%m"))
    if odoo:
        try:
            revenue = odoo.search_read(
                "account.move.line",
                [
                    ("parent_state", "=", "posted"),
                    ("account_id.account_type", "=", "income"),
                    ("date", ">=", now.replace(day=1).strftime("%Y-%m-%d")),
                ],
                fields=["balance"],
                limit=1000,
            )
            expenses = odoo.search_read(
                "account.move.line",
                [
                    ("parent_state", "=", "posted"),
                    ("account_id.account_type", "=", "expense"),
                    ("date", ">=", now.replace(day=1).strftime("%Y-%m-%d")),
                ],
                fields=["balance"],
                limit=1000,
            )
            pl.total_revenue = abs(sum(r.get("balance", 0) for r in revenue))
            pl.total_expenses = abs(sum(e.get("balance", 0) for e in expenses))
            pl.net_income = pl.total_revenue - pl.total_expenses
        except Exception as exc:
            logger.warning("pl_fetch_failed", error=str(exc))

    # Close status
    close_status = CloseStatusSummary()
    period_str = now.strftime("%Y-%m")
    closing = (
        session.query(MonthEndClosing)
        .filter(MonthEndClosing.period == period_str)
        .first()
    )
    if closing:
        steps = session.query(ClosingStep).filter(ClosingStep.closing_id == closing.id).all()
        completed = sum(1 for s in steps if s.status == "complete")
        progress = round((completed / len(steps) * 100) if steps else 0, 1)
        close_status = CloseStatusSummary(
            period=period_str,
            status=closing.status,
            progress_pct=progress,
            steps_total=len(steps),
            steps_completed=completed,
        )

    pending = (
        session.query(AuditLog)
        .filter(AuditLog.status == ActionStatus.PENDING)
        .count()
    )

    # Recent anomalies from digest
    anomalies: list[DigestAnomaly] = []
    latest_digest = (
        session.query(DailyDigest)
        .filter(DailyDigest.user_role == "cfo")
        .order_by(DailyDigest.generated_at.desc())
        .first()
    )
    if latest_digest and latest_digest.content:
        raw_anomalies = latest_digest.content.get("anomalies", [])
        anomalies = [
            DigestAnomaly(
                description=a.get("description", ""),
                severity=a.get("severity", "medium"),
                source=a.get("source", ""),
            )
            for a in raw_anomalies[:5]
        ]

    return CFODashboardResponse(
        cash_position=round(current_balance, 2),
        total_ar=round(total_ar, 2),
        total_ap=round(total_ap, 2),
        ar_aging=ar_aging,
        ap_aging=ap_aging,
        cash_forecast=cash_forecast,
        pl_summary=pl,
        close_status=close_status,
        pending_approvals=pending,
        anomalies=anomalies,
        generated_at=now,
    )


@router.get("/sales", response_model=SalesDashboardResponse)
async def get_sales_dashboard(session: Session = Depends(get_db)):
    now = datetime.utcnow()
    odoo = _safe_odoo_client()

    pipeline_stages: list[PipelineStage] = []
    pipeline_value = 0.0
    win_rate = 0.0
    deals_closing = 0
    at_risk: list[AtRiskDeal] = []
    conversion_funnel: list[PipelineStage] = []
    revenue_month = 0.0

    if odoo:
        try:
            leads = odoo.search_read(
                "crm.lead",
                [("type", "=", "opportunity"), ("active", "=", True)],
                fields=[
                    "name", "expected_revenue", "probability",
                    "stage_id", "date_deadline", "write_date",
                    "partner_id",
                ],
                limit=500,
            )

            stage_map: dict[str, PipelineStage] = {}
            for lead in leads:
                stage_name = lead.get("stage_id", [0, "Unknown"])
                if isinstance(stage_name, list):
                    stage_name = stage_name[1] if len(stage_name) > 1 else "Unknown"
                else:
                    stage_name = str(stage_name)

                if stage_name not in stage_map:
                    stage_map[stage_name] = PipelineStage(stage=stage_name)
                stage_map[stage_name].count += 1
                stage_map[stage_name].value += lead.get("expected_revenue", 0) or 0

                pipeline_value += lead.get("expected_revenue", 0) or 0

                # Deals closing this month
                deadline = lead.get("date_deadline")
                if deadline:
                    if isinstance(deadline, str):
                        try:
                            dl = datetime.strptime(deadline, "%Y-%m-%d")
                            if dl.year == now.year and dl.month == now.month:
                                deals_closing += 1
                        except ValueError:
                            pass

                # At-risk: stale or low probability with high value
                write_date = lead.get("write_date", "")
                days_stale = 0
                if write_date:
                    try:
                        wd = datetime.strptime(write_date[:10], "%Y-%m-%d")
                        days_stale = (now - wd).days
                    except (ValueError, TypeError):
                        pass

                prob = lead.get("probability", 0) or 0
                rev = lead.get("expected_revenue", 0) or 0
                if (days_stale > 14 and rev > 0) or (prob < 30 and rev > 5000):
                    at_risk.append(AtRiskDeal(
                        lead_id=lead.get("id", 0),
                        name=lead.get("name", ""),
                        value=rev,
                        probability=prob,
                        days_stale=days_stale,
                        stage=stage_name,
                    ))

            pipeline_stages = sorted(stage_map.values(), key=lambda s: s.value, reverse=True)
            conversion_funnel = list(pipeline_stages)
            at_risk = sorted(at_risk, key=lambda d: d.value, reverse=True)[:10]

            # Win rate
            won = odoo.search_count("crm.lead", [
                ("type", "=", "opportunity"),
                ("stage_id.is_won", "=", True),
                ("date_closed", ">=", (now - timedelta(days=90)).strftime("%Y-%m-%d")),
            ])
            total_closed = odoo.search_count("crm.lead", [
                ("type", "=", "opportunity"),
                ("active", "=", False),
                ("date_closed", ">=", (now - timedelta(days=90)).strftime("%Y-%m-%d")),
            ]) + won
            win_rate = round((won / total_closed * 100) if total_closed > 0 else 0, 1)

            # Revenue this month
            month_sales = odoo.search_read(
                "sale.order",
                [
                    ("state", "=", "sale"),
                    ("date_order", ">=", now.replace(day=1).strftime("%Y-%m-%d")),
                ],
                fields=["amount_total"],
                limit=500,
            )
            revenue_month = sum(s.get("amount_total", 0) for s in month_sales)

        except Exception as exc:
            logger.warning("sales_dashboard_odoo_failed", error=str(exc))

    recent_auto = (
        session.query(AuditLog)
        .filter(
            AuditLog.automation_type.in_(["crm", "sales"]),
            AuditLog.timestamp >= now - timedelta(days=7),
        )
        .count()
    )

    return SalesDashboardResponse(
        pipeline_value=round(pipeline_value, 2),
        pipeline_stages=pipeline_stages,
        win_rate=win_rate,
        deals_closing_this_month=deals_closing,
        at_risk_deals=at_risk,
        conversion_funnel=conversion_funnel,
        revenue_this_month=round(revenue_month, 2),
        quota_target=0.0,
        quota_pct=0.0,
        recent_automations=recent_auto,
        generated_at=now,
    )


@router.get("/warehouse", response_model=WarehouseDashboardResponse)
async def get_warehouse_dashboard(session: Session = Depends(get_db)):
    now = datetime.utcnow()
    odoo = _safe_odoo_client()

    stock_alerts: list[StockAlert] = []
    total_products = 0
    below_reorder = 0
    shipments = ShipmentSummary()

    if odoo:
        try:
            products = odoo.search_read(
                "product.product",
                [("type", "=", "product")],
                fields=["name", "qty_available", "reorder_min_qty"],
                limit=200,
            )
            total_products = len(products)

            for p in products:
                qty = p.get("qty_available", 0) or 0
                reorder = p.get("reorder_min_qty", 0) or 0
                status = "ok"
                if reorder > 0:
                    if qty <= 0:
                        status = "critical"
                    elif qty < reorder:
                        status = "low"
                    elif qty < reorder * 1.2:
                        status = "warning"

                if status != "ok":
                    below_reorder += 1
                    stock_alerts.append(StockAlert(
                        product_id=p.get("id", 0),
                        product_name=p.get("name", ""),
                        qty_available=qty,
                        reorder_point=reorder,
                        status=status,
                    ))

            stock_alerts = sorted(
                stock_alerts,
                key=lambda a: {"critical": 0, "low": 1, "warning": 2}.get(a.status, 3),
            )[:20]

            # Shipments
            incoming = odoo.search_read(
                "stock.picking",
                [("picking_type_code", "=", "incoming"), ("state", "not in", ["done", "cancel"])],
                fields=["state"],
                limit=200,
            )
            outgoing = odoo.search_read(
                "stock.picking",
                [("picking_type_code", "=", "outgoing"), ("state", "not in", ["done", "cancel"])],
                fields=["state"],
                limit=200,
            )
            shipments = ShipmentSummary(
                incoming_count=len(incoming),
                incoming_ready=sum(1 for s in incoming if s.get("state") == "assigned"),
                outgoing_count=len(outgoing),
                outgoing_ready=sum(1 for s in outgoing if s.get("state") == "assigned"),
            )

        except Exception as exc:
            logger.warning("warehouse_dashboard_odoo_failed", error=str(exc))

    recent_auto = (
        session.query(AuditLog)
        .filter(
            AuditLog.automation_type.in_(["inventory", "purchase"]),
            AuditLog.timestamp >= now - timedelta(days=7),
        )
        .count()
    )

    return WarehouseDashboardResponse(
        total_products=total_products,
        below_reorder=below_reorder,
        stock_alerts=stock_alerts,
        shipments=shipments,
        recent_automations=recent_auto,
        generated_at=now,
    )
