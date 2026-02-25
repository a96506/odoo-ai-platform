from odoo import models


class MrpProduction(models.Model):
    _name = "mrp.production"
    _inherit = ["mrp.production", "ai.webhook.mixin"]
    _ai_module_toggle = "enable_manufacturing"
    _ai_webhook_fields = [
        "name",
        "product_id",
        "product_qty",
        "qty_produced",
        "bom_id",
        "date_start",
        "date_finished",
        "state",
        "priority",
    ]
