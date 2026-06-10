from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from app.api.providers import TicketConversationServiceProvider
from app.models import Customer, Message, TicketHistory
from app.schemas import (
    ConversationResponse,
    CreateMessageRequest,
    CreateTicketRequest,
    CreateTicketResponse,
    CustomerOption,
    MessageResponse,
    TicketResponse,
    TicketSummary,
)
from app.services import (
    AgentResponseError,
    ConversationMessages,
    CustomerNotFoundError,
    run_agent_and_store_ticket_response,
    TicketNotFoundError,
    TicketSummaryData,
)

router = APIRouter(prefix="/api", tags=["conversations"])


@router.get("/customers", response_model=list[CustomerOption])
def list_customers(
    service: TicketConversationServiceProvider,
) -> list[Customer]:
    return service.list_customers()


@router.get("/tickets", response_model=list[TicketSummary])
def list_tickets(
    service: TicketConversationServiceProvider,
) -> list[TicketSummaryData]:
    return service.list_tickets()


@router.post(
    "/tickets",
    response_model=CreateTicketResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_ticket(
    request: CreateTicketRequest,
    background_tasks: BackgroundTasks,
    service: TicketConversationServiceProvider,
) -> CreateTicketResponse:
    try:
        ticket = service.create_ticket(
            customer_id=request.customer_id,
            title=request.title,
            description=request.description,
        )
    except CustomerNotFoundError as error:
        raise HTTPException(
            status_code=422,
            detail="Customer does not exist",
        ) from error

    background_tasks.add_task(
        run_agent_and_store_ticket_response,
        ticket.id,
        new_thread=True,
    )
    return CreateTicketResponse(id=ticket.id)


@router.get("/tickets/{ticket_id}", response_model=TicketResponse)
def get_ticket(
    ticket_id: int,
    service: TicketConversationServiceProvider,
) -> TicketHistory:
    try:
        return service.get_ticket(ticket_id)
    except TicketNotFoundError as error:
        raise HTTPException(status_code=404, detail="Ticket not found") from error


@router.get("/tickets/{ticket_id}/messages", response_model=list[MessageResponse])
def list_messages(
    ticket_id: int,
    service: TicketConversationServiceProvider,
) -> list[Message]:
    try:
        return service.list_messages(ticket_id)
    except TicketNotFoundError as error:
        raise HTTPException(status_code=404, detail="Ticket not found") from error


@router.post(
    "/tickets/{ticket_id}/messages",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user_message(
    ticket_id: int,
    request: CreateMessageRequest,
    service: TicketConversationServiceProvider,
) -> ConversationMessages:
    try:
        return service.create_user_message(
            ticket_id,
            message=request.message,
        )
    except TicketNotFoundError as error:
        raise HTTPException(status_code=404, detail="Ticket not found") from error
    except AgentResponseError as error:
        raise HTTPException(
            status_code=500,
            detail="Agent response failed",
        ) from error
