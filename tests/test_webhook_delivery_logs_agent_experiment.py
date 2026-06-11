import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from eval.langfuse.webhook.webhook_delivery_logs_agent_experiment import (
    DATASET_NAME,
    run_experiment,
    run_webhook_delivery_logs_agent,
)


class WebhookDeliveryLogsAgentExperimentTests(unittest.IsolatedAsyncioTestCase):
    async def test_runs_single_dataset_input(self) -> None:
        item = SimpleNamespace(
            input={
                "purpose": "Count failed deliveries.",
                "expected_result": "Return the failed delivery count.",
                "customer_id": 2,
            }
        )

        with patch(
            "eval.langfuse.webhook.webhook_delivery_logs_agent_experiment."
            "run_webhook_delivery_logs_investigation",
            return_value="150 failed deliveries.",
        ) as investigate:
            result = await run_webhook_delivery_logs_agent(item=item)

        self.assertEqual(result, "150 failed deliveries.")
        self.assertEqual(investigate.call_args.kwargs["purpose"], "Count failed deliveries.")
        self.assertEqual(investigate.call_args.kwargs["customer_id"], 2)

    async def test_defaults_to_customer_two(self) -> None:
        item = SimpleNamespace(
            input={
                "purpose": "Review delivery health.",
                "expected_result": "Return a concise summary.",
            }
        )

        with patch(
            "eval.langfuse.webhook.webhook_delivery_logs_agent_experiment."
            "run_webhook_delivery_logs_investigation",
            return_value="Healthy.",
        ) as investigate:
            await run_webhook_delivery_logs_agent(item=item)

        self.assertEqual(investigate.call_args.kwargs["customer_id"], 2)

    async def test_runs_every_input_in_array(self) -> None:
        item = SimpleNamespace(
            input=[
                {"purpose": "First", "expected_result": "First result"},
                {"purpose": "Second", "expected_result": "Second result"},
            ]
        )

        with patch(
            "eval.langfuse.webhook.webhook_delivery_logs_agent_experiment."
            "run_webhook_delivery_logs_investigation",
            side_effect=["First output", "Second output"],
        ):
            result = await run_webhook_delivery_logs_agent(item=item)

        self.assertEqual(result, ["First output", "Second output"])

    async def test_requires_purpose_and_expected_result(self) -> None:
        item = SimpleNamespace(input={"purpose": "Count failures."})

        with self.assertRaisesRegex(ValueError, "expected_result"):
            await run_webhook_delivery_logs_agent(item=item)

    def test_experiment_uses_delivery_log_dataset(self) -> None:
        dataset = Mock()
        dataset.id = "dataset-id"
        dataset.run_experiment.return_value = Mock()
        client = Mock()
        client.get_dataset.return_value = dataset

        with patch(
            "eval.langfuse.webhook.webhook_delivery_logs_agent_experiment.get_client",
            return_value=client,
        ):
            run_experiment()

        client.get_dataset.assert_called_once_with(DATASET_NAME)
        kwargs = dataset.run_experiment.call_args.kwargs
        self.assertEqual(kwargs["name"], "webhook-delivery-logs-agent")
        self.assertIs(kwargs["task"], run_webhook_delivery_logs_agent)
        self.assertEqual(kwargs["metadata"]["scenario"], "world_2")

    async def test_uses_concurrent_scenario_factory(self) -> None:
        item = SimpleNamespace(
            input={
                "purpose": "Count failures.",
                "expected_result": "Return count.",
            }
        )

        with (
            patch(
                "eval.langfuse.webhook.webhook_delivery_logs_agent_experiment."
                "concurrent_scenario_session_factory"
            ) as scenario_factory,
            patch(
                "eval.langfuse.webhook.webhook_delivery_logs_agent_experiment."
                "run_webhook_delivery_logs_investigation",
                return_value="Done",
            ),
        ):
            scenario_factory.return_value.__enter__.return_value = Mock()
            await run_webhook_delivery_logs_agent(item=item)

        scenario_factory.assert_called_once()


if __name__ == "__main__":
    unittest.main()
