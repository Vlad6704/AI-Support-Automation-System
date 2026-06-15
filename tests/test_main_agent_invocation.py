import unittest
from unittest.mock import Mock, patch

from app.agents.context import AgentContext
from app.agents.main_agent import MainAgentState
from app.agents.main_agent_invocation import (
    _invoke,
    _review_metrics,
    invoke_existing_ticket_thread,
    invoke_main_agent_for_ticket,
    invoke_new_ticket_thread,
    resume_main_agent_review,
)
from app.enums import AgentRunHumanReviewResult, AgentRunOutcome


class MainAgentInvocationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = Mock()
        self.context = AgentContext(repository=self.repository)
        self.ticket: MainAgentState = {
            "id": 5,
            "customer_id": 2,
            "title": "Webhook events contain incorrect data",
            "description": "Please investigate.",
        }

    @patch("app.agents.main_agent_invocation._invoke")
    def test_new_thread_uses_full_ticket_state(self, invoke: Mock) -> None:
        invoke.return_value = {"id": 5}

        result = invoke_new_ticket_thread(self.ticket, context=self.context)

        self.assertEqual(result, {"id": 5})
        invoke.assert_called_once_with(
            self.ticket,
            ticket_data=self.ticket,
            context=self.context,
        )
        self.repository.get_latest_user_message.assert_not_called()

    @patch("app.agents.main_agent_invocation._invoke")
    def test_existing_thread_uses_latest_user_message(self, invoke: Mock) -> None:
        self.repository.get_latest_user_message.return_value = {
            "message": "The amount should be 120.50."
        }
        invoke.return_value = {"id": 5}

        result = invoke_existing_ticket_thread(self.ticket, context=self.context)

        self.assertEqual(result, {"id": 5})
        input_data = invoke.call_args.args[0]
        self.assertEqual(input_data["messages"][0].content, "The amount should be 120.50.")
        self.repository.get_latest_user_message.assert_called_once_with(5)

    @patch("app.agents.main_agent_invocation.invoke_new_ticket_thread")
    @patch("app.agents.main_agent_invocation.ticket_thread_exists", return_value=False)
    def test_invokes_ticket_with_stable_thread_id(
        self,
        _: Mock,
        invoke_new: Mock,
    ) -> None:
        self.repository.get_ticket_by_id.return_value = self.ticket
        invoke_new.return_value = {"id": 5}

        result = invoke_main_agent_for_ticket(5, context=self.context)

        self.assertEqual(result, {"id": 5})
        invoke_new.assert_called_once_with(self.ticket, context=self.context)

    @patch("app.agents.main_agent_invocation.invoke_graph_with_langfuse")
    def test_trace_metadata_identifies_ticket_and_customer(self, invoke: Mock) -> None:
        self.repository.start_agent_run.return_value = 12
        invoke.return_value = {
            "id": 5,
            "intent": "support",
            "category": "webhook",
        }

        _invoke(self.ticket, ticket_data=self.ticket, context=self.context)

        metadata = invoke.call_args.kwargs["metadata"]
        self.assertEqual(metadata["ticket_id"], 5)
        self.assertEqual(metadata["customer_id"], 2)
        self.assertEqual(metadata["agent_run_id"], 12)
        self.assertEqual(
            invoke.call_args.kwargs["trace_id"],
            self.repository.start_agent_run.call_args.kwargs["trace_id"],
        )
        self.repository.finish_agent_run.assert_called_once_with(
            run_id=12,
            ticket_id=5,
            outcome=AgentRunOutcome.AUTOMATED,
            draft_risk=None,
            guardrail_passed=None,
            human_review_required=False,
            human_review_result=None,
            edit_percentage=None,
            event_type="response_sent",
            event_payload={"outcome": "automated"},
        )

    @patch("app.agents.main_agent_invocation.invoke_graph_with_langfuse")
    def test_records_review_interruption(self, invoke: Mock) -> None:
        self.repository.start_agent_run.return_value = 13
        invoke.return_value = {
            "id": 5,
            "intent": "support",
            "category": "webhook",
            "draft_risk": "high",
            "__interrupt__": ("review",),
        }

        _invoke(self.ticket, ticket_data=self.ticket, context=self.context)

        self.repository.finish_agent_run.assert_called_once_with(
            run_id=13,
            ticket_id=5,
            outcome=AgentRunOutcome.AWAITING_REVIEW,
            draft_risk="high",
            guardrail_passed=None,
            human_review_required=True,
            human_review_result=None,
            edit_percentage=None,
            event_type="review_requested",
            event_payload={"outcome": "awaiting_review"},
        )

    @patch("app.agents.main_agent_invocation.invoke_graph_with_langfuse")
    def test_records_unsupported_request(self, invoke: Mock) -> None:
        self.repository.start_agent_run.return_value = 15
        invoke.return_value = {
            "id": 5,
            "intent": "support",
            "category": "other",
        }

        _invoke(self.ticket, ticket_data=self.ticket, context=self.context)

        self.repository.finish_agent_run.assert_called_once_with(
            run_id=15,
            ticket_id=5,
            outcome=AgentRunOutcome.UNSUPPORTED,
            draft_risk=None,
            guardrail_passed=None,
            human_review_required=False,
            human_review_result=None,
            edit_percentage=None,
            event_type="response_sent",
            event_payload={"outcome": "unsupported"},
        )

    @patch("app.agents.main_agent_invocation.invoke_graph_with_langfuse")
    def test_records_failed_invocation(self, invoke: Mock) -> None:
        self.repository.start_agent_run.return_value = 14
        invoke.side_effect = RuntimeError("model unavailable")

        with self.assertRaisesRegex(RuntimeError, "model unavailable"):
            _invoke(self.ticket, ticket_data=self.ticket, context=self.context)

        self.repository.finish_agent_run.assert_called_once_with(
            run_id=14,
            ticket_id=5,
            outcome=AgentRunOutcome.FAILED,
            draft_risk=None,
            guardrail_passed=None,
            human_review_required=False,
            human_review_result=None,
            edit_percentage=None,
            event_type="agent_failed",
            event_payload={"error_type": "RuntimeError"},
        )

    def test_review_metrics_accepts_unchanged_draft(self) -> None:
        result, percentage = _review_metrics("Same draft", "Same draft")

        self.assertEqual(result, AgentRunHumanReviewResult.ACCEPTED_WITHOUT_EDITING)
        self.assertEqual(percentage, 0.0)

    def test_review_metrics_calculates_normalized_difference(self) -> None:
        result, percentage = _review_metrics("abc", "xyz")

        self.assertEqual(result, AgentRunHumanReviewResult.EDITED)
        self.assertEqual(percentage, 1.0)

    @patch("app.agents.main_agent_invocation._invoke")
    @patch("app.agents.main_agent_invocation.get_ticket_thread_state")
    def test_resume_records_review_metrics_on_original_run(
        self,
        get_state: Mock,
        invoke: Mock,
    ) -> None:
        self.repository.get_ticket_by_id.return_value = self.ticket
        get_state.return_value = {"draft_response": "Original draft"}
        invoke.return_value = {"id": 5}

        result = resume_main_agent_review(
            5,
            review_id=9,
            edited_draft="Edited draft",
            reviewer_notes=None,
            updated_by="reviewer",
            context=self.context,
        )

        self.assertEqual(result, {"id": 5})
        review_call = self.repository.record_agent_run_human_review.call_args.kwargs
        self.assertEqual(review_call["ticket_id"], 5)
        self.assertEqual(
            review_call["human_review_result"],
            AgentRunHumanReviewResult.EDITED,
        )
        self.assertGreater(review_call["edit_percentage"], 0)


if __name__ == "__main__":
    unittest.main()
