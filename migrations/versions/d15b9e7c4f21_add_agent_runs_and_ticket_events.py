"""add agent runs and ticket events

Revision ID: d15b9e7c4f21
Revises: 32a611c3ab8e
Create Date: 2026-06-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d15b9e7c4f21"
down_revision: Union[str, Sequence[str], None] = "32a611c3ab8e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("trace_id", sa.String(length=255), nullable=True),
        sa.Column("agent_name", sa.String(length=100), nullable=False),
        sa.Column("agent_version", sa.String(length=100), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "outcome",
            sa.Enum(
                "automated",
                "awaiting_review",
                "unsupported",
                "failed",
                name="agentrunoutcome",
                native_enum=False,
            ),
            nullable=True,
        ),
        sa.Column("draft_risk", sa.String(length=20), nullable=True),
        sa.Column("guardrail_passed", sa.Boolean(), nullable=True),
        sa.Column("human_review_required", sa.Boolean(), nullable=False),
        sa.Column("model_cost", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.ForeignKeyConstraint(["ticket_id"], ["ticket_history.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_runs_agent_name", "agent_runs", ["agent_name"])
    op.create_index("ix_agent_runs_agent_version", "agent_runs", ["agent_version"])
    op.create_index("ix_agent_runs_draft_risk", "agent_runs", ["draft_risk"])
    op.create_index("ix_agent_runs_id", "agent_runs", ["id"])
    op.create_index("ix_agent_runs_outcome", "agent_runs", ["outcome"])
    op.create_index("ix_agent_runs_started_at", "agent_runs", ["started_at"])
    op.create_index("ix_agent_runs_ticket_id", "agent_runs", ["ticket_id"])
    op.create_index("ix_agent_runs_trace_id", "agent_runs", ["trace_id"])

    op.create_table(
        "ticket_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("actor_type", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["ticket_id"], ["ticket_history.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ticket_events_actor_type", "ticket_events", ["actor_type"])
    op.create_index("ix_ticket_events_created_at", "ticket_events", ["created_at"])
    op.create_index("ix_ticket_events_event_type", "ticket_events", ["event_type"])
    op.create_index("ix_ticket_events_id", "ticket_events", ["id"])
    op.create_index("ix_ticket_events_ticket_id", "ticket_events", ["ticket_id"])


def downgrade() -> None:
    op.drop_index("ix_ticket_events_ticket_id", table_name="ticket_events")
    op.drop_index("ix_ticket_events_id", table_name="ticket_events")
    op.drop_index("ix_ticket_events_event_type", table_name="ticket_events")
    op.drop_index("ix_ticket_events_created_at", table_name="ticket_events")
    op.drop_index("ix_ticket_events_actor_type", table_name="ticket_events")
    op.drop_table("ticket_events")

    op.drop_index("ix_agent_runs_trace_id", table_name="agent_runs")
    op.drop_index("ix_agent_runs_ticket_id", table_name="agent_runs")
    op.drop_index("ix_agent_runs_started_at", table_name="agent_runs")
    op.drop_index("ix_agent_runs_outcome", table_name="agent_runs")
    op.drop_index("ix_agent_runs_id", table_name="agent_runs")
    op.drop_index("ix_agent_runs_draft_risk", table_name="agent_runs")
    op.drop_index("ix_agent_runs_agent_version", table_name="agent_runs")
    op.drop_index("ix_agent_runs_agent_name", table_name="agent_runs")
    op.drop_table("agent_runs")
