import unittest
from unittest.mock import Mock, patch

from app.agents.billing_agent.main import run_billing_agent


class BillingAgentMainTests(unittest.TestCase):
    @patch("app.agents.billing_agent.main.invoke_graph_with_langfuse")
    @patch("app.agents.billing_agent.main.create_database_agent_context")
    def test_uses_database_context_by_default(
        self,
        create_database_agent_context: Mock,
        invoke_graph_with_langfuse: Mock,
    ) -> None:
        context = Mock()
        create_database_agent_context.return_value = context
        invoke_graph_with_langfuse.return_value = {}

        run_billing_agent("Invoice question")

        create_database_agent_context.assert_called_once_with()
        self.assertIs(invoke_graph_with_langfuse.call_args.kwargs["context"], context)


if __name__ == "__main__":
    unittest.main()
