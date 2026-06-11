from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.repositories import (
    DatabaseTicketConversationRepository,
    DatabaseDraftReviewRepository,
    database_ticket_conversation_repository,
)
from app.services import DraftReviewService, TicketAgentService, TicketConversationService


def get_ticket_conversation_service(
    db: Session = Depends(get_db),
) -> TicketConversationService:
    return TicketConversationService(
        DatabaseTicketConversationRepository(db),
        TicketAgentService(database_ticket_conversation_repository),
    )


TicketConversationServiceProvider = Annotated[
    TicketConversationService,
    Depends(get_ticket_conversation_service),
]


def get_draft_review_service(
    db: Session = Depends(get_db),
) -> DraftReviewService:
    @contextmanager
    def repository_factory() -> Iterator[DatabaseDraftReviewRepository]:
        yield DatabaseDraftReviewRepository(db)

    return DraftReviewService(repository_factory)


def get_ticket_agent_service() -> TicketAgentService:
    return TicketAgentService(database_ticket_conversation_repository)


DraftReviewServiceProvider = Annotated[
    DraftReviewService,
    Depends(get_draft_review_service),
]
TicketAgentServiceProvider = Annotated[
    TicketAgentService,
    Depends(get_ticket_agent_service),
]
