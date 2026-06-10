from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.repositories import (
    DatabaseTicketConversationRepository,
    database_ticket_conversation_repository,
)
from app.services import TicketAgentService, TicketConversationService


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
