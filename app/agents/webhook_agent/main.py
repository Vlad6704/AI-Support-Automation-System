from langgraph.graph import END, START, StateGraph

from app.agents.context import AgentContext
from app.agents.webhook_agent.nodes import node_get_customer_context
from app.agents.webhook_agent.state import WebhookAgentState

builder = StateGraph(WebhookAgentState, context_schema=AgentContext)
builder.add_node("get_customer_context", node_get_customer_context)
builder.add_edge(START, "get_customer_context")
builder.add_edge("get_customer_context", END)

graph = builder.compile()
