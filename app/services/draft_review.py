from collections.abc import Callable
from contextlib import AbstractContextManager, contextmanager
from datetime import datetime, timezone
from typing import Iterator

from sqlalchemy.orm import Session, sessionmaker

from app.db import SessionLocal
from app.enums import DraftReviewStatus
from app.models import DraftReview, TicketHistory
from app.repositories.draft_review_repository import (
    DatabaseDraftReviewRepository,
    DraftReviewRepository,
)
from app.services.exceptions import DraftReviewNotFoundError

RepositoryFactory = Callable[[], AbstractContextManager[DraftReviewRepository]]


class DraftReviewService:
    def __init__(self, repository_factory: RepositoryFactory) -> None:
        self.repository_factory = repository_factory

    @classmethod
    def database(
        cls,
        session_factory: sessionmaker[Session] = SessionLocal,
    ) -> "DraftReviewService":
        @contextmanager
        def repository_factory() -> Iterator[DatabaseDraftReviewRepository]:
            db = session_factory()
            try:
                yield DatabaseDraftReviewRepository(db)
            finally:
                db.close()

        return cls(repository_factory)

    @classmethod
    def in_memory(cls) -> "DraftReviewService":
        repository = InMemoryDraftReviewRepository()

        @contextmanager
        def repository_factory() -> Iterator[InMemoryDraftReviewRepository]:
            yield repository

        return cls(repository_factory)

    def list_open_reviews(self) -> list[tuple[DraftReview, TicketHistory]]:
        with self.repository_factory() as repository:
            return repository.list_open_reviews()

    def get_review_with_ticket(
        self,
        review_id: int,
    ) -> tuple[DraftReview, TicketHistory]:
        with self.repository_factory() as repository:
            row = repository.get_review_with_ticket(review_id)
        if row is None:
            raise DraftReviewNotFoundError(f"Draft review {review_id} does not exist.")
        return row

    def list_review_history(self, review_id: int) -> list[DraftReview]:
        with self.repository_factory() as repository:
            history = repository.list_review_history(review_id)
        if not history:
            raise DraftReviewNotFoundError(f"Draft review {review_id} does not exist.")
        return history

    def get_or_create_open_review(
        self,
        *,
        ticket_id: int,
        customer_id: int,
        original_draft: str,
        guardrail_feedback: str | None,
    ) -> DraftReview:
        with self.repository_factory() as repository:
            review = repository.get_open_review_for_ticket(ticket_id)
            if review is not None:
                return review
            previous_review = repository.get_latest_review_for_ticket(ticket_id)
            return repository.create_review(
                ticket_id=ticket_id,
                customer_id=customer_id,
                original_draft=original_draft,
                previous_review_id=previous_review.id if previous_review else None,
                guardrail_feedback=guardrail_feedback,
            )

    def submit_review(
        self,
        review_id: int,
        *,
        edited_draft: str,
        reviewer_notes: str | None,
        updated_by: str,
    ) -> DraftReview:
        with self.repository_factory() as repository:
            review = repository.submit_review(
                review_id,
                edited_draft=edited_draft,
                reviewer_notes=reviewer_notes,
                updated_by=updated_by,
            )
        if review is None:
            raise DraftReviewNotFoundError(f"Draft review {review_id} does not exist.")
        return review

    def close_review(
        self,
        review_id: int,
        *,
        guardrail_feedback: str | None = None,
    ) -> DraftReview:
        with self.repository_factory() as repository:
            review = repository.close_review(
                review_id,
                guardrail_feedback=guardrail_feedback,
            )
        if review is None:
            raise DraftReviewNotFoundError(f"Draft review {review_id} does not exist.")
        return review


class InMemoryDraftReviewRepository:
    def __init__(self) -> None:
        self.reviews: list[DraftReview] = []

    def list_open_reviews(self) -> list[tuple[DraftReview, TicketHistory]]:
        return []

    def get_review(self, review_id: int) -> DraftReview | None:
        return next((review for review in self.reviews if review.id == review_id), None)

    def get_review_with_ticket(
        self,
        review_id: int,
    ) -> tuple[DraftReview, TicketHistory] | None:
        return None

    def get_open_review_for_ticket(self, ticket_id: int) -> DraftReview | None:
        return next(
            (
                review
                for review in reversed(self.reviews)
                if review.ticket_id == ticket_id
                and review.status == DraftReviewStatus.OPEN
            ),
            None,
        )

    def get_latest_review_for_ticket(self, ticket_id: int) -> DraftReview | None:
        return next(
            (review for review in reversed(self.reviews) if review.ticket_id == ticket_id),
            None,
        )

    def list_review_history(self, review_id: int) -> list[DraftReview]:
        history: list[DraftReview] = []
        review = self.get_review(review_id)
        while review is not None:
            history.append(review)
            review = (
                self.get_review(review.previous_review_id)
                if review.previous_review_id is not None
                else None
            )
        history.reverse()
        return history

    def create_review(
        self,
        *,
        ticket_id: int,
        customer_id: int,
        original_draft: str,
        previous_review_id: int | None,
        guardrail_feedback: str | None,
    ) -> DraftReview:
        now = datetime.now(timezone.utc)
        review = DraftReview(
            id=len(self.reviews) + 1,
            ticket_id=ticket_id,
            customer_id=customer_id,
            original_draft=original_draft,
            previous_review_id=previous_review_id,
            created_at=now,
            updated_at=now,
            guardrail_feedback=guardrail_feedback,
            status=DraftReviewStatus.OPEN,
        )
        self.reviews.append(review)
        return review

    def submit_review(
        self,
        review_id: int,
        *,
        edited_draft: str,
        reviewer_notes: str | None,
        updated_by: str,
    ) -> DraftReview | None:
        review = self.get_review(review_id)
        if review is not None:
            review.edited_draft = edited_draft
            review.reviewer_notes = reviewer_notes
            review.updated_by = updated_by
        return review

    def close_review(
        self,
        review_id: int,
        *,
        guardrail_feedback: str | None = None,
    ) -> DraftReview | None:
        review = self.get_review(review_id)
        if review is not None:
            review.status = DraftReviewStatus.CLOSED
            if guardrail_feedback is not None:
                review.guardrail_feedback = guardrail_feedback
        return review
