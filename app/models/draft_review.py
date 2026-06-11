from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.enums import DraftReviewStatus
from app.enums.utils import enum_values


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DraftReview(Base):
    __tablename__ = "drafts_review"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    previous_review_id: Mapped[int | None] = mapped_column(
        ForeignKey("drafts_review.id"),
        nullable=True,
        index=True,
    )
    ticket_id: Mapped[int] = mapped_column(ForeignKey("ticket_history.id"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    original_draft: Mapped[str] = mapped_column(Text)
    edited_draft: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    guardrail_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[DraftReviewStatus] = mapped_column(
        Enum(
            DraftReviewStatus,
            values_callable=enum_values,
            native_enum=False,
        ),
        default=DraftReviewStatus.OPEN,
        server_default=DraftReviewStatus.OPEN.value,
        index=True,
    )
