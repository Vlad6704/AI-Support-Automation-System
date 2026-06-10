from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.enums import WebhookDeliveryStatus
from app.enums.utils import enum_values


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WebhookDeliveryLog(Base):
    __tablename__ = "webhook_delivery_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    webhook_endpoint_id: Mapped[int] = mapped_column(
        ForeignKey("webhook_endpoints.id"),
        index=True,
    )
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delivery_status: Mapped[WebhookDeliveryStatus] = mapped_column(
        Enum(
            WebhookDeliveryStatus,
            values_callable=enum_values,
            native_enum=False,
        ),
        index=True,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
