from difflib import SequenceMatcher
from sys import argv
from typing import Mapping, TypeGuard, cast
from uuid import uuid4

from langchain.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from langgraph.checkpoint.sqlite import SqliteSaver

from app.agents.context import AgentContext, create_database_agent_context
from app.agents.main_agent import MainAgentState, graph
from app.enums import AgentRunHumanReviewResult, AgentRunOutcome
from app.observability import (
    AGENT_VERSION,
    invoke_graph_with_langfuse,
    shutdown_langfuse,
)
from app.repositories.agent_repository_protocols import SerializedValue
from rich import print


def get_ticket_data(
    ticket_id: int | None = None,
    *,
    context: AgentContext,
) -> MainAgentState | None:
    if ticket_id is None:
        return cast(MainAgentState | None, context.repository.get_first_ticket())
    return cast(MainAgentState | None, context.repository.get_ticket_by_id(ticket_id))


def ticket_thread_config(ticket_id: int) -> RunnableConfig:
    return {"configurable": {"thread_id": f"ticket-{ticket_id}"}}


def ticket_thread_exists(ticket_id: int) -> bool:
    return main_agent_checkpointer().get_tuple(ticket_thread_config(ticket_id)) is not None


def delete_ticket_thread(ticket_id: int) -> None:
    main_agent_checkpointer().delete_thread(f"ticket-{ticket_id}")


def main_agent_checkpointer() -> SqliteSaver:
    return cast(SqliteSaver, graph.checkpointer)


def ticket_thread_is_interrupted(ticket_id: int) -> bool:
    return bool(graph.get_state(ticket_thread_config(ticket_id)).interrupts)


def get_ticket_thread_state(ticket_id: int) -> MainAgentState:
    return cast(MainAgentState, graph.get_state(ticket_thread_config(ticket_id)).values)


def invoke_new_ticket_thread(
    ticket_data: MainAgentState,
    *,
    context: AgentContext,
) -> MainAgentState:
    return _invoke(ticket_data, ticket_data=ticket_data, context=context)


def invoke_existing_ticket_thread(
    ticket_data: MainAgentState,
    *,
    context: AgentContext,
) -> MainAgentState:
    ticket_id = require_state_int(ticket_data, "id")
    message = context.repository.get_latest_user_message(ticket_id)
    if message is None:
        raise ValueError(f"No user message found for ticket {ticket_id}.")
    return _invoke(
        {"messages": [HumanMessage(content=str(message["message"]))]},
        ticket_data=ticket_data,
        context=context,
    )


def invoke_main_agent_for_ticket(
    ticket_id: int | None = None,
    *,
    context: AgentContext,
) -> MainAgentState:
    ticket_data = get_ticket_data(ticket_id, context=context)
    if ticket_data is None:
        target = "first ticket" if ticket_id is None else f"ticket {ticket_id}"
        raise ValueError(f"No data found for {target}.")

    if ticket_thread_exists(require_state_int(ticket_data, "id")):
        return invoke_existing_ticket_thread(ticket_data, context=context)
    return invoke_new_ticket_thread(ticket_data, context=context)


def resume_main_agent_review(
    ticket_id: int,
    *,
    review_id: int,
    edited_draft: str,
    reviewer_notes: str | None,
    updated_by: str,
    context: AgentContext,
) -> MainAgentState:
    ticket_data = get_ticket_data(ticket_id, context=context)
    if ticket_data is None:
        raise ValueError(f"No data found for ticket {ticket_id}.")
    original_draft = get_ticket_thread_state(ticket_id).get("draft_response")
    human_review_result, edit_percentage = _review_metrics(
        original_draft,
        edited_draft,
    )
    if human_review_result is None or edit_percentage is None:
        raise ValueError("Review metrics require original and edited drafts.")
    context.repository.record_agent_run_human_review(
        ticket_id=ticket_id,
        human_review_result=human_review_result,
        edit_percentage=edit_percentage,
    )
    return _invoke(
        Command(
            resume={
                "review_id": review_id,
                "edited_draft": edited_draft,
                "reviewer_notes": reviewer_notes,
                "updated_by": updated_by,
            }
        ),
        ticket_data=ticket_data,
        context=context,
    )


