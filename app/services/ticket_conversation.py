from dataclasses import dataclass
from datetime import datetime

from app.enums import MessageSource
from app.models import Customer, Message, TicketHistory
from app.repositories import TicketConversationRepository
from app.services.exceptions import (
    AgentResponseError,
    CustomerNotFoundError,
    TicketNotFoundError,
)
from app.services.ticket_agent import TicketAgentService


@dataclass(frozen=True)
class TicketSummaryData:
    id: int
    title: str
    updated_at: datetime


@dataclass(frozen=True)
class ConversationMessages:
    user_message: Message
    agent_message: Message


class TicketConversationService:
    def __init__(
        self,
        repository: TicketConversationRepository,
        ticket_agent_service: TicketAgentService,
    ) -> None:
        self.repository = repository
        self.ticket_agent_service = ticket_agent_service

    def list_customers(self) -> list[Customer]:
        return self.repository.list_customers()

    def list_tickets(self) -> list[TicketSummaryData]:
        rows = self.repository.list_tickets()
        return [
            TicketSummaryData(
                id=ticket.id,
                title=ticket.title,
                updated_at=message_at or ticket.updated_at,
            )
            for ticket, message_at in rows
        ]

    def create_ticket(
        self,
        *,
        customer_id: int,
        title: str,
        description: str,
    ) -> TicketHistory:
        if self.repository.get_customer(customer_id) is None:
            raise CustomerNotFoundError(f"Customer {customer_id} does not exist.")

        return self.repository.create_ticket(
            customer_id=customer_id,
            title=title,
            description=description,
            status="open",
            updated_by="customer",
            initial_message_source=MessageSource.USER,
        )

    def get_ticket(self, ticket_id: int) -> TicketHistory:
        ticket = self.repository.get_ticket(ticket_id)
        if ticket is None:
            raise TicketNotFoundError(f"Ticket {ticket_id} does not exist.")
        return ticket

    def list_messages(self, ticket_id: int) -> list[Message]:
        self.get_ticket(ticket_id)
        return self.repository.list_messages(ticket_id)

    def create_user_message(
        self,
        ticket_id: int,
        *,
        message: str,
    ) -> ConversationMessages:
        ticket = self.get_ticket(ticket_id)
        user_message = self.repository.create_message(
            customer_id=ticket.customer_id,
            ticket_id=ticket.id,
            message=message,
            source=MessageSource.USER,
        )

        try:
            agent_message = self.ticket_agent_service.run_and_store_response(ticket.id)
        except Exception as error:
            raise AgentResponseError(
                f"Agent response failed for ticket {ticket.id}."
            ) from error
        return ConversationMessages(
            user_message=user_message,
            agent_message=agent_message,
        )
