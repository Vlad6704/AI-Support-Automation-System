from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.enums import DraftReviewStatus
from app.schemas.conversations import MessageResponse, NonBlankString


class DraftReviewSummary(BaseModel):
    id: int
    previous_review_id: int | None
    ticket_id: int
    customer_id: int
    ticket_title: str
    original_draft: str
    created_at: datetime
    updated_at: datetime
    status: DraftReviewStatus


class DraftReviewHistoryItem(BaseModel):
    id: int
    previous_review_id: int | None
    original_draft: str
    edited_draft: str | None
    reviewer_notes: str | None
    guardrail_feedback: str | None
    updated_by: str | None
    created_at: datetime
    updated_at: datetime
    status: DraftReviewStatus


class DraftReviewDetail(DraftReviewSummary):
    ticket_description: str
    edited_draft: str | None
    updated_by: str | None
    reviewer_notes: str | None
    guardrail_feedback: str | None
    history: list[DraftReviewHistoryItem]
    agent_state: dict[str, Any]


class SubmitDraftReviewRequest(BaseModel):
    edited_draft: NonBlankString = Field(max_length=10_000)
    reviewer_notes: str | None = Field(default=None, max_length=10_000)
    updated_by: NonBlankString = Field(default="support_team", max_length=255)


class SubmitDraftReviewResponse(BaseModel):
    completed: bool
    message: MessageResponse | None
