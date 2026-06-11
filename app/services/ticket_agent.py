from collections.abc import Callable
from contextlib import AbstractContextManager
import logging
from time import perf_counter

from langchain.messages import AIMessage

from app.agents.context import create_database_agent_context
from app.agents.main_agent import MainAgentState
from app.agents.main_agent_invocation import (
    delete_ticket_thread,
    invoke_main_agent_for_ticket,
    resume_main_agent_review,
    ticket_thread_is_interrupted,
)
from app.enums import MessageSource
from app.models import Message
from app.repositories import (
    DatabaseTicketConversationRepository,
    TicketConversationRepository,
    database_ticket_conversation_repository,
)
from app.services.exceptions import TicketNotFoundError

logger = logging.getLogger(__name__)


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
    ) -> Message | None:
        started_at = perf_counter()
        logger.info(
            "Agent response started ticket_id=%s new_thread=%s",
            ticket_id,
            new_thread,
        )
        if new_thread:
            delete_ticket_thread(ticket_id)
        result = invoke_main_agent_for_ticket(
            ticket_id,
            context=create_database_agent_context(),
        )
        if ticket_thread_is_interrupted(ticket_id):
            logger.info("Agent response awaiting review ticket_id=%s", ticket_id)
            return None

        with self.repository_factory() as repository:
            message = self._store_response(repository, ticket_id, result)
        logger.info(
            "Agent response stored ticket_id=%s message_id=%s duration_ms=%.2f",
            ticket_id,
            message.id,
            (perf_counter() - started_at) * 1000,
        )
        return message

    def resume_review_and_store_response(
        self,
        ticket_id: int,
        *,
        review_id: int,
        edited_draft: str,
        reviewer_notes: str | None,
        updated_by: str,
    ) -> Message | None:
        result = resume_main_agent_review(
            ticket_id,
            review_id=review_id,
            edited_draft=edited_draft,
            reviewer_notes=reviewer_notes,
            updated_by=updated_by,
            context=create_database_agent_context(),
        )
        if ticket_thread_is_interrupted(ticket_id):
            return None
        with self.repository_factory() as repository:
            return self._store_response(repository, ticket_id, result)

    @staticmethod
    def _store_response(
        repository: TicketConversationRepository,
        ticket_id: int,
        result: MainAgentState,
    ) -> Message:
        ticket = repository.get_ticket(ticket_id)
        if ticket is None:
            logger.warning("Cannot store agent response; ticket missing ticket_id=%s", ticket_id)
            raise TicketNotFoundError(f"Ticket {ticket_id} does not exist.")

        messages = result.get("messages") or []
        final_message = messages[-1] if messages else None
        response = (
            final_message.content.strip()
            if isinstance(final_message, AIMessage)
            and isinstance(final_message.content, str)
            else ""
        )
        if not response:
            raise ValueError(f"Agent returned no final response for ticket {ticket_id}.")

        return repository.create_message(
            customer_id=ticket.customer_id,
            ticket_id=ticket.id,
            message=response,
            source=MessageSource.SUPPORT_TEAM,
        )


def run_agent_and_store_ticket_response(
    ticket_id: int,
    *,
    new_thread: bool = False,
) -> Message | None:
    return TicketAgentService(
        database_ticket_conversation_repository
    ).run_and_store_response(ticket_id, new_thread=new_thread)
