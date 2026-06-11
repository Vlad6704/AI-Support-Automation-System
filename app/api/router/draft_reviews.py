from fastapi import APIRouter, HTTPException, status
from fastapi.encoders import jsonable_encoder

from app.agents.main_agent_invocation import get_ticket_thread_state
from app.api.providers import DraftReviewServiceProvider, TicketAgentServiceProvider
from app.enums import DraftReviewStatus
from app.schemas import (
    DraftReviewDetail,
    DraftReviewHistoryItem,
    DraftReviewSummary,
    MessageResponse,
    SubmitDraftReviewRequest,
    SubmitDraftReviewResponse,
)
from app.services import DraftReviewNotFoundError

router = APIRouter(prefix="/api/draft-reviews", tags=["draft-reviews"])


@router.get("", response_model=list[DraftReviewSummary])
def list_open_draft_reviews(
    service: DraftReviewServiceProvider,
) -> list[DraftReviewSummary]:
    return [
        DraftReviewSummary(
            id=review.id,
            previous_review_id=review.previous_review_id,
            ticket_id=review.ticket_id,
            customer_id=review.customer_id,
            ticket_title=ticket.title,
            original_draft=review.original_draft,
            created_at=review.created_at,
            updated_at=review.updated_at,
            status=review.status,
        )
        for review, ticket in service.list_open_reviews()
    ]


@router.get("/{review_id}", response_model=DraftReviewDetail)
def get_draft_review(
    review_id: int,
    service: DraftReviewServiceProvider,
) -> DraftReviewDetail:
    try:
        review, ticket = service.get_review_with_ticket(review_id)
    except DraftReviewNotFoundError as error:
        raise HTTPException(status_code=404, detail="Draft review not found") from error
    return DraftReviewDetail(
        id=review.id,
        previous_review_id=review.previous_review_id,
        ticket_id=review.ticket_id,
        customer_id=review.customer_id,
        ticket_title=ticket.title,
        ticket_description=ticket.description,
        original_draft=review.original_draft,
        edited_draft=review.edited_draft,
        created_at=review.created_at,
        updated_at=review.updated_at,
        updated_by=review.updated_by,
        reviewer_notes=review.reviewer_notes,
        guardrail_feedback=review.guardrail_feedback,
        status=review.status,
        history=[
            DraftReviewHistoryItem(
                id=item.id,
                previous_review_id=item.previous_review_id,
                original_draft=item.original_draft,
                edited_draft=item.edited_draft,
                reviewer_notes=item.reviewer_notes,
                guardrail_feedback=item.guardrail_feedback,
                updated_by=item.updated_by,
                created_at=item.created_at,
                updated_at=item.updated_at,
                status=item.status,
            )
            for item in service.list_review_history(review.id)
        ],
        agent_state=jsonable_encoder(get_ticket_thread_state(ticket.id)),
    )


@router.post(
    "/{review_id}/submit",
    response_model=SubmitDraftReviewResponse,
    status_code=status.HTTP_200_OK,
)
def submit_draft_review(
    review_id: int,
    request: SubmitDraftReviewRequest,
    review_service: DraftReviewServiceProvider,
    agent_service: TicketAgentServiceProvider,
) -> SubmitDraftReviewResponse:
    try:
        review, _ = review_service.get_review_with_ticket(review_id)
    except DraftReviewNotFoundError as error:
        raise HTTPException(status_code=404, detail="Draft review not found") from error
    if review.status != DraftReviewStatus.OPEN:
        raise HTTPException(status_code=409, detail="Draft review is already closed")

    message = agent_service.resume_review_and_store_response(
        review.ticket_id,
        review_id=review.id,
        edited_draft=request.edited_draft,
        reviewer_notes=request.reviewer_notes,
        updated_by=request.updated_by,
    )
    response_message = (
        MessageResponse.model_validate(message, from_attributes=True)
        if message is not None
        else None
    )
    return SubmitDraftReviewResponse(
        completed=response_message is not None,
        message=response_message,
    )
