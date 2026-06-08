from __future__ import annotations

from typing import Any
from uuid import uuid4

from langfuse import get_client

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


def main() -> None:
    langfuse = get_client()
    dataset = langfuse.get_dataset(DATASET_NAME)

    try:
        result = dataset.run_experiment(
            name=EXPERIMENT_NAME,
            description="Evaluate the main agent on webhook support tickets.",
            task=run_main_agent,
            # evaluators=[webhook_route_evaluator, draft_response_evaluator],
            max_concurrency=5,
            metadata={
                "agent": "main_agent",
                "scenario": "webhook",
            },
        )
        print(f"Experiment results: {result.dataset_run_url}")
    finally:
        shutdown_langfuse()


if __name__ == "__main__":
    main()
