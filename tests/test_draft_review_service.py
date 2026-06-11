import unittest

from app.enums import DraftReviewStatus
from app.services.draft_review import DraftReviewService


class DraftReviewServiceTests(unittest.TestCase):
    def test_get_or_create_open_review_is_idempotent(self) -> None:
        service = DraftReviewService.in_memory()

        first = service.get_or_create_open_review(
            ticket_id=1,
            customer_id=2,
            original_draft="Original draft",
            guardrail_feedback=None,
        )
        second = service.get_or_create_open_review(
            ticket_id=1,
            customer_id=2,
            original_draft="Another draft",
            guardrail_feedback=None,
        )

        self.assertEqual(first.id, second.id)

    def test_closed_review_is_replaced_by_new_open_review(self) -> None:
        service = DraftReviewService.in_memory()
        first = service.get_or_create_open_review(
            ticket_id=1,
            customer_id=2,
            original_draft="Original draft",
            guardrail_feedback=None,
        )
        service.close_review(
            first.id,
            guardrail_feedback="Guardrail rejected the edit.",
        )

        second = service.get_or_create_open_review(
            ticket_id=1,
            customer_id=2,
            original_draft="Edited draft",
            guardrail_feedback="Guardrail rejected the edit.",
        )

        self.assertEqual(first.status, DraftReviewStatus.CLOSED)
        self.assertIsNone(first.reviewer_notes)
        self.assertEqual(
            first.guardrail_feedback,
            "Guardrail rejected the edit.",
        )
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(second.previous_review_id, first.id)
        self.assertEqual(second.status, DraftReviewStatus.OPEN)

        history = service.list_review_history(second.id)
        self.assertEqual([review.id for review in history], [first.id, second.id])

    def test_reviewer_notes_do_not_replace_guardrail_feedback(self) -> None:
        service = DraftReviewService.in_memory()
        review = service.get_or_create_open_review(
            ticket_id=1,
            customer_id=2,
            original_draft="Original draft",
            guardrail_feedback="Initial guardrail feedback.",
        )

        service.submit_review(
            review.id,
            edited_draft="Edited draft",
            reviewer_notes="Reviewer explanation.",
            updated_by="maya@example.test",
        )

        self.assertEqual(review.reviewer_notes, "Reviewer explanation.")
        self.assertEqual(review.guardrail_feedback, "Initial guardrail feedback.")


if __name__ == "__main__":
    unittest.main()
