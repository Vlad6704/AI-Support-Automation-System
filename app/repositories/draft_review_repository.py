from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import DraftReviewStatus
from app.models import DraftReview, TicketHistory


class DraftReviewRepository(Protocol):
    def list_open_reviews(self) -> list[tuple[DraftReview, TicketHistory]]: ...

    def get_review(self, review_id: int) -> DraftReview | None: ...

    def get_review_with_ticket(
        self,
        review_id: int,
    ) -> tuple[DraftReview, TicketHistory] | None: ...

    def get_open_review_for_ticket(self, ticket_id: int) -> DraftReview | None: ...

    def get_latest_review_for_ticket(self, ticket_id: int) -> DraftReview | None: ...

    def list_review_history(self, review_id: int) -> list[DraftReview]: ...

    def create_review(
        self,
        *,
        ticket_id: int,
        customer_id: int,
        original_draft: str,
        previous_review_id: int | None,
        guardrail_feedback: str | None,
    ) -> DraftReview: ...

    def submit_review(
        self,
        review_id: int,
        *,
        edited_draft: str,
        reviewer_notes: str | None,
        updated_by: str,
    ) -> DraftReview | None: ...

    def close_review(
        self,
        review_id: int,
        *,
        guardrail_feedback: str | None = None,
    ) -> DraftReview | None: ...


class DatabaseDraftReviewRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_open_reviews(self) -> list[tuple[DraftReview, TicketHistory]]:
        rows = self.db.execute(
            select(DraftReview, TicketHistory)
            .join(TicketHistory, TicketHistory.id == DraftReview.ticket_id)
            .where(DraftReview.status == DraftReviewStatus.OPEN)
            .order_by(DraftReview.updated_at.desc(), DraftReview.id.desc())
        ).all()
        return [
            (review, ticket)
            for review, ticket in rows
        ]

    def get_review(self, review_id: int) -> DraftReview | None:
        return self.db.get(DraftReview, review_id)

    def get_review_with_ticket(
        self,
        review_id: int,
    ) -> tuple[DraftReview, TicketHistory] | None:
        row = self.db.execute(
            select(DraftReview, TicketHistory)
            .join(TicketHistory, TicketHistory.id == DraftReview.ticket_id)
            .where(DraftReview.id == review_id)
        ).one_or_none()
        return (row[0], row[1]) if row is not None else None

    def get_open_review_for_ticket(self, ticket_id: int) -> DraftReview | None:
        return self.db.scalars(
            select(DraftReview)
            .where(
                DraftReview.ticket_id == ticket_id,
                DraftReview.status == DraftReviewStatus.OPEN,
            )
            .order_by(DraftReview.id.desc())
        ).first()

    def get_latest_review_for_ticket(self, ticket_id: int) -> DraftReview | None:
        return self.db.scalars(
            select(DraftReview)
            .where(DraftReview.ticket_id == ticket_id)
            .order_by(DraftReview.id.desc())
        ).first()

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
        review = DraftReview(
            ticket_id=ticket_id,
            customer_id=customer_id,
            original_draft=original_draft,
            previous_review_id=previous_review_id,
            guardrail_feedback=guardrail_feedback,
            status=DraftReviewStatus.OPEN,
        )
        self.db.add(review)
        self.db.commit()
        self.db.refresh(review)
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
        if review is None:
            return None
        review.edited_draft = edited_draft
        review.updated_by = updated_by
        if reviewer_notes is not None:
            review.reviewer_notes = reviewer_notes
        self.db.commit()
        self.db.refresh(review)
        return review

    def close_review(
        self,
        review_id: int,
        *,
        guardrail_feedback: str | None = None,
    ) -> DraftReview | None:
        review = self.get_review(review_id)
        if review is None:
            return None
        review.status = DraftReviewStatus.CLOSED
        if guardrail_feedback is not None:
            review.guardrail_feedback = guardrail_feedback
        self.db.commit()
        self.db.refresh(review)
        return review
