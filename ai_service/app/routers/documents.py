"""Smart Invoice Processing (IDP) API endpoints."""

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.models.audit import (
    DocumentProcessingJob,
    ExtractionCorrection,
    AuditLog,
    ActionStatus,
    AutomationType,
    get_db,
)
from app.models.schemas import (
    DocumentProcessResponse,
    DocumentJobResponse,
    DocumentExtractionResult,
    DocumentCorrectionRequest,
    DocumentCorrectionResponse,
)
from app.automations.document_processing import DocumentProcessingAutomation

router = APIRouter(
    prefix="/api/documents",
    tags=["document-processing"],
    dependencies=[Depends(require_api_key)],
)

ALLOWED_TYPES = {
    "application/pdf": "pdf",
    "image/jpeg": "jpeg",
    "image/jpg": "jpeg",
    "image/png": "png",
    "image/webp": "webp",
}


@router.post("/process", response_model=DocumentProcessResponse)
async def process_document(
    file: UploadFile = File(...),
    document_type: str = Form(default="auto"),
    uploaded_by: str = Form(default="admin"),
    session: Session = Depends(get_db),
):
    """Upload a PDF or image invoice for AI-powered extraction."""
    content_type = file.content_type or ""
    if content_type not in ALLOWED_TYPES:
        ext = (file.filename or "").rsplit(".", 1)[-1].lower() if file.filename else ""
        if ext in ("pdf", "jpg", "jpeg", "png", "webp"):
            content_type = f"image/{ext}" if ext != "pdf" else "application/pdf"
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {content_type}. Accepted: PDF, JPEG, PNG, WebP",
            )

    file_content = await file.read()
    if not file_content:
        raise HTTPException(status_code=400, detail="Empty file")

    file_type = ALLOWED_TYPES.get(content_type, content_type)

    job = DocumentProcessingJob(
        file_name=file.filename or "unknown",
        file_type=file_type,
        document_type=document_type if document_type != "auto" else None,
        status="processing",
        source="upload",
        uploaded_by=uploaded_by,
    )
    session.add(job)
    session.flush()

    automation = DocumentProcessingAutomation()
    result = automation.process_document(
        file_content=file_content,
        file_name=file.filename or "unknown",
        file_type=file_type,
        uploaded_by=uploaded_by,
    )

    job.status = result.get("status", "failed")
    job.document_type = result.get("document_type", document_type)
    job.extraction_result = result.get("extraction")
    job.overall_confidence = Decimal(str(result.get("confidence", 0)))
    job.field_confidences = result.get("field_confidences", {})
    job.matched_vendor_id = result.get("matched_vendor_id")
    job.matched_po_id = result.get("matched_po_id")
    job.odoo_record_created = result.get("odoo_record_created")
    job.odoo_model_created = "account.move" if result.get("odoo_record_created") else None
    job.error_message = result.get("error_message")
    job.processing_time_ms = result.get("processing_time_ms")
    job.completed_at = datetime.utcnow()

    audit = AuditLog(
        automation_type=AutomationType.DOCUMENT_PROCESSING,
        action_name="process_document",
        odoo_model="account.move",
        odoo_record_id=result.get("odoo_record_created") or 0,
        status=ActionStatus.EXECUTED if result.get("status") == "completed" else ActionStatus.FAILED,
        confidence=result.get("confidence", 0),
        ai_reasoning=f"IDP: {result.get('document_type', 'unknown')} from {file.filename}, confidence={result.get('confidence', 0):.2f}",
        input_data={"file_name": file.filename, "file_type": file_type},
        output_data={
            "vendor": result.get("extraction", {}).get("vendor", ""),
            "total": result.get("extraction", {}).get("total", 0),
            "matched_vendor_id": result.get("matched_vendor_id"),
            "matched_po_id": result.get("matched_po_id"),
            "odoo_record_created": result.get("odoo_record_created"),
        },
        executed_at=datetime.utcnow(),
    )
    session.add(audit)

    return DocumentProcessResponse(job_id=job.id, status=job.status)


