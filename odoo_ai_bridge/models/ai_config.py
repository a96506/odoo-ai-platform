from odoo import models, fields, api


class AiConfig(models.Model):
    _name = "ai.config"
    _description = "AI Platform Configuration"

    name = fields.Char(default="AI Configuration", readonly=True)
    ai_service_url = fields.Char(
        string="AI Service URL",
        default="http://ai-service:8000",
        required=True,
    )
    webhook_secret = fields.Char(
        string="Webhook Secret",
        default="change-me-webhook-secret",
    )
    enabled = fields.Boolean(string="Enable AI Webhooks", default=True)
    log_webhooks = fields.Boolean(string="Log Webhook Calls", default=True)

    # Per-model toggles
    enable_accounting = fields.Boolean(string="Accounting", default=True)
    enable_crm = fields.Boolean(string="CRM", default=True)
    enable_sales = fields.Boolean(string="Sales", default=True)
    enable_purchase = fields.Boolean(string="Purchase", default=True)
    enable_inventory = fields.Boolean(string="Inventory", default=True)
    enable_hr = fields.Boolean(string="HR", default=True)
    enable_project = fields.Boolean(string="Project", default=True)
    enable_helpdesk = fields.Boolean(string="Helpdesk", default=True)
    enable_manufacturing = fields.Boolean(string="Manufacturing", default=True)
    enable_marketing = fields.Boolean(string="Marketing", default=True)

    @api.model
    def get_config(self):
        config = self.search([], limit=1)
        if not config:
            config = self.create({"name": "AI Configuration"})
        return config
