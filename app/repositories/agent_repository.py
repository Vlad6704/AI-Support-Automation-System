from datetime import date, datetime
from typing import Any

from sqlalchemy import and_, func, not_, or_, select
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.orm import Session, sessionmaker

from app.db import SessionLocal
from app.enums import AffectedService, MessageSource
from app.models import (
    ApiUsageLog,
    Customer,
    Deployment,
    Incident,
    Invoice,
    Message,
    Subscription,
    TicketHistory,
    WebhookDeliveryLog,
    WebhookEndpoint,
)
from app.repositories.agent_repository_protocols import (
    CustomerContextData,
    CustomerData,
    InvoiceData,
    QueryResult,
    RepositoryWhere,
    SerializedRow,
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
        "supportability": ticket.supportability,
        "category": ticket.category,
        "updated_by": ticket.updated_by,
        "resolution_summery": ticket.resolution_summery,
    }


def _all_for_customer(
    db: Session,
    model: Any,
    customer_id: int,
    limit: int = 50,
) -> list[SerializedRow]:
    rows = db.scalars(
        select(model)
        .where(model.customer_id == customer_id)
        .order_by(model.id.desc())
        .limit(limit)
    ).all()
    return [model_to_dict(row) for row in rows]


def _query_for_customer(
    db: Session,
    model: Any,
    customer_id: int,
    where: RepositoryWhere | None,
    limit: int,
    offset: int,
) -> QueryResult:
    conditions = [model.customer_id == customer_id]
    if where is not None and where["conditions"]:
        where_conditions = [
            _build_where_condition(model, condition)
            for condition in where["conditions"]
        ]
        conditions.append(
            or_(*where_conditions)
            if where["match"] == "any"
            else and_(*where_conditions)
        )
    safe_limit = max(1, min(limit, 100))
    safe_offset = max(0, offset)

    count = db.scalar(
        select(func.count()).select_from(model).where(*conditions)
    )
    rows = db.scalars(
        select(model)
        .where(*conditions)
        .order_by(model.id.desc())
        .offset(safe_offset)
        .limit(safe_limit)
    ).all()
    return {
        "rows": [model_to_dict(row) for row in rows],
        "count": count or 0,
    }


def _coerce_filter_value(model: Any, name: str, value: Any) -> Any:
    column_type = model.__table__.columns[name].type
    try:
        python_type = column_type.python_type
    except NotImplementedError:
        return value

    if python_type is datetime and isinstance(value, datetime):
        return value
    if python_type is date and isinstance(value, date):
        return value
    if python_type not in {datetime, date}:
        return value
    if not isinstance(value, str):
        raise ValueError(
            f"Invalid {model.__name__} filter value for {name}: "
            f"expected ISO timestamp string, got {type(value).__name__}"
        )

    try:
        if python_type is datetime:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        if python_type is date:
            return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(
            f"Invalid {model.__name__} filter value for {name}: {value!r}"
        ) from error
    return value


def _build_where_condition(
    model: Any,
    condition: dict[str, Any],
) -> ColumnElement[bool]:
    name = condition["column"]
    operator = condition["operator"]
    value = condition.get("value")
    if name == "customer_id":
        raise ValueError("customer_id is fixed by the ticket and cannot be filtered")
    if name not in model.__table__.columns:
        raise ValueError(f"Invalid {model.__name__} where column: {name}")

    column = getattr(model, name)
    if operator == "is_null":
        return column.is_(None)
    if operator == "is_not_null":
        return column.is_not(None)
    if operator in {"in", "not_in"}:
        if not isinstance(value, list) or not value:
            raise ValueError(f"{operator} requires a non-empty list value")
        coerced = [_coerce_filter_value(model, name, item) for item in value]
        expression = column.in_(coerced)
        return not_(expression) if operator == "not_in" else expression
    if value is None:
        raise ValueError(f"{operator} requires a value")

    coerced_value = _coerce_filter_value(model, name, value)
    if operator == "eq":
        return column == coerced_value
    if operator == "ne":
        return column != coerced_value
    if operator == "gt":
        return column > coerced_value
    if operator == "gte":
        return column >= coerced_value
    if operator == "lt":
        return column < coerced_value
    if operator == "lte":
        return column <= coerced_value
    if not isinstance(coerced_value, str):
        raise ValueError(f"{operator} requires a string value")
    try:
        python_type = model.__table__.columns[name].type.python_type
    except NotImplementedError:
        python_type = None
    if operator in {"starts_with", "ends_with"} and python_type is not str:
        raise ValueError(f"{operator} requires a string column")
    if operator == "contains":
        return column.contains(coerced_value)
    if operator == "starts_with":
        return column.startswith(coerced_value)
    if operator == "ends_with":
        return column.endswith(coerced_value)
    raise ValueError(f"Unsupported where operator: {operator}")


