"""Add Phase 2 tables: agent orchestration (runs, steps, decisions,
suspensions) and supply chain intelligence (risk scores, risk factors,
disruption predictions, alerts, alternative supplier maps).

Revision ID: 003_phase2_tables
Revises: 002_phase1_tables
Create Date: 2026-02-27
"""

from alembic import op
import sqlalchemy as sa

revision = "003_phase2_tables"
down_revision = "002_phase1_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- 2.1 Agent Orchestration --
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("agent_type", sa.String(100), nullable=False),
        sa.Column("trigger_type", sa.String(50), nullable=False),
        sa.Column("trigger_id", sa.String(255)),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("started_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime),
        sa.Column("total_steps", sa.Integer, server_default="0"),
        sa.Column("token_usage", sa.Integer, server_default="0"),
        sa.Column("error", sa.Text),
        sa.Column("initial_state", sa.JSON, server_default="{}"),
        sa.Column("final_state", sa.JSON),
    )
    op.create_index("idx_agent_runs_type", "agent_runs", ["agent_type"])
    op.create_index("idx_agent_runs_status", "agent_runs", ["status"])
    op.create_index("idx_agent_runs_started", "agent_runs", ["started_at"])

    op.create_table(
        "agent_steps",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("agent_run_id", sa.Integer, sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_name", sa.String(100), nullable=False),
        sa.Column("step_index", sa.Integer, nullable=False),
        sa.Column("input_data", sa.JSON),
        sa.Column("output_data", sa.JSON),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("claude_tokens_used", sa.Integer, server_default="0"),
        sa.Column("started_at", sa.DateTime),
        sa.Column("completed_at", sa.DateTime),
    )
    op.create_index("idx_agent_steps_run", "agent_steps", ["agent_run_id"])
    op.create_index("idx_agent_steps_status", "agent_steps", ["status"])

    op.create_table(
        "agent_decisions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("agent_step_id", sa.Integer, sa.ForeignKey("agent_steps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prompt_hash", sa.String(64)),
        sa.Column("response", sa.JSON),
        sa.Column("confidence", sa.Float),
        sa.Column("tools_used", sa.JSON, server_default="[]"),
        sa.Column("tokens_input", sa.Integer, server_default="0"),
        sa.Column("tokens_output", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_agent_decisions_step", "agent_decisions", ["agent_step_id"])

    op.create_table(
        "agent_suspensions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("agent_run_id", sa.Integer, sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resume_condition", sa.String(100), nullable=False),
        sa.Column("resume_data", sa.JSON, server_default="{}"),
        sa.Column("suspended_at_step", sa.String(100)),
        sa.Column("timeout_at", sa.DateTime),
        sa.Column("suspended_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("resumed_at", sa.DateTime),
    )
    op.create_index("idx_agent_suspensions_run", "agent_suspensions", ["agent_run_id"])
    op.create_index("idx_agent_suspensions_timeout", "agent_suspensions", ["timeout_at"])

    # -- 2.8 Supply Chain Intelligence --
    op.create_table(
        "supplier_risk_scores",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("vendor_id", sa.Integer, nullable=False),
        sa.Column("vendor_name", sa.String(255)),
        sa.Column("score", sa.Numeric(5, 2), nullable=False),
        sa.Column("previous_score", sa.Numeric(5, 2)),
        sa.Column("classification", sa.String(20), nullable=False),
        sa.Column("summary", sa.Text),
        sa.Column("scored_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_risk_scores_vendor", "supplier_risk_scores", ["vendor_id"])
    op.create_index("idx_risk_scores_classification", "supplier_risk_scores", ["classification"])
    op.create_index("idx_risk_scores_scored_at", "supplier_risk_scores", ["scored_at"])

    op.create_table(
        "supplier_risk_factors",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("risk_score_id", sa.Integer, sa.ForeignKey("supplier_risk_scores.id", ondelete="CASCADE"), nullable=False),
        sa.Column("factor_name", sa.String(100), nullable=False),
        sa.Column("weight", sa.Numeric(4, 2), nullable=False),
        sa.Column("raw_value", sa.Numeric(10, 4)),
        sa.Column("weighted_score", sa.Numeric(6, 2), nullable=False),
        sa.Column("details", sa.JSON),
    )
    op.create_index("idx_risk_factors_score", "supplier_risk_factors", ["risk_score_id"])

    op.create_table(
        "disruption_predictions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("vendor_id", sa.Integer, nullable=False),
        sa.Column("vendor_name", sa.String(255)),
        sa.Column("prediction_type", sa.String(50), nullable=False),
        sa.Column("probability", sa.Numeric(5, 4), nullable=False),
        sa.Column("estimated_impact", sa.JSON),
        sa.Column("recommended_actions", sa.JSON, server_default="[]"),
        sa.Column("supporting_data", sa.JSON),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime),
        sa.Column("resolved_at", sa.DateTime),
    )
    op.create_index("idx_disruption_vendor", "disruption_predictions", ["vendor_id"])
    op.create_index("idx_disruption_active", "disruption_predictions", ["is_active"])

    op.create_table(
        "supply_chain_alerts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("vendor_id", sa.Integer, nullable=False),
        sa.Column("vendor_name", sa.String(255)),
        sa.Column("alert_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("related_prediction_id", sa.Integer, sa.ForeignKey("disruption_predictions.id")),
        sa.Column("acknowledged_by", sa.String(255)),
        sa.Column("acknowledged_at", sa.DateTime),
        sa.Column("resolved_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_sc_alerts_vendor", "supply_chain_alerts", ["vendor_id"])
    op.create_index("idx_sc_alerts_severity", "supply_chain_alerts", ["severity"])
    op.create_index("idx_sc_alerts_resolved", "supply_chain_alerts", ["resolved_at"])

    op.create_table(
        "alternative_supplier_maps",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("product_id", sa.Integer, nullable=False),
        sa.Column("product_name", sa.String(255)),
        sa.Column("primary_vendor_id", sa.Integer, nullable=False),
        sa.Column("primary_vendor_name", sa.String(255)),
        sa.Column("alternative_vendor_id", sa.Integer, nullable=False),
        sa.Column("alternative_vendor_name", sa.String(255)),
        sa.Column("price_delta_pct", sa.Numeric(6, 2)),
        sa.Column("lead_time_delta_days", sa.Integer),
        sa.Column("quality_comparable", sa.Boolean),
        sa.Column("last_evaluated", sa.DateTime, server_default=sa.func.now()),
        sa.Column("is_single_source", sa.Boolean, server_default="false"),
        sa.Column("revenue_at_risk", sa.Numeric(15, 2)),
    )
    op.create_index("idx_alt_supplier_product", "alternative_supplier_maps", ["product_id"])
    op.create_index("idx_alt_supplier_primary", "alternative_supplier_maps", ["primary_vendor_id"])
    op.create_unique_constraint(
        "uq_alt_supplier_mapping",
        "alternative_supplier_maps",
        ["product_id", "primary_vendor_id", "alternative_vendor_id"],
    )

    # Extend AutomationType enum with new values
    op.execute("ALTER TYPE automationtype ADD VALUE IF NOT EXISTS 'supply_chain'")
    op.execute("ALTER TYPE automationtype ADD VALUE IF NOT EXISTS 'agent_workflow'")


def downgrade() -> None:
    op.drop_table("alternative_supplier_maps")
    op.drop_table("supply_chain_alerts")
    op.drop_table("disruption_predictions")
    op.drop_table("supplier_risk_factors")
    op.drop_table("supplier_risk_scores")
    op.drop_table("agent_suspensions")
    op.drop_table("agent_decisions")
    op.drop_table("agent_steps")
    op.drop_table("agent_runs")
