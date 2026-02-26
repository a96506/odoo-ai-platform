"""Add all Phase 1 tables: month-end closing, reconciliation,
document processing, deduplication, credit scores, report jobs,
cash forecasts, and daily digests.

Revision ID: 002_phase1_tables
Revises: 001_extend_enum
Create Date: 2026-02-26
"""

from alembic import op
import sqlalchemy as sa

revision = "002_phase1_tables"
down_revision = "001_extend_enum"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- 1.1 Month-End Closing --
    op.create_table(
        "month_end_closings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("status", sa.String(20), server_default="in_progress"),
        sa.Column("started_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime),
        sa.Column("started_by", sa.String(255)),
        sa.Column("checklist", sa.JSON, server_default="{}"),
        sa.Column("issues_found", sa.JSON, server_default="[]"),
        sa.Column("summary", sa.Text),
        sa.Column("lock_date_set", sa.Boolean, server_default="false"),
    )
    op.create_index("uq_month_end_period", "month_end_closings", ["period"], unique=True)

    op.create_table(
        "closing_steps",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("closing_id", sa.Integer, sa.ForeignKey("month_end_closings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_name", sa.String(100), nullable=False),
        sa.Column("step_order", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("auto_check_result", sa.JSON),
        sa.Column("items_found", sa.Integer, server_default="0"),
        sa.Column("items_resolved", sa.Integer, server_default="0"),
        sa.Column("started_at", sa.DateTime),
        sa.Column("completed_at", sa.DateTime),
        sa.Column("completed_by", sa.String(255)),
        sa.Column("notes", sa.Text),
    )
    op.create_index("idx_closing_steps_closing", "closing_steps", ["closing_id"])

    # -- 1.3 Reconciliation Sessions --
    op.create_table(
        "reconciliation_sessions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(255)),
        sa.Column("journal_id", sa.Integer),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.Column("total_lines", sa.Integer, server_default="0"),
        sa.Column("auto_matched", sa.Integer, server_default="0"),
        sa.Column("manually_matched", sa.Integer, server_default="0"),
        sa.Column("skipped", sa.Integer, server_default="0"),
        sa.Column("remaining", sa.Integer, server_default="0"),
        sa.Column("learned_rules", sa.JSON, server_default="[]"),
        sa.Column("started_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("last_activity", sa.DateTime, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime),
    )
    op.create_index("idx_recon_sessions_status", "reconciliation_sessions", ["status"])
    op.create_index("idx_recon_sessions_user", "reconciliation_sessions", ["user_id"])

    # -- 1.4 Document Processing --
    op.create_table(
        "document_processing_jobs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("file_name", sa.String(500)),
        sa.Column("file_type", sa.String(20)),
        sa.Column("document_type", sa.String(50)),
        sa.Column("status", sa.String(20), server_default="queued"),
        sa.Column("source", sa.String(50), server_default="upload"),
        sa.Column("uploaded_by", sa.String(255)),
        sa.Column("extraction_result", sa.JSON),
        sa.Column("matched_po_id", sa.Integer),
        sa.Column("matched_vendor_id", sa.Integer),
        sa.Column("overall_confidence", sa.Numeric(5, 4)),
        sa.Column("field_confidences", sa.JSON, server_default="{}"),
        sa.Column("odoo_record_created", sa.Integer),
        sa.Column("odoo_model_created", sa.String(255)),
        sa.Column("error_message", sa.Text),
        sa.Column("processing_time_ms", sa.Integer),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime),
    )
    op.create_index("idx_doc_jobs_status", "document_processing_jobs", ["status"])
    op.create_index("idx_doc_jobs_type", "document_processing_jobs", ["document_type"])

    op.create_table(
        "extraction_corrections",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.Integer, sa.ForeignKey("document_processing_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("field_name", sa.String(100), nullable=False),
        sa.Column("original_value", sa.Text),
        sa.Column("corrected_value", sa.Text),
        sa.Column("corrected_by", sa.String(255)),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_corrections_job", "extraction_corrections", ["job_id"])

    # -- 1.5 Deduplication --
    op.create_table(
        "deduplication_scans",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("scan_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), server_default="running"),
        sa.Column("total_records", sa.Integer, server_default="0"),
        sa.Column("duplicates_found", sa.Integer, server_default="0"),
        sa.Column("auto_merged", sa.Integer, server_default="0"),
        sa.Column("pending_review", sa.Integer, server_default="0"),
        sa.Column("started_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime),
    )
    op.create_index("idx_dedup_scans_type", "deduplication_scans", ["scan_type"])

    op.create_table(
        "duplicate_groups",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("scan_id", sa.Integer, sa.ForeignKey("deduplication_scans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("odoo_model", sa.String(255), nullable=False),
        sa.Column("record_ids", sa.JSON, nullable=False),
        sa.Column("master_record_id", sa.Integer),
        sa.Column("similarity_score", sa.Numeric(5, 4)),
        sa.Column("match_fields", sa.JSON, server_default="[]"),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("resolved_at", sa.DateTime),
        sa.Column("resolved_by", sa.String(255)),
        sa.Column("resolution", sa.String(20)),
    )
    op.create_index("idx_duplicate_groups_scan", "duplicate_groups", ["scan_id"])
    op.create_index("idx_duplicate_groups_status", "duplicate_groups", ["status"])

    # -- 1.6 Credit Management --
    op.create_table(
        "credit_scores",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("customer_id", sa.Integer, nullable=False, unique=True),
        sa.Column("customer_name", sa.String(255)),
        sa.Column("credit_score", sa.Numeric(5, 2)),
        sa.Column("credit_limit", sa.Numeric(15, 2)),
        sa.Column("current_exposure", sa.Numeric(15, 2), server_default="0"),
        sa.Column("overdue_amount", sa.Numeric(15, 2), server_default="0"),
        sa.Column("payment_history_score", sa.Numeric(5, 2)),
        sa.Column("order_volume_score", sa.Numeric(5, 2)),
        sa.Column("risk_level", sa.String(20), server_default="normal"),
        sa.Column("hold_active", sa.Boolean, server_default="false"),
        sa.Column("hold_reason", sa.Text),
        sa.Column("last_calculated", sa.DateTime, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_credit_scores_customer", "credit_scores", ["customer_id"])
    op.create_index("idx_credit_scores_hold", "credit_scores", ["hold_active"])

    # -- 1.7 Report Builder --
    op.create_table(
        "report_jobs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("request_text", sa.Text, nullable=False),
        sa.Column("parsed_query", sa.JSON),
        sa.Column("result_data", sa.JSON),
        sa.Column("format", sa.String(20), server_default="table"),
        sa.Column("file_path", sa.String(500)),
        sa.Column("schedule_cron", sa.String(100)),
        sa.Column("requested_by", sa.String(255)),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("error_message", sa.Text),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime),
    )
    op.create_index("idx_report_jobs_status", "report_jobs", ["status"])

    # -- 1.8 Cash Flow Forecasting --
    op.create_table(
        "cash_forecasts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("forecast_date", sa.Date, nullable=False),
        sa.Column("target_date", sa.Date, nullable=False),
        sa.Column("predicted_balance", sa.Numeric(15, 2), nullable=False),
        sa.Column("confidence_low", sa.Numeric(15, 2)),
        sa.Column("confidence_high", sa.Numeric(15, 2)),
        sa.Column("ar_expected", sa.Numeric(15, 2), server_default="0"),
        sa.Column("ap_expected", sa.Numeric(15, 2), server_default="0"),
        sa.Column("pipeline_expected", sa.Numeric(15, 2), server_default="0"),
        sa.Column("recurring_expected", sa.Numeric(15, 2), server_default="0"),
        sa.Column("model_version", sa.String(50)),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_cash_forecasts_dates", "cash_forecasts", ["forecast_date", "target_date"])

    op.create_table(
        "forecast_scenarios",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("adjustments", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("base_forecast_id", sa.Integer, sa.ForeignKey("cash_forecasts.id")),
        sa.Column("result_data", sa.JSON),
        sa.Column("created_by", sa.String(255)),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "forecast_accuracy_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("forecast_id", sa.Integer, sa.ForeignKey("cash_forecasts.id")),
        sa.Column("target_date", sa.Date, nullable=False),
        sa.Column("predicted_balance", sa.Numeric(15, 2)),
        sa.Column("actual_balance", sa.Numeric(15, 2)),
        sa.Column("error_pct", sa.Numeric(8, 4)),
        sa.Column("logged_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_forecast_accuracy_date", "forecast_accuracy_log", ["target_date"])

    # -- 1.11 Daily Digests --
    op.create_table(
        "daily_digests",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_role", sa.String(100), nullable=False),
        sa.Column("digest_date", sa.Date, nullable=False),
        sa.Column("content", sa.JSON, nullable=False),
        sa.Column("channels_sent", sa.JSON, server_default="[]"),
        sa.Column("delivered", sa.Boolean, server_default="false"),
        sa.Column("generated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_digest_date_role", "daily_digests", ["digest_date", "user_role"])


def downgrade() -> None:
    op.drop_table("daily_digests")
    op.drop_table("forecast_accuracy_log")
    op.drop_table("forecast_scenarios")
    op.drop_table("cash_forecasts")
    op.drop_table("report_jobs")
    op.drop_table("credit_scores")
    op.drop_table("duplicate_groups")
    op.drop_table("deduplication_scans")
    op.drop_table("extraction_corrections")
    op.drop_table("document_processing_jobs")
    op.drop_table("reconciliation_sessions")
    op.drop_table("closing_steps")
    op.drop_table("month_end_closings")
