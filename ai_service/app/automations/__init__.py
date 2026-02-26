"""
Automation registry — maps Odoo models to their automation handlers.
"""

from app.automations.base import BaseAutomation

_MODEL_REGISTRY: dict[str, BaseAutomation] = {}
_TYPE_REGISTRY: dict[str, BaseAutomation] = {}


def register_automation(handler: BaseAutomation):
    for model in handler.watched_models:
        _MODEL_REGISTRY[model] = handler
    _TYPE_REGISTRY[handler.automation_type] = handler


def get_automation_handler(odoo_model: str) -> BaseAutomation | None:
    return _MODEL_REGISTRY.get(odoo_model)


def get_automation_handler_by_type(automation_type: str) -> BaseAutomation | None:
    return _TYPE_REGISTRY.get(automation_type)


def init_automations():
    """Initialize and register all automation handlers."""
    from app.automations.accounting import AccountingAutomation
    from app.automations.crm import CRMAutomation
    from app.automations.sales import SalesAutomation
    from app.automations.purchase import PurchaseAutomation
    from app.automations.inventory import InventoryAutomation
    from app.automations.hr import HRAutomation
    from app.automations.project import ProjectAutomation
    from app.automations.helpdesk import HelpdeskAutomation
    from app.automations.manufacturing import ManufacturingAutomation
    from app.automations.marketing import MarketingAutomation
    from app.automations.month_end import MonthEndClosingAutomation
    from app.automations.deduplication import DeduplicationAutomation
    from app.automations.credit import CreditManagementAutomation
    from app.automations.document_processing import DocumentProcessingAutomation
    from app.automations.daily_digest import DailyDigestAutomation
    from app.automations.cash_flow import CashFlowForecastingAutomation
    from app.automations.report_builder import ReportBuilderAutomation

    handlers = [
        AccountingAutomation(),
        CRMAutomation(),
        SalesAutomation(),
        PurchaseAutomation(),
        InventoryAutomation(),
        HRAutomation(),
        ProjectAutomation(),
        HelpdeskAutomation(),
        ManufacturingAutomation(),
        MarketingAutomation(),
        MonthEndClosingAutomation(),
        DeduplicationAutomation(),
        CreditManagementAutomation(),
        DocumentProcessingAutomation(),
        DailyDigestAutomation(),
        CashFlowForecastingAutomation(),
        ReportBuilderAutomation(),
    ]
    for handler in handlers:
        register_automation(handler)
