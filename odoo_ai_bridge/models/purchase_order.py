from odoo import models


class PurchaseOrder(models.Model):
    _name = "purchase.order"
    _inherit = ["purchase.order", "ai.webhook.mixin"]
    _ai_module_toggle = "enable_purchase"
    _ai_webhook_fields = [
        "name",
        "partner_id",
        "user_id",
        "amount_total",
        "amount_untaxed",
        "state",
        "date_order",
        "date_planned",
        "currency_id",
        "notes",
    ]
