"""add invoices

Revision ID: 32a611c3ab8e
Revises: a27d91b3e604
Create Date: 2026-06-11 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "32a611c3ab8e"
down_revision: Union[str, Sequence[str], None] = "a27d91b3e604"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "invoices",
        sa.Column("invoice_id", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.String(length=10), nullable=False),
        sa.Column("end_date", sa.String(length=10), nullable=False),
        sa.Column("amount", sa.String(length=50), nullable=False),
        sa.Column("refundable", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("invoice_id"),
    )


def downgrade() -> None:
    op.drop_table("invoices")
