from sys import argv
from typing import cast

from langchain.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from langgraph.checkpoint.sqlite import SqliteSaver

from app.agents.context import AgentContext, create_database_agent_context
from app.agents.main_agent import MainAgentState, graph
from app.observability import invoke_graph_with_langfuse, shutdown_langfuse
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
    input_data: MainAgentState | Command,
    *,
    ticket_data: MainAgentState,
    context: AgentContext,
) -> MainAgentState:
    ticket_id = require_state_int(ticket_data, "id")
    customer_id = require_state_int(ticket_data, "customer_id")
    thread_id = f"ticket-{ticket_id}"
    return invoke_graph_with_langfuse(
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
        },
        context=context,
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
