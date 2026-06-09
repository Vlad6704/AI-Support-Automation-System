from datetime import datetime
from pathlib import Path
from sqlite3 import connect
from sys import argv
from typing import Annotated, Literal, TypedDict, cast

from langchain.chat_models import init_chat_model
from langchain.messages import HumanMessage, SystemMessage
from langchain_core.messages import MessageLikeRepresentation
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.runtime import Runtime
from pydantic import BaseModel

from app.agents.context import (
    AgentContext,
    create_database_agent_context,
    create_stub_agent_context,
)
from app.agents.webhook_agent import graph as webhook_agent_graph
from app.observability import invoke_graph_with_langfuse, shutdown_langfuse
from app.repositories import CustomerContextData

from rich import print

Intent = Literal["support", "not_support"]
SupportCategory = Literal["webhook", "other"]


def merge_node_calls(
    left: dict[str, object] | None, right: dict[str, object] | None
) -> dict[str, object]:
    return {**(left or {}), **(right or {})}


class CustomerData(TypedDict):
    id: int
    company_name: str
    contact_email: str
    region: str | None
    plan: str | None
    status: str
    created_at: datetime


class MainAgentState(TypedDict, total=False):
    id: int
    customer_id: int
    title: str
    description: str
    created_at: datetime
    updated_at: datetime
    status: str
    category: str | None
    updated_by: str | None
    resolution_summery: str | None
    customer: CustomerData
    customer_context: CustomerContextData
    intent: Intent
    intent_reason: str
    draft_response: str
    node_calls: Annotated[dict[str, object], merge_node_calls]


class IntentOutput(BaseModel):
    intent: Intent
    category: SupportCategory
    reason: str


class DraftOutput(BaseModel):
    draft: str


def node_classify_intent(
    state: MainAgentState, config: RunnableConfig | None = None
) -> MainAgentState:
    model = init_chat_model(model="openai:gpt-5.4-nano")
    structured_model = model.with_structured_output(IntentOutput)
    messages: list[MessageLikeRepresentation] = [
        SystemMessage(
            "Classify whether this ticket message is related to customer support. "
            "Return intent='support' for product issues, account questions, billing, "
            "webhooks, incidents, access problems, bugs, or how-to requests. "
            "Return intent='not_support' for unrelated spam, sales outreach, or casual "
            "messages that do not require support action. "
            "Return category='webhook' when the request concerns webhook delivery, "
            "configuration, events, endpoints, retries, or failures. Return "
            "category='other' for all other requests."
        ),
        HumanMessage(
            f"Title: {state.get('title')}\n\nDescription: {state.get('description')}"
        ),
    ]
    result = cast(IntentOutput, structured_model.invoke(messages, config=config))
    return {
        "intent": result.intent,
        "category": result.category,
        "intent_reason": result.reason,
        "node_calls": {
            "node_classify_intent": {
                "messages": messages,
                "result": result.model_dump(),
            }
        },
    }


def node_get_customer_data(
    state: MainAgentState,
    runtime: Runtime[AgentContext],
) -> MainAgentState:
    customer_id = state.get("customer_id")
    if customer_id is None:
        return {}

    customer = runtime.context.repository.get_customer_by_id(customer_id)
    if customer is None:
        return {}

    return {"customer": customer}


def node_get_draft_response(
    state: MainAgentState, config: RunnableConfig | None = None
) -> MainAgentState:
    model = init_chat_model(model="openai:gpt-5.4-nano")
    structured_model = model.with_structured_output(DraftOutput)
    messages: list[MessageLikeRepresentation] = [
        SystemMessage(
            "You are a support agent. Write a concise, helpful draft response for the "
            "ticket."
        ),
        HumanMessage(
            "Ticket:\n"
            f"Title: {state.get('title')}\n"
            f"Description: {state.get('description')}\n\n"
            f"Intent: {state.get('intent')}\n"
            f"Intent reason: {state.get('intent_reason')}\n"
            f"Customer data: {state.get('customer')}\n"
            f"Customer context: {state.get('customer_context')}"
        ),
    ]
    result = cast(DraftOutput, structured_model.invoke(messages, config=config))
    return {
        "draft_response": result.draft,
        "node_calls": {
            "node_get_draft_response": {
                "messages": messages,
                "result": result.model_dump(),
            }
        },
    }


def node_return_friendly_message(state: MainAgentState) -> MainAgentState:
    message = (
        "Thanks for reaching out. This message does not look like a support request, "
        "so I do not have a ticket-specific action to take right now. If you need "
        "help with the product, your account, billing, or a technical issue, please "
        "send a few details and I will be happy to help."
    )
    return {
        "draft_response": message,
        "node_calls": {
            "node_return_friendly_message": {
                "result": {
                    "draft_response": message,
                    "intent": state.get("intent"),
                    "intent_reason": state.get("intent_reason"),
                }
            }
        },
    }


def route_after_intent(
    state: MainAgentState,
) -> Literal["webhook_agent", "get_customer_data", "friendly_message"]:
    if state.get("intent") == "support" and state.get("category") in {
        "webhook",
        "webhooks",
    }:
        return "webhook_agent"
    if state.get("intent") == "support":
        return "get_customer_data"
    return "friendly_message"


builder = StateGraph(MainAgentState, context_schema=AgentContext)
builder.add_node("classify_intent", node_classify_intent)
builder.add_node("webhook_agent", webhook_agent_graph)
builder.add_node("get_customer_data", node_get_customer_data)
builder.add_node("draft_response", node_get_draft_response)
builder.add_node("friendly_message", node_return_friendly_message)

builder.add_edge(START, "classify_intent")
builder.add_conditional_edges("classify_intent", route_after_intent)
builder.add_edge("webhook_agent", "draft_response")
builder.add_edge("get_customer_data", "draft_response")
builder.add_edge("draft_response", END)
builder.add_edge("friendly_message", END)

CHECKPOINT_DB_PATH = Path(__file__).resolve().parents[2] / "checkpoints.db"
checkpoint_connection = connect(CHECKPOINT_DB_PATH, check_same_thread=False)
checkpointer = SqliteSaver(checkpoint_connection)
graph = builder.compile(checkpointer=checkpointer)


def get_ticket_data(
    ticket_id: int | None = None,
    *,
    context: AgentContext,
) -> MainAgentState | None:
    if ticket_id is None:
        return context.repository.get_first_ticket()
    return context.repository.get_ticket_by_id(ticket_id)


if __name__ == "__main__":
    ticket_id = int(argv[1]) if len(argv) > 1 else None
    context = create_stub_agent_context()
    ticket_data = get_ticket_data(ticket_id, context=context)
    if ticket_data is None:
        if ticket_id is None:
            raise SystemExit("No ticket_history rows found.")
        raise SystemExit(f"No ticket_history row found for id {ticket_id}.")

    try:
        thread_id = f"ticket-{ticket_data['id']}"
        result = invoke_graph_with_langfuse(
            graph,
            ticket_data,
            trace_name="main-agent",
            config={"configurable": {"thread_id": thread_id}},
            session_id=thread_id,
            user_id=str(ticket_data["customer_id"]),
            tags=("main-agent", "support"),
            context=context,
        )
        print(result)
    finally:
        shutdown_langfuse()
