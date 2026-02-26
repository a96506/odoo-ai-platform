"""Automation rules CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.models.audit import AutomationRule, get_db
from app.models.schemas import AutomationRuleCreate, AutomationRuleResponse

router = APIRouter(
    prefix="/api",
    tags=["rules"],
    dependencies=[Depends(require_api_key)],
)


@router.get("/rules", response_model=list[AutomationRuleResponse])
async def list_rules(session: Session = Depends(get_db)):
    rules = session.query(AutomationRule).all()
    return [AutomationRuleResponse.model_validate(r) for r in rules]


@router.post("/rules", response_model=AutomationRuleResponse)
async def create_rule(
    rule: AutomationRuleCreate,
    session: Session = Depends(get_db),
):
    db_rule = AutomationRule(**rule.model_dump())
    session.add(db_rule)
    session.flush()
    session.refresh(db_rule)
    return AutomationRuleResponse.model_validate(db_rule)


@router.put("/rules/{rule_id}", response_model=AutomationRuleResponse)
async def update_rule(
    rule_id: int,
    rule: AutomationRuleCreate,
    session: Session = Depends(get_db),
):
    db_rule = session.get(AutomationRule, rule_id)
    if not db_rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    for key, value in rule.model_dump().items():
        setattr(db_rule, key, value)
    session.flush()
    session.refresh(db_rule)
    return AutomationRuleResponse.model_validate(db_rule)


@router.delete("/rules/{rule_id}")
async def delete_rule(
    rule_id: int,
    session: Session = Depends(get_db),
):
    db_rule = session.get(AutomationRule, rule_id)
    if not db_rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    session.delete(db_rule)
    return {"status": "deleted"}