class DatabaseAgentRepository:
    def __init__(self, session_factory: sessionmaker[Session] = SessionLocal) -> None:
        self.session_factory = session_factory

    def get_customer_by_id(self, customer_id: int) -> CustomerData | None:
        db = self.session_factory()
        try:
            customer = db.get(Customer, customer_id)
            return _customer_to_data(customer) if customer is not None else None
        finally:
            db.close()

    def get_ticket_by_id(self, ticket_id: int) -> TicketHistoryData | None:
        db = self.session_factory()
        try:
            ticket = db.get(TicketHistory, ticket_id)
            return _ticket_to_data(ticket) if ticket is not None else None
        finally:
            db.close()

    def get_first_ticket(self) -> TicketHistoryData | None:
        db = self.session_factory()
        try:
            ticket = db.scalars(
                select(TicketHistory).order_by(TicketHistory.id)
            ).first()
            return _ticket_to_data(ticket) if ticket is not None else None
        finally:
            db.close()

    def get_latest_user_message(self, ticket_id: int) -> SerializedRow | None:
        db = self.session_factory()
        try:
            message = db.scalars(
                select(Message)
                .where(
                    Message.ticket_id == ticket_id,
                    Message.source == MessageSource.USER,
                )
                .order_by(Message.created_at.desc(), Message.id.desc())
            ).first()
            return model_to_dict(message) if message is not None else None
        finally:
            db.close()

    def get_invoice_by_id(self, invoice_id: int) -> InvoiceData | None:
        db = self.session_factory()
        try:
            invoice = db.get(Invoice, invoice_id)
            return model_to_dict(invoice) if invoice is not None else None
        finally:
            db.close()

    def get_customer_context(self, customer_id: int) -> CustomerContextData:
        db = self.session_factory()
        try:
            customer = db.get(Customer, customer_id)
            return {
                "customer": model_to_dict(customer) if customer else None,
                "messages": _all_for_customer(db, Message, customer_id),
                "subscriptions": _all_for_customer(db, Subscription, customer_id),
                "api_usage_logs": _all_for_customer(db, ApiUsageLog, customer_id),
                "ticket_history": _all_for_customer(db, TicketHistory, customer_id),
                "last_30_webhook_delivery_logs": _all_for_customer(
                    db,
                    WebhookDeliveryLog,
                    customer_id,
                    limit=30,
                ),
                "last_30_webhook_endpoints": _all_for_customer(
                    db,
                    WebhookEndpoint,
                    customer_id,
                    limit=30,
                ),
            }
        finally:
            db.close()

    def get_webhook_delivery_logs(
        self,
        customer_id: int,
        where: RepositoryWhere | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> QueryResult:
        db = self.session_factory()
        try:
            return _query_for_customer(
                db,
                WebhookDeliveryLog,
                customer_id,
                where,
                limit,
                offset,
            )
        finally:
            db.close()

    def get_webhook_endpoints(
        self,
        customer_id: int,
        where: RepositoryWhere | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> QueryResult:
        db = self.session_factory()
        try:
            return _query_for_customer(
                db,
                WebhookEndpoint,
                customer_id,
                where,
                limit,
                offset,
            )
        finally:
            db.close()

    def get_incidents(
        self,
        affected_service: AffectedService,
        limit: int = 20,
    ) -> list[SerializedRow]:
        db = self.session_factory()
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
    ) -> list[SerializedRow]:
        db = self.session_factory()
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
