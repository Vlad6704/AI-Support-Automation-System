from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import uuid4

from langfuse import get_client
from langfuse.experiment import ExperimentResult

from app.agents.context import create_database_agent_context
from app.agents.tools.webhook_agents import run_webhook_delivery_logs_investigation
from app.observability import merge_langfuse_callbacks, shutdown_langfuse
from app.scenario_database import concurrent_scenario_session_factory
from app.scenarios import world_path

DATASET_NAME = "Test webhook_delivery_logs_agent"
EXPERIMENT_NAME = "webhook-delivery-logs-agent"


async def run_webhook_delivery_logs_agent(
    *,
    item: Any,
    **_: Any,
) -> str | list[str]:
    inputs = item.input
    if isinstance(inputs, Mapping):
        return await _invoke_agent(inputs)
    if isinstance(inputs, Sequence) and not isinstance(inputs, (str, bytes)):
        if not all(isinstance(input_, Mapping) for input_ in inputs):
            raise TypeError("Each dataset item input must be an object.")
        return [await _invoke_agent(input_) for input_ in inputs]
    raise TypeError("Dataset item input must be an object or an array of objects.")


async def _invoke_agent(input_: Mapping[str, Any]) -> str:
    purpose = _required_string(input_, "purpose")
    expected_result = _required_string(input_, "expected_result")
    customer_id = int(input_.get("customer_id", 2))
    config = merge_langfuse_callbacks(
        {
            "configurable": {
                "thread_id": f"webhook_delivery_logs_agent_eval__{uuid4()}",
            }
        }
    )

    def invoke() -> str:
        with concurrent_scenario_session_factory(world_path("world_2")) as sessions:
            return run_webhook_delivery_logs_investigation(
                purpose=purpose,
                expected_result=expected_result,
                customer_id=customer_id,
                context=create_database_agent_context(sessions),
                config=config,
            )

    return await asyncio.to_thread(invoke)


def run_experiment(
    *,
    dataset_name: str = DATASET_NAME,
    dataset_id: str | None = None,
    config: Mapping[str, Any] | None = None,
) -> ExperimentResult:
    config = config or {}
    dataset = get_client().get_dataset(dataset_name)
    if dataset_id is not None and dataset.id != dataset_id:
        raise ValueError(
            f"Dataset ID mismatch for {dataset_name!r}: received {dataset_id!r}."
        )

    return dataset.run_experiment(
        name=str(config.get("experimentName", config.get("experiment_name", EXPERIMENT_NAME))),
        run_name=_optional_string(config.get("runName", config.get("run_name"))),
        description="Evaluate the specialized webhook delivery-log investigation agent.",
        task=run_webhook_delivery_logs_agent,
        max_concurrency=int(
            config.get("maxConcurrency", config.get("max_concurrency", 5))
        ),
        metadata={
            "agent": "webhook_delivery_logs_agent",
            "scenario": "world_2",
        },
    )


def main() -> None:
    try:
        result = run_experiment()
        print(f"Experiment results: {result.dataset_run_url}")
    finally:
        shutdown_langfuse()


def _required_string(input_: Mapping[str, Any], key: str) -> str:
    value = input_.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Dataset item input requires non-empty {key!r}.")
    return value


def _optional_string(value: Any) -> str | None:
    return str(value) if value is not None else None


if __name__ == "__main__":
    main()
