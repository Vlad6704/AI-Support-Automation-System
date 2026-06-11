"""add draft review history

Revision ID: a27d91b3e604
Revises: f6c1329da7be
Create Date: 2026-06-11 00:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a27d91b3e604"
down_revision: Union[str, Sequence[str], None] = "f6c1329da7be"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("drafts_review") as batch_op:
        batch_op.alter_column("notes", new_column_name="reviewer_notes")
        batch_op.add_column(
            sa.Column("guardrail_feedback", sa.Text(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("previous_review_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_drafts_review_previous_review_id",
            "drafts_review",
            ["previous_review_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_drafts_review_previous_review_id",
            ["previous_review_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("drafts_review") as batch_op:
        batch_op.drop_index("ix_drafts_review_previous_review_id")
        batch_op.drop_constraint(
            "fk_drafts_review_previous_review_id",
            type_="foreignkey",
        )
        batch_op.drop_column("previous_review_id")
        batch_op.drop_column("guardrail_feedback")
        batch_op.alter_column("reviewer_notes", new_column_name="notes")
