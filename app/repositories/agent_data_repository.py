from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.enums import AffectedService
from app.models import (
    ApiUsageLog,
    Customer,
    Deployment,
    Incident,
    Subscription,
    TicketHistory,
    WebhookDeliveryLog,
)
from app.repositories.serialization import model_to_dict


def _all_for_customer(
    db: Session,
    model: Any,
    customer_id: int,
    limit: int = 50,
) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(model)
        .where(model.customer_id == customer_id)
        .order_by(model.id.desc())
        .limit(limit)
    ).all()
    return [model_to_dict(row) for row in rows]


def select_customer_context_by_id(customer_id: int) -> dict[str, Any]:
    db = SessionLocal()
    try:
        customer = db.get(Customer, customer_id)
        return {
            "customer": model_to_dict(customer) if customer else None,
            "subscriptions": _all_for_customer(db, Subscription, customer_id),
            "api_usage_logs": _all_for_customer(db, ApiUsageLog, customer_id),
            "ticket_history": _all_for_customer(db, TicketHistory, customer_id),
            "webhook_delivery_logs": _all_for_customer(
                db,
                WebhookDeliveryLog,
                customer_id,
            ),
        }
    finally:
        db.close()


def select_incidents_for_affected_service(
    affected_service: AffectedService,
    limit: int = 20,
) -> list[dict[str, Any]]:
    db = SessionLocal()
    try:
        safe_limit = max(1, min(limit, 20))
        rows = db.scalars(
            select(Incident)
            .where(Incident.affected_service == affected_service)
            .order_by(Incident.started_at.desc())
            .limit(safe_limit)
        ).all()
        return [model_to_dict(row) for row in rows]
    finally:
        db.close()


def select_deployments_by_time_window(
    deployed_from: datetime | None = None,
    deployed_to: datetime | None = None,
) -> list[dict[str, Any]]:
    db = SessionLocal()
    try:
        statement = select(Deployment)
        if deployed_from is not None:
            statement = statement.where(Deployment.deployed_at >= deployed_from)
        if deployed_to is not None:
            statement = statement.where(Deployment.deployed_at <= deployed_to)
        rows = db.scalars(statement.order_by(Deployment.deployed_at.desc()).limit(10)).all()
        return [model_to_dict(row) for row in rows]
    finally:
        db.close()
