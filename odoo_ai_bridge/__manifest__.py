{
    "name": "AI Bridge",
    "version": "18.0.1.0.0",
    "category": "Technical",
    "summary": "Bridges Odoo with the AI Automation Platform via webhooks",
    "description": """
        Sends webhook notifications to the AI Service on record
        create/update/delete for all essential business models.
        Provides callback endpoints for the AI to act on Odoo data.
    """,
    "author": "Odoo AI Platform",
    "depends": [
        "base",
        "mail",
        "crm",
        "sale_management",
        "purchase",
        "account",
        "stock",
        "hr",
        "hr_holidays",
        "hr_expense",
        "project",
        "helpdesk",
        "mrp",
        "mass_mailing",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/ai_config_data.xml",
        "views/ai_config_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "license": "LGPL-3",
}
