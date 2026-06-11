from dataclasses import dataclass, field
from typing import Protocol

from app.models import DraftReview
from app.repositories import (
    AgentRepository,
    DatabaseAgentRepository,
    StubAgentRepository,
)


class DraftReviewOperations(Protocol):
    def get_or_create_open_review(
        self,
        *,
        ticket_id: int,
        customer_id: int,
        original_draft: str,
        guardrail_feedback: str | None,
    ) -> DraftReview: ...

    def submit_review(
        self,
        review_id: int,
        *,
        edited_draft: str,
        reviewer_notes: str | None,
        updated_by: str,
    ) -> DraftReview: ...

    def close_review(
        self,
        review_id: int,
        *,
        guardrail_feedback: str | None = None,
    ) -> DraftReview: ...


def create_in_memory_draft_review_service() -> DraftReviewOperations:
    from app.services.draft_review import DraftReviewService

    return DraftReviewService.in_memory()


@dataclass(frozen=True)
class AgentContext:
    repository: AgentRepository
    draft_review_service: DraftReviewOperations = field(
        default_factory=create_in_memory_draft_review_service
    )


def create_stub_agent_context(world: str = "world_1") -> AgentContext:
    from app.services.draft_review import DraftReviewService

    return AgentContext(
        repository=StubAgentRepository(world),
        draft_review_service=DraftReviewService.in_memory(),
    )


def create_database_agent_context() -> AgentContext:
    from app.services.draft_review import DraftReviewService

    return AgentContext(
        repository=DatabaseAgentRepository(),
        draft_review_service=DraftReviewService.database(),
    )
