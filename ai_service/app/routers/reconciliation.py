"""Enhanced Bank Reconciliation API endpoints."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.models.audit import (
    ReconciliationSession,
    AuditLog,
    ActionStatus,
    AutomationType,
    get_db,
)
from app.models.schemas import (
    ReconciliationStartRequest,
    ReconciliationStartResponse,
    ReconciliationSuggestionsResponse,
    ReconciliationMatchRequest,
    ReconciliationMatchResponse,
    ReconciliationSkipRequest,
    MatchSuggestion,
)
from app.automations.reconciliation import ReconciliationAutomation

router = APIRouter(
    prefix="/api/reconciliation",
    tags=["bank-reconciliation"],
    dependencies=[Depends(require_api_key)],
)


@router.post("/start", response_model=ReconciliationStartResponse)
async def start_reconciliation(
    request: ReconciliationStartRequest,
    session: Session = Depends(get_db),
):
    """Start a new bank reconciliation session for a journal."""
    active = (
        session.query(ReconciliationSession)
        .filter(
            ReconciliationSession.journal_id == request.journal_id,
            ReconciliationSession.status == "active",
        )
        .first()
    )
    if active:
        recon = ReconciliationAutomation()
        result = recon.start_session(request.journal_id, request.user_id)
        active.total_lines = result["total_lines"]
        active.auto_matched = result["auto_matchable"]
        active.remaining = result["needs_review"]
        active.last_activity = datetime.utcnow()
        return ReconciliationStartResponse(
            session_id=active.id,
            total_lines=result["total_lines"],
            auto_matchable=result["auto_matchable"],
            needs_review=result["needs_review"],
        )

    recon = ReconciliationAutomation()
    result = recon.start_session(request.journal_id, request.user_id)

    recon_session = ReconciliationSession(
        user_id=request.user_id,
        journal_id=request.journal_id,
        status="active",
        total_lines=result["total_lines"],
        auto_matched=result["auto_matchable"],
        remaining=result["needs_review"],
    )
    session.add(recon_session)
    session.flush()

    audit = AuditLog(
        automation_type=AutomationType.ACCOUNTING,
        action_name="start_reconciliation",
        odoo_model="account.bank.statement.line",
        odoo_record_id=request.journal_id,
        status=ActionStatus.EXECUTED,
        confidence=0.0,
        ai_reasoning=f"Started reconciliation: {result['total_lines']} lines, {result['auto_matchable']} auto-matchable",
        output_data={
            "total_lines": result["total_lines"],
            "auto_matchable": result["auto_matchable"],
            "needs_review": result["needs_review"],
        },
        executed_at=datetime.utcnow(),
    )
    session.add(audit)

    return ReconciliationStartResponse(
        session_id=recon_session.id,
        total_lines=result["total_lines"],
        auto_matchable=result["auto_matchable"],
        needs_review=result["needs_review"],
    )


@router.get("/{session_id}/suggestions", response_model=ReconciliationSuggestionsResponse)
async def get_suggestions(
    session_id: int,
    page: int = 1,
    limit: int = 20,
    session: Session = Depends(get_db),
):
    """Get match suggestions for a reconciliation session."""
    recon_session = session.get(ReconciliationSession, session_id)
    if not recon_session:
        raise HTTPException(status_code=404, detail="Reconciliation session not found")

    recon = ReconciliationAutomation()
    learned_rules = recon_session.learned_rules or []
    suggestions, total = recon.get_suggestions(
        journal_id=recon_session.journal_id,
        learned_rules=learned_rules,
        page=page,
        limit=limit,
    )

    recon_session.last_activity = datetime.utcnow()

    return ReconciliationSuggestionsResponse(
        session_id=session_id,
        suggestions=suggestions,
        total=total,
        page=page,
        limit=limit,
    )


@router.post("/{session_id}/match", response_model=ReconciliationMatchResponse)
async def match_entries(
    session_id: int,
    request: ReconciliationMatchRequest,
    session: Session = Depends(get_db),
):
    """Confirm a match between a bank line and an entry, creating a learned rule."""
    recon_session = session.get(ReconciliationSession, session_id)
    if not recon_session:
        raise HTTPException(status_code=404, detail="Reconciliation session not found")
    if recon_session.status != "active":
        raise HTTPException(status_code=400, detail="Session is not active")

    recon = ReconciliationAutomation()

    bank_line = recon.fetch_record_context(
        "account.bank.statement.line",
        request.bank_line_id,
        ["payment_ref", "partner_id", "amount"],
    )
    entry = recon.fetch_record_context(
        "account.move",
        request.entry_id,
        ["name", "ref", "partner_id", "amount_residual"],
    )

    if bank_line and entry:
        new_rule = recon.create_learned_rule(
            bank_ref=str(bank_line.get("payment_ref") or ""),
            bank_partner=recon._extract_partner_name(bank_line.get("partner_id")),
            entry_ref=str(entry.get("ref") or entry.get("name") or ""),
            entry_partner=recon._extract_partner_name(entry.get("partner_id")),
        )
        rules = list(recon_session.learned_rules or [])
        rules.append(new_rule)
        recon_session.learned_rules = rules

    recon_session.manually_matched = (recon_session.manually_matched or 0) + 1
    recon_session.remaining = max(0, (recon_session.remaining or 0) - 1)
    recon_session.last_activity = datetime.utcnow()

    if recon_session.remaining == 0:
        recon_session.status = "completed"
        recon_session.completed_at = datetime.utcnow()

    progress = {
        "matched": (recon_session.auto_matched or 0) + (recon_session.manually_matched or 0),
        "remaining": recon_session.remaining or 0,
        "total": recon_session.total_lines or 0,
    }

    return ReconciliationMatchResponse(matched=True, session_progress=progress)


@router.post("/{session_id}/skip")
async def skip_line(
    session_id: int,
    request: ReconciliationSkipRequest,
    session: Session = Depends(get_db),
):
    """Skip a bank line (mark as needing manual handling later)."""
    recon_session = session.get(ReconciliationSession, session_id)
    if not recon_session:
        raise HTTPException(status_code=404, detail="Reconciliation session not found")
    if recon_session.status != "active":
        raise HTTPException(status_code=400, detail="Session is not active")

    recon_session.skipped = (recon_session.skipped or 0) + 1
    recon_session.remaining = max(0, (recon_session.remaining or 0) - 1)
    recon_session.last_activity = datetime.utcnow()

    return {"skipped": True, "reason": request.reason}
