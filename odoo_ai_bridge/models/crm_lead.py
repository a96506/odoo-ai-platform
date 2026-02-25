from odoo import models


class CrmLead(models.Model):
    _name = "crm.lead"
    _inherit = ["crm.lead", "ai.webhook.mixin"]
    _ai_module_toggle = "enable_crm"
    _ai_webhook_fields = [
        "name",
        "partner_id",
        "partner_name",
        "email_from",
        "phone",
        "stage_id",
        "user_id",
        "team_id",
        "expected_revenue",
        "probability",
        "priority",
        "type",
        "source_id",
        "medium_id",
        "campaign_id",
        "city",
        "country_id",
        "description",
        "tag_ids",
    ]
