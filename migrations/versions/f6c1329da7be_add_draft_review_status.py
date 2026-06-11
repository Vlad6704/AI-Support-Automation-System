"""add draft review status

Revision ID: f6c1329da7be
Revises: b41f83d29a72
Create Date: 2026-06-10 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f6c1329da7be"
down_revision: Union[str, Sequence[str], None] = "b41f83d29a72"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "drafts_review",
        sa.Column(
            "status",
            sa.Enum(
                "open",
                "closed",
                name="draftreviewstatus",
                native_enum=False,
            ),
            nullable=False,
            server_default="open",
        ),
    )
    op.create_index(
        "ix_drafts_review_status",
        "drafts_review",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_drafts_review_status", table_name="drafts_review")
    with op.batch_alter_table("drafts_review") as batch_op:
        batch_op.drop_column("status")
