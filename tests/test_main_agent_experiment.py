import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from eval.langfuse.webhook.main_agent_experiment import run_main_agent


class MainAgentExperimentTests(unittest.IsolatedAsyncioTestCase):
    async def test_runs_single_object_input(self) -> None:
        item = SimpleNamespace(input={"id": 1})

        with patch(
            "eval.langfuse.webhook.main_agent_experiment.graph.ainvoke",
            new=AsyncMock(return_value={"id": 1, "draft_response": "Done"}),
        ) as invoke:
            result = await run_main_agent(item=item)

        self.assertEqual(result, {"id": 1, "draft_response": "Done"})
        self.assertEqual(invoke.await_count, 1)

    async def test_runs_every_object_in_array_input(self) -> None:
        item = SimpleNamespace(input=[{"id": 1}, {"id": 2}])

        with patch(
            "eval.langfuse.webhook.main_agent_experiment.graph.ainvoke",
            new=AsyncMock(
                side_effect=[
                    {"id": 1, "draft_response": "First"},
                    {"id": 2, "draft_response": "Second"},
                ]
            ),
        ) as invoke:
            result = await run_main_agent(item=item)

        self.assertEqual(
            result,
            [
                {"id": 1, "draft_response": "First"},
                {"id": 2, "draft_response": "Second"},
            ],
        )
        self.assertEqual(invoke.await_count, 2)

    async def test_rejects_non_object_array_elements(self) -> None:
        item = SimpleNamespace(input=[{"id": 1}, "invalid"])

        with self.assertRaisesRegex(TypeError, "Each dataset item input"):
            await run_main_agent(item=item)


if __name__ == "__main__":
    unittest.main()
