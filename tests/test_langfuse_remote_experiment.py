import unittest
from unittest.mock import Mock, patch

from fastapi import BackgroundTasks, HTTPException

from app.api.router.experiments import (
    RemoteExperimentRequest,
    trigger_langfuse_experiment,
)


class LangfuseRemoteExperimentTests(unittest.IsolatedAsyncioTestCase):
    async def test_case_1_experiment_is_queued(self) -> None:
        background_tasks = Mock(spec=BackgroundTasks)
        request = RemoteExperimentRequest.model_validate(
            {
                "datasetId": "dataset-id",
                "datasetName": "case_1",
                "config": {"runName": "manual-run"},
            }
        )

        with patch.dict(
            "os.environ",
            {"LANGFUSE_REMOTE_EXPERIMENT_SECRET": "test-secret"},
        ):
            response = await trigger_langfuse_experiment(
                request,
                background_tasks,
                secret="test-secret",
            )

        self.assertEqual(response["status"], "accepted")
        background_tasks.add_task.assert_called_once()
        _, kwargs = background_tasks.add_task.call_args
        self.assertEqual(kwargs["dataset_name"], "case_1")
        self.assertEqual(kwargs["dataset_id"], "dataset-id")
        self.assertEqual(kwargs["config"]["run_name"], "manual-run")
        self.assertEqual(kwargs["config"]["max_concurrency"], 5)

    async def test_other_dataset_is_rejected(self) -> None:
        request = RemoteExperimentRequest.model_validate(
            {
                "datasetId": "dataset-id",
                "datasetName": "other",
            }
        )

        with (
            patch.dict(
                "os.environ",
                {"LANGFUSE_REMOTE_EXPERIMENT_SECRET": "test-secret"},
            ),
            self.assertRaises(HTTPException) as context,
        ):
            await trigger_langfuse_experiment(
                request,
                Mock(spec=BackgroundTasks),
                secret="test-secret",
            )

        self.assertEqual(context.exception.status_code, 400)

    async def test_invalid_secret_is_rejected(self) -> None:
        request = RemoteExperimentRequest.model_validate(
            {
                "datasetId": "dataset-id",
                "datasetName": "case_1",
            }
        )

        with (
            patch.dict(
                "os.environ",
                {"LANGFUSE_REMOTE_EXPERIMENT_SECRET": "test-secret"},
            ),
            self.assertRaises(HTTPException) as context,
        ):
            await trigger_langfuse_experiment(
                request,
                Mock(spec=BackgroundTasks),
                secret="wrong-secret",
            )

        self.assertEqual(context.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
