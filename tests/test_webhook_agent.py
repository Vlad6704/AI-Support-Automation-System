import unittest
from unittest.mock import Mock

from langgraph.runtime import Runtime
from langgraph.checkpoint.sqlite import SqliteSaver

from app.agents.context import AgentContext
from app.agents.main_agent import CHECKPOINT_DB_PATH, graph, route_after_intent
from app.agents.webhook_agent.nodes import node_get_customer_context


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

        self.assertEqual(result["customer_context"], {"customer": {"id": 1}})
        repository.get_customer_context.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()
