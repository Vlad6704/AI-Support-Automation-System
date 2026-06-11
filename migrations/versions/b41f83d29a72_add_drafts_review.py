"""add drafts review

Revision ID: b41f83d29a72
Revises: 8c54d9bf318a
Create Date: 2026-06-10 22:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b41f83d29a72"
down_revision: Union[str, Sequence[str], None] = "8c54d9bf318a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "drafts_review",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("original_draft", sa.Text(), nullable=False),
        sa.Column("edited_draft", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["ticket_id"], ["ticket_history.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_drafts_review_customer_id", "drafts_review", ["customer_id"])
    op.create_index("ix_drafts_review_id", "drafts_review", ["id"])
    op.create_index("ix_drafts_review_ticket_id", "drafts_review", ["ticket_id"])


def downgrade() -> None:
    op.drop_index("ix_drafts_review_ticket_id", table_name="drafts_review")
    op.drop_index("ix_drafts_review_id", table_name="drafts_review")
    op.drop_index("ix_drafts_review_customer_id", table_name="drafts_review")
    op.drop_table("drafts_review")
