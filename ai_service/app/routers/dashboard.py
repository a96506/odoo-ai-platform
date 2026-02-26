"""Dashboard API: stats, audit logs, and approval endpoints."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.models.audit import AuditLog, ActionStatus, get_db
from app.models.schemas import DashboardStats, AuditLogResponse, ApprovalRequest
from app.tasks.celery_tasks import execute_approved_action

router = APIRouter(
    prefix="/api",
    tags=["dashboard"],
    dependencies=[Depends(require_api_key)],
)


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(session: Session = Depends(get_db)):
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    total = session.query(AuditLog).count()
    today_count = (
        session.query(AuditLog).filter(AuditLog.timestamp >= today).count()
    )
    pending = (
        session.query(AuditLog)
        .filter(AuditLog.status == ActionStatus.PENDING)
        .count()
    )
    executed = (
        session.query(AuditLog)
        .filter(AuditLog.status == ActionStatus.EXECUTED)
        .count()
    )
    success_rate = (executed / total * 100) if total > 0 else 0.0

    tokens_today = (
        session.query(func.coalesce(func.sum(AuditLog.tokens_used), 0))
        .filter(AuditLog.timestamp >= today)
        .scalar()
    )

    by_type = {}
    type_counts = (
        session.query(AuditLog.automation_type, func.count(AuditLog.id))
        .group_by(AuditLog.automation_type)
        .all()
    )
    for atype, count in type_counts:
        by_type[atype] = count

    time_saved = executed * 2.0

    return DashboardStats(
        total_automations=total,
        automations_today=today_count,
        pending_approvals=pending,
        success_rate=round(success_rate, 1),
        tokens_used_today=tokens_today,
        by_type=by_type,
        time_saved_minutes=time_saved,
    )


@router.get("/audit-logs", response_model=list[AuditLogResponse])
async def get_audit_logs(
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    automation_type: str | None = None,
    session: Session = Depends(get_db),
):
    query = session.query(AuditLog).order_by(AuditLog.timestamp.desc())
    if status:
        query = query.filter(AuditLog.status == status)
    if automation_type:
        query = query.filter(AuditLog.automation_type == automation_type)
    logs = query.offset(offset).limit(limit).all()
    return [AuditLogResponse.model_validate(log) for log in logs]


@router.post("/approve")
async def approve_action(
    request: ApprovalRequest,
    session: Session = Depends(get_db),
):
    audit = session.get(AuditLog, request.audit_log_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit log not found")
    if audit.status != ActionStatus.PENDING:
        raise HTTPException(status_code=400, detail="Action is not pending")

    if request.approved:
        audit.status = ActionStatus.APPROVED
        audit.approved_by = request.approved_by
        session.flush()
        execute_approved_action.delay(audit.id)
        return {"status": "approved", "message": "Action queued for execution"}
    else:
        audit.status = ActionStatus.REJECTED
        audit.approved_by = request.approved_by
        return {"status": "rejected"}
