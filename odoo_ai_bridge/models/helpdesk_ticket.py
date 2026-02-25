from odoo import models


class HelpdeskTicket(models.Model):
    _name = "helpdesk.ticket"
    _inherit = ["helpdesk.ticket", "ai.webhook.mixin"]
    _ai_module_toggle = "enable_helpdesk"
    _ai_webhook_fields = [
        "name",
        "partner_id",
        "partner_email",
        "user_id",
        "team_id",
        "stage_id",
        "priority",
        "description",
        "tag_ids",
        "channel_id",
        "sla_deadline",
    ]
