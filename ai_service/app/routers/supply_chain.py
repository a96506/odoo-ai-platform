"""
Supply Chain Intelligence API endpoints.

GET  /api/supply-chain/risk-scores         — list vendor risk scores
GET  /api/supply-chain/risk-scores/{id}    — get specific vendor risk score with factors
GET  /api/supply-chain/predictions         — list active disruption predictions
GET  /api/supply-chain/alerts              — list active supply chain alerts
POST /api/supply-chain/alerts/{id}/resolve — resolve an alert
GET  /api/supply-chain/single-source       — list single-source risks
POST /api/supply-chain/scan               — trigger a risk scoring scan
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Any

from app.auth import require_api_key
from app.models.audit import (
    SupplierRiskScore,
    SupplierRiskFactor,
    DisruptionPrediction,
    SupplyChainAlert,
    get_db,
)

router = APIRouter(
    prefix="/api/supply-chain",
    tags=["supply-chain"],
    dependencies=[Depends(require_api_key)],
)


@router.get("/risk-scores")
def list_risk_scores(
    db: Session = Depends(get_db),
    classification: str | None = None,
    limit: int = Query(default=50, le=200),
):
    query = db.query(SupplierRiskScore).order_by(SupplierRiskScore.scored_at.desc())

    if classification:
        query = query.filter(SupplierRiskScore.classification == classification)

    scores = query.limit(limit).all()
    return [
        {
            "id": s.id,
            "vendor_id": s.vendor_id,
            "vendor_name": s.vendor_name,
            "score": float(s.score) if s.score else None,
            "previous_score": float(s.previous_score) if s.previous_score else None,
            "classification": s.classification.value if s.classification else None,
            "scored_at": s.scored_at.isoformat() if s.scored_at else None,
        }
        for s in scores
    ]


@router.get("/risk-scores/{vendor_id}")
def get_vendor_risk(vendor_id: int, db: Session = Depends(get_db), history: int = Query(default=1, le=30)):
    scores = (
        db.query(SupplierRiskScore)
        .filter(SupplierRiskScore.vendor_id == vendor_id)
        .order_by(SupplierRiskScore.scored_at.desc())
        .limit(history)
        .all()
    )

    if not scores:
        raise HTTPException(status_code=404, detail="No risk scores for this vendor")

    return {
        "vendor_id": vendor_id,
        "current": {
            "score": float(scores[0].score) if scores[0].score else None,
            "classification": scores[0].classification.value if scores[0].classification else None,
            "scored_at": scores[0].scored_at.isoformat() if scores[0].scored_at else None,
        },
        "history": [
            {
                "score": float(s.score) if s.score else None,
                "classification": s.classification.value if s.classification else None,
                "scored_at": s.scored_at.isoformat() if s.scored_at else None,
            }
            for s in scores[1:]
        ],
    }


@router.get("/predictions")
def list_predictions(db: Session = Depends(get_db), active_only: bool = True, limit: int = Query(default=20, le=100)):
    query = db.query(DisruptionPrediction).order_by(DisruptionPrediction.created_at.desc())

    if active_only:
        query = query.filter(DisruptionPrediction.resolved_at.is_(None))

    predictions = query.limit(limit).all()
    return [
        {
            "id": p.id,
            "vendor_id": p.vendor_id,
            "prediction_type": p.prediction_type,
            "probability": float(p.probability) if p.probability else None,
            "estimated_impact": p.estimated_impact,
            "recommended_actions": p.recommended_actions,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "resolved_at": p.resolved_at.isoformat() if p.resolved_at else None,
        }
        for p in predictions
    ]


@router.get("/alerts")
def list_alerts(
    db: Session = Depends(get_db),
    severity: str | None = None,
    alert_type: str | None = None,
    resolved: bool = False,
    limit: int = Query(default=50, le=200),
):
    query = db.query(SupplyChainAlert).order_by(SupplyChainAlert.created_at.desc())

    if severity:
        query = query.filter(SupplyChainAlert.severity == severity)
    if alert_type:
        query = query.filter(SupplyChainAlert.alert_type == alert_type)
    if not resolved:
        query = query.filter(SupplyChainAlert.resolved_at.is_(None))

    alerts = query.limit(limit).all()
    return [
        {
            "id": a.id,
            "vendor_id": a.vendor_id,
            "alert_type": a.alert_type,
            "severity": a.severity.value if a.severity else None,
            "title": a.title,
            "message": a.message,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
        }
        for a in alerts
    ]


@router.post("/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: int, db: Session = Depends(get_db)):
    from datetime import datetime

    alert = db.get(SupplyChainAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.resolved_at:
        raise HTTPException(status_code=400, detail="Alert already resolved")

    alert.resolved_at = datetime.utcnow()
    db.flush()
    return {"status": "resolved", "alert_id": alert_id}


@router.get("/single-source")
def list_single_source_risks(db: Session = Depends(get_db), limit: int = Query(default=50, le=200)):
    alerts = (
        db.query(SupplyChainAlert)
        .filter(
            SupplyChainAlert.alert_type == "single_source_risk",
            SupplyChainAlert.resolved_at.is_(None),
        )
        .order_by(SupplyChainAlert.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": a.id,
            "vendor_id": a.vendor_id,
            "title": a.title,
            "message": a.message,
            "severity": a.severity.value if a.severity else None,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in alerts
    ]


@router.post("/scan")
def trigger_risk_scan():
    """Manually trigger a supplier risk scoring run."""
    from app.tasks.celery_tasks import run_supplier_risk_scoring
    run_supplier_risk_scoring.delay()
    return {"status": "scan_queued"}
