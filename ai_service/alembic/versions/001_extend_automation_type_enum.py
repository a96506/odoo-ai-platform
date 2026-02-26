"""Extend AutomationType enum with Phase 1 categories.

Revision ID: 001_extend_enum
Revises: None
Create Date: 2026-02-26
"""

from alembic import op

revision = "001_extend_enum"
down_revision = None
branch_labels = None
depends_on = None

NEW_VALUES = [
    "month_end",
    "deduplication",
    "credit_management",
    "forecasting",
    "reporting",
    "document_processing",
]


def upgrade() -> None:
    for value in NEW_VALUES:
        op.execute(f"ALTER TYPE automationtype ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    pass
