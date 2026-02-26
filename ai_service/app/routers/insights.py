"""Cross-app intelligence and manual trigger endpoints."""

from fastapi import APIRouter, Depends

from app.auth import require_api_key
from app.automations.cross_app import CrossAppIntelligence

router = APIRouter(
    prefix="/api",
    tags=["insights"],
    dependencies=[Depends(require_api_key)],
)


@router.get("/insights")
async def get_cross_app_insights():
    """Run cross-module intelligence analysis and return insights."""
    intelligence = CrossAppIntelligence()
    result = intelligence.run_full_analysis()
    return result


@router.post("/trigger/{automation_type}/{action}")
async def trigger_automation(
    automation_type: str, action: str, model: str, record_id: int
):
    """Manually trigger an automation action on a specific record."""
    from app.tasks.celery_tasks import run_automation

    run_automation.delay(automation_type, action, record_id, model)
    return {"status": "queued", "automation_type": automation_type, "action": action}
