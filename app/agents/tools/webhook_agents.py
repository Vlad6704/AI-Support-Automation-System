from typing import Any, cast

from langchain.agents import AgentState, create_agent
from langchain.messages import HumanMessage
from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.graph.state import CompiledStateGraph

from app.agents.context import AgentContext
from app.agents.tools.database import (
    AgentToolRuntime,
    select_webhook_delivery_logs,
    select_webhook_endpoints,
)


WEBHOOK_DELIVERY_LOGS_AGENT_PROMPT = """
You are a webhook delivery-log investigation agent.

Use select_webhook_delivery_logs to investigate delivery attempts belonging to the
active ticket's customer. The tool supports SQL-like where conditions, pagination, and
returns both matching rows and the total count. Use additional queries when needed
to verify counts, inspect representative rows, compare outcomes, or query date ranges.

Base conclusions only on tool results. Clearly distinguish confirmed findings from
missing information. Do not invent delivery events, causes, or customer impact.
Follow the requested purpose and return exactly the requested result.
""".strip()


WEBHOOK_ENDPOINTS_AGENT_PROMPT = """
You are a webhook endpoint investigation agent.

Use select_webhook_endpoints to investigate webhook endpoint configuration belonging
to the active ticket's customer. The tool supports SQL-like where conditions, pagination,
and returns both matching rows and the total count. Use additional queries when
needed to verify counts or inspect endpoint configuration.

Base conclusions only on tool results. Clearly distinguish confirmed findings from
missing information. Do not invent endpoint configuration, behavior, or customer
impact. Follow the requested purpose and return exactly the requested result.
""".strip()


class WebhookQueryAgentState(AgentState):
    customer_id: int


def _agent_context(runtime: AgentToolRuntime) -> AgentContext:
    return cast(AgentContext, runtime.context)


def _ticket_customer_id(runtime: AgentToolRuntime) -> int:
    customer_id = runtime.state.get("customer_id")
    if not isinstance(customer_id, int):
        raise ValueError("Webhook agent tools require a ticket customer_id in state.")
    return customer_id


def _task_message(purpose: str, expected_result: str) -> HumanMessage:
    return HumanMessage(
        "Purpose:\n"
        f"{purpose}\n\n"
        "Expected result:\n"
        f"{expected_result}"
    )


def _final_message_text(result: dict[str, Any]) -> str:
    messages = cast(list[BaseMessage], result.get("messages", []))
    if not messages:
        raise ValueError("Webhook query agent returned no messages.")
    return messages[-1].text


def run_webhook_delivery_logs_investigation(
    *,
    purpose: str,
    expected_result: str,
    customer_id: int,
    context: AgentContext,
    config: RunnableConfig | None = None,
) -> str:
    agent = cast(
        CompiledStateGraph[
            WebhookQueryAgentState,
            AgentContext,
            WebhookQueryAgentState,
            WebhookQueryAgentState,
        ],
        create_agent(
            model="openai:gpt-5.4-nano",
            tools=[select_webhook_delivery_logs],
            system_prompt=WEBHOOK_DELIVERY_LOGS_AGENT_PROMPT,
            state_schema=WebhookQueryAgentState,
            context_schema=AgentContext,
            name="webhook_delivery_logs_agent",
        ),
    )
    agent_input: WebhookQueryAgentState = {
        "messages": [_task_message(purpose, expected_result)],
        "customer_id": customer_id,
    }
    result = agent.invoke(
        agent_input,
        config=config,
        context=context,
    )
    return _final_message_text(cast(dict[str, Any], result))


@tool
def run_webhook_delivery_logs_agent(
    purpose: str,
    expected_result: str,
    runtime: AgentToolRuntime,
) -> str:
    """Delegate a focused webhook delivery-log investigation.

    Provide the exact investigation purpose and the exact result the delegated agent
    should return.
    """
    return run_webhook_delivery_logs_investigation(
        purpose=purpose,
        expected_result=expected_result,
        customer_id=_ticket_customer_id(runtime),
        context=_agent_context(runtime),
        config=runtime.config,
    )


@tool
def run_webhook_endpoints_agent(
    purpose: str,
    expected_result: str,
    runtime: AgentToolRuntime,
) -> str:
    """Delegate a focused webhook endpoint investigation.

    Provide the exact investigation purpose and the exact result the delegated agent
    should return.
    """
    agent = cast(
        CompiledStateGraph[
            WebhookQueryAgentState,
            AgentContext,
            WebhookQueryAgentState,
            WebhookQueryAgentState,
        ],
        create_agent(
            model="openai:gpt-5.4-nano",
            tools=[select_webhook_endpoints],
            system_prompt=WEBHOOK_ENDPOINTS_AGENT_PROMPT,
            state_schema=WebhookQueryAgentState,
            context_schema=AgentContext,
            name="webhook_endpoints_agent",
        ),
    )
    agent_input: WebhookQueryAgentState = {
        "messages": [_task_message(purpose, expected_result)],
        "customer_id": _ticket_customer_id(runtime),
    }
    result = agent.invoke(
        agent_input,
        config=runtime.config,
        context=_agent_context(runtime),
    )
    return _final_message_text(cast(dict[str, Any], result))
