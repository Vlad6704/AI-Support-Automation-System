"""constrain agent run edit percentage

Revision ID: f73d02ac519b
Revises: e42c61b98a30
Create Date: 2026-06-15 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "f73d02ac519b"
down_revision: Union[str, Sequence[str], None] = "e42c61b98a30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.create_check_constraint(
            "ck_agent_runs_edit_percentage_range",
            "edit_percentage >= 0 AND edit_percentage <= 1",
        )


def downgrade() -> None:
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.drop_constraint(
            "ck_agent_runs_edit_percentage_range",
            type_="check",
        )
