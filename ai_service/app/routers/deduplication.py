"""Cross-Entity Deduplication API endpoints."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.models.audit import (
    DeduplicationScan,
    DuplicateGroup,
    AuditLog,
    ActionStatus,
    AutomationType,
    get_db,
)
from app.models.schemas import (
    DedupScanRequest,
    DedupScanResponse,
    DedupFullScanResponse,
    DedupGroupResponse,
    DedupCheckRequest,
    DedupCheckResponse,
    DedupMergeRequest,
    DedupMergeResponse,
)
from app.automations.deduplication import DeduplicationAutomation

router = APIRouter(
    prefix="/api/dedup",
    tags=["deduplication"],
    dependencies=[Depends(require_api_key)],
)


@router.post("/scan", response_model=DedupScanResponse)
async def run_dedup_scan(
    request: DedupScanRequest,
    session: Session = Depends(get_db),
):
    """Run a deduplication scan for a specific entity type."""
    dedup = DeduplicationAutomation()
    result = dedup.run_scan(request.scan_type)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    scan = DeduplicationScan(
        scan_type=request.scan_type,
        status="completed",
        total_records=result["total_records"],
        duplicates_found=result["duplicates_found"],
        pending_review=len(result["groups"]),
        completed_at=datetime.utcnow(),
    )
    session.add(scan)
    session.flush()

    group_responses = []
    for g in result["groups"]:
        db_group = DuplicateGroup(
            scan_id=scan.id,
            odoo_model=g["odoo_model"],
            record_ids=g["record_ids"],
            master_record_id=g["master_record_id"],
            similarity_score=g["similarity_score"],
            match_fields=g["match_fields"],
            status="pending",
        )
        session.add(db_group)
        session.flush()

        group_responses.append(DedupGroupResponse(
            id=db_group.id,
            odoo_model=g["odoo_model"],
            record_ids=g["record_ids"],
            master_record_id=g["master_record_id"],
            similarity_score=g["similarity_score"],
            match_fields=g["match_fields"],
            status="pending",
            records=g.get("records", []),
        ))

    audit = AuditLog(
        automation_type=AutomationType.DEDUPLICATION,
        action_name="dedup_scan",
        odoo_model=request.scan_type,
        odoo_record_id=0,
        status=ActionStatus.EXECUTED,
        confidence=0.0,
        ai_reasoning=f"Dedup scan: {result['total_records']} records, {result['duplicates_found']} duplicates in {len(result['groups'])} groups",
        output_data={
            "total_records": result["total_records"],
            "duplicates_found": result["duplicates_found"],
            "groups": len(result["groups"]),
        },
        executed_at=datetime.utcnow(),
    )
    session.add(audit)

    return DedupScanResponse(
        scan_id=scan.id,
        scan_type=request.scan_type,
        status="completed",
        total_records=result["total_records"],
        duplicates_found=result["duplicates_found"],
        groups=group_responses,
    )


@router.post("/scan/all", response_model=DedupFullScanResponse)
async def run_full_dedup_scan(
    session: Session = Depends(get_db),
):
    """Run deduplication scans across all entity types."""
    dedup = DeduplicationAutomation()
    result = dedup.run_full_scan()

    entity_responses = {}
    for scan_type, scan_result in result["entity_results"].items():
        scan = DeduplicationScan(
            scan_type=scan_type,
            status="completed",
            total_records=scan_result["total_records"],
            duplicates_found=scan_result["duplicates_found"],
            pending_review=len(scan_result["groups"]),
            completed_at=datetime.utcnow(),
        )
        session.add(scan)
        session.flush()

        group_responses = []
        for g in scan_result["groups"]:
            db_group = DuplicateGroup(
                scan_id=scan.id,
                odoo_model=g["odoo_model"],
                record_ids=g["record_ids"],
                master_record_id=g["master_record_id"],
                similarity_score=g["similarity_score"],
                match_fields=g["match_fields"],
                status="pending",
            )
            session.add(db_group)
            session.flush()

            group_responses.append(DedupGroupResponse(
                id=db_group.id,
                odoo_model=g["odoo_model"],
                record_ids=g["record_ids"],
                master_record_id=g["master_record_id"],
                similarity_score=g["similarity_score"],
                match_fields=g["match_fields"],
                status="pending",
            ))

        entity_responses[scan_type] = DedupScanResponse(
            scan_id=scan.id,
            scan_type=scan_type,
            status="completed",
            total_records=scan_result["total_records"],
            duplicates_found=scan_result["duplicates_found"],
            groups=group_responses,
        )

    return DedupFullScanResponse(
        entity_results=entity_responses,
        total_groups=result["total_groups"],
        total_duplicates=result["total_duplicates"],
    )


@router.get("/scans", response_model=list[DedupScanResponse])
async def list_scans(
    limit: int = 20,
    session: Session = Depends(get_db),
):
    """List recent deduplication scans."""
    scans = (
        session.query(DeduplicationScan)
        .order_by(DeduplicationScan.started_at.desc())
        .limit(limit)
        .all()
    )

    results = []
    for scan in scans:
        groups = (
            session.query(DuplicateGroup)
            .filter(DuplicateGroup.scan_id == scan.id)
            .all()
        )
        results.append(DedupScanResponse(
            scan_id=scan.id,
            scan_type=scan.scan_type,
            status=scan.status,
            total_records=scan.total_records,
            duplicates_found=scan.duplicates_found,
            groups=[
                DedupGroupResponse(
                    id=g.id,
                    odoo_model=g.odoo_model,
                    record_ids=g.record_ids,
                    master_record_id=g.master_record_id,
                    similarity_score=float(g.similarity_score or 0),
                    match_fields=g.match_fields or [],
                    status=g.status,
                )
                for g in groups
            ],
        ))

    return results


@router.get("/groups/{group_id}", response_model=DedupGroupResponse)
async def get_group(
    group_id: int,
    session: Session = Depends(get_db),
):
    """Get a specific duplicate group with record details."""
    group = session.get(DuplicateGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Duplicate group not found")

    return DedupGroupResponse(
        id=group.id,
        odoo_model=group.odoo_model,
        record_ids=group.record_ids,
        master_record_id=group.master_record_id,
        similarity_score=float(group.similarity_score or 0),
        match_fields=group.match_fields or [],
        status=group.status,
    )


@router.post("/groups/{group_id}/merge", response_model=DedupMergeResponse)
async def merge_group(
    group_id: int,
    request: DedupMergeRequest,
    session: Session = Depends(get_db),
):
    """Approve and merge a duplicate group, keeping the master record."""
    group = session.get(DuplicateGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Duplicate group not found")
    if group.status != "pending":
        raise HTTPException(status_code=400, detail=f"Group already {group.status}")

    if request.master_record_id not in (group.record_ids or []):
        raise HTTPException(status_code=400, detail="Master record not in group")

    group.master_record_id = request.master_record_id
    group.status = "merged"
    group.resolved_at = datetime.utcnow()
    group.resolved_by = request.merged_by
    group.resolution = "merged"

    merged_ids = [rid for rid in group.record_ids if rid != request.master_record_id]

    scan = session.get(DeduplicationScan, group.scan_id)
    if scan:
        scan.auto_merged = (scan.auto_merged or 0) + 1
        scan.pending_review = max(0, (scan.pending_review or 0) - 1)

    audit = AuditLog(
        automation_type=AutomationType.DEDUPLICATION,
        action_name="dedup_merge",
        odoo_model=group.odoo_model,
        odoo_record_id=request.master_record_id,
        status=ActionStatus.EXECUTED,
        confidence=float(group.similarity_score or 0),
        ai_reasoning=f"Merged {len(merged_ids)} records into master #{request.master_record_id}",
        output_data={
            "master_record_id": request.master_record_id,
            "merged_record_ids": merged_ids,
        },
        executed_at=datetime.utcnow(),
        approved_by=request.merged_by,
    )
    session.add(audit)

    return DedupMergeResponse(
        merged=True,
        group_id=group_id,
        master_record_id=request.master_record_id,
        merged_record_ids=merged_ids,
    )


@router.post("/groups/{group_id}/dismiss")
async def dismiss_group(
    group_id: int,
    session: Session = Depends(get_db),
):
    """Dismiss a duplicate group (mark as not duplicates)."""
    group = session.get(DuplicateGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Duplicate group not found")

    group.status = "dismissed"
    group.resolved_at = datetime.utcnow()
    group.resolution = "dismissed"

    scan = session.get(DeduplicationScan, group.scan_id)
    if scan:
        scan.pending_review = max(0, (scan.pending_review or 0) - 1)

    return {"dismissed": True, "group_id": group_id}


@router.post("/check", response_model=DedupCheckResponse)
async def check_duplicates(
    request: DedupCheckRequest,
    session: Session = Depends(get_db),
):
    """Real-time duplicate check for a record being created."""
    dedup = DeduplicationAutomation()
    matches = dedup.check_duplicate_on_create(request.model, request.values)

    return DedupCheckResponse(
        has_duplicates=len(matches) > 0,
        matches=matches,
    )
