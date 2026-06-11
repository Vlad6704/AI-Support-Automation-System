from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from app.agents.billing_agent.condition_edges import (
    route_after_billing_data,
    route_get_route,
)
from app.agents.billing_agent.nodes import (
    node_ask_fot_billing_data,
    node_check_refund,
    node_classify_ticket,
    node_get_draft_response,
    node_get_invoice_date,
)
from app.agents.billing_agent.state import SupportState
from app.agents.context import AgentContext, create_stub_agent_context
from app.observability import invoke_graph_with_langfuse

from rich import print


builder = StateGraph(SupportState, context_schema=AgentContext)
builder.add_node("classify_ticket", node_classify_ticket)
builder.add_node("get_draft_response", node_get_draft_response)
builder.add_node("ask_for_billing_data", node_ask_fot_billing_data)
builder.add_node("get_invoice_date", node_get_invoice_date)
builder.add_node("check_refund", node_check_refund)

builder.add_edge(START, "classify_ticket")
builder.add_conditional_edges("classify_ticket", route_get_route)
builder.add_conditional_edges("ask_for_billing_data", route_after_billing_data)
builder.add_edge("get_invoice_date", "get_draft_response")
builder.add_edge("check_refund", "get_draft_response")
builder.add_edge("get_draft_response", END)

checkpointer = InMemorySaver()
graph = builder.compile(checkpointer=checkpointer)


def run_billing_agent(
    user_input: str,
    *,
    thread_id: str = "ticket-1",
    user_id: str | None = None,
    context: AgentContext | None = None,
) -> SupportState:
    config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
    return invoke_graph_with_langfuse(
        graph,
        {"ticket": user_input},
        trace_name="billing-support-agent",
        config=config,
        session_id=thread_id,
        user_id=user_id,
        tags=("billing", "support-agent"),
        context=context or create_stub_agent_context(),
    )


if __name__ == "__main__":
    thread_id = "ticket-1"
    context = create_stub_agent_context()
    config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
    user_input = input("Input: ")
    result = run_billing_agent(user_input, thread_id=thread_id, context=context)
    interrupts = result.get("__interrupt__")
    if interrupts:
        print(interrupts[0].value)
        user_input = input("> ")
        result = invoke_graph_with_langfuse(
            graph,
            Command(resume=user_input),
            trace_name="billing-support-agent-resume",
            config=config,
            session_id=thread_id,
            tags=("billing", "support-agent", "resume"),
            metadata={"resume": True},
            context=context,
        )
    print(result)
