from typing import Literal

from langgraph.graph import END, START, StateGraph

from app.agents.context import AgentContext
from app.agents.webhook_agent.nodes import (
    node_get_customer_context,
    node_get_draft_response,
    node_validate_draft_response,
)
from app.agents.webhook_agent.state import WebhookAgentState


def route_start(
    state: WebhookAgentState,
) -> Literal["get_customer_context", "guardrail_output"]:
    if state.get("draft_review_id") is not None:
        return "guardrail_output"
    return "get_customer_context"


def route_after_guardrail(
    state: WebhookAgentState,
) -> Literal["draft_response", "__end__"]:
    if state.get("draft_review_id") is not None:
        return END
    if (state.get("draft_guardrail") or {}).get("decision") == "invalid":
        return "draft_response"
    return END


builder = StateGraph(WebhookAgentState, context_schema=AgentContext)
builder.add_node("get_customer_context", node_get_customer_context)
builder.add_node("draft_response", node_get_draft_response)
builder.add_node("guardrail_output", node_validate_draft_response)
builder.add_conditional_edges(START, route_start)
builder.add_edge("get_customer_context", "draft_response")
builder.add_edge("draft_response", "guardrail_output")
builder.add_conditional_edges("guardrail_output", route_after_guardrail)

graph = builder.compile()
