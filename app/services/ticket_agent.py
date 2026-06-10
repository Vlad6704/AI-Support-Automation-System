from collections.abc import Callable
from contextlib import AbstractContextManager

from app.agents.context import create_database_agent_context
from app.agents.main_agent_invocation import (
    delete_ticket_thread,
    invoke_main_agent_for_ticket,
)
from app.enums import MessageSource
from app.models import Message
from app.repositories import (
    DatabaseTicketConversationRepository,
    TicketConversationRepository,
    database_ticket_conversation_repository,
)
from app.services.exceptions import TicketNotFoundError


RepositoryContextFactory = Callable[
    [],
    AbstractContextManager[DatabaseTicketConversationRepository],
]


class TicketAgentService:
    def __init__(
        self,
        repository_factory: RepositoryContextFactory,
    ) -> None:
        self.repository_factory = repository_factory

    def run_and_store_response(
        self,
        ticket_id: int,
        *,
        new_thread: bool = False,
    ) -> Message:
        if new_thread:
            delete_ticket_thread(ticket_id)
        result = invoke_main_agent_for_ticket(
            ticket_id,
            context=create_database_agent_context(),
        )
        draft_response = str(result.get("draft_response") or "").strip()
        if not draft_response:
            raise ValueError(f"Agent returned no draft response for ticket {ticket_id}.")

        with self.repository_factory() as repository:
            return self._store_response(repository, ticket_id, draft_response)

    @staticmethod
    def _store_response(
        repository: TicketConversationRepository,
        ticket_id: int,
        draft_response: str,
    ) -> Message:
        ticket = repository.get_ticket(ticket_id)
        if ticket is None:
            raise TicketNotFoundError(f"Ticket {ticket_id} does not exist.")

        return repository.create_message(
            customer_id=ticket.customer_id,
            ticket_id=ticket.id,
            message=draft_response,
            source=MessageSource.SUPPORT_TEAM,
        )


def run_agent_and_store_ticket_response(
    ticket_id: int,
    *,
    new_thread: bool = False,
) -> Message:
    return TicketAgentService(
        database_ticket_conversation_repository
    ).run_and_store_response(ticket_id, new_thread=new_thread)
