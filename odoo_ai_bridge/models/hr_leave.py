from odoo import models


class HrLeave(models.Model):
    _name = "hr.leave"
    _inherit = ["hr.leave", "ai.webhook.mixin"]
    _ai_module_toggle = "enable_hr"
    _ai_webhook_fields = [
        "employee_id",
        "holiday_status_id",
        "date_from",
        "date_to",
        "number_of_days",
        "state",
        "name",
    ]
