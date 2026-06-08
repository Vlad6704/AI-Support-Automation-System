from langgraph.runtime import Runtime

from app.agents.context import AgentContext
from app.agents.webhook_agent.state import WebhookAgentState


def node_get_customer_context(
    state: WebhookAgentState,
    runtime: Runtime[AgentContext],
) -> WebhookAgentState:
    customer_id = state.get("customer_id")
    if customer_id is None:
        return {}

    return {
        "customer_context": runtime.context.repository.get_customer_context(customer_id)
    }
