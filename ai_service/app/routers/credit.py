"""Customer Credit Management API endpoints."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.models.audit import (
    CreditScore,
    AuditLog,
    ActionStatus,
    AutomationType,
    get_db,
)
from app.models.schemas import (
    CreditScoreResponse,
    CreditCheckRequest,
    CreditCheckResponse,
    CreditHoldReleaseResponse,
    CreditBatchResponse,
)
from app.automations.credit import CreditManagementAutomation

router = APIRouter(
    prefix="/api/credit",
    tags=["credit-management"],
    dependencies=[Depends(require_api_key)],
)


@router.get("/{customer_id}", response_model=CreditScoreResponse)
async def get_credit_score(
    customer_id: int,
    session: Session = Depends(get_db),
):
    """Get credit score and risk assessment for a customer."""
    existing = (
        session.query(CreditScore)
        .filter(CreditScore.customer_id == customer_id)
        .first()
    )
    if existing:
        return CreditScoreResponse(
            customer_id=existing.customer_id,
            customer_name=existing.customer_name or "",
            credit_score=float(existing.credit_score or 0),
            risk_level=existing.risk_level or "normal",
            credit_limit=float(existing.credit_limit or 0),
            current_exposure=float(existing.current_exposure or 0),
            overdue_amount=float(existing.overdue_amount or 0),
            hold_active=existing.hold_active or False,
            hold_reason=existing.hold_reason,
            breakdown={
                "payment_history": float(existing.payment_history_score or 0),
                "order_volume": float(existing.order_volume_score or 0),
            },
        )

    credit = CreditManagementAutomation()
    result = credit.calculate_credit_score(customer_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return CreditScoreResponse(**result)


@router.post("/{customer_id}/recalculate", response_model=CreditScoreResponse)
async def recalculate_credit_score(
    customer_id: int,
    session: Session = Depends(get_db),
):
    """Force recalculate credit score for a customer."""
    credit = CreditManagementAutomation()
    result = credit.calculate_credit_score(customer_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    from decimal import Decimal

    existing = (
        session.query(CreditScore)
        .filter(CreditScore.customer_id == customer_id)
        .first()
    )
    if existing:
        existing.credit_score = Decimal(str(result["credit_score"]))
        existing.credit_limit = Decimal(str(result["credit_limit"]))
        existing.current_exposure = Decimal(str(result["current_exposure"]))
        existing.overdue_amount = Decimal(str(result["overdue_amount"]))
        existing.payment_history_score = Decimal(str(result["breakdown"]["payment_history"]))
        existing.order_volume_score = Decimal(str(result["breakdown"]["order_volume"]))
        existing.risk_level = result["risk_level"]
        existing.hold_active = result["hold_active"]
        existing.hold_reason = result.get("hold_reason")
        existing.last_calculated = datetime.utcnow()
    else:
        new_cs = CreditScore(
            customer_id=customer_id,
            customer_name=result["customer_name"],
            credit_score=Decimal(str(result["credit_score"])),
            credit_limit=Decimal(str(result["credit_limit"])),
            current_exposure=Decimal(str(result["current_exposure"])),
            overdue_amount=Decimal(str(result["overdue_amount"])),
            payment_history_score=Decimal(str(result["breakdown"]["payment_history"])),
            order_volume_score=Decimal(str(result["breakdown"]["order_volume"])),
            risk_level=result["risk_level"],
            hold_active=result["hold_active"],
            hold_reason=result.get("hold_reason"),
        )
        session.add(new_cs)

    audit = AuditLog(
        automation_type=AutomationType.CREDIT_MANAGEMENT,
        action_name="recalculate_credit",
        odoo_model="res.partner",
        odoo_record_id=customer_id,
        status=ActionStatus.EXECUTED,
        confidence=result["credit_score"] / 100.0,
        ai_reasoning=f"Credit score: {result['credit_score']}, risk: {result['risk_level']}",
        output_data=result,
        executed_at=datetime.utcnow(),
    )
    session.add(audit)

    return CreditScoreResponse(**result)


@router.post("/check", response_model=CreditCheckResponse)
async def check_credit(
    request: CreditCheckRequest,
    session: Session = Depends(get_db),
):
    """Check if a sales order is allowed based on customer credit."""
    credit = CreditManagementAutomation()
    result = credit.check_credit_on_order(request.customer_id, request.order_amount)

    if not result["allowed"]:
        audit = AuditLog(
            automation_type=AutomationType.CREDIT_MANAGEMENT,
            action_name="credit_check_failed",
            odoo_model="sale.order",
            odoo_record_id=0,
            status=ActionStatus.PENDING,
            confidence=result.get("credit_score", 0) / 100.0 if result.get("credit_score") else 0,
            ai_reasoning=result["reason"],
            output_data=result,
            executed_at=datetime.utcnow(),
        )
        session.add(audit)

    return CreditCheckResponse(**result)


@router.get("/", response_model=list[CreditScoreResponse])
async def list_credit_scores(
    risk_level: str | None = None,
    hold_only: bool = False,
    limit: int = 50,
    session: Session = Depends(get_db),
):
    """List credit scores with optional filtering."""
    query = session.query(CreditScore)

    if risk_level:
        query = query.filter(CreditScore.risk_level == risk_level)
    if hold_only:
        query = query.filter(CreditScore.hold_active == True)  # noqa: E712

    scores = (
        query.order_by(CreditScore.credit_score.asc())
        .limit(limit)
        .all()
    )

    return [
        CreditScoreResponse(
            customer_id=cs.customer_id,
            customer_name=cs.customer_name or "",
            credit_score=float(cs.credit_score or 0),
            risk_level=cs.risk_level or "normal",
            credit_limit=float(cs.credit_limit or 0),
            current_exposure=float(cs.current_exposure or 0),
            overdue_amount=float(cs.overdue_amount or 0),
            hold_active=cs.hold_active or False,
            hold_reason=cs.hold_reason,
            breakdown={
                "payment_history": float(cs.payment_history_score or 0),
                "order_volume": float(cs.order_volume_score or 0),
            },
        )
        for cs in scores
    ]


@router.post("/releases", response_model=CreditHoldReleaseResponse)
async def check_hold_releases(
    session: Session = Depends(get_db),
):
    """Check if any credit holds can be released based on recent payments."""
    credit = CreditManagementAutomation()
    releases = credit.check_payment_releases()

    held_count = (
        session.query(CreditScore)
        .filter(CreditScore.hold_active == True)  # noqa: E712
        .count()
    )

    for release in releases:
        audit = AuditLog(
            automation_type=AutomationType.CREDIT_MANAGEMENT,
            action_name="credit_hold_released",
            odoo_model="res.partner",
            odoo_record_id=release["customer_id"],
            status=ActionStatus.EXECUTED,
            confidence=release["new_score"] / 100.0,
            ai_reasoning=f"Hold released: score improved to {release['new_score']}, risk now {release['new_risk']}",
            executed_at=datetime.utcnow(),
        )
        session.add(audit)

    return CreditHoldReleaseResponse(
        releases=releases,
        total_checked=held_count + len(releases),
    )


@router.post("/batch-recalculate", response_model=CreditBatchResponse)
async def batch_recalculate(
    session: Session = Depends(get_db),
):
    """Batch recalculate credit scores for all active customers."""
    credit = CreditManagementAutomation()
    result = credit.calculate_all_scores()

    audit = AuditLog(
        automation_type=AutomationType.CREDIT_MANAGEMENT,
        action_name="batch_credit_recalculation",
        odoo_model="res.partner",
        odoo_record_id=0,
        status=ActionStatus.EXECUTED,
        ai_reasoning=f"Batch recalculated {result['updated']} of {result['total_customers']} customers ({result['errors']} errors)",
        output_data=result,
        executed_at=datetime.utcnow(),
    )
    session.add(audit)

    return CreditBatchResponse(**result)
