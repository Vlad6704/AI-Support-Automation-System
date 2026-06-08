from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from langfuse import get_client
from langfuse.experiment import ExperimentResult

from app.agents.context import create_stub_agent_context
from app.agents.main_agent import graph
from app.observability import merge_langfuse_callbacks, shutdown_langfuse

DATASET_NAME = "case_1"
EXPERIMENT_NAME = "main-agent-webhook"


async def run_main_agent(*, item: Any, **_: Any) -> dict[str, Any]:
    config = merge_langfuse_callbacks(
        {
            "configurable": {
                "thread_id": f"main_agent_webhook_eval__{uuid4()}",
            }
        }
    )
    return await graph.ainvoke(
        item.input,
        config=config,
        context=create_stub_agent_context(),
    )


def webhook_route_evaluator(*, output: dict[str, Any], **_: Any) -> dict[str, Any]:
    customer_context = output.get("customer_context")
    passed = (
        output.get("intent") == "support"
        and output.get("category") in {"webhook", "webhooks"}
        and isinstance(customer_context, dict)
        and bool(customer_context)
    )
    return {
        "name": "webhook_route_correct",
        "value": passed,
        "data_type": "BOOLEAN",
        "comment": "Checks webhook classification and customer-context retrieval.",
    }


def draft_response_evaluator(
    *,
    output: dict[str, Any],
    expected_output: dict[str, Any] | None = None,
    **_: Any,
) -> dict[str, Any]:
    draft = output.get("draft_response")
    expected_draft = (expected_output or {}).get("draft_response")
    passed = isinstance(draft, str) and bool(draft.strip())
    return {
        "name": "draft_response_present",
        "value": passed,
        "data_type": "BOOLEAN",
        "comment": (
            "Checks that the main agent produced a non-empty draft response. "
            f"Reference draft available: {isinstance(expected_draft, str)}."
        ),
    }


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
        # evaluators=[webhook_route_evaluator, draft_response_evaluator],
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
