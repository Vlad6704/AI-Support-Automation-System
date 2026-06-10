"""add ticket supportability

Revision ID: 8c54d9bf318a
Revises: c7992c71e143
Create Date: 2026-06-10 18:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8c54d9bf318a"
down_revision: Union[str, Sequence[str], None] = "c7992c71e143"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ticket_history",
        sa.Column(
            "supportability",
            sa.Enum(
                "unchecked",
                "supported",
                "unsupported",
                name="ticketsupportability",
                native_enum=False,
            ),
            nullable=False,
            server_default="unchecked",
        ),
    )
    op.create_index(
        "ix_ticket_history_supportability",
        "ticket_history",
        ["supportability"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ticket_history_supportability",
        table_name="ticket_history",
    )
    with op.batch_alter_table("ticket_history") as batch_op:
        batch_op.drop_column("supportability")
