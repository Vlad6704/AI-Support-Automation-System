import unittest
from pathlib import Path

from app.agents.context import create_database_agent_context
from app.scenario_database import scenario_session_factory
from app.scenario_world import load_world


WORLD_PATH = Path(__file__).resolve().parents[1] / "scenarios" / "world_1.json"


class AgentContextTests(unittest.TestCase):
    def test_database_context_uses_injected_scenario_sessions(self) -> None:
        with scenario_session_factory(WORLD_PATH) as sessions:
            context = create_database_agent_context(sessions)

            customer = context.repository.get_customer_by_id(1)
            review = context.draft_review_service.get_or_create_open_review(
                ticket_id=1,
                customer_id=1,
                original_draft="Review me",
                guardrail_feedback=None,
            )

            expected_customer = load_world(WORLD_PATH).customers[0]
            self.assertEqual(customer["company_name"], expected_customer.company_name)
            self.assertEqual(review.ticket_id, 1)


if __name__ == "__main__":
    unittest.main()
