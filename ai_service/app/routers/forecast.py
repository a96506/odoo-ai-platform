"""Cash Flow Forecasting API endpoints."""

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.models.audit import (
    CashForecast,
    ForecastScenario,
    ForecastAccuracyLog,
    AuditLog,
    ActionStatus,
    AutomationType,
    get_db,
)
from app.models.schemas import (
    CashFlowForecastResponse,
    ForecastDataPoint,
    ForecastSummary,
    ScenarioRequest,
    ScenarioResponse,
    ForecastAccuracyResponse,
)
from app.automations.cash_flow import CashFlowForecastingAutomation

router = APIRouter(
    prefix="/api/forecast",
    tags=["cash-flow-forecast"],
    dependencies=[Depends(require_api_key)],
)


@router.get("/cashflow", response_model=CashFlowForecastResponse)
async def get_cash_flow_forecast(
    horizon: int = Query(default=90, ge=7, le=365, description="Forecast horizon in days"),
    session: Session = Depends(get_db),
):
    """
    Get cash flow forecast for the specified horizon.

    Returns predicted cash positions with confidence bands,
    AR/AP summaries, and cash gap warnings.
    """
    automation = CashFlowForecastingAutomation()
    result = automation.generate_forecast(horizon_days=horizon)

    audit = AuditLog(
        automation_type=AutomationType.FORECASTING,
        action_name="generate_forecast",
        odoo_model="cash.forecast",
        odoo_record_id=0,
        status=ActionStatus.EXECUTED,
        confidence=0.85,
        ai_reasoning=f"Generated {horizon}-day forecast with {len(result.get('cash_gap_dates', []))} cash gap warnings",
        output_data={
            "horizon_days": horizon,
            "cash_gaps": len(result.get("cash_gap_dates", [])),
            "model_version": result.get("model_version", ""),
        },
        executed_at=datetime.utcnow(),
    )
    session.add(audit)

    return CashFlowForecastResponse(
        generated_at=datetime.fromisoformat(result["generated_at"]) if result.get("generated_at") else datetime.utcnow(),
        horizon_days=result.get("horizon_days", horizon),
        current_balance=result.get("current_balance", 0),
        forecasts=[ForecastDataPoint(**f) for f in result.get("forecasts", [])],
        ar_summary=ForecastSummary(**result.get("ar_summary", {})),
        ap_summary=ForecastSummary(**result.get("ap_summary", {})),
        cash_gap_dates=result.get("cash_gap_dates", []),
        model_version=result.get("model_version", ""),
    )


@router.post("/scenario", response_model=ScenarioResponse)
async def create_scenario(
    request: ScenarioRequest,
    session: Session = Depends(get_db),
):
    """
    Run a what-if scenario on the cash flow forecast.

    Supported adjustments:
    - delay_customer_{id}: days to delay payment
    - remove_deal_{id}: remove deal from pipeline
    - reduce_ar_by: percentage reduction in AR
    - increase_ap_by: percentage increase in AP
    - adjust_expense_{category}: multiplier for expenses
    """
    automation = CashFlowForecastingAutomation()
    result = automation.run_scenario(
        name=request.name,
        adjustments=request.adjustments,
        description=request.description,
    )

    scenario = ForecastScenario(
        name=request.name,
        description=request.description,
        adjustments=request.adjustments,
        result_data=result,
        created_by="api",
    )
    session.add(scenario)
    session.flush()

    audit = AuditLog(
        automation_type=AutomationType.FORECASTING,
        action_name="scenario_analysis",
        odoo_model="forecast.scenario",
        odoo_record_id=scenario.id,
        status=ActionStatus.EXECUTED,
        confidence=0.8,
        ai_reasoning=f"Scenario '{request.name}': end balance change {result['impact'].get('end_balance_change', 0):.2f}",
        output_data=result.get("impact", {}),
        executed_at=datetime.utcnow(),
    )
    session.add(audit)

    return ScenarioResponse(
        scenario_id=scenario.id,
        name=result["name"],
        forecasts=[ForecastDataPoint(**f) for f in result.get("forecasts", [])],
        impact=result.get("impact", {}),
        created_at=scenario.created_at,
    )


@router.get("/accuracy", response_model=ForecastAccuracyResponse)
async def get_forecast_accuracy(
    session: Session = Depends(get_db),
):
    """
    Get forecast accuracy metrics comparing predicted vs actual balances.

    Returns MAE and MAPE for 30/60/90-day windows.
    """
    automation = CashFlowForecastingAutomation()
    result = automation.check_accuracy()

    return ForecastAccuracyResponse(
        last_30_days=result.get("last_30_days", {}),
        last_60_days=result.get("last_60_days", {}),
        last_90_days=result.get("last_90_days", {}),
        total_comparisons=result.get("total_comparisons", 0),
    )


@router.get("/scenarios", response_model=list[ScenarioResponse])
async def list_scenarios(
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db),
):
    """List recent forecast scenarios."""
    scenarios = (
        session.query(ForecastScenario)
        .order_by(ForecastScenario.created_at.desc())
        .limit(limit)
        .all()
    )

    results = []
    for sc in scenarios:
        data = sc.result_data or {}
        results.append(ScenarioResponse(
            scenario_id=sc.id,
            name=sc.name,
            forecasts=[ForecastDataPoint(**f) for f in data.get("forecasts", [])[:5]],
            impact=data.get("impact", {}),
            created_at=sc.created_at,
        ))

    return results


@router.get("/scenarios/{scenario_id}", response_model=ScenarioResponse)
async def get_scenario(
    scenario_id: int,
    session: Session = Depends(get_db),
):
    """Get a specific scenario by ID."""
    scenario = session.get(ForecastScenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    data = scenario.result_data or {}
    return ScenarioResponse(
        scenario_id=scenario.id,
        name=scenario.name,
        forecasts=[ForecastDataPoint(**f) for f in data.get("forecasts", [])],
        impact=data.get("impact", {}),
        created_at=scenario.created_at,
    )
