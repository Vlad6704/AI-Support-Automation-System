from sys import argv
from typing import cast

from langchain.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from app.agents.context import AgentContext, create_stub_agent_context
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
    return graph.checkpointer.get_tuple(ticket_thread_config(ticket_id)) is not None


def delete_ticket_thread(ticket_id: int) -> None:
    graph.checkpointer.delete_thread(f"ticket-{ticket_id}")


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
    message = context.repository.get_latest_user_message(ticket_data["id"])
    if message is None:
        raise ValueError(f"No user message found for ticket {ticket_data['id']}.")
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

    if ticket_thread_exists(ticket_data["id"]):
        return invoke_existing_ticket_thread(ticket_data, context=context)
    return invoke_new_ticket_thread(ticket_data, context=context)


def _invoke(
    input_data: MainAgentState,
    *,
    ticket_data: MainAgentState,
    context: AgentContext,
) -> MainAgentState:
    ticket_id = ticket_data["id"]
    thread_id = f"ticket-{ticket_id}"
    return invoke_graph_with_langfuse(
        graph,
        input_data,
        trace_name="main-agent",
        config=ticket_thread_config(ticket_id),
        session_id=thread_id,
        user_id=str(ticket_data["customer_id"]),
        tags=("main-agent", "support"),
        context=context,
    )


if __name__ == "__main__":
    requested_ticket_id = int(argv[1]) if len(argv) > 1 else None
    try:
        print(
            invoke_main_agent_for_ticket(
                requested_ticket_id,
                context=create_stub_agent_context(),
            )
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error
    finally:
        shutdown_langfuse()
