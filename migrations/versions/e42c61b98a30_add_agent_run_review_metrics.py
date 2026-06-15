"""add agent run review metrics

Revision ID: e42c61b98a30
Revises: d15b9e7c4f21
Create Date: 2026-06-15 00:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e42c61b98a30"
down_revision: Union[str, Sequence[str], None] = "d15b9e7c4f21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column(
            "human_review_result",
            sa.Enum(
                "accepted_without_editing",
                "edited",
                name="agentrunhumanreviewresult",
                native_enum=False,
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "agent_runs",
        sa.Column("edit_percentage", sa.Numeric(precision=5, scale=4), nullable=True),
    )
    op.create_index(
        "ix_agent_runs_human_review_result",
        "agent_runs",
        ["human_review_result"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agent_runs_human_review_result",
        table_name="agent_runs",
    )
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.drop_column("edit_percentage")
        batch_op.drop_column("human_review_result")
