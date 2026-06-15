from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.enums import AgentRunHumanReviewResult, AgentRunOutcome
from app.enums.utils import enum_values


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(
            "edit_percentage >= 0 AND edit_percentage <= 1",
            name="ck_agent_runs_edit_percentage_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("ticket_history.id"), index=True)
    trace_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    agent_name: Mapped[str] = mapped_column(String(100), index=True)
    agent_version: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        index=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    outcome: Mapped[AgentRunOutcome | None] = mapped_column(
        Enum(
            AgentRunOutcome,
            values_callable=enum_values,
            native_enum=False,
        ),
        nullable=True,
        index=True,
    )
    draft_risk: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    guardrail_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    human_review_required: Mapped[bool] = mapped_column(Boolean, default=False)
    human_review_result: Mapped[AgentRunHumanReviewResult | None] = mapped_column(
        Enum(
            AgentRunHumanReviewResult,
            values_callable=enum_values,
            native_enum=False,
        ),
        nullable=True,
        index=True,
    )
    edit_percentage: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4),
        nullable=True,
    )
    model_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6),
        nullable=True,
    )
