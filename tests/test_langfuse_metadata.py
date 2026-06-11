import unittest
from unittest.mock import Mock, patch

from app.observability.langfuse import AGENT_VERSION, invoke_graph_with_langfuse


class LangfuseMetadataTests(unittest.TestCase):
    @patch("app.observability.langfuse.merge_langfuse_callbacks", return_value={})
    @patch("app.observability.langfuse.get_client")
    def test_enriches_trace_metadata_with_agent_result(
        self,
        get_client: Mock,
        _: Mock,
    ) -> None:
        span = Mock()
        observation = get_client.return_value.start_as_current_observation.return_value
        observation.__enter__.return_value = span
        graph = Mock()
        graph.invoke.return_value = {
            "category": "webhook",
            "node_calls": {
                "node_estimate_draft_risk": {
                    "result": {"draft_risk": "high"},
                }
            },
        }

        invoke_graph_with_langfuse(
            graph,
            {"id": 5},
            trace_name="main-agent",
            metadata={"ticket_id": 5, "customer_id": 2},
        )

        self.assertEqual(
            span.update.call_args_list[-1].kwargs["metadata"],
            {
                "ticket_id": 5,
                "customer_id": 2,
                "agent_version": AGENT_VERSION,
                "category": "webhook",
                "risk": "high",
            },
        )


if __name__ == "__main__":
    unittest.main()
