from odoo import models


class MailingMailing(models.Model):
    _name = "mailing.mailing"
    _inherit = ["mailing.mailing", "ai.webhook.mixin"]
    _ai_module_toggle = "enable_marketing"
    _ai_webhook_fields = [
        "subject",
        "mailing_model_id",
        "state",
        "sent",
        "opened",
        "clicked",
        "replied",
        "bounced",
        "schedule_date",
        "body_html",
    ]
