from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.enums import AffectedService


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    affected_service: Mapped[AffectedService] = mapped_column(
        Enum(
            AffectedService,
            values_callable=lambda enum: [item.value for item in enum],
            native_enum=False,
        ),
        index=True,
    )
    status: Mapped[str] = mapped_column(String(50), index=True)
    severity: Mapped[str] = mapped_column(String(50), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary: Mapped[str] = mapped_column(Text)
    customer_impact: Mapped[str | None] = mapped_column(Text, nullable=True)
