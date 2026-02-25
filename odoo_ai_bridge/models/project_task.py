from odoo import models


class ProjectTask(models.Model):
    _name = "project.task"
    _inherit = ["project.task", "ai.webhook.mixin"]
    _ai_module_toggle = "enable_project"
    _ai_webhook_fields = [
        "name",
        "project_id",
        "user_ids",
        "stage_id",
        "priority",
        "date_deadline",
        "description",
        "tag_ids",
        "parent_id",
    ]
