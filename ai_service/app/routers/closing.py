"""Month-End Closing API endpoints."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.models.audit import (
    MonthEndClosing,
    ClosingStep,
    AuditLog,
    ActionStatus,
    AutomationType,
    get_db,
)
from app.models.schemas import (
    ClosingStartRequest,
    ClosingStatusResponse,
    ClosingStepResponse,
    ClosingStepCompleteRequest,
)
from app.automations.month_end import MonthEndClosingAutomation, CLOSING_STEPS

router = APIRouter(
    prefix="/api/close",
    tags=["month-end-closing"],
    dependencies=[Depends(require_api_key)],
)


def _build_status_response(closing: MonthEndClosing) -> ClosingStatusResponse:
    steps = sorted(closing.steps, key=lambda s: s.step_order)
    total = len(steps) or 1
    completed = sum(1 for s in steps if s.status == "complete")
    progress = round(completed / total * 100, 1)

    return ClosingStatusResponse(
        closing_id=closing.id,
        period=closing.period,
        status=closing.status,
        overall_progress_pct=progress,
        steps=[ClosingStepResponse.model_validate(s) for s in steps],
        issues=closing.issues_found or [],
        summary=closing.summary,
        started_at=closing.started_at,
        completed_at=closing.completed_at,
    )


@router.post("/start", response_model=ClosingStatusResponse)
async def start_closing(
    request: ClosingStartRequest,
    session: Session = Depends(get_db),
):
    """Start a month-end closing process for the given period."""
    existing = (
        session.query(MonthEndClosing)
        .filter(MonthEndClosing.period == request.period)
        .first()
    )
    if existing and existing.status != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"A closing is already in progress for {request.period}",
        )
    if existing and existing.status == "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Period {request.period} is already closed. Use rescan to re-open.",
        )

    closing = MonthEndClosing(
        period=request.period,
        status="scanning",
        started_by=request.started_by,
    )
    session.add(closing)
    session.flush()

    for step_def in CLOSING_STEPS:
        step = ClosingStep(
            closing_id=closing.id,
            step_name=step_def["name"],
            step_order=step_def["order"],
            status="pending",
        )
        session.add(step)
    session.flush()

    automation = MonthEndClosingAutomation()
    scan_results = automation.run_full_scan(request.period)

    issues_found = []
    for step in closing.steps:
        result = scan_results.get(step.step_name, {})
        step.items_found = result.get("items_found", 0)
        step.auto_check_result = result
        if step.items_found > 0:
            step.status = "needs_attention"
            issues_found.append({
                "step": step.step_name,
                "items_found": step.items_found,
                "details": result.get("details", [])[:5],
            })
        else:
            step.status = "complete"
            step.completed_at = datetime.utcnow()
    session.flush()

    ai_summary = automation.generate_ai_summary(request.period, scan_results)
    closing.summary = ai_summary.get("summary", "")
    closing.issues_found = issues_found
    closing.checklist = {
        "risk_level": ai_summary.get("risk_level", "unknown"),
        "priority_actions": ai_summary.get("priority_actions", []),
        "estimated_hours": ai_summary.get("estimated_completion_hours", 0),
    }
    closing.status = "in_progress"

    audit = AuditLog(
        automation_type=AutomationType.MONTH_END,
        action_name="start_closing",
        odoo_model="month_end.closing",
        odoo_record_id=closing.id,
        status=ActionStatus.EXECUTED,
        confidence=ai_summary.get("confidence", 0.5),
        ai_reasoning=closing.summary,
        output_data={"scan_results": {k: v.get("items_found", 0) for k, v in scan_results.items()}},
        executed_at=datetime.utcnow(),
    )
    session.add(audit)

    return _build_status_response(closing)


@router.get("/{period}/status", response_model=ClosingStatusResponse)
async def get_closing_status(
    period: str,
    session: Session = Depends(get_db),
):
    """Get the current status of a month-end closing."""
    closing = (
        session.query(MonthEndClosing)
        .filter(MonthEndClosing.period == period)
        .first()
    )
    if not closing:
        raise HTTPException(status_code=404, detail=f"No closing found for period {period}")
    return _build_status_response(closing)


@router.post("/{period}/step/{step_name}/complete")
async def complete_step(
    period: str,
    step_name: str,
    request: ClosingStepCompleteRequest,
    session: Session = Depends(get_db),
):
    """Mark a closing step as complete."""
    closing = (
        session.query(MonthEndClosing)
        .filter(MonthEndClosing.period == period)
        .first()
    )
    if not closing:
        raise HTTPException(status_code=404, detail=f"No closing found for period {period}")
    if closing.status == "completed":
        raise HTTPException(status_code=400, detail="Closing is already completed")

    step = next((s for s in closing.steps if s.step_name == step_name), None)
    if not step:
        raise HTTPException(status_code=404, detail=f"Step '{step_name}' not found")

    step.status = "complete"
    step.completed_at = datetime.utcnow()
    step.completed_by = request.completed_by
    step.items_resolved = step.items_found
    if request.notes:
        step.notes = request.notes

    all_complete = all(s.status == "complete" for s in closing.steps)
    if all_complete:
        closing.status = "completed"
        closing.completed_at = datetime.utcnow()

    return {
        "step_name": step_name,
        "status": step.status,
        "closing_status": closing.status,
    }


@router.post("/{period}/rescan", response_model=ClosingStatusResponse)
async def rescan_period(
    period: str,
    session: Session = Depends(get_db),
):
    """Re-run the scan for a period (useful after fixing issues)."""
    closing = (
        session.query(MonthEndClosing)
        .filter(MonthEndClosing.period == period)
        .first()
    )
    if not closing:
        raise HTTPException(status_code=404, detail=f"No closing found for period {period}")

    closing.status = "scanning"

    automation = MonthEndClosingAutomation()
    scan_results = automation.run_full_scan(period)

    issues_found = []
    for step in closing.steps:
        result = scan_results.get(step.step_name, {})
        step.items_found = result.get("items_found", 0)
        step.auto_check_result = result
        if step.items_found > 0 and step.status != "complete":
            step.status = "needs_attention"
            issues_found.append({
                "step": step.step_name,
                "items_found": step.items_found,
            })
        elif step.items_found == 0 and step.status != "complete":
            step.status = "complete"
            step.completed_at = datetime.utcnow()

    ai_summary = automation.generate_ai_summary(period, scan_results)
    closing.summary = ai_summary.get("summary", "")
    closing.issues_found = issues_found
    closing.status = "in_progress"

    return _build_status_response(closing)
