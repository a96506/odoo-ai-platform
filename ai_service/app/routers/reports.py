"""Natural Language Report Builder API endpoints."""

import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.models.audit import (
    ReportJob,
    AuditLog,
    ActionStatus,
    AutomationType,
    get_db,
)
from app.models.schemas import (
    ReportGenerateRequest,
    ReportGenerateResponse,
    ReportJobResponse,
    ReportScheduleRequest,
    ReportScheduleResponse,
)
from app.automations.report_builder import ReportBuilderAutomation

router = APIRouter(
    prefix="/api/reports",
    tags=["report-builder"],
    dependencies=[Depends(require_api_key)],
)


@router.post("/generate", response_model=ReportGenerateResponse)
async def generate_report(
    request: ReportGenerateRequest,
    session: Session = Depends(get_db),
):
    """
    Generate a report from a natural language query.

    Examples:
    - "Sales by product category for Q4 2025"
    - "Top 10 customers by revenue this year"
    - "Overdue invoices summary"
    - "Pipeline by stage with expected revenue"
    """
    job = ReportJob(
        request_text=request.query,
        format=request.format,
        status="generating",
        requested_by="api",
    )
    session.add(job)
    session.flush()

    try:
        automation = ReportBuilderAutomation()
        result = automation.generate_report(request.query)

        job.parsed_query = result.get("parsed_query")
        job.result_data = result.get("result_data")
        job.status = result.get("status", "completed")
        job.error_message = result.get("error_message")
        job.completed_at = datetime.utcnow()

        if request.format == "excel" and job.status == "completed":
            file_path = automation.export_excel(result["result_data"])
            job.file_path = file_path
        elif request.format == "pdf" and job.status == "completed":
            file_path = automation.export_pdf(result["result_data"])
            job.file_path = file_path

    except Exception as exc:
        job.status = "error"
        job.error_message = str(exc)
        job.completed_at = datetime.utcnow()

    audit = AuditLog(
        automation_type=AutomationType.REPORTING,
        action_name="generate_report",
        odoo_model="report.job",
        odoo_record_id=job.id,
        status=ActionStatus.EXECUTED if job.status == "completed" else ActionStatus.FAILED,
        confidence=0.85,
        ai_reasoning=f"Report: '{request.query}' -> {job.status}",
        output_data={
            "query": request.query,
            "format": request.format,
            "record_count": result.get("result_data", {}).get("record_count", 0) if 'result' in dir() else 0,
        },
        executed_at=datetime.utcnow(),
    )
    session.add(audit)

    return ReportGenerateResponse(job_id=job.id, status=job.status)


@router.get("/{job_id}", response_model=ReportJobResponse)
async def get_report(
    job_id: int,
    session: Session = Depends(get_db),
):
    """Get report job status and results."""
    job = session.get(ReportJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Report job not found")

    return ReportJobResponse(
        job_id=job.id,
        status=job.status,
        request_text=job.request_text or "",
        format=job.format or "table",
        parsed_query=job.parsed_query,
        data=job.result_data,
        error_message=job.error_message,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


@router.get("/{job_id}/download")
async def download_report(
    job_id: int,
    format: str = Query(default="excel", pattern=r"^(excel|pdf)$"),
    session: Session = Depends(get_db),
):
    """Download the report as Excel or PDF."""
    job = session.get(ReportJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Report job not found")

    if job.status != "completed":
        raise HTTPException(status_code=400, detail=f"Report is not ready: {job.status}")

    if not job.result_data:
        raise HTTPException(status_code=400, detail="No report data available")

    automation = ReportBuilderAutomation()

    if format == "excel":
        file_name = f"report_{job_id}.xlsx"
        file_path = automation.export_excel(job.result_data, file_name)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        file_name = f"report_{job_id}.txt"
        file_path = automation.export_pdf(job.result_data, file_name)
        media_type = "text/plain"

    if not os.path.exists(file_path):
        raise HTTPException(status_code=500, detail="Report file generation failed")

    job.file_path = file_path

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=file_name,
    )


@router.post("/schedule", response_model=ReportScheduleResponse)
async def schedule_report(
    request: ReportScheduleRequest,
    session: Session = Depends(get_db),
):
    """
    Schedule a recurring report.

    Cron examples:
    - "0 8 * * MON" = Every Monday at 8 AM
    - "0 9 1 * *" = First of every month at 9 AM
    - "0 7 * * *" = Daily at 7 AM
    """
    job = ReportJob(
        request_text=request.query,
        format=request.format,
        schedule_cron=request.cron,
        requested_by=request.recipient or "api",
        status="scheduled",
    )
    session.add(job)
    session.flush()

    schedule_desc = ReportBuilderAutomation._parse_cron_to_description(request.cron)

    audit = AuditLog(
        automation_type=AutomationType.REPORTING,
        action_name="schedule_report",
        odoo_model="report.job",
        odoo_record_id=job.id,
        status=ActionStatus.EXECUTED,
        confidence=1.0,
        ai_reasoning=f"Scheduled report: '{request.query}' -> {schedule_desc}",
        output_data={
            "query": request.query,
            "cron": request.cron,
            "format": request.format,
            "deliver_via": request.deliver_via,
            "recipient": request.recipient,
        },
        executed_at=datetime.utcnow(),
    )
    session.add(audit)

    return ReportScheduleResponse(
        job_id=job.id,
        schedule=schedule_desc,
        next_run="",
    )


@router.get("/", response_model=list[ReportJobResponse])
async def list_reports(
    status: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db),
):
    """List report jobs with optional status filter."""
    query = session.query(ReportJob)

    if status:
        query = query.filter(ReportJob.status == status)

    jobs = (
        query.order_by(ReportJob.created_at.desc())
        .limit(limit)
        .all()
    )

    return [
        ReportJobResponse(
            job_id=j.id,
            status=j.status or "pending",
            request_text=j.request_text or "",
            format=j.format or "table",
            parsed_query=j.parsed_query,
            data=j.result_data,
            error_message=j.error_message,
            created_at=j.created_at,
            completed_at=j.completed_at,
        )
        for j in jobs
    ]
