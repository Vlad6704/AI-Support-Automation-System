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
    IntentOutput,
    RiskOutput,
    graph,
    node_finalize_response,
    node_support_review,
    node_estimate_draft_risk,
    route_after_intent,
    route_after_webhook_agent,
)
from app.agents.webhook_agent.main import (
    route_after_guardrail as route_after_webhook_guardrail,
    route_start as route_webhook_start,
)
from app.agents.webhook_agent.nodes import (
    DraftOutput as WebhookDraftOutput,
    GuardrailOutput as WebhookGuardrailOutput,
    node_get_customer_context,
    node_get_draft_response,
    node_investigation_orchestrator,
    node_validate_draft_response,
)
from app.agents.tools import (
    run_webhook_delivery_logs_agent,
    run_webhook_endpoints_agent,
)


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

    @patch("app.agents.webhook_agent.nodes.create_agent")
    def test_investigation_orchestrator_uses_delegated_agents(
        self,
        create_agent: Mock,
    ) -> None:
        agent = create_agent.return_value
        agent.invoke.return_value = {
            "messages": [AIMessage("Delivery failures affect 10% of attempts.")]
        }
        runtime = Runtime(context=AgentContext(repository=Mock()))

        result = node_investigation_orchestrator(
            {
                "customer_id": 2,
                "title": "Webhook failures",
                "description": "Some deliveries fail.",
                "customer_context": {"customer": {"id": 2}},
            },
            runtime,
        )

        self.assertEqual(
            result.get("investigation_result"),
            "Delivery failures affect 10% of attempts.",
        )
        create_kwargs = create_agent.call_args.kwargs
        self.assertEqual(create_kwargs["model"], "openai:gpt-5.4-nano")
        self.assertEqual(
            create_kwargs["tools"],
            [run_webhook_delivery_logs_agent, run_webhook_endpoints_agent],
        )
        self.assertEqual(agent.invoke.call_args.args[0]["customer_id"], 2)

    @patch("app.agents.webhook_agent.nodes.init_chat_model")
    def test_draft_response_uses_investigation_result(
        self,
        init_chat_model: Mock,
    ) -> None:
        structured_model = Mock()
        structured_model.invoke.return_value = WebhookDraftOutput(draft="Draft.")
        init_chat_model.return_value.with_structured_output.return_value = structured_model

        node_get_draft_response(
            {
                "description": "Webhook deliveries fail.",
                "investigation_result": "Confirmed 150 failed deliveries.",
            }
        )

        messages = structured_model.invoke.call_args.args[0]
        self.assertIn("Confirmed 150 failed deliveries.", messages[1].content)

    def test_webhook_subgraph_revalidates_reviewed_draft_without_regenerating(self) -> None:
        self.assertEqual(
            route_webhook_start(
                {
                    "draft_response": "Human edit.",
                    "draft_review_id": 4,
                }
            ),
            "guardrail_output",
        )

    def test_main_routes_reviewed_webhook_draft_to_close_review(self) -> None:
        self.assertEqual(
            route_after_webhook_agent({"draft_review_id": 4}),
            "close_prev_review",
        )
        self.assertEqual(route_after_webhook_agent({}), "estimate_risk")

    @patch("app.agents.webhook_agent.nodes.init_chat_model")
    def test_invalid_draft_routes_back_with_guardrail_feedback(
        self,
        init_chat_model: Mock,
    ) -> None:
        structured_model = Mock()
        structured_model.invoke.return_value = WebhookGuardrailOutput(
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

        self.assertEqual(route_after_webhook_guardrail(result), "draft_response")
        guardrail = required_state_value(cast(dict[str, Any], result), "draft_guardrail")
        self.assertEqual(guardrail["decision"], "invalid")
        self.assertIn("unsupported refund", guardrail["message"])

    @patch("app.agents.webhook_agent.nodes.init_chat_model")
    def test_valid_draft_routes_to_risk_estimation(
        self, init_chat_model: Mock
    ) -> None:
        structured_model = Mock()
        structured_model.invoke.return_value = WebhookGuardrailOutput(
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

        self.assertEqual(route_after_webhook_guardrail(result), "__end__")
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
                "category": "webhook",
                "draft_response": "Agent draft.",
                "draft_guardrail": {
                    "decision": "valid",
                    "message": "Approved.",
                },
            },
            runtime,
        )

        self.assertEqual(command.goto, "webhook_agent")
        update = command_update(command)
        self.assertEqual(update["draft_response"], "Human-edited response.")
        self.assertEqual(update["draft_review_id"], 1)

    @patch("app.agents.webhook_agent.nodes.create_agent")
    @patch("app.agents.webhook_agent.nodes.init_chat_model")
    @patch("app.agents.main_agent.init_chat_model")
    def test_high_risk_draft_interrupts_then_human_edit_is_finalized(
        self,
        main_init_chat_model: Mock,
        webhook_init_chat_model: Mock,
        create_agent: Mock,
    ) -> None:
        guardrails = iter(
            [
                WebhookGuardrailOutput(
                    guardrail_decision="valid",
                    guardrail_message="Approved.",
                ),
                WebhookGuardrailOutput(
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
                    category="webhook",
                    reason="Support request.",
                )
            elif schema is RiskOutput:
                structured_model.invoke.return_value = RiskOutput(draft_risk="high")
            return structured_model

        def webhook_structured_output(schema):
            structured_model = Mock()
            if schema is WebhookDraftOutput:
                structured_model.invoke.return_value = WebhookDraftOutput(
                    draft="High-risk agent draft."
                )
            elif schema is WebhookGuardrailOutput:
                structured_model.invoke.side_effect = lambda *_args, **_kwargs: next(
                    guardrails
                )
            return structured_model

        main_init_chat_model.return_value.with_structured_output.side_effect = (
            structured_output
        )
        webhook_init_chat_model.return_value.with_structured_output.side_effect = (
            webhook_structured_output
        )
        create_agent.return_value.invoke.return_value = {
            "messages": [AIMessage("Investigation complete.")]
        }
        repository = Mock()
        repository.get_customer_context.return_value = {"customer": {"id": 2}}
        context = AgentContext(repository=repository)
        config: RunnableConfig = {
            "configurable": {"thread_id": f"review-test-{uuid4()}"}
        }

        interrupted = graph.invoke(
            {
                "id": 10,
                "customer_id": 2,
                "title": "Webhook security issue",
                "description": "An unknown webhook destination received our events.",
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
