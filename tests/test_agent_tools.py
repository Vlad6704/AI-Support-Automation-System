import unittest
from typing import Any, cast
from unittest.mock import Mock, patch

from langchain.messages import AIMessage
from langchain.tools import ToolRuntime
from pydantic import ValidationError

from app.agents.context import AgentContext
from app.agents.tools import (
    WebhookDeliveryLogCondition,
    WebhookDeliveryLogWhere,
    WebhookEndpointCondition,
    WebhookEndpointWhere,
    run_webhook_delivery_logs_agent,
    run_webhook_endpoints_agent,
    select_webhook_delivery_logs,
    select_webhook_endpoints,
)


def tool_runtime(repository: Mock, state: dict[str, Any]) -> ToolRuntime:
    runtime = Mock(spec=ToolRuntime)
    runtime.context = AgentContext(repository=repository)
    runtime.state = state
    runtime.config = {"configurable": {"thread_id": "test-thread"}}
    return cast(ToolRuntime, runtime)


class WebhookDatabaseToolTests(unittest.TestCase):
    def test_delivery_tool_uses_ticket_customer_id(self) -> None:
        repository = Mock()
        repository.get_webhook_delivery_logs.return_value = {"rows": [], "count": 0}
        runtime = tool_runtime(repository, {"customer_id": 2})

        result = select_webhook_delivery_logs.func(
            runtime=runtime,
            where=WebhookDeliveryLogWhere(
                conditions=[
                    WebhookDeliveryLogCondition(
                        column="status_code",
                        operator="eq",
                        value=500,
                    )
                ]
            ),
            limit=10,
            offset=20,
        )

        self.assertEqual(result, {"rows": [], "count": 0})
        repository.get_webhook_delivery_logs.assert_called_once_with(
            2,
            {
                "match": "all",
                "conditions": [
                    {"column": "status_code", "operator": "eq", "value": 500}
                ],
            },
            10,
            20,
        )

    def test_endpoint_tool_uses_ticket_customer_id(self) -> None:
        repository = Mock()
        repository.get_webhook_endpoints.return_value = {"rows": [], "count": 0}
        runtime = tool_runtime(repository, {"customer_id": 3})

        select_webhook_endpoints.func(
            runtime=runtime,
            where=WebhookEndpointWhere(
                conditions=[
                    WebhookEndpointCondition(
                        column="status",
                        operator="eq",
                        value="active",
                    )
                ]
            ),
            limit=5,
            offset=0,
        )

        repository.get_webhook_endpoints.assert_called_once_with(
            3,
            {
                "match": "all",
                "conditions": [
                    {"column": "status", "operator": "eq", "value": "active"}
                ],
            },
            5,
            0,
        )

    def test_tools_do_not_expose_customer_id_to_model(self) -> None:
        for database_tool in (
            select_webhook_delivery_logs,
            select_webhook_endpoints,
        ):
            schema = database_tool.tool_call_schema.model_json_schema()
            self.assertNotIn("customer_id", schema["properties"])
            self.assertNotIn("runtime", schema["properties"])

    def test_tool_requires_customer_id_in_ticket_state(self) -> None:
        with self.assertRaisesRegex(ValueError, "ticket customer_id"):
            select_webhook_delivery_logs.func(
                runtime=tool_runtime(Mock(), {}),
                where=None,
                limit=50,
                offset=0,
            )

    def test_where_schema_rejects_customer_id(self) -> None:
        with self.assertRaises(ValidationError):
            WebhookEndpointCondition.model_validate(
                {"column": "customer_id", "operator": "eq", "value": 999}
            )

    def test_delivery_tool_forwards_iso_datetime_filter(self) -> None:
        repository = Mock()
        repository.get_webhook_delivery_logs.return_value = {"rows": [], "count": 0}
        timestamp = "2026-06-08T16:20:00.000000"

        select_webhook_delivery_logs.func(
            runtime=tool_runtime(repository, {"customer_id": 2}),
            where=WebhookDeliveryLogWhere(
                conditions=[
                    WebhookDeliveryLogCondition(
                        column="created_at",
                        operator="eq",
                        value=timestamp,
                    )
                ]
            ),
            limit=50,
            offset=0,
        )

        repository.get_webhook_delivery_logs.assert_called_once_with(
            2,
            {
                "match": "all",
                "conditions": [
                    {
                        "column": "created_at",
                        "operator": "eq",
                        "value": timestamp,
                    }
                ],
            },
            50,
            0,
        )

    def test_where_schema_rejects_bad_value_object(self) -> None:
        with self.assertRaises(ValidationError):
            WebhookDeliveryLogCondition.model_validate(
                {"column": "created_at", "operator": "eq", "value": {}}
            )

    def test_where_schema_rejects_unknown_endpoint_column(self) -> None:
        with self.assertRaises(ValidationError):
            WebhookEndpointCondition.model_validate(
                {"column": "unknown", "operator": "eq", "value": "value"}
            )

    def test_delivery_where_schema_lists_columns_and_operators(self) -> None:
        tool_schema = select_webhook_delivery_logs.tool_call_schema.model_json_schema()
        condition_schema = tool_schema["$defs"]["WebhookDeliveryLogCondition"]["properties"]

        self.assertNotIn("customer_id", condition_schema["column"]["enum"])
        self.assertIn("created_at", condition_schema["column"]["enum"])
        self.assertIn("gte", condition_schema["operator"]["enum"])
        self.assertIn("is_null", condition_schema["operator"]["enum"])
        self.assertIn("Maximum rows", tool_schema["properties"]["limit"]["description"])
        self.assertIn("matching rows to skip", tool_schema["properties"]["offset"]["description"])

    def test_endpoint_where_schema_lists_columns(self) -> None:
        condition_schema = select_webhook_endpoints.tool_call_schema.model_json_schema()[
            "$defs"
        ]["WebhookEndpointCondition"]["properties"]

        self.assertNotIn("customer_id", condition_schema["column"]["enum"])
        self.assertIn("events", condition_schema["column"]["enum"])
        self.assertIn("contains", condition_schema["operator"]["enum"])

    @patch("app.agents.tools.webhook_agents.create_agent")
    def test_delivery_agent_uses_only_delivery_tool_and_task_parameters(
        self,
        create_agent: Mock,
    ) -> None:
        agent = create_agent.return_value
        agent.invoke.return_value = {"messages": [AIMessage("Confirmed result.")]}
        runtime = tool_runtime(Mock(), {"customer_id": 2})

        result = run_webhook_delivery_logs_agent.func(
            purpose="Find whether failed deliveries are common.",
            expected_result="Return the failed count and a brief conclusion.",
            runtime=runtime,
        )

        self.assertEqual(result, "Confirmed result.")
        create_kwargs = create_agent.call_args.kwargs
        self.assertEqual(create_kwargs["model"], "openai:gpt-5.4-nano")
        self.assertEqual(create_kwargs["tools"], [select_webhook_delivery_logs])
        invoke_input = agent.invoke.call_args.args[0]
        self.assertEqual(invoke_input["customer_id"], 2)
        self.assertIn("Find whether failed deliveries are common.", invoke_input["messages"][0].content)
        self.assertIn("Return the failed count", invoke_input["messages"][0].content)

    @patch("app.agents.tools.webhook_agents.create_agent")
    def test_endpoint_agent_uses_only_endpoint_tool(
        self,
        create_agent: Mock,
    ) -> None:
        agent = create_agent.return_value
        agent.invoke.return_value = {"messages": [AIMessage("One active endpoint.")]}

        result = run_webhook_endpoints_agent.func(
            purpose="Inspect active endpoints.",
            expected_result="Return endpoint count.",
            runtime=tool_runtime(Mock(), {"customer_id": 3}),
        )

        self.assertEqual(result, "One active endpoint.")
        self.assertEqual(
            create_agent.call_args.kwargs["tools"],
            [select_webhook_endpoints],
        )
        self.assertEqual(agent.invoke.call_args.args[0]["customer_id"], 3)

    def test_delegated_agent_tools_expose_only_task_parameters(self) -> None:
        for agent_tool in (
            run_webhook_delivery_logs_agent,
            run_webhook_endpoints_agent,
        ):
            properties = agent_tool.tool_call_schema.model_json_schema()["properties"]
            self.assertEqual(set(properties), {"purpose", "expected_result"})


if __name__ == "__main__":
    unittest.main()
