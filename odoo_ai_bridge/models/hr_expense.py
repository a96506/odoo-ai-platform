from odoo import models


class HrExpense(models.Model):
    _name = "hr.expense"
    _inherit = ["hr.expense", "ai.webhook.mixin"]
    _ai_module_toggle = "enable_hr"
    _ai_webhook_fields = [
        "name",
        "employee_id",
        "product_id",
        "total_amount",
        "currency_id",
        "date",
        "state",
        "description",
        "reference",
    ]
