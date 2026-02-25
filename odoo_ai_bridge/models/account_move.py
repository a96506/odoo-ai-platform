from odoo import models


class AccountMove(models.Model):
    _name = "account.move"
    _inherit = ["account.move", "ai.webhook.mixin"]
    _ai_module_toggle = "enable_accounting"
    _ai_webhook_fields = [
        "name",
        "move_type",
        "partner_id",
        "amount_total",
        "amount_residual",
        "state",
        "payment_state",
        "invoice_date",
        "invoice_date_due",
        "journal_id",
        "currency_id",
        "ref",
    ]


class AccountBankStatementLine(models.Model):
    _name = "account.bank.statement.line"
    _inherit = ["account.bank.statement.line", "ai.webhook.mixin"]
    _ai_module_toggle = "enable_accounting"
    _ai_webhook_fields = [
        "date",
        "payment_ref",
        "partner_id",
        "amount",
        "journal_id",
        "narration",
    ]
