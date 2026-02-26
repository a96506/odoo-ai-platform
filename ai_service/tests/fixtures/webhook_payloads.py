"""
Webhook payload fixtures for all 11 Odoo models handled by the AI Bridge module.
Each fixture returns a dict matching the WebhookPayload schema.
"""


def account_move_create() -> dict:
    return {
        "event_type": "create",
        "model": "account.move",
        "record_id": 101,
        "values": {
            "name": "INV/2026/0042",
            "partner_id": 10,
            "move_type": "out_invoice",
            "amount_total": 5400.00,
            "state": "draft",
            "invoice_date": "2026-02-26",
            "currency_id": 1,
            "journal_id": 1,
        },
        "old_values": {},
        "timestamp": "2026-02-26T10:00:00",
        "user_id": 2,
    }


def account_move_write() -> dict:
    return {
        "event_type": "write",
        "model": "account.move",
        "record_id": 101,
        "values": {"state": "posted"},
        "old_values": {"state": "draft"},
        "timestamp": "2026-02-26T10:05:00",
        "user_id": 2,
    }


def crm_lead_create() -> dict:
    return {
        "event_type": "create",
        "model": "crm.lead",
        "record_id": 201,
        "values": {
            "name": "New opportunity from Website",
            "partner_name": "Acme Corp",
            "email_from": "contact@acme.com",
            "phone": "+1-555-0100",
            "expected_revenue": 25000.00,
            "stage_id": 1,
            "team_id": 1,
            "type": "opportunity",
        },
        "old_values": {},
        "timestamp": "2026-02-26T09:00:00",
        "user_id": 2,
    }


def crm_lead_write() -> dict:
    return {
        "event_type": "write",
        "model": "crm.lead",
        "record_id": 201,
        "values": {"stage_id": 3, "probability": 60.0},
        "old_values": {"stage_id": 1, "probability": 10.0},
        "timestamp": "2026-02-26T11:00:00",
        "user_id": 2,
    }


def sale_order_create() -> dict:
    return {
        "event_type": "create",
        "model": "sale.order",
        "record_id": 301,
        "values": {
            "name": "SO042",
            "partner_id": 10,
            "amount_total": 12000.00,
            "state": "draft",
            "date_order": "2026-02-26",
            "pricelist_id": 1,
        },
        "old_values": {},
        "timestamp": "2026-02-26T08:30:00",
        "user_id": 2,
    }


def purchase_order_create() -> dict:
    return {
        "event_type": "create",
        "model": "purchase.order",
        "record_id": 401,
        "values": {
            "name": "PO042",
            "partner_id": 20,
            "amount_total": 8500.00,
            "state": "draft",
            "date_order": "2026-02-26",
        },
        "old_values": {},
        "timestamp": "2026-02-26T08:45:00",
        "user_id": 2,
    }


def stock_picking_write() -> dict:
    return {
        "event_type": "write",
        "model": "stock.picking",
        "record_id": 501,
        "values": {"state": "done"},
        "old_values": {"state": "assigned"},
        "timestamp": "2026-02-26T14:00:00",
        "user_id": 2,
    }


def hr_leave_create() -> dict:
    return {
        "event_type": "create",
        "model": "hr.leave",
        "record_id": 601,
        "values": {
            "employee_id": 5,
            "holiday_status_id": 1,
            "date_from": "2026-03-01",
            "date_to": "2026-03-03",
            "number_of_days": 3,
            "state": "confirm",
        },
        "old_values": {},
        "timestamp": "2026-02-26T09:30:00",
        "user_id": 5,
    }


def hr_expense_create() -> dict:
    return {
        "event_type": "create",
        "model": "hr.expense",
        "record_id": 701,
        "values": {
            "name": "Client dinner",
            "employee_id": 5,
            "total_amount": 185.00,
            "product_id": 100,
            "date": "2026-02-25",
            "state": "draft",
        },
        "old_values": {},
        "timestamp": "2026-02-26T10:15:00",
        "user_id": 5,
    }


def project_task_create() -> dict:
    return {
        "event_type": "create",
        "model": "project.task",
        "record_id": 801,
        "values": {
            "name": "Implement payment gateway",
            "project_id": 3,
            "stage_id": 1,
            "user_ids": [5],
            "date_deadline": "2026-03-15",
            "priority": "1",
        },
        "old_values": {},
        "timestamp": "2026-02-26T10:30:00",
        "user_id": 2,
    }


def helpdesk_ticket_create() -> dict:
    return {
        "event_type": "create",
        "model": "helpdesk.ticket",
        "record_id": 901,
        "values": {
            "name": "Cannot login to portal",
            "partner_id": 10,
            "team_id": 1,
            "description": "User reports 500 error on portal login page.",
            "priority": "2",
        },
        "old_values": {},
        "timestamp": "2026-02-26T11:30:00",
        "user_id": 2,
    }


def mrp_production_create() -> dict:
    return {
        "event_type": "create",
        "model": "mrp.production",
        "record_id": 1001,
        "values": {
            "name": "MO/00042",
            "product_id": 50,
            "product_qty": 100,
            "bom_id": 5,
            "state": "confirmed",
            "date_start": "2026-03-01",
        },
        "old_values": {},
        "timestamp": "2026-02-26T07:00:00",
        "user_id": 2,
    }


def mailing_mailing_write() -> dict:
    return {
        "event_type": "write",
        "model": "mailing.mailing",
        "record_id": 1101,
        "values": {"state": "done", "sent": 1500, "opened": 450},
        "old_values": {"state": "sending"},
        "timestamp": "2026-02-26T16:00:00",
        "user_id": 2,
    }


ALL_FIXTURES = {
    "account.move_create": account_move_create,
    "account.move_write": account_move_write,
    "crm.lead_create": crm_lead_create,
    "crm.lead_write": crm_lead_write,
    "sale.order_create": sale_order_create,
    "purchase.order_create": purchase_order_create,
    "stock.picking_write": stock_picking_write,
    "hr.leave_create": hr_leave_create,
    "hr.expense_create": hr_expense_create,
    "project.task_create": project_task_create,
    "helpdesk.ticket_create": helpdesk_ticket_create,
    "mrp.production_create": mrp_production_create,
    "mailing.mailing_write": mailing_mailing_write,
}
