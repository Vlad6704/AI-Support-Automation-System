from datetime import datetime
from typing import TypedDict

from sqlalchemy import select

from app.db import SessionLocal
from app.models import TicketHistory


class TicketHistoryData(TypedDict):
    id: int
    customer_id: int
    title: str
    description: str
    created_at: datetime
    updated_at: datetime
    status: str
    category: str | None
    updated_by: str | None
    resolution_summery: str | None


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


def get_ticket_history_data_by_id(ticket_id: int) -> TicketHistoryData | None:
    db = SessionLocal()
    try:
        ticket = db.get(TicketHistory, ticket_id)
        if ticket is None:
            return None
        return _ticket_to_data(ticket)
    finally:
        db.close()


def get_first_ticket_history_data() -> TicketHistoryData | None:
    db = SessionLocal()
    try:
        ticket = db.scalars(select(TicketHistory).order_by(TicketHistory.id)).first()
        if ticket is None:
            return None
        return _ticket_to_data(ticket)
    finally:
        db.close()
