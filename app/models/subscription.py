from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    plan: Mapped[str] = mapped_column(String(100))
    monthly_event_limit: Mapped[int] = mapped_column(Integer)
    current_month_events: Mapped[int] = mapped_column(Integer, default=0)
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer)
    sla_response_time_minutes: Mapped[int] = mapped_column(Integer)
    support_tier: Mapped[str] = mapped_column(String(100))
    is_over_limit: Mapped[bool] = mapped_column(Boolean, default=False)
