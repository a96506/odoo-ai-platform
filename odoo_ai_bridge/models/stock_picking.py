from odoo import models


class StockPicking(models.Model):
    _name = "stock.picking"
    _inherit = ["stock.picking", "ai.webhook.mixin"]
    _ai_module_toggle = "enable_inventory"
    _ai_webhook_fields = [
        "name",
        "partner_id",
        "picking_type_id",
        "location_id",
        "location_dest_id",
        "state",
        "scheduled_date",
        "origin",
    ]


class ProductProduct(models.Model):
    _name = "product.product"
    _inherit = ["product.product", "ai.webhook.mixin"]
    _ai_module_toggle = "enable_inventory"
    _ai_webhook_fields = [
        "name",
        "default_code",
        "type",
        "categ_id",
        "list_price",
        "standard_price",
        "qty_available",
        "virtual_available",
    ]
