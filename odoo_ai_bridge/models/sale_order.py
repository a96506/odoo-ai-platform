from odoo import models


class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ["sale.order", "ai.webhook.mixin"]
    _ai_module_toggle = "enable_sales"
    _ai_webhook_fields = [
        "name",
        "partner_id",
        "user_id",
        "team_id",
        "amount_total",
        "amount_untaxed",
        "state",
        "date_order",
        "validity_date",
        "pricelist_id",
        "currency_id",
        "note",
    ]