@router.get("/{job_id}", response_model=DocumentJobResponse)
async def get_document_job(
    job_id: int,
    session: Session = Depends(get_db),
):
    """Get the status and extraction results for a document processing job."""
    job = session.get(DocumentProcessingJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    extraction = None
    if job.extraction_result:
        extraction = DocumentExtractionResult(**job.extraction_result)

    matched_vendor_name = ""
    if job.matched_vendor_id:
        try:
            automation = DocumentProcessingAutomation()
            partner = automation.fetch_record_context(
                "res.partner", job.matched_vendor_id, ["name"]
            )
            if partner:
                matched_vendor_name = partner.get("name", "")
        except Exception:
            pass

    po_validation = None
    if job.matched_po_id and job.extraction_result:
        po_ref = job.extraction_result.get("po_reference", "")
        if po_ref:
            try:
                automation = DocumentProcessingAutomation()
                po_validation = automation._validate_against_po(po_ref, job.extraction_result)
            except Exception:
                pass

    return DocumentJobResponse(
        job_id=job.id,
        file_name=job.file_name or "",
        document_type=job.document_type or "",
        status=job.status or "unknown",
        extraction=extraction,
        confidence=float(job.overall_confidence or 0),
        field_confidences=job.field_confidences or {},
        matched_vendor_id=job.matched_vendor_id,
        matched_vendor_name=matched_vendor_name,
        matched_po_id=job.matched_po_id,
        po_validation=po_validation,
        odoo_record_created=job.odoo_record_created,
        error_message=job.error_message,
        processing_time_ms=job.processing_time_ms,
        created_at=job.created_at,
    )


@router.post("/{job_id}/correct", response_model=DocumentCorrectionResponse)
async def correct_extraction(
    job_id: int,
    request: DocumentCorrectionRequest,
    session: Session = Depends(get_db),
):
    """Submit a correction for an extracted field (learning loop)."""
    job = session.get(DocumentProcessingJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    original_value = None
    if job.extraction_result:
        original_value = str(job.extraction_result.get(request.field_name, ""))

    correction = ExtractionCorrection(
        job_id=job_id,
        field_name=request.field_name,
        original_value=original_value,
        corrected_value=request.corrected_value,
        corrected_by="admin",
    )
    session.add(correction)

    if job.extraction_result:
        updated = dict(job.extraction_result)
        updated[request.field_name] = request.corrected_value
        job.extraction_result = updated

    audit = AuditLog(
        automation_type=AutomationType.DOCUMENT_PROCESSING,
        action_name="extraction_correction",
        odoo_model="account.move",
        odoo_record_id=job.odoo_record_created or 0,
        status=ActionStatus.EXECUTED,
        ai_reasoning=f"Correction: {request.field_name} '{original_value}' -> '{request.corrected_value}'",
        executed_at=datetime.utcnow(),
    )
    session.add(audit)

    return DocumentCorrectionResponse(
        correction_saved=True,
        job_id=job_id,
        field_name=request.field_name,
        original_value=original_value,
        corrected_value=request.corrected_value,
    )


@router.get("/", response_model=list[DocumentJobResponse])
async def list_document_jobs(
    status: str | None = None,
    limit: int = 20,
    page: int = 1,
    session: Session = Depends(get_db),
):
    """List document processing jobs with optional status filter."""
    query = session.query(DocumentProcessingJob)

    if status:
        query = query.filter(DocumentProcessingJob.status == status)

    jobs = (
        query.order_by(DocumentProcessingJob.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    results = []
    for job in jobs:
        extraction = None
        if job.extraction_result:
            extraction = DocumentExtractionResult(**job.extraction_result)

        results.append(
            DocumentJobResponse(
                job_id=job.id,
                file_name=job.file_name or "",
                document_type=job.document_type or "",
                status=job.status or "unknown",
                extraction=extraction,
                confidence=float(job.overall_confidence or 0),
                field_confidences=job.field_confidences or {},
                matched_vendor_id=job.matched_vendor_id,
                matched_po_id=job.matched_po_id,
                odoo_record_created=job.odoo_record_created,
                error_message=job.error_message,
                processing_time_ms=job.processing_time_ms,
                created_at=job.created_at,
            )
        )

    return results
