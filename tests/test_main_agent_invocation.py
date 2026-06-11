import unittest
from unittest.mock import Mock, patch

from app.agents.context import AgentContext
from app.agents.main_agent import MainAgentState
from app.agents.main_agent_invocation import (
    invoke_existing_ticket_thread,
    invoke_main_agent_for_ticket,
    invoke_new_ticket_thread,
)


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


if __name__ == "__main__":
    unittest.main()
