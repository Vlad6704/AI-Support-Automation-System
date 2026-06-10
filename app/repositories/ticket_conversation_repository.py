from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
import logging
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.enums import MessageSource
from app.models import Customer, Message, TicketHistory

logger = logging.getLogger(__name__)


class TicketConversationRepository(Protocol):
    def list_customers(self) -> list[Customer]: ...

    def list_tickets(self) -> list[tuple[TicketHistory, datetime | None]]: ...

    def get_customer(self, customer_id: int) -> Customer | None: ...

    def get_ticket(self, ticket_id: int) -> TicketHistory | None: ...

    def list_messages(self, ticket_id: int) -> list[Message]: ...

    def create_ticket(
        self,
        *,
        customer_id: int,
        title: str,
        description: str,
        status: str,
        updated_by: str,
        initial_message_source: MessageSource,
    ) -> TicketHistory: ...

    def create_message(
        self,
        *,
        customer_id: int,
        ticket_id: int,
        message: str,
        source: MessageSource,
    ) -> Message: ...


class DatabaseTicketConversationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_customers(self) -> list[Customer]:
        return list(
            self.db.scalars(select(Customer).order_by(Customer.company_name)).all()
        )

    def list_tickets(self) -> list[tuple[TicketHistory, datetime | None]]:
        last_message_at = func.max(Message.updated_at).label("last_message_at")
        rows = self.db.execute(
            select(TicketHistory, last_message_at)
            .outerjoin(Message, Message.ticket_id == TicketHistory.id)
            .group_by(TicketHistory.id)
            .order_by(func.coalesce(last_message_at, TicketHistory.updated_at).desc())
        ).all()
        return [(ticket, message_at) for ticket, message_at in rows]

    def get_customer(self, customer_id: int) -> Customer | None:
        return self.db.get(Customer, customer_id)

    def get_ticket(self, ticket_id: int) -> TicketHistory | None:
        return self.db.get(TicketHistory, ticket_id)

    def list_messages(self, ticket_id: int) -> list[Message]:
        return list(
            self.db.scalars(
                select(Message)
                .where(Message.ticket_id == ticket_id)
                .order_by(Message.created_at, Message.id)
            ).all()
        )

    def create_ticket(
        self,
        *,
        customer_id: int,
        title: str,
        description: str,
        status: str,
        updated_by: str,
        initial_message_source: MessageSource,
    ) -> TicketHistory:
        ticket = TicketHistory(
            customer_id=customer_id,
            title=title,
            description=description,
            status=status,
            updated_by=updated_by,
        )
        try:
            self.db.add(ticket)
            self.db.flush()
            self.db.add(
                Message(
                    customer_id=ticket.customer_id,
                    ticket_id=ticket.id,
                    message=ticket.description,
                    source=initial_message_source,
                )
            )
            self.db.commit()
            self.db.refresh(ticket)
        except Exception:
            self.db.rollback()
            logger.exception("Ticket transaction failed customer_id=%s", customer_id)
            raise
        return ticket

    def create_message(
        self,
        *,
        customer_id: int,
        ticket_id: int,
        message: str,
        source: MessageSource,
    ) -> Message:
        stored_message = Message(
            customer_id=customer_id,
            ticket_id=ticket_id,
            message=message,
            source=source,
        )
        try:
            self.db.add(stored_message)
            self.db.commit()
            self.db.refresh(stored_message)
        except Exception:
            self.db.rollback()
            logger.exception(
                "Message transaction failed ticket_id=%s source=%s",
                ticket_id,
                source,
            )
            raise
        return stored_message


@contextmanager
def database_ticket_conversation_repository() -> Iterator[
    DatabaseTicketConversationRepository
]:
    db = SessionLocal()
    try:
        yield DatabaseTicketConversationRepository(db)
    finally:
        db.close()