def _invoke(
    input_data: MainAgentState | Command[str],
    *,
    ticket_data: MainAgentState,
    context: AgentContext,
) -> MainAgentState:
    ticket_id = require_state_int(ticket_data, "id")
    customer_id = require_state_int(ticket_data, "customer_id")
    thread_id = f"ticket-{ticket_id}"
    trace_id = uuid4().hex
    run_id = context.repository.start_agent_run(
        ticket_id=ticket_id,
        trace_id=trace_id,
        agent_name="main-agent",
        agent_version=AGENT_VERSION,
    )
    try:
        result = invoke_graph_with_langfuse(
            graph,
            input_data,
            trace_name="main-agent",
            config=ticket_thread_config(ticket_id),
            session_id=thread_id,
            user_id=str(customer_id),
            tags=("main-agent", "support"),
            metadata={
                "ticket_id": ticket_id,
                "customer_id": customer_id,
                "category": ticket_data.get("category"),
                "risk": ticket_data.get("draft_risk"),
                "agent_run_id": run_id,
            },
            trace_id=trace_id,
            context=context,
        )
    except Exception as error:
        context.repository.finish_agent_run(
            run_id=run_id,
            ticket_id=ticket_id,
            outcome=AgentRunOutcome.FAILED,
            draft_risk=None,
            guardrail_passed=None,
            human_review_required=False,
            human_review_result=None,
            edit_percentage=None,
            event_type="agent_failed",
            event_payload={"error_type": type(error).__name__},
        )
        raise

    draft_risk = _result_string(result, "draft_risk") or _node_result_string(
        result,
        node_name="node_estimate_draft_risk",
        key="draft_risk",
    )
    guardrail_decision = _node_result_string(
        result,
        node_name="node_validate_draft_response",
        key="guardrail_decision",
    )
    guardrail_passed = (
        guardrail_decision == "valid" if guardrail_decision is not None else None
    )
    interrupted = bool(result.get("__interrupt__"))
    outcome = (
        AgentRunOutcome.AWAITING_REVIEW
        if interrupted
        else AgentRunOutcome.UNSUPPORTED
        if result.get("intent") != "support"
        or result.get("category") not in {"webhook", "webhooks"}
        else AgentRunOutcome.AUTOMATED
    )
    event_payload: dict[str, SerializedValue] = {"outcome": outcome.value}
    context.repository.finish_agent_run(
        run_id=run_id,
        ticket_id=ticket_id,
        outcome=outcome,
        draft_risk=draft_risk,
        guardrail_passed=guardrail_passed,
        human_review_required=interrupted,
        human_review_result=None,
        edit_percentage=None,
        event_type="review_requested" if interrupted else "response_sent",
        event_payload=event_payload,
    )
    return result


def _review_metrics(
    original_draft: str | None,
    edited_draft: str | None,
) -> tuple[AgentRunHumanReviewResult | None, float | None]:
    if original_draft is None or edited_draft is None:
        return None, None
    if original_draft == edited_draft:
        return AgentRunHumanReviewResult.ACCEPTED_WITHOUT_EDITING, 0.0
    difference = round(
        1.0 - SequenceMatcher(None, original_draft, edited_draft).ratio(),
        4,
    )
    return AgentRunHumanReviewResult.EDITED, difference


def _result_string(result: MainAgentState, key: str) -> str | None:
    value = result.get(key)  # type: ignore[literal-required]
    return value if isinstance(value, str) else None


def _node_result_string(
    result: MainAgentState,
    *,
    node_name: str,
    key: str,
) -> str | None:
    node_calls = result.get("node_calls")
    if not _is_string_object_mapping(node_calls):
        return None
    node_call = node_calls.get(node_name)
    if not _is_string_object_mapping(node_call):
        return None
    node_result = node_call.get("result")
    if not _is_string_object_mapping(node_result):
        return None
    value = node_result.get(key)
    return value if isinstance(value, str) else None


def _is_string_object_mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    if not isinstance(value, Mapping):
        return False
    return all(
        isinstance(key, str) for key in cast(Mapping[object, object], value)
    )


def require_state_int(state: MainAgentState, key: str) -> int:
    value = state.get(key)  # type: ignore[literal-required]
    if not isinstance(value, int):
        raise ValueError(f"Agent state requires integer {key}.")
    return value


if __name__ == "__main__":
    requested_ticket_id = int(argv[1]) if len(argv) > 1 else None
    try:
        print(
            invoke_main_agent_for_ticket(
                requested_ticket_id,
                context=create_database_agent_context(),
            )
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error
    finally:
        shutdown_langfuse()
