from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import uuid4

from langfuse import get_client
from langfuse.experiment import ExperimentResult

from app.agents.context import create_stub_agent_context
from app.agents.main_agent import graph
from app.observability import merge_langfuse_callbacks, shutdown_langfuse

DATASET_NAME = "case_1"
EXPERIMENT_NAME = "main-agent-webhook"


async def run_main_agent(*, item: Any, **_: Any) -> dict[str, Any] | list[dict[str, Any]]:
    inputs = item.input
    if isinstance(inputs, Mapping):
        return await _invoke_main_agent(inputs)
    if isinstance(inputs, Sequence) and not isinstance(inputs, (str, bytes)):
        if not all(isinstance(input_, Mapping) for input_ in inputs):
            raise TypeError("Each dataset item input must be an object.")
        return [await _invoke_main_agent(input_) for input_ in inputs]
    raise TypeError("Dataset item input must be an object or an array of objects.")


async def _invoke_main_agent(input_: Any) -> dict[str, Any]:
    if not isinstance(input_, Mapping):
        raise TypeError("Each dataset item input must be an object.")

    config = merge_langfuse_callbacks(
        {
            "configurable": {
                "thread_id": f"main_agent_webhook_eval__{uuid4()}",
            }
        }
    )
    return await asyncio.to_thread(
        graph.invoke,
        dict(input_),
        config=config,
        context=create_stub_agent_context(),
    )


def run_experiment(
    *,
    dataset_name: str = DATASET_NAME,
    dataset_id: str | None = None,
    config: Mapping[str, Any] | None = None,
) -> ExperimentResult:
    config = config or {}
    langfuse = get_client()
    dataset = langfuse.get_dataset(dataset_name)

    if dataset_id is not None and dataset.id != dataset_id:
        raise ValueError(
            f"Dataset ID mismatch for {dataset_name!r}: received {dataset_id!r}."
        )

    config_metadata = _config_value(config, "metadata", default={})
    metadata = {
        "agent": "main_agent",
        "scenario": "webhook",
        **{str(key): str(value) for key, value in config_metadata.items()},
    }
    return dataset.run_experiment(
        name=str(
            _config_value(
                config,
                "experimentName",
                "experiment_name",
                default=EXPERIMENT_NAME,
            )
        ),
        run_name=_optional_string(_config_value(config, "runName", "run_name")),
        description="Evaluate the main agent on webhook support tickets.",
        task=run_main_agent,
        max_concurrency=int(
            _config_value(config, "maxConcurrency", "max_concurrency", default=5)
        ),
        metadata=metadata,
    )


def main() -> None:
    try:
        result = run_experiment()
        print(f"Experiment results: {result.dataset_run_url}")
    finally:
        shutdown_langfuse()


def _config_value(
    config: Mapping[str, Any],
    *keys: str,
    default: Any = None,
) -> Any:
    return next((config[key] for key in keys if key in config), default)


def _optional_string(value: Any) -> str | None:
    return str(value) if value is not None else None


if __name__ == "__main__":
    main()
