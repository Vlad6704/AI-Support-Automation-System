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
from app.repositories.agent_repository_protocols import (
    CustomerData,
    InvoiceData,
    TicketHistoryData,
)
from app.repositories.utils.serialization import model_to_dict


def _customer_to_data(customer: Customer) -> CustomerData:
    return {
        "id": customer.id,
        "company_name": customer.company_name,
        "contact_email": customer.contact_email,
        "region": customer.region,
        "plan": customer.plan,
        "status": customer.status,
        "created_at": customer.created_at,
    }


def _ticket_to_data(ticket: TicketHistory) -> TicketHistoryData:
    return {
        "id": ticket.id,
        "customer_id": ticket.customer_id,
        "title": ticket.title,
        "description": ticket.description,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
        "status": ticket.status,
        "category": ticket.category,
        "updated_by": ticket.updated_by,
        "resolution_summery": ticket.resolution_summery,
    }


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


class DatabaseAgentRepository:
    def get_customer_by_id(self, customer_id: int) -> CustomerData | None:
        db = SessionLocal()
        try:
            customer = db.get(Customer, customer_id)
            return _customer_to_data(customer) if customer is not None else None
        finally:
            db.close()

    def get_ticket_by_id(self, ticket_id: int) -> TicketHistoryData | None:
        db = SessionLocal()
        try:
            ticket = db.get(TicketHistory, ticket_id)
            return _ticket_to_data(ticket) if ticket is not None else None
        finally:
            db.close()

    def get_first_ticket(self) -> TicketHistoryData | None:
        db = SessionLocal()
        try:
            ticket = db.scalars(
                select(TicketHistory).order_by(TicketHistory.id)
            ).first()
            return _ticket_to_data(ticket) if ticket is not None else None
        finally:
            db.close()

    def get_invoice_by_id(self, invoice_id: int) -> InvoiceData | None:
        return None

    def get_customer_context(self, customer_id: int) -> dict[str, Any]:
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

    def get_incidents(
        self,
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

    def get_deployments(
        self,
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
            rows = db.scalars(
                statement.order_by(Deployment.deployed_at.desc()).limit(10)
            ).all()
            return [model_to_dict(row) for row in rows]
        finally:
            db.close()
