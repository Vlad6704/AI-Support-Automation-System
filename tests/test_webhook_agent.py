import unittest
from typing import Any, cast
from uuid import uuid4
from unittest.mock import Mock, patch

from langchain.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from app.agents.context import AgentContext
from app.agents.main_agent import (
    CHECKPOINT_DB_PATH,
    DraftOutput,
    GuardrailOutput,
    IntentOutput,
    RiskOutput,
    graph,
    node_finalize_response,
    node_support_review,
    node_estimate_draft_risk,
    node_validate_draft_response,
    route_after_guardrail,
    route_after_intent,
)
from app.agents.webhook_agent.nodes import node_get_customer_context


def command_update(command: Command[Any]) -> dict[str, Any]:
    return cast(dict[str, Any], command.update)


def required_state_value(state: dict[str, Any], key: str) -> Any:
    value = state.get(key)
    if value is None:
        raise AssertionError(f"Expected state value {key}.")
    return value


class WebhookAgentTests(unittest.TestCase):
    def test_main_agent_uses_sqlite_checkpointer(self) -> None:
        self.assertIsInstance(graph.checkpointer, SqliteSaver)
        self.assertEqual(CHECKPOINT_DB_PATH.name, "checkpoints.db")

    def test_support_webhook_routes_to_webhook_agent(self) -> None:
        route = route_after_intent({"intent": "support", "category": "webhooks"})
        self.assertEqual(route, "webhook_agent")

    def test_get_customer_context_stores_repository_result(self) -> None:
        repository = Mock()
        repository.get_customer_context.return_value = {"customer": {"id": 1}}
        runtime = Runtime(context=AgentContext(repository=repository))

        result = node_get_customer_context({"customer_id": 1}, runtime)

        self.assertEqual(result.get("customer_context"), {"customer": {"id": 1}})
        repository.get_customer_context.assert_called_once_with(1)

    @patch("app.agents.main_agent.init_chat_model")
    def test_invalid_draft_routes_back_with_guardrail_feedback(
        self,
        init_chat_model: Mock,
    ) -> None:
        structured_model = Mock()
        structured_model.invoke.return_value = GuardrailOutput(
            guardrail_decision="invalid",
            guardrail_message="The draft promises an unsupported refund.",
        )
        init_chat_model.return_value.with_structured_output.return_value = structured_model

        result = node_validate_draft_response(
            {
                "description": "Please refund this invoice.",
                "draft_response": "We have issued your refund.",
            }
        )

        self.assertEqual(route_after_guardrail(result), "draft_response")
        guardrail = required_state_value(cast(dict[str, Any], result), "draft_guardrail")
        self.assertEqual(guardrail["decision"], "invalid")
        self.assertIn("unsupported refund", guardrail["message"])

    @patch("app.agents.main_agent.init_chat_model")
    def test_valid_draft_routes_to_risk_estimation(
        self, init_chat_model: Mock
    ) -> None:
        structured_model = Mock()
        structured_model.invoke.return_value = GuardrailOutput(
            guardrail_decision="valid",
            guardrail_message="The draft is ready to send.",
        )
        init_chat_model.return_value.with_structured_output.return_value = structured_model

        result = node_validate_draft_response(
            {
                "description": "Webhook deliveries are failing.",
                "draft_response": "Please provide an affected event ID.",
            }
        )

        self.assertEqual(route_after_guardrail(result), "estimate_risk")
        guardrail = required_state_value(cast(dict[str, Any], result), "draft_guardrail")
        self.assertEqual(guardrail["decision"], "valid")
        guardrail_messages = structured_model.invoke.call_args.args[0]
        self.assertIn(
            "Approve the draft unless it contains a clear, material problem",
            guardrail_messages[0].content,
        )
        self.assertIn(
            "commitments to check or investigate",
            guardrail_messages[0].content,
        )

    @patch("app.agents.main_agent.init_chat_model")
    def test_estimate_draft_risk_stores_structured_result(
        self, init_chat_model: Mock
    ) -> None:
        structured_model = Mock()
        structured_model.invoke.return_value = RiskOutput(draft_risk="high")
        init_chat_model.return_value.with_structured_output.return_value = structured_model

        command = node_estimate_draft_risk(
            {
                "description": "An unauthorized user accessed my account.",
                "draft_response": "We are escalating this account-access issue.",
                "draft_guardrail": {
                    "decision": "valid",
                    "message": "The draft is ready to send.",
                },
            }
        )

        update = command_update(command)
        self.assertEqual(command.goto, "support_review")
        self.assertEqual(update["draft_risk"], "high")
        self.assertEqual(
            update["node_calls"]["node_estimate_draft_risk"]["result"],
            {"draft_risk": "high"},
        )

    def test_finalize_response_adds_message_and_clears_draft_fields(self) -> None:
        result = node_finalize_response(
            {
                "draft_response": "Final approved response.",
                "draft_guardrail": {
                    "decision": "valid",
                    "message": "Approved.",
                },
                "draft_risk": "low",
            }
        )

        result_dict = cast(dict[str, Any], result)
        self.assertEqual(result_dict["messages"][0].content, "Final approved response.")
        self.assertIsNone(result_dict["draft_response"])
        self.assertIsNone(result_dict["draft_guardrail"])
        self.assertIsNone(result_dict["draft_risk"])

    @patch("app.agents.main_agent.interrupt")
    def test_support_review_submits_edit_and_returns_to_guardrail(
        self,
        interrupt: Mock,
    ) -> None:
        interrupt.return_value = {
            "review_id": 1,
            "edited_draft": "Human-edited response.",
            "reviewer_notes": "Clarified the wording.",
            "updated_by": "maya@example.test",
        }
        runtime = Runtime(
            context=AgentContext(repository=Mock())
        )

        command = node_support_review(
            {
                "id": 10,
                "customer_id": 2,
                "draft_response": "Agent draft.",
                "draft_guardrail": {
                    "decision": "valid",
                    "message": "Approved.",
                },
            },
            runtime,
        )

        self.assertEqual(command.goto, "guardrail_output")
        update = command_update(command)
        self.assertEqual(update["draft_response"], "Human-edited response.")
        self.assertEqual(update["draft_review_id"], 1)

    @patch("app.agents.main_agent.init_chat_model")
    def test_high_risk_draft_interrupts_then_human_edit_is_finalized(
        self,
        init_chat_model: Mock,
    ) -> None:
        guardrails = iter(
            [
                GuardrailOutput(
                    guardrail_decision="valid",
                    guardrail_message="Approved.",
                ),
                GuardrailOutput(
                    guardrail_decision="valid",
                    guardrail_message="Approved after review.",
                ),
            ]
        )

        def structured_output(schema):
            structured_model = Mock()
            if schema is IntentOutput:
                structured_model.invoke.return_value = IntentOutput(
                    intent="support",
                    category="other",
                    reason="Support request.",
                )
            elif schema is DraftOutput:
                structured_model.invoke.return_value = DraftOutput(
                    draft="High-risk agent draft."
                )
            elif schema is GuardrailOutput:
                structured_model.invoke.side_effect = lambda *_args, **_kwargs: next(
                    guardrails
                )
            elif schema is RiskOutput:
                structured_model.invoke.return_value = RiskOutput(draft_risk="high")
            return structured_model

        init_chat_model.return_value.with_structured_output.side_effect = structured_output
        repository = Mock()
        repository.get_customer_by_id.return_value = {
            "id": 2,
            "company_name": "Acme",
            "contact_email": "support@acme.test",
            "region": None,
            "plan": None,
            "status": "active",
            "created_at": "2026-06-10T00:00:00",
        }
        context = AgentContext(repository=repository)
        config: RunnableConfig = {
            "configurable": {"thread_id": f"review-test-{uuid4()}"}
        }

        interrupted = graph.invoke(
            {
                "id": 10,
                "customer_id": 2,
                "title": "Account access",
                "description": "An unknown user accessed my account.",
            },
            config=config,
            context=context,
        )

        self.assertTrue(graph.get_state(config).interrupts)
        self.assertFalse(
            any(isinstance(message, AIMessage) for message in interrupted.get("messages", []))
        )

        completed = graph.invoke(
            Command(
                resume={
                    "review_id": 1,
                    "edited_draft": "Human-approved response.",
                    "reviewer_notes": "Reviewed.",
                    "updated_by": "maya@example.test",
                }
            ),
            config=config,
            context=context,
        )

        self.assertFalse(graph.get_state(config).interrupts)
        completed_dict = cast(dict[str, Any], completed)
        self.assertEqual(completed_dict["messages"][-1].content, "Human-approved response.")
        self.assertIsNone(completed_dict["draft_response"])


if __name__ == "__main__":
    unittest.main()
